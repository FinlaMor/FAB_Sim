"""Data-driven trigger parser — generates TriggerDef from functional_text.

Parses structured patterns in card functional_text and maps them to existing
template trigger builders from triggers.py.  This eliminates the need to
manually add CARD_TRIGGERS entries for cards that follow standard
trigger + effect patterns.

Design constraints:
  - Only emits triggers for patterns it can parse with high confidence.
  - Skips cards that already have CARD_TRIGGERS entries (manual overrides win).
  - Uses existing effect primitives from keywords.py.
  - Conditions are only attached when the text is unambiguous.

Integration:
  Called from get_triggers_for_card() in triggers.py, between keyword triggers
  and CARD_TRIGGERS lookups.  CARD_TRIGGERS entries take precedence.

Rules reference:
  CR 5.4.6  — Triggered-static abilities
  CR 6.6    — Triggered effects
  CR 8.3    — Ability keyword triggers
  CR 8.4    — Label keyword triggers
"""

from __future__ import annotations

import re
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.card import Card

from engine.card_effects.triggers import TriggerDef


# ===================================================================
# Effect primitives — thin wrappers returning (card, event, state) callables
# ===================================================================

def _eff_draw(n: int):
    def fn(card, event, state):
        from engine.card_effects.keywords import effect_draw, _controller_id
        effect_draw(state, _controller_id(card), n)
    return fn

def _eff_deal_arcane(n: int):
    def fn(card, event, state):
        from engine.card_effects.keywords import effect_deal_arcane, _controller_id
        cid = _controller_id(card)
        effect_deal_arcane(state, 3 - cid, n, card)
    return fn

def _eff_deal_damage(n: int):
    def fn(card, event, state):
        from engine.card_effects.keywords import effect_deal_damage, _controller_id
        cid = _controller_id(card)
        effect_deal_damage(state, 3 - cid, n, card)
    return fn

def _eff_gain_life(n: int):
    def fn(card, event, state):
        from engine.card_effects.keywords import effect_gain_life, _controller_id
        effect_gain_life(state, _controller_id(card), n)
    return fn

def _eff_lose_life(n: int):
    def fn(card, event, state):
        from engine.card_effects.keywords import effect_lose_life, _controller_id
        cid = _controller_id(card)
        effect_lose_life(state, 3 - cid, n)
    return fn

def _eff_discard(n: int):
    def fn(card, event, state):
        from engine.card_effects.keywords import effect_discard, _controller_id
        cid = _controller_id(card)
        effect_discard(state, 3 - cid, n)
    return fn

def _eff_power_bonus(n: int):
    def fn(card, event, state):
        card.effects.append(("base_power", lambda base, _n=n: base + _n))
    return fn

def _eff_next_attack_power(n: int):
    def fn(card, event, state):
        from engine.card_effects.keywords import _controller_id
        cid = _controller_id(card)
        state.players[cid].current_turn_effects.append(f"next_attack_+{n}")
    return fn

def _eff_defense_bonus(n: int):
    def fn(card, event, state):
        card.effects.append(("base_defense", lambda base, _n=n: base + _n))
    return fn

def _eff_go_again():
    def fn(card, event, state):
        if state.combat and "go_again" not in state.combat.keywords:
            state.combat.grant_keyword("go_again")
    return fn

def _eff_dominate():
    def fn(card, event, state):
        if state.combat and "dominate" not in state.combat.keywords:
            state.combat.grant_keyword("dominate")
    return fn

def _eff_overpower():
    def fn(card, event, state):
        if state.combat and "overpower" not in state.combat.keywords:
            state.combat.grant_keyword("overpower")
    return fn

def _eff_intimidate():
    def fn(card, event, state):
        from engine.card_effects.keywords import effect_intimidate, _controller_id
        cid = _controller_id(card)
        effect_intimidate(state, 3 - cid, card)
    return fn

def _eff_create_token(token_slug: str, count: int = 1):
    def fn(card, event, state):
        from engine.card_effects.keywords import create_token, _controller_id
        create_token(state, _controller_id(card), token_slug, count)
    return fn

def _eff_create_token_opponent(token_slug: str, count: int = 1):
    def fn(card, event, state):
        from engine.card_effects.keywords import create_token, _controller_id
        cid = _controller_id(card)
        create_token(state, 3 - cid, token_slug, count)
    return fn

def _eff_opt(n: int):
    def fn(card, event, state):
        from engine.card_effects.keywords import effect_opt, _controller_id
        effect_opt(state, _controller_id(card), n)
    return fn

def _eff_gain_action_point():
    def fn(card, event, state):
        from engine.card_effects.keywords import effect_gain_action_point, _controller_id
        effect_gain_action_point(state, _controller_id(card))
    return fn

def _eff_gain_resources(n: int):
    def fn(card, event, state):
        from engine.card_effects.keywords import effect_gain_resources, _controller_id
        effect_gain_resources(state, _controller_id(card), n)
    return fn

def _eff_amp(n: int):
    def fn(card, event, state):
        from engine.card_effects.keywords import effect_amp, _controller_id
        effect_amp(state, _controller_id(card), n)
    return fn

def _eff_banish_top(n: int):
    def fn(card, event, state):
        from engine.card_effects.keywords import _controller_id
        cid = _controller_id(card)
        target = state.players[3 - cid]
        from engine.card_effects.keywords import banish_card
        for _ in range(n):
            if target.deck.cards:
                top = target.deck.pop_top()
                banish_card(state, target, top, face_up=True)
    return fn

def _eff_prevent_damage(n: int):
    def fn(card, event, state):
        from engine.card_effects.keywords import _controller_id
        cid = _controller_id(card)
        state.players[cid].current_turn_effects.append(f"prevent_next_{n}")
    return fn

def _eff_put_counter(counter_type: str, n: int):
    def fn(card, event, state):
        from engine.card_effects.keywords import effect_put_counter
        effect_put_counter(state, card, counter_type, n)
    return fn

def _eff_next_attack_keyword(keyword: str):
    def fn(card, event, state):
        from engine.card_effects.keywords import _controller_id
        cid = _controller_id(card)
        state.players[cid].current_turn_effects.append(f"next_attack_{keyword}")
    return fn

def _eff_self_gain_go_again():
    """Card itself gains go again (on_play context)."""
    def fn(card, event, state):
        if state.combat and state.combat.attack_card is card:
            if "go_again" not in state.combat.keywords:
                state.combat.grant_keyword("go_again")
        else:
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            state.players[cid].current_turn_effects.append("next_action_go_again")
    return fn

def _eff_compound(effects: list[Callable]):
    """Execute multiple effects in sequence."""
    def fn(card, event, state):
        for eff in effects:
            eff(card, event, state)
    return fn


# ===================================================================
# Token slug normalisation
# ===================================================================

_TOKEN_SLUG_MAP = {
    "seismic surge": "seismic_surge",
    "vigor": "vigor",
    "might": "might",
    "agility": "agility",
    "runechant": "runechant",
    "spectral shield": "spectral_shield",
    "ponder": "ponder",
    "quicken": "quicken",
    "soul shackle": "soul_shackle",
    "zen state": "zen_state",
    "crouching tiger": "crouching_tiger",
    "embodiment of lightning": "embodiment_of_lightning",
    "embodiment of earth": "embodiment_of_earth",
    "eloquence": "eloquence",
    "copper": "copper",
    "silver": "silver",
    "gold": "gold",
    "golden cog": "golden_cog",
    "bloodrot pox": "bloodrot_pox",
    "frailty": "frailty",
    "inertia": "inertia",
    "frostbite": "frostbite",
    "courage": "courage",
    "toughness": "toughness",
    "confidence": "confidence",
    "fealty": "fealty",
    "ash": "ash",
    "aether ashwing": "aether_ashwing",
    "spectral": "spectral",
    "embodiment of wind": "embodiment_of_wind",
    "suraya": "suraya",
    "figment": "figment",
    "winter's bite": "winters_bite",
    "verdance": "verdance",
    "eye of ophidia": "eye_of_ophidia",
}

def _normalize_token(text: str) -> Optional[str]:
    """Map a token name from card text to its slug, if known."""
    t = text.strip().lower()
    if t.endswith(" tokens"):
        t = t[:-len(" tokens")]
    elif t.endswith(" token"):
        t = t[:-len(" token")]
    return _TOKEN_SLUG_MAP.get(t)


# ===================================================================
# Number parsing
# ===================================================================

_WORD_NUMS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
              "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

def _parse_number(s: str) -> Optional[int]:
    s = s.strip().lower()
    if s in _WORD_NUMS:
        return _WORD_NUMS[s]
    try:
        return int(s)
    except ValueError:
        return None


# ===================================================================
# Effect parsing — extract effect callable(s) from a text fragment
# ===================================================================

# Order matters: more specific patterns first.
_EFFECT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # --- Draw ---
    (re.compile(r'draw (\d+|a|an|one|two|three) cards?', re.I), 'draw'),
    # --- Damage ---
    (re.compile(r'deal (\d+) arcane damage', re.I), 'deal_arcane'),
    (re.compile(r'deal (\d+) damage', re.I), 'deal_damage'),
    # --- Power/Defense bonus ---
    (re.compile(r'(?:the )?next (?:\w+ )?attack (?:action card )?(?:you play )?this (?:turn|combat chain) (?:gets?|gains?) \+(\d+)\{p\}', re.I), 'next_attack_power'),
    (re.compile(r'(?:this |it )(?:gets?|has) \+(\d+)\{p\}', re.I), 'power_bonus'),
    (re.compile(r'(?:gets?|has) \+(\d+)\{p\}', re.I), 'power_bonus'),
    (re.compile(r'(?:this |it )(?:gets?|has) \+(\d+)\{d\}', re.I), 'defense_bonus'),
    (re.compile(r'(?:gets?|has) \+(\d+)\{d\}', re.I), 'defense_bonus'),
    # --- Keyword grants ---
    (re.compile(r'(?:this |it )?(?:gets?|gains?|has) \*\*go again\*\*', re.I), 'go_again'),
    (re.compile(r'(?:this |it )?(?:gets?|gains?|has) \*\*dominate\*\*', re.I), 'dominate'),
    (re.compile(r'(?:this |it )?(?:gets?|gains?|has) \*\*overpower\*\*', re.I), 'overpower'),
    # --- Life ---
    (re.compile(r'gain (\d+)\{h\}', re.I), 'gain_life'),
    (re.compile(r'gain (\d+) life', re.I), 'gain_life'),
    (re.compile(r'(?:they |the (?:attacking|defending|opposing) hero )?loses? (\d+)\{h\}', re.I), 'lose_life'),
    # --- Discard ---
    (re.compile(r'(?:they |the (?:attacking|defending|opposing) hero )?discards? (\d+|a|an) (?:random )?cards?', re.I), 'discard'),
    # --- Tokens ---
    (re.compile(r'create (\d+|a|an|two|three) ([A-Z][a-z][a-z A-Z]*?) tokens?', re.I), 'create_token'),
    # --- Opt ---
    (re.compile(r'\*\*opt (\d+)\*\*', re.I), 'opt'),
    (re.compile(r'\bopt (\d+)\b', re.I), 'opt'),
    # --- Action points ---
    (re.compile(r'gain (\d+) action points?', re.I), 'gain_action_point'),
    # --- Resources ---
    (re.compile(r'gain (\{r\})+', re.I), 'gain_resources'),
    # --- Amp ---
    (re.compile(r'\*\*amp (\d+)\*\*', re.I), 'amp'),
    (re.compile(r'\bamp (\d+)\b', re.I), 'amp'),
    # --- Intimidate ---
    (re.compile(r'\*\*intimidate\*\*', re.I), 'intimidate'),
    (re.compile(r'\bintimidate\b(?! you)', re.I), 'intimidate'),
    # --- Banish top ---
    (re.compile(r'banish the top (\d+|a|an) cards? of', re.I), 'banish_top'),
    # --- Prevent damage ---
    (re.compile(r'prevent the next (\d+) damage', re.I), 'prevent_damage'),
    # --- Counter manipulation ---
    (re.compile(r'put (\d+|a|an) \+1\{p\} counters? on (?:this|it)', re.I), 'put_p_counter'),
    # --- Next-attack keyword ---
    (re.compile(r'(?:the )?next (?:\w+ )?attack (?:action card )?(?:you play )?this (?:turn|combat chain) (?:gets?|gains?) \*\*go again\*\*', re.I), 'next_attack_go_again'),
    (re.compile(r'(?:the )?next (?:\w+ )?attack (?:action card )?(?:you play )?this (?:turn|combat chain) (?:gets?|gains?) \*\*dominate\*\*', re.I), 'next_attack_dominate'),
    (re.compile(r'(?:the )?next (?:\w+ )?attack (?:action card )?(?:you play )?this (?:turn|combat chain) (?:gets?|gains?) \*\*overpower\*\*', re.I), 'next_attack_overpower'),
]


def _parse_effect(text: str) -> Optional[Callable]:
    """Try to parse a single effect from a text fragment.

    Returns a (card, event, state) callable, or None if unparseable.
    """
    for pattern, etype in _EFFECT_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue

        if etype == 'draw':
            n = _parse_number(m.group(1))
            return _eff_draw(n) if n else None
        if etype == 'deal_arcane':
            return _eff_deal_arcane(int(m.group(1)))
        if etype == 'deal_damage':
            return _eff_deal_damage(int(m.group(1)))
        if etype == 'power_bonus':
            return _eff_power_bonus(int(m.group(1)))
        if etype == 'next_attack_power':
            return _eff_next_attack_power(int(m.group(1)))
        if etype == 'defense_bonus':
            return _eff_defense_bonus(int(m.group(1)))
        if etype == 'go_again':
            return _eff_go_again()
        if etype == 'dominate':
            return _eff_dominate()
        if etype == 'overpower':
            return _eff_overpower()
        if etype == 'gain_life':
            return _eff_gain_life(int(m.group(1)))
        if etype == 'lose_life':
            return _eff_lose_life(int(m.group(1)))
        if etype == 'discard':
            n = _parse_number(m.group(1))
            return _eff_discard(n) if n else None
        if etype == 'create_token':
            count = _parse_number(m.group(1))
            token_name = m.group(2)
            token_slug = _normalize_token(token_name)
            if token_slug and count:
                return _eff_create_token(token_slug, count)
            return None
        if etype == 'opt':
            return _eff_opt(int(m.group(1)))
        if etype == 'gain_action_point':
            return _eff_gain_action_point()
        if etype == 'gain_resources':
            n = m.group(0).count('{r}')
            return _eff_gain_resources(n)
        if etype == 'amp':
            return _eff_amp(int(m.group(1)))
        if etype == 'intimidate':
            return _eff_intimidate()
        if etype == 'banish_top':
            n = _parse_number(m.group(1))
            return _eff_banish_top(n) if n else None
        if etype == 'prevent_damage':
            return _eff_prevent_damage(int(m.group(1)))
        if etype == 'put_p_counter':
            n = _parse_number(m.group(1))
            return _eff_put_counter("+1{p}", n) if n else None
        if etype == 'next_attack_go_again':
            return _eff_next_attack_keyword("go_again")
        if etype == 'next_attack_dominate':
            return _eff_next_attack_keyword("dominate")
        if etype == 'next_attack_overpower':
            return _eff_next_attack_keyword("overpower")

    return None


def _parse_all_effects(text: str) -> Optional[Callable]:
    """Try to parse ALL effects from a text fragment.

    Handles compound effects separated by commas/and/periods.
    Returns a compound callable, or None if any part is unparseable.
    """
    # First try as a single effect
    single = _parse_effect(text)
    if single is not None:
        return single

    # Try splitting on ", " + "and " to find compound effects
    # e.g. "draw a card and this gets +1{p}"
    # e.g. "this gets +2{p}, **go again**, and draw a card"
    parts = re.split(r',\s+(?:and\s+)?|\s+and\s+', text)
    if len(parts) < 2:
        return None

    effects = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        eff = _parse_effect(part)
        if eff is None:
            return None  # Can't parse all parts — bail
        effects.append(eff)

    if not effects:
        return None
    if len(effects) == 1:
        return effects[0]
    return _eff_compound(effects)


# ===================================================================
# Trigger event detection
# ===================================================================

def _is_this_attacking(card, event, state):
    if not state.combat:
        return False
    ac = state.combat.attack_card
    return ac is card or (ac is not None and ac.slug == card.slug)

def _is_this_defending(card, event, state):
    return state.combat is not None and card in state.combat.defending_cards

def _is_this_hit(card, event, state):
    """Condition: this card hit (used for 'If X hits' pattern)."""
    event_data = event.data if isinstance(event.data, dict) else {}
    hit_card = event_data.get("card")
    if hit_card is not None and getattr(hit_card, 'slug', '') == card.slug:
        return True
    if not state.combat:
        return False
    ac = state.combat.attack_card
    return ac is card or (ac is not None and ac.slug == card.slug)


# Trigger patterns: (regex, event_type, condition_key)
# Note: when(?:ever)? handles both "when" and "whenever" — identical in engine
# since EventManager never removes listeners (see engine/state.py EventManager).
_TRIGGER_PATTERNS: list[tuple[re.Pattern, str, Optional[str]]] = [
    # "When(ever) {name/this} hits a hero" — hit trigger
    (re.compile(r'when(?:ever)? (?:this|[\w\' ,]+?) hits(?: a hero)?', re.I), 'hit', 'is_attacking'),
    # "If {name/this} hits" — hit trigger (alternate phrasing)
    (re.compile(r'if (?:this|[\w\' ,]+?) hits', re.I), 'hit', 'is_hit'),
    # "When(ever) {name/this} attacks a hero" — attacking trigger
    (re.compile(r'when(?:ever)? (?:this|[\w\' ,]+?) attacks(?: a hero)?', re.I), 'attacking', 'is_attacking'),
    # "When(ever) {name/this} defends" — defend trigger
    (re.compile(r'when(?:ever)? (?:this|[\w\' ,]+?) defends', re.I), 'defend', 'is_defending'),
    # "When(ever) this enters the arena"
    (re.compile(r'when(?:ever)? (?:this|[\w\' ,]+?) enters the arena', re.I), 'enters_arena', None),
    # "When(ever) this leaves the arena"
    (re.compile(r'when(?:ever)? (?:this|[\w\' ,]+?) leaves the arena', re.I), 'leaves_arena', None),
    # "When(ever) you play this"
    (re.compile(r'when(?:ever)? you play this', re.I), 'on_play', None),
    # "When(ever) this deals damage" — damage_dealt trigger
    (re.compile(r'when(?:ever)? (?:this|[\w\' ,]+?) deals damage', re.I), 'damage_dealt', 'is_attacking'),
    # "When you attack with X" — attacking trigger
    (re.compile(r'when(?:ever)? you attack with', re.I), 'attacking', 'is_attacking'),
]

# Label keyword triggers with inline effects
_LABEL_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # "**Crush** — <effect>"
    (re.compile(r'\*\*Crush\*\*\s*[-\u2013\u2014:]\s*(.+?)(?:\.|$)', re.I | re.S), 'damage_dealt', 'crush'),
    # "**Reprise** — <effect>"
    (re.compile(r'\*\*Reprise\*\*\s*[-\u2013\u2014:]\s*(.+?)(?:\.|$)', re.I | re.S), 'on_play', 'reprise'),
    # "**Combo** — <effect>"
    (re.compile(r'\*\*Combo\*\*\s*[-\u2013\u2014:]\s*(.+?)(?:\.|$)', re.I | re.S), 'on_play', 'combo'),
    # "**Surge** — <effect>"
    (re.compile(r'\*\*Surge\*\*\s*[-\u2013\u2014:]\s*(.+?)(?:\.|$)', re.I | re.S), 'damage_dealt', 'surge'),
    # "**Rupture** — <effect>"
    (re.compile(r'\*\*Rupture\*\*\s*[-\u2013\u2014:]\s*(.+?)(?:\.|$)', re.I | re.S), 'on_play', 'rupture'),
]


# ===================================================================
# If-condition patterns — simple conditions parseable from text
# ===================================================================

# Each entry: (regex, builder_fn_name)
# The builder returns a (card, event, state) -> bool callable
_IF_CONDITION_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "if you have less {h} than" — health comparison
    (re.compile(r'if you have (?:less|fewer) \{h\} than', re.I), 'less_health'),
    # "if you have more {h} than" — health comparison
    (re.compile(r'if you have more \{h\} than', re.I), 'more_health'),
    # "if this is/was played from arsenal"
    (re.compile(r'if (?:this|[\w ]+?) is played from arsenal', re.I), 'played_from_arsenal'),
    (re.compile(r'if (?:this|[\w ]+?) was played from arsenal', re.I), 'played_from_arsenal'),
    # "if there are N or more CARDS in your pitch zone"
    (re.compile(r'if there (?:are|is) (\d+) or more (\w+) cards? in your pitch zone', re.I), 'pitch_zone_count'),
    # "if there are N or more CARDS in your banished zone"
    (re.compile(r'if there (?:are|is) (\d+) or more (\w+) cards? in your banished zone', re.I), 'banished_zone_count'),
    # "if there is a card with N or more {p} in your pitch zone"
    (re.compile(r'if there is a card with (\d+) or more \{p\} in your pitch zone', re.I), 'pitch_has_power'),
    # "if you've been cheered this turn"
    (re.compile(r"if you(?:'ve| have) been cheered this turn", re.I), 'cheered_this_turn'),
    # "if you control a TOKEN token"
    (re.compile(r'if you control (?:a|an) ([A-Z][a-z][a-z A-Z]*?) token', re.I), 'control_token'),
    # "if this is defended by fewer than N non-equipment cards"
    (re.compile(r'if (?:this|it) is defended by fewer than (\d+) non-equipment cards?', re.I), 'few_defenders'),
    # "if you have no cards in hand"
    (re.compile(r'if you have no cards in hand', re.I), 'empty_hand'),
    # "if you've discarded a card with N or more {p} this turn"
    (re.compile(r"if you(?:'ve| have) discarded a card with (\d+) or more \{p\} this turn", re.I), 'discarded_power'),
    # "if you've controlled a TOKEN token this turn"
    (re.compile(r"if you(?:'ve| have) controlled a (\w[\w ]*?) token this turn", re.I), 'controlled_token_this_turn'),
    # "if X was fused / **fused**"
    (re.compile(r'if [\w\' ]+ was (?:\*\*)?fused(?:\*\*)?', re.I), 'was_fused'),
    # "if X was charged / **charged**"
    (re.compile(r'if [\w\' ]+ was (?:\*\*)?charged(?:\*\*)?', re.I), 'was_charged'),
    # "if you've dealt arcane damage this turn"
    (re.compile(r"if you(?:'ve| have) dealt arcane damage this turn", re.I), 'dealt_arcane_this_turn'),
    # "if you've intimidated (an opponent) this turn"
    (re.compile(r"if you(?:'ve| have) intimidated", re.I), 'intimidated_this_turn'),
    # "if this/it has stealth"
    (re.compile(r'if (?:this|it) has \*\*stealth\*\*', re.I), 'has_stealth'),
    # "if this/it is attacking a hero"
    (re.compile(r'if (?:this|it) is attacking a hero', re.I), 'is_attacking_hero'),
    # "if you control N or more TYPE chain links/cards"
    (re.compile(r'if you control (\d+) or more (\w[\w ]*?) (?:chain links?|cards?)', re.I), 'control_count'),
    # "if you've played a/another TYPE card this turn"
    (re.compile(r"if you(?:'ve| have) played (?:a|an|another) (\w[\w ]*?) card this turn", re.I), 'played_type_this_turn'),
    # "if this/it has N or more {p}"
    (re.compile(r'if (?:this|it|[\w\' ]+) has (\d+) or more \{p\}', re.I), 'has_power_threshold'),
    # "if this/it has {p} greater than its base {p}"
    (re.compile(r'if (?:this|it|[\w\' ]+) has \{p\} greater than its base \{p\}', re.I), 'power_above_base'),
    # "if you have a COLOR card in your pitch zone"
    (re.compile(r'if you have (?:a|an) (\w+) card in your pitch zone', re.I), 'have_color_in_pitch'),
    # "if you've drawn a card this turn"
    (re.compile(r"if you(?:'ve| have) drawn a card this turn", re.I), 'drawn_this_turn'),
    # "if you've banished a card with N or more {p} this turn"
    (re.compile(r"if you(?:'ve| have) banished a card with (\d+) or more \{p\} this turn", re.I), 'banished_power_this_turn'),
    # "if you've created a card/token this turn"
    (re.compile(r"if you(?:'ve| have) created (?:a card|an? \w[\w ]*? token) this turn", re.I), 'created_this_turn'),
    # "if you've boosted N or more times this turn"
    (re.compile(r"if you(?:'ve| have) \*\*boosted\*\* (\d+) or more times? this turn", re.I), 'boosted_this_turn'),
    # "if you have a card in your arsenal"
    (re.compile(r'if you have a card in your arsenal', re.I), 'has_card_in_arsenal'),
    # "while/if X is defended by less/fewer than N non-equipment cards"
    (re.compile(r'(?:while|if) [\w\' ]+ is defended by (?:less|fewer) than (\d+) non-equipment cards?', re.I), 'few_defenders'),
    # "if it is / this is Draconic / Elemental / etc" (supertype check)
    (re.compile(r'if (?:this|it) is (\w+)', re.I), 'has_supertype'),
]


def _build_condition(cond_key: str, match: re.Match) -> Optional[Callable]:
    """Build a condition callable from a parsed if-pattern."""

    if cond_key == 'less_health':
        def cond(card, event, state):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return state.players[cid].health < state.players[3 - cid].health
        return cond

    if cond_key == 'more_health':
        def cond(card, event, state):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return state.players[cid].health > state.players[3 - cid].health
        return cond

    if cond_key == 'played_from_arsenal':
        def cond(card, event, state):
            return getattr(card, '_played_from_arsenal', False)
        return cond

    if cond_key == 'pitch_zone_count':
        n = int(match.group(1))
        color_word = match.group(2).lower()
        color_map = {"blue": 3, "red": 1, "yellow": 2}
        pitch_val = color_map.get(color_word)
        if pitch_val is None:
            return None
        def cond(card, event, state, _n=n, _pv=pitch_val):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            count = sum(1 for c in state.players[cid].pitch.cards if c.pitch == _pv)
            return count >= _n
        return cond

    if cond_key == 'banished_zone_count':
        n = int(match.group(1))
        type_word = match.group(2).strip().title()
        def cond(card, event, state, _n=n, _tw=type_word):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            count = sum(1 for c in state.players[cid].banished.cards
                        if _tw in (c.subtypes or []) or _tw in (c.types or []))
            return count >= _n
        return cond

    if cond_key == 'pitch_has_power':
        n = int(match.group(1))
        def cond(card, event, state, _n=n):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return any(c.power is not None and c.power >= _n
                       for c in state.players[cid].pitch.cards)
        return cond

    if cond_key == 'cheered_this_turn':
        def cond(card, event, state):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return "crowd_cheers" in state.players[cid].current_turn_effects
        return cond

    if cond_key == 'control_token':
        token_name = match.group(1).strip().lower()
        token_slug = _normalize_token(token_name)
        if not token_slug:
            return None
        def cond(card, event, state, _ts=token_slug):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return any(c.slug == _ts for c in state.players[cid].items.cards)
        return cond

    if cond_key == 'few_defenders':
        n = int(match.group(1))
        def cond(card, event, state, _n=n):
            if not state.combat:
                return False
            non_equip = [c for c in state.combat.defending_cards
                         if "Equipment" not in (c.types or [])]
            return len(non_equip) < _n
        return cond

    if cond_key == 'empty_hand':
        def cond(card, event, state):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return len(state.players[cid].hand.cards) == 0
        return cond

    if cond_key == 'discarded_power':
        n = int(match.group(1))
        def cond(card, event, state, _n=n):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return any(f"discarded_{_n}p" in eff
                       for eff in state.players[cid].current_turn_effects)
        return cond

    if cond_key == 'controlled_token_this_turn':
        token_name = match.group(1).strip().lower()
        token_slug = _normalize_token(token_name)
        if not token_slug:
            return None
        def cond(card, event, state, _ts=token_slug):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return any(f"controlled_{_ts}" in eff
                       for eff in state.players[cid].current_turn_effects)
        return cond

    if cond_key == 'has_supertype':
        st = match.group(1).strip().title()
        def cond(card, event, state, _st=st):
            return _st in (card.subtypes or []) or _st in (card.types or [])
        return cond

    if cond_key == 'was_fused':
        def cond(card, event, state):
            return getattr(card, '_was_fused', False)
        return cond

    if cond_key == 'was_charged':
        def cond(card, event, state):
            return getattr(card, '_was_charged', False)
        return cond

    if cond_key == 'dealt_arcane_this_turn':
        def cond(card, event, state):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return any("dealt_arcane" in eff for eff in state.players[cid].current_turn_effects)
        return cond

    if cond_key == 'intimidated_this_turn':
        def cond(card, event, state):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return any("intimidated" in eff for eff in state.players[cid].current_turn_effects)
        return cond

    if cond_key == 'has_stealth':
        def cond(card, event, state):
            return "Stealth" in (card.keywords or [])
        return cond

    if cond_key == 'is_attacking_hero':
        def cond(card, event, state):
            return _is_this_attacking(card, event, state)
        return cond

    if cond_key == 'control_count':
        n = int(match.group(1))
        type_word = match.group(2).strip()
        def cond(card, event, state, _n=n, _tw=type_word):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            tw_title = _tw.title()
            count = sum(1 for c in state.players[cid].items.cards
                        if tw_title in (c.subtypes or []) or tw_title in (c.types or []))
            return count >= _n
        return cond

    if cond_key == 'played_type_this_turn':
        type_word = match.group(1).strip().lower()
        def cond(card, event, state, _tw=type_word):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return any(f"played_{_tw}" in eff for eff in state.players[cid].current_turn_effects)
        return cond

    if cond_key == 'has_power_threshold':
        n = int(match.group(1))
        def cond(card, event, state, _n=n):
            return (card.power or 0) >= _n
        return cond

    if cond_key == 'power_above_base':
        def cond(card, event, state):
            current = card.power or 0
            base = getattr(card, 'base_power', current)
            return current > base
        return cond

    if cond_key == 'have_color_in_pitch':
        color_word = match.group(1).lower()
        color_map = {"blue": 3, "red": 1, "yellow": 2}
        pitch_val = color_map.get(color_word)
        if pitch_val is None:
            return None
        def cond(card, event, state, _pv=pitch_val):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return any(c.pitch == _pv for c in state.players[cid].pitch.cards)
        return cond

    if cond_key == 'drawn_this_turn':
        def cond(card, event, state):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return any("drawn_card" in eff for eff in state.players[cid].current_turn_effects)
        return cond

    if cond_key == 'banished_power_this_turn':
        n = int(match.group(1))
        def cond(card, event, state, _n=n):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return any(f"banished_{_n}p" in eff for eff in state.players[cid].current_turn_effects)
        return cond

    if cond_key == 'created_this_turn':
        def cond(card, event, state):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return any("created_card" in eff or "created_token" in eff
                       for eff in state.players[cid].current_turn_effects)
        return cond

    if cond_key == 'boosted_this_turn':
        n = int(match.group(1))
        def cond(card, event, state, _n=n):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            count = sum(1 for eff in state.players[cid].current_turn_effects if "boosted" in eff)
            return count >= _n
        return cond

    if cond_key == 'has_card_in_arsenal':
        def cond(card, event, state):
            from engine.card_effects.keywords import _controller_id
            cid = _controller_id(card)
            return len(state.players[cid].arsenal.cards) > 0
        return cond

    return None


# ===================================================================
# Condition builders for label keywords
# ===================================================================

def _make_crush_condition():
    def cond(card, event, state):
        from engine.card_effects.keywords import crush_check
        return crush_check(event, state)
    return cond

def _make_reprise_condition():
    def cond(card, event, state):
        from engine.card_effects.keywords import reprise_check
        return reprise_check(state)
    return cond

def _make_combo_condition():
    def cond(card, event, state):
        from engine.card_effects.keywords import combo_check
        return combo_check(state, [])
    return cond

def _make_surge_condition():
    def cond(card, event, state):
        from engine.card_effects.keywords import surge_check
        return surge_check(event, 0)
    return cond

def _make_rupture_condition():
    def cond(card, event, state):
        from engine.card_effects.keywords import rupture_check
        return rupture_check(state)
    return cond


# ===================================================================
# Complexity detection — patterns we refuse to auto-generate
# ===================================================================

def _has_complex_markers(text: str) -> bool:
    """Return True if the effect text contains markers that indicate
    complexity beyond what the parser can handle."""
    complex_pats = [
        r'\bchoose\b',
        r'\bfor each\b',
        r'\bequal to\b',
        r'\bunless\b',
        r'\binstead\b',
        r'\bbecomes?\b',
        r'\bsearch your deck\b',
        r'\blook at the top\b',
        r'\breveal\b',
        r'\bany number\b',
        r'\bput .+ into play\b',
        r'\btransform\b',
        r'\btranscend\b',
        r'\bgraft\b',
        r'\btake control\b',
        r'\bname a card\b',
        r'\bcopy\b',
        r'\bexchange\b',
    ]
    for p in complex_pats:
        if re.search(p, text, re.I):
            return True
    return False


# ===================================================================
# Keyword-only and skippable paragraph detection
# ===================================================================

_KEYWORD_PARAGRAPH_RE = re.compile(
    r'^\*\*(?:'
    r'Go again|Dominate|Overpower|Phantasm|Spectra|Stealth|'
    r'Blood Debt|Battleworn|Temper|Legendary|Ephemeral|'
    r'Universal|Modular|Cloaked|Blade Break|Guardwell|'
    r'Galvanize|Intimidate|Heave|Boost|Wager|Freeze|'
    r'(?:Ice|Lightning|Earth|Elemental) Fusion|'
    r'[\w\' ]+ Specialization|'
    r'Arcane Barrier \d+|Ward \d+|Spellvoid \d+|Arcane Shelter \d+'
    r')\*\*\.?$', re.I
)

_SKIPPABLE_PARAGRAPH_RE = re.compile(
    r'^As an additional cost to play .+', re.I
)


# ===================================================================
# Main parser entry point
# ===================================================================

def parse_functional_text(card: 'Card') -> list[TriggerDef]:
    """Parse a card's functional_text and return TriggerDef objects.

    Handles:
      - Label keyword triggers (Crush, Reprise, Combo, Surge, Rupture)
      - "When X event, effect" triggers
      - "If condition, effect" on-play triggers
      - Standalone paragraph effects (go again, keyword grants)
      - Compound effects (A and B, A, B)
      - Multi-paragraph cards (each paragraph parsed independently)
    """
    text = card.base_functional_text or ""
    if not text:
        return []

    triggers: list[TriggerDef] = []

    # --- Phase A: Label keyword triggers (Crush, Reprise, Combo, Surge, Rupture) ---
    for pat, event_type, label in _LABEL_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        effect_text = m.group(1).strip()
        effect_fn = _parse_all_effects(effect_text)
        if effect_fn is None:
            continue

        if label == 'crush':
            cond = _make_crush_condition()
        elif label == 'reprise':
            cond = _make_reprise_condition()
        elif label == 'combo':
            cond = _make_combo_condition()
        elif label == 'surge':
            cond = _make_surge_condition()
        elif label == 'rupture':
            cond = _make_rupture_condition()
        else:
            cond = None

        triggers.append(TriggerDef(
            event_type=event_type,
            condition_fn=cond,
            effect_fn=effect_fn,
            source_slug=card.slug,
        ))

    # --- Phase B: Parse each paragraph independently ---
    paragraphs = re.split(r'\n\n+', text)
    all_recognized = True
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        # Skip paragraphs already handled by label patterns
        if any(lp[0].search(paragraph) for lp in _LABEL_PATTERNS):
            continue

        # B.1: Standalone keyword paragraph — "**Go again**"
        standalone_go = re.match(r'^\*\*Go again\*\*\.?$', paragraph, re.I)
        if standalone_go:
            triggers.append(TriggerDef(
                event_type="on_play",
                effect_fn=_eff_self_gain_go_again(),
                source_slug=card.slug,
            ))
            continue

        # B.1b: Skip keyword-only paragraphs (handled by keyword system)
        if _KEYWORD_PARAGRAPH_RE.match(paragraph):
            continue

        # B.1c: Skip known cost/restriction paragraphs
        if _SKIPPABLE_PARAGRAPH_RE.match(paragraph):
            continue

        # B.2: Try "When/If trigger, effect" patterns
        before_len = len(triggers)
        _parse_trigger_paragraph(card, paragraph, triggers)

        # B.3: Try standalone if-condition + effect (no trigger word)
        _parse_if_condition_paragraph(card, paragraph, triggers)

        # B.4: Try standalone effect (deal N arcane, gain N{h}, etc.)
        _parse_standalone_effect(card, paragraph, triggers)

        if len(triggers) == before_len:
            all_recognized = False

    # If all paragraphs recognized but no triggers produced, card is keyword-only
    if not triggers and all_recognized:
        triggers.append(TriggerDef(
            event_type="__keyword_only__",
            effect_fn=lambda c, e, s: None,
            source_slug=card.slug,
        ))

    return triggers


def _parse_trigger_paragraph(card: 'Card', paragraph: str,
                             triggers: list[TriggerDef]) -> None:
    """Parse a paragraph for "When/If X, effect" trigger patterns."""
    for trig_pat, event_type, cond_key in _TRIGGER_PATTERNS:
        m = trig_pat.search(paragraph)
        if not m:
            continue

        # Extract the effect portion: everything after the trigger clause
        effect_start = m.end()
        effect_text = paragraph[effect_start:].strip().lstrip(',').strip()

        # Check for an embedded if-condition in the effect text
        extra_condition = None
        if_match = None
        for if_pat, if_key in _IF_CONDITION_PATTERNS:
            if_m = if_pat.search(effect_text)
            if if_m:
                if_match = if_m
                extra_condition = _build_condition(if_key, if_m)
                # Strip the if-clause from the effect text
                effect_text = effect_text[if_m.end():].strip().lstrip(',').strip()
                break

        # Detect "you may" — marks trigger as optional (agent yes/no choice)
        is_optional = False
        you_may_m = re.match(r'you may\b\s*', effect_text, re.I)
        if you_may_m:
            is_optional = True
            effect_text = effect_text[you_may_m.end():].strip()
        # Handle "you may PAY. If you do, EFFECT" pattern
        if_you_do_m = re.search(r'\bif you do,?\s*', effect_text, re.I)
        if if_you_do_m:
            effect_text = effect_text[if_you_do_m.end():].strip()
            is_optional = True

        # Skip if effect text has complex markers
        if _has_complex_markers(effect_text):
            continue

        effect_fn = _parse_all_effects(effect_text)
        if effect_fn is None:
            continue

        # Build the trigger condition
        if cond_key == 'is_attacking':
            base_condition = _is_this_attacking
        elif cond_key == 'is_defending':
            base_condition = _is_this_defending
        elif cond_key == 'is_hit':
            base_condition = _is_this_hit
        else:
            base_condition = None

        # Combine base condition with extra if-condition
        if base_condition and extra_condition:
            bc, ec = base_condition, extra_condition
            def combined(card, event, state, _bc=bc, _ec=ec):
                return _bc(card, event, state) and _ec(card, event, state)
            condition_fn = combined
        elif extra_condition:
            condition_fn = extra_condition
        else:
            condition_fn = base_condition

        triggers.append(TriggerDef(
            event_type=event_type,
            condition_fn=condition_fn,
            effect_fn=effect_fn,
            source_slug=card.slug,
            is_optional=is_optional,
        ))
        return  # Only match first trigger pattern per paragraph


def _parse_if_condition_paragraph(card: 'Card', paragraph: str,
                                  triggers: list[TriggerDef]) -> None:
    """Parse a paragraph starting with an if-condition (no trigger word)."""
    # Skip if already has a trigger word
    if re.search(r'^when(?:ever)? ', paragraph, re.I):
        return
    # "While" conditions are semantically equivalent to "if" for our purposes
    paragraph = re.sub(r'^while\b', 'if', paragraph, count=1, flags=re.I)

    for if_pat, if_key in _IF_CONDITION_PATTERNS:
        if_m = if_pat.search(paragraph)
        if not if_m:
            continue

        # Effect text is after the if-clause
        effect_text = paragraph[if_m.end():].strip().lstrip(',').strip()

        # Detect "you may" — marks trigger as optional
        is_optional = False
        you_may_m = re.match(r'you may\b\s*', effect_text, re.I)
        if you_may_m:
            is_optional = True
            effect_text = effect_text[you_may_m.end():].strip()
        if_you_do_m = re.search(r'\bif you do,?\s*', effect_text, re.I)
        if if_you_do_m:
            effect_text = effect_text[if_you_do_m.end():].strip()
            is_optional = True

        if _has_complex_markers(effect_text):
            continue

        condition_fn = _build_condition(if_key, if_m)
        if condition_fn is None:
            continue

        effect_fn = _parse_all_effects(effect_text)
        if effect_fn is None:
            continue

        # If-conditions on the card itself are typically "on_play" or "attacking" triggers
        # Determine from effect: power/defense bonus → on_play, else on_play
        triggers.append(TriggerDef(
            event_type="on_play",
            condition_fn=condition_fn,
            effect_fn=effect_fn,
            source_slug=card.slug,
            is_optional=is_optional,
        ))
        return  # Only match first if-condition per paragraph


def _parse_standalone_effect(card: 'Card', paragraph: str,
                             triggers: list[TriggerDef]) -> None:
    """Parse a standalone effect paragraph (no trigger/condition prefix)."""
    # Skip if has trigger words or if-conditions or complex markers
    if re.search(r'^(?:when(?:ever)? |if |\*\*(?:crush|reprise|combo|surge|rupture)\*\*)', paragraph, re.I):
        return
    if _has_complex_markers(paragraph):
        return

    # Detect "You may EFFECT" — optional standalone effect
    is_optional = False
    text = paragraph
    you_may_m = re.match(r'^you may\b\s*', text, re.I)
    if you_may_m:
        is_optional = True
        text = text[you_may_m.end():].strip()
    if_you_do_m = re.search(r'\bif you do,?\s*', text, re.I)
    if if_you_do_m:
        text = text[if_you_do_m.end():].strip()
        is_optional = True

    # Only parse very simple standalone effects:
    # "Deal N arcane damage.", "Gain N{h}.", "Create N TOKEN tokens."
    # Must be the entire paragraph (single statement)
    if re.search(r'\.\s+[A-Z]', text):
        return  # Multiple sentences — too complex for standalone

    effect_fn = _parse_effect(text)
    if effect_fn is None:
        return

    triggers.append(TriggerDef(
        event_type="on_play",
        effect_fn=effect_fn,
        source_slug=card.slug,
        is_optional=is_optional,
    ))

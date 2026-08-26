"""Compile JSON effect objects into (card, event, state) -> None callables."""
from __future__ import annotations
from typing import Any, Callable


def _track_injected_effect(slug: str, effect_type: str) -> None:
    """Record a coverage hit for an effect that fires via an injected trigger
    (INJECT_TRIGGER one-shots / turn / chain hooks). These run through the engine's
    trigger machinery, not the interpreter's run_ability, so the interpreter's
    _track_effect never sees them — without this they read as authored-but-dead in
    scripts/dsl_coverage.py. No-op unless a coverage tracker is active."""
    from engine.card_effects.dsl import coverage as _cov
    tracker = _cov.active()
    if tracker is not None:
        tracker.record_effect(slug, effect_type)


def _resolve_amount(amount: Any, state, card=None) -> int | float:
    """Resolve a dynamic amount token to a numeric value.

    Two authoring forms are accepted: a bare string token ("ROLL_NUMBER") and a
    nested expression dict ({"type": "HALF", "value": {"type": "ROLL_RESULT"}}).
    Both appear in card JSON; an unresolved dict used to flow through as a dict
    and blow up the arithmetic in the calling effect.

    An UNKNOWN amount resolves to 0, which makes the effect silently do nothing —
    "create X Runechants" creates none. That is why invented amount strings
    (BOOST_COUNT, DRACONIC_CHAIN_LINKS_CONTROLLED, ...) are audited as defects:
    they look implemented and are inert. Prefer the COUNT_* expressions below.
    """
    roll = getattr(state, '_roll_result', 0) or 0
    if isinstance(amount, str):
        if amount in ("ROLL_NUMBER", "ROLL_RESULT"):
            return roll
        if amount == "ROLL_NUMBER_HALF_ROUND_DOWN":
            return roll // 2
        # The X a player chose to pay for a card with an X in its cost. play.py
        # stamps it at play time; before that (or on a card with no X cost) it
        # is 0, which is also the correct answer for "X" when nothing was paid.
        if amount == "X":
            return int(getattr(card, "x_paid", 0) or 0)
        return 0
    if isinstance(amount, dict):
        atype = (amount.get("type") or "").upper()
        # "the top X+1 cards" (Reel In) — arithmetic over other expressions, so
        # an offset needs no new expression per card.
        #   {"type":"SUM","values":[{"type":"X"}, 1]}
        #   {"type":"X","plus":1}   — sugar for the same thing
        #
        # Checked FIRST: {"type":"X","plus":1} must not be answered by the "X"
        # branch below, which would silently drop the +1.
        if amount.get("plus") is not None or amount.get("minus") is not None:
            base = _resolve_amount({k: v for k, v in amount.items()
                                    if k not in ("plus", "minus")}, state, card)
            return (base + int(amount.get("plus") or 0)
                    - int(amount.get("minus") or 0))
        if atype in ("SUM", "ADD", "PLUS"):
            return sum(_resolve_amount(v, state, card)
                       for v in (amount.get("values") or []))
        if atype == "X":
            return int(getattr(card, "x_paid", 0) or 0)
        if atype in ("ROLL_NUMBER", "ROLL_RESULT"):
            return roll
        # "that many times" / "that many tokens" — how much a preceding
        # PAY_UP_TO actually charged. Same mechanism as ROLL_RESULT.
        if atype in ("PAID_AMOUNT", "AMOUNT_PAID"):
            return getattr(state, "_paid_amount", 0) or 0
        # "Create a Silver token for each permanent destroyed this way" (Cash
        # Out) — how many the DESTROY_PERMANENTS_OPTIONAL additional cost
        # actually destroyed. Same publish-on-state mechanism as PAID_AMOUNT.
        if atype in ("DESTROYED_COUNT", "PERMANENTS_DESTROYED"):
            return getattr(state, "_destroyed_count", 0) or 0
        # "equal to or less than the damage dealt by <this card>" — the amount
        # that ACTUALLY landed, which the printed number does not give once
        # prevention or replacement effects have had their say.
        if atype in ("LAST_DAMAGE_DEALT", "DAMAGE_JUST_DEALT"):
            return int(getattr(state, "_last_damage_dealt", 0) or 0)

        # "X is the total {h} you've gained this turn" (Thistle Bloom). A
        # MAGNITUDE, not an occurrence count — turn-event markers record that
        # something happened, never how much — so gain() tallies it directly.
        # "X is the damage dealt by this attack" — the damage AFTER defence,
        # which attack_power does not give.
        if atype in ("DAMAGE_DEALT", "NET_DAMAGE"):
            combat = getattr(state, "combat", None)
            if combat is None:
                return 0
            return int(getattr(combat, "net_damage_dealt", 0) or 0)

        if atype in ("LIFE_GAINED_THIS_TURN", "COUNT_LIFE_GAINED"):
            pid = _amount_controller(state, card)
            if pid is None:
                return 0
            return int(getattr(state.players[pid], "life_gained_this_turn", 0) or 0)
        # "X is the number of non-attack action cards you've played this turn"
        # (Rift Bind), "for each card you've banished this turn". The
        # EVENT_THIS_TURN *condition* could already TEST these markers; nothing
        # could COUNT them, so every such card invented a private counter that
        # nothing incremented. Same event/qualifier vocabulary as the condition,
        # so a card that tests and a card that counts speak one language.
        if atype in ("COUNT_TURN_EVENT", "EVENT_COUNT_THIS_TURN"):
            pid = _amount_controller(state, card)
            if pid is None:
                return 0
            event = _norm_amt(amount.get("event"))
            if not event:
                return 0
            if (amount.get("player") or "SELF").upper() in (
                    "OPPONENT", "ATTACKING", "ATTACKER", "DEFENDING"):
                pid = 3 - pid
            qualifier = _norm_amt(amount.get("qualifier") or amount.get("name"))
            from engine.effect_keywords import TURN_EVENT_MARKER
            marker = f"{TURN_EVENT_MARKER}{event}" + (f":{qualifier}" if qualifier else "")
            return sum(1 for m in state.players[pid].current_turn_effects
                       if m == marker)

        # "X is the total arcane damage you've dealt to opposing heroes this
        # turn" (Vaporize). A MAGNITUDE, so it reads the tally rather than
        # counting markers — four 1-point hits are 4, not 1.
        #   {"type":"DAMAGE_DEALT_THIS_TURN","damage_type":"arcane","target":"hero"}
        if atype in ("DAMAGE_DEALT_THIS_TURN", "TOTAL_DAMAGE_THIS_TURN"):
            pid = _amount_controller(state, card)
            if pid is None:
                return 0
            dtype = _norm_amt(amount.get("damage_type"))
            target = _norm_amt(amount.get("target"))
            key = ":".join([p for p in (dtype, target) if p]) or "total"
            tally = getattr(state.players[pid], "damage_dealt_this_turn", None) or {}
            return int(tally.get(key, 0) or 0)

        # "the number of opposing heroes with greater {h} than you"
        # (Grandstand Legplates). Two-player games make this 0 or 1, but it is
        # written as a count because the game supports multiplayer, and reading
        # it as a boolean would be wrong there.
        # "X is the number of cards with 6 or more {p} revealed this way"
        # (Song of Sinew). Counts the ability-scoped ref a preceding LOOK_AT /
        # REVEAL_TOP_DECK stored, so any question about a looked-at set is a
        # filter here rather than a new parameter on the reveal effect.
        if atype in ("COUNT_REF", "REF_COUNT"):
            from engine.context import get_ref
            pool = get_ref(amount.get("ref") or "revealed")
            if pool is None:
                return 0
            if not isinstance(pool, list):
                pool = [pool]
            power_gte = amount.get("power_gte")
            cost_gte = amount.get("cost_gte")
            want_sub = _norm_amt(amount.get("subtype"))
            want_type = _norm_amt(amount.get("card_type") or amount.get("type_name"))
            # "a RUNEBLADE attack action card revealed this way" — there was no
            # class filter, so the count was too generous in any deck holding
            # attack actions of another class.
            want_class = _norm_amt(amount.get("card_class") or amount.get("class"))
            n = 0
            for c in pool:
                if power_gte is not None and (getattr(c, "power", None) or 0) < power_gte:
                    continue
                if cost_gte is not None and (getattr(c, "cost", None) or 0) < cost_gte:
                    continue
                if want_sub and want_sub not in {_norm_amt(x) for x in (getattr(c, "subtypes", None) or [])}:
                    continue
                if want_type:
                    # Types AND subtypes, as CARD_IS_TYPE does: "Attack" is a
                    # SUBTYPE while "Action" is a type, and cards use either
                    # word for the same idea. Checking only `types` here made
                    # card_type:"Attack" count nothing — an inconsistency
                    # between two spellings of the same question.
                    have = {_norm_amt(x) for x in (getattr(c, "types", None) or [])}
                    have |= {_norm_amt(x) for x in (getattr(c, "subtypes", None) or [])}
                    if want_type not in have:
                        continue
                if want_class and want_class not in {
                        _norm_amt(x) for x in ((getattr(c, "classes", None) or [])
                                               + (getattr(c, "talents", None) or []))}:
                    continue
                n += 1
            return n

        if atype in ("COUNT_OPPOSING_HEROES", "COUNT_OPPONENTS"):
            pid = _amount_controller(state, card)
            if pid is None:
                return 0
            mine = getattr(state.players[pid], "life", 0) or 0
            cmp_life = (amount.get("life") or "").upper()
            n = 0
            for other_id, other in (state.players or {}).items():
                if other_id == pid:
                    continue
                their = getattr(other, "life", 0) or 0
                if cmp_life in ("GREATER", "GT", "MORE") and not their > mine:
                    continue
                if cmp_life in ("LESS", "LT", "FEWER") and not their < mine:
                    continue
                n += 1
            return n

        if atype in ("HALF", "HALF_ROUND_DOWN"):
            return int(_resolve_amount(amount.get("value", 0), state, card)) // 2
        if atype in ("VALUE", "CONSTANT", "LITERAL"):
            return _resolve_amount(amount.get("value", 0), state, card)

        # "X is the number of Draconic chain links you control" — ChainLink
        # already records talents/classes/subtypes per link, so this is a count
        # over existing state rather than new bookkeeping.
        if atype == "COUNT_CHAIN_LINKS":
            pid = _amount_controller(state, card)
            want_talent = _norm_amt(amount.get("talent"))
            want_class = _norm_amt(amount.get("class") or amount.get("card_class"))
            want_sub = _norm_amt(amount.get("subtype"))
            only_hit = amount.get("hit")
            n = 0
            for link in getattr(state, "chain_links", None) or []:
                if pid is not None and link.attacker_id != pid:
                    continue
                if only_hit is not None and bool(link.hit) is not bool(only_hit):
                    continue
                if want_talent and want_talent not in {_norm_amt(x) for x in (link.talents or [])}:
                    continue
                if want_class and want_class not in {_norm_amt(x) for x in (link.classes or [])}:
                    continue
                if want_sub and want_sub not in {_norm_amt(x) for x in (link.subtypes or [])}:
                    continue
                n += 1
            return n

        # "for each Runechant you control" — the commonest "X is the number of"
        # phrasing in the game. Counts permanents you control, filtered by
        # subtype / type / slug.
        if atype in ("COUNT_PERMANENT", "COUNT_PERMANENTS"):
            pid = _amount_controller(state, card)
            if pid is None:
                return 0
            want_sub = _norm_amt(amount.get("subtype"))
            want_type = _norm_amt(amount.get("card_type") or amount.get("type_name"))
            want_slug = _norm_amt(amount.get("slug") or amount.get("name"))
            # "you control" covers the whole arena, not just the permanents zone:
            # "the number of Evos you have EQUIPPED" counts head/chest/arms/legs
            # and weapon slots, none of which live in `permanents`. Scanning
            # permanents alone returned 0 for every equipment count.
            # zone: "ARENA" (default) | "PERMANENTS" | "EQUIPMENT".
            player = state.players[pid]
            zone = (amount.get("zone") or "ARENA").upper()
            equipment = [player.head, player.chest, player.arms, player.legs,
                         player.weapon1, player.weapon2]
            if zone == "PERMANENTS":
                pool = list(player.permanents.cards)
            elif zone == "EQUIPMENT":
                pool = [c for z in equipment for c in z.cards]
            else:
                pool = list(player.permanents.cards) + [c for z in equipment for c in z.cards]
            n = 0
            for perm in pool:
                if want_sub and want_sub not in {_norm_amt(x) for x in (getattr(perm, "subtypes", None) or [])}:
                    continue
                if want_type and want_type not in {_norm_amt(x) for x in (getattr(perm, "types", None) or [])}:
                    continue
                if want_slug and _norm_amt(getattr(perm, "slug", "")) != want_slug:
                    continue
                n += 1
            return n

        if atype in ("COUNT_DEFENDING", "COUNT_DEFENDERS"):
            # "X is the number of equipment defending it" (Panel Beater, Fender
            # Bender), "for each card with 6 or more {p} defending it" (Power of
            # Make Believe). Five cards expressed this as
            # MODIFY_ATTACK_POWER_PER_UNIQUE_AURA — an effect that counts
            # distinct AURA NAMES in the arena and has nothing to do with
            # defenders — because there was no way to count them.
            #
            #   {"type":"COUNT_DEFENDING","equipment":true}
            #   {"type":"COUNT_DEFENDING","power_gte":6}
            combat = state.combat
            if not combat:
                return 0
            cards = getattr(combat, "defending_cards", None) or []
            want_equipment = amount.get("equipment")
            if want_equipment is not None:
                cards = [d for d in cards
                         if bool(getattr(d, "is_equipment", False)) is bool(want_equipment)]
            power_gte = amount.get("power_gte")
            if power_gte is not None:
                try:
                    threshold = int(power_gte)
                except (TypeError, ValueError):
                    threshold = 0
                cards = [d for d in cards
                         if (getattr(d, "power", None) or 0) >= threshold]
            return len(cards)

        # "the number of times you've boosted this <turn|combat chain>".
        # ability_keywords.boost already appends one "boosted_this_turn" marker
        # PER boost precisely so it can be counted, not just tested.
        if atype in ("COUNT_BOOSTS", "BOOST_COUNT"):
            # scope: "CHAIN" (default) counts boosts made during the CURRENT
            # combat chain; "TURN" counts the whole turn. Both printed wordings
            # exist, and they differ: a second attack in the same turn must not
            # inherit the first attack's boosts, so a turn count OVER-counts for
            # a card that says "this combat chain".
            pid = _amount_controller(state, card)
            if pid is None:
                return 0
            player = state.players[pid]
            if (amount.get("scope") or "CHAIN").upper() == "TURN":
                return sum(1 for m in player.current_turn_effects
                           if m == "boosted_this_turn")
            return int(getattr(player, "boosts_this_chain", 0) or 0)

        # "X is the number of doom counters on this" — counters already live on
        # the player keyed by (slug, zone, counter).
        if atype in ("COUNT_COUNTERS", "COUNTER"):
            pid = _amount_controller(state, card)
            want = _norm_amt(amount.get("counter") or amount.get("name"))
            slug = _norm_amt(getattr(card, "slug", None)) if card is not None else ""
            if pid is None or not want:
                return 0
            total = 0
            for key, value in (state.players[pid].counters or {}).items():
                try:
                    k_slug, _zone, k_counter = key
                except (TypeError, ValueError):
                    continue
                if _norm_amt(k_counter) != want:
                    continue
                if slug and _norm_amt(k_slug) != slug:
                    continue
                total += value
            return total
        return 0
    return amount


def _norm_amt(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isalnum()).lower()


def canonical_keyword(keyword: str) -> str:
    """The card-data spelling of a keyword name written in DSL SHOUTING_CASE.

    A granted keyword has to land in combat.keywords spelled the way a PRINTED
    one does, because several checks compare exactly. Only "go again" was
    canonicalised; everything else was lowercased, so a GAIN of OVERPOWER
    produced "overpower" while the printed keyword produced "Overpower" — two
    spellings of one keyword, and an exact-match check sees only one of them.
    """
    words = str(keyword or "").replace("_", " ").split()
    return " ".join(w.capitalize() for w in words)


def _amount_controller(state, card):
    """Whose things to count. The card's controller when known; otherwise the
    attacking player, so a count inside combat still resolves.

    Returns None rather than an id that is not a real player: a card with no
    owner/controller yields 0 from _controller_id, and `state.players[0]` raises
    KeyError, aborting resolution mid-game. An unresolvable controller must make
    the count 0, not crash.
    """
    players = getattr(state, "players", None) or {}

    def _valid(pid):
        return pid if pid in players else None

    if card is not None:
        from engine.card_effects.ability_keywords import _controller_id
        try:
            pid = _valid(_controller_id(card))
            if pid is not None:
                return pid
        except Exception:
            pass
    combat = getattr(state, "combat", None)
    if combat is not None:
        pid = _valid(getattr(combat, "attacker_id", None))
        if pid is not None:
            return pid
    return _valid(getattr(state, "active_player", None))


def _first(params, *keys, default=None):
    """First present key among `keys`. See condition_types._as_list.

    A parameter the compiler does not read is silently dropped, and the effect
    then does nothing or does the wrong thing — indistinguishable from an
    invented type at runtime, but invisible to a type-name audit. Reading every
    spelling a card plausibly uses is what keeps that class closed;
    scripts/audit_params.py reports any that slip through.
    """
    for key in keys:
        value = params.get(key)
        if value is not None:
            return value
    return default


#: Zone words a card may use in an effect's "target", mapped to canonical zone
#: names. Spellings vary because cards were authored by hand: "TOP_CARD" and
#: "DECK_TOP" both mean the top of the deck, and "hero_graveyard" is just the
#: graveyard with the controller named twice.
_TARGET_ZONES = {
    "top_deck": "TOP_DECK", "topdeck": "TOP_DECK", "deck_top": "TOP_DECK",
    "top_card": "TOP_DECK", "top": "TOP_DECK", "deck": "DECK",
    "hand": "HAND", "graveyard": "GRAVEYARD", "arsenal": "ARSENAL",
    "soul": "SOUL",
}

#: Words naming whose zone it is. "hero" reads as the controller's own — a card
#: saying "hero_graveyard" means its own side. The opponent words are tested
#: FIRST, because "defending_hero_hand" contains "hero" too and would otherwise
#: resolve to the wrong player.
_TARGET_OPPONENT = ("opponent", "their", "defending", "enemy")
_TARGET_SELF = ("self", "your", "hero", "my", "own")


#: Where an object target may live. "ARENA" is every permanent (auras, items,
#: allies, tokens); equipment and weapons are separate zones on Player and are
#: NOT covered by Player.equipment (which is head/chest/arms/legs only), so a
#: card saying "equipment, items, and/or weapons" has to name them.
_OBJECT_TARGET_ZONES = ("ARENA", "EQUIPMENT", "WEAPON", "ARSENAL", "HERO",
                        "DECK_TOP", "DECK", "GRAVEYARD", "BANISHED", "HAND",
                        "SOUL", "PITCH")


def _grant_go_again(card, state) -> None:
    """CR 8.3.5 -- "gain 1 action point", by whichever route the rule names.

    8.3.5b: an ability of an ATTACK on the active chain link puts the keyword on
    the combat, and the engine pays the point out at the Resolution Step.
    8.3.5a: an ability of a NON-ATTACK LAYER pays its controller directly.

    8.3.5c: an object cannot have two go agains, so neither route pays twice for
    one resolution.

    KNOWN LIMIT: the test is "is there a combat", not "is this ability on the
    attack". An INSTANT activated during someone else's combat therefore puts
    its go again on that attack instead of paying its own controller. The
    stricter test (card is combat.attack_card) is what 8.3.5b actually says, but
    no card in the corpus demonstrates the difference, and narrowing it on
    speculation risks the INJECT_TRIGGER ON_HIT users that grant onto the attack
    they are riding.
    """
    if state.combat is not None:
        # The PRINTED keyword arrives from the card DB spelled "GoAgain" and a
        # granted one is spelled "Go Again". An exact-match guard therefore
        # never saw a printed go again and happily appended a second -- which
        # CR 8.3.5c says must fail. The engine's own payout check splits the
        # camel case before comparing (engine._resolution_step); so does this.
        import re as _re
        already = any(
            _re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', str(k)).lower() == "go again"
            for k in (state.combat.keywords or []))
        if not already:
            state.combat.grant_keyword("Go Again")
        return
    from engine.card_effects.ability_keywords import _controller_id
    player = state.players.get(_controller_id(card))
    if player is None:
        return
    player.action_points = (player.action_points or 0) + 1


def _object_zone_cards(player, zone: str) -> list:
    zone = (zone or "ARENA").upper()
    if zone == "ARENA":
        return list(player.permanents.cards)
    if zone == "EQUIPMENT":
        # player.equipment is the four body slots. An OFF-HAND is an equipment
        # card too -- CR 2.10.6a makes Off-Hand a functional SUBTYPE, and
        # 3.16.2a equips it to a WEAPON zone -- so "an equipment you control"
        # that skipped the weapon zones could never see one, and the single
        # card naming an off-hand searched a pool it was never in.
        # Weapons themselves stay out: they are a TYPE of their own.
        cards = list(player.equipment)
        for z in (player.weapon1, player.weapon2):
            for c in z.cards:
                types = {str(t).lower() for t in (getattr(c, "types", None) or [])}
                if "weapon" in types:
                    continue
                if c not in cards:
                    cards.append(c)
        return cards
    if zone == "WEAPON":
        return list(player.weapon1.cards) + list(player.weapon2.cards)
    if zone == "ARSENAL":
        return list(player.arsenal.cards)
    if zone == "HERO":
        return [player.hero] if player.hero is not None else []
    # DECK_TOP is the top card only, and is deliberately NOT the same pool as
    # DECK: "destroy the top card of their deck" must not become a prompt to
    # choose any card in it, which is both a different effect and an
    # information leak.
    if zone == "DECK_TOP":
        return list(player.deck.cards[:1])
    if zone in ("DECK", "GRAVEYARD", "BANISHED", "HAND", "SOUL", "PITCH"):
        return list(getattr(player, zone.lower()).cards)
    return []


def _hand_card_filter(params):
    """Build a predicate for "discard a <kind of> card", or None for no filter.

    One vocabulary shared by the DISCARD effect and the DISCARD_CARD cost,
    because the cards use the same words for both and each had its own partial
    reading: the cost knew only type_filter/class_filter, the effect knew
    nothing at all. A filter nobody reads is not a weakened effect — the discard
    still happens, on a card the text excludes, and on the COST side can_pay
    said yes whenever the hand was non-empty, so cards were playable when their
    cost could not actually be paid.

        {"color": "yellow"}                  colour of the card
        {"card_type": "Instant"}             type OR subtype (Attack is a subtype)
        {"card_name": "Phoenix Flame"}       by name or slug
        {"keyword": "watery grave"}          a printed keyword
        {"class_filter": "Assassin"}         class, the cost's original spelling
        {"filter": [ <DSL condition specs> ]} anything else
    """
    from engine.card_effects.dsl.condition_types import compile_condition

    def _norm(v):
        return "".join(ch for ch in str(v).lower() if ch.isalnum())

    color = _first(params, "color", "colour")
    kind = _first(params, "card_type", "type_filter", "subtype")
    name = _first(params, "card_name", "name")
    keyword = _first(params, "keyword")
    klass = _first(params, "class_filter", "card_class")
    specs = [compile_condition((f.get("type") or "none"), f)
             for f in (params.get("filter") or []) if isinstance(f, dict)]
    if not any((color, kind, name, keyword, klass)) and not specs:
        return None

    def _matches(c, state=None, _co=color, _k=kind, _n=name, _kw=keyword,
                 _cl=klass, _sp=specs):
        if _co:
            # Card.color is None on a real card until something sets it; the
            # PRINTED colour lives on base_color (raw_color before that). A
            # colour filter reading only .color matched nothing at all.
            have = (getattr(c, "color", None) or getattr(c, "base_color", None)
                    or getattr(c, "raw_color", None) or "")
            if _norm(have) != _norm(_co):
                return False
        if _k:
            have = {_norm(x) for x in (getattr(c, "types", None) or [])}
            have |= {_norm(x) for x in (getattr(c, "subtypes", None) or [])}
            if _norm(_k) not in have:
                return False
        if _n and _norm(_n) not in (_norm(getattr(c, "name", "") or ""),
                                    _norm(getattr(c, "slug", "") or "")):
            return False
        if _kw:
            have = {_norm(x) for x in (getattr(c, "keywords", None) or [])}
            if _norm(_kw) not in have:
                return False
        if _cl:
            have = {_norm(x) for x in (getattr(c, "classes", None) or [])}
            if _norm(_cl) not in have:
                return False
        for fn in _sp:
            # Ordinary DSL conditions, evaluated with the CANDIDATE as the card
            # argument — the same contract _compile_object_target's filters use.
            # State is threaded through by the caller rather than passed as
            # None, so a condition that reads the game state still works.
            if fn is not None and not fn(c, None, state):
                return False
        return True
    return _matches


def _permanent_filter(params):
    """Build a predicate for "destroy a <kind of> permanent", or None.

    Shared by the DESTROY_PERMANENT effect and the cost of the same name,
    because the cards use the same words for both and each read a DIFFERENT
    subset: the effect knew `subtype`, the cost knew `slug`/`permanent_type`,
    and NEITHER knew `asset` — which is how "destroy X GOLD you control" came to
    destroy X arbitrary permanents, and, as a cost, to be payable with any
    permanent at all.

        {"asset": "GOLD"}            a token, by printed name or slug
        {"slug": "gold"}             by slug
        {"subtype": "Aura"}          by subtype
        {"permanent_type": "Item"}   by type
        {"target": "ITEM"}           the same, in the spelling two cards use
        {"token": true}              tokens only (false: non-tokens only)
        {"max_cost": 2}              printed cost at most N
    """
    def _norm(v):
        return "".join(ch for ch in str(v).lower() if ch.isalnum())

    named = _first(params, "asset", "slug", "token_slug", "token_name")
    subtype = _first(params, "subtype", "permanent_type")
    # "target" holds "self"/"controlled" (not a filter) on most cards and a TYPE
    # name on the two that reach for it that way.
    raw_target = params.get("target")
    # Two KINDS of value arrive here and only one is a filter. "self" and
    # friends name WHICH object; a type name ("item") narrows WHAT qualifies.
    # A directive read as a type is a filter nothing satisfies, so the card
    # silently does nothing -- and can_pay says the cost is unpayable, which
    # made good_time_chapeau's ability impossible to activate with a Gold in
    # play. "chosen" (9 cards) means "the player picks" and was being matched
    # as a subtype.
    _DIRECTIVES = ("", "self", "this", "source", "controlled",
                   "controlled_permanent", "chosen", "choice", "choose",
                   "any", "target")
    if isinstance(raw_target, str):
        low = raw_target.lower()
        # "controlled_item" is "an item you control": the prefix is the
        # directive half and the rest is the real filter. Read whole it named a
        # subtype no card has (2 cards).
        if low.startswith("controlled_") and low not in _DIRECTIVES:
            low = low[len("controlled_"):]
        if low not in _DIRECTIVES:
            subtype = subtype or low
    want_token = params.get("token")
    max_cost = params.get("max_cost")
    if named is None and subtype is None and want_token is None and max_cost is None:
        return None

    def _matches(c, state=None, _nm=named, _sub=subtype, _tok=want_token,
                 _max=max_cost):
        if _nm and _norm(_nm) not in (_norm(getattr(c, "slug", "") or ""),
                                      _norm(getattr(c, "name", "") or "")):
            return False
        if _sub:
            have = {_norm(x) for x in (getattr(c, "subtypes", None) or [])}
            have |= {_norm(x) for x in (getattr(c, "types", None) or [])}
            if _norm(_sub) not in have:
                return False
        if _tok is not None and bool(getattr(c, "is_token", False)) is not bool(_tok):
            return False
        if _max is not None:
            cost = getattr(c, "raw_cost", None)
            if cost is None:
                cost = getattr(c, "cost", None)
            try:
                cost = int(cost)
            except (TypeError, ValueError):
                # A token has no printed cost; "cost X or less" is satisfied by
                # a costless permanent rather than excluding it.
                cost = 0
            limit = _resolve_amount(_max, state, c) if state is not None else _max
            try:
                if cost > int(limit):
                    return False
            except (TypeError, ValueError):
                return False
        return True
    return _matches


def _object_target_spec(target):
    """Normalise an effect's "target" to the canonical dict, or None.

    None means "the source card", which is what these effects have always done
    and is right for the twelve nodes that say "self" — honouring those would
    change nothing, so they are left on the original path rather than routed
    through a resolver that could only reproduce it.

    Anything that is NOT the canonical dict and NOT "self" is refused rather
    than guessed at. The card is then still reported by
    scripts/audit_params.py, which is the only thing that will bring it back
    up; resolving it to something plausible would hide it for good.
    """
    # A fifth spelling: {"type": "TOP_DECK", "controller": "opponent"} uses
    # `type` to name the ZONE. Such a dict was already accepted as canonical (it
    # has `controller`) but carried no `zone`, so it fell through to the ARENA
    # default — five cards saying "banish the top card of THEIR DECK" were
    # banishing from their arena instead. Silent, and the wrong zone.
    #
    # Only a `type` that NAMES A ZONE is read this way. A dict whose type is
    # anything else ({"type": "CARD"}) is still refused below, which is what
    # keeps an unparseable target visible to scripts/audit_params.py rather than
    # resolved to a plausible guess.
    if isinstance(target, dict) and "zone" not in target and "zones" not in target:
        named = str(target.get("type") or "").upper()
        if named in _OBJECT_TARGET_ZONES or named in ("TOP_CARD", "TOP_DECK"):
            target = {k: v for k, v in target.items() if k != "type"}
            target["zone"] = ("DECK_TOP" if named in ("TOP_CARD", "TOP_DECK")
                              else named)

    if isinstance(target, dict) and any(
            k in target for k in ("controller", "zone", "zones", "name",
                                  "name_ref", "filter", "ref")):
        return target
    # Everything else — "self", the bespoke strings ("controlled_aura_with_ward",
    # "ally", "opponent", ...) and the older dict shapes — falls back to the
    # source card, which is the behaviour that was already there.
    return None


def _compile_object_target(spec):
    """Compile a canonical object target into fn(card, event, state) -> [Card].

    Shared by the counter effects and DESTROY_MATCHING. Nothing about it is
    counter-specific: it answers "which objects does this card mean", which is
    the question every one of these effects was getting wrong.

    PUT_COUNTER / REMOVE_COUNTER / REMOVE_COUNTERS acted on the source card and
    ignored "target" entirely, so "put a +1{p} counter on target aura with ward
    you control" put it on the action card, and "put a -1{d} counter on an
    equipment THEY control" put it on the attacker.

    The twelve cards involved had each invented their own vocabulary for the
    target — "controlled_aura_with_ward", "ally", "equipment", "opponent",
    "TREASURE_ISLAND", and four incompatible dict shapes. Teaching the compiler
    those strings would encode the guesses one card at a time, which is how one
    boolean ended up standing in for six unrelated mechanics. So there is ONE
    shape, and the cards are written to it:

        {"controller": "SELF"|"OPPONENT"|"ANY",   default SELF
         "zone":       "ARENA"|"EQUIPMENT"|"WEAPON"|"ARSENAL"|"HERO",
         "zones":      [...],                     several of the above
         "name":       "Treasure Island",         match by card name or slug
         "ref":        "flipped",                 what an earlier effect stored,
                                                  INSTEAD of a zone search
         "record_as":  "flipped",                 store the chosen objects under
                                                  this ref for a later effect
         "amount":     n | "ALL",                 how many to affect
         "filter":     [ <ordinary DSL condition specs> ]}

    `filter` entries are ordinary conditions evaluated with the CANDIDATE as the
    card argument, so "an item you control with crank" is HAS_KEYWORD and "a
    Guardian off-hand" is CARD_IS_CLASS — reusing every condition type that
    already exists rather than growing an eleventh vocabulary here.
    """
    if not isinstance(spec, dict):
        return None

    controller = str(spec.get("controller") or "SELF").upper()
    zones = spec.get("zones") or [spec.get("zone") or "ARENA"]
    zones = [str(z).upper() for z in zones]
    want_name = spec.get("name")
    # "cards WITH THAT NAME" — the name was chosen by a player, so it cannot be
    # a literal in the JSON. Read from the ref, falling back to the source
    # card's own store for a later ability on the same object (a reference
    # scope lasts one ability execution).
    name_ref = spec.get("name_ref")
    limit = spec.get("amount", 1)
    # "put an aim counter on IT" — the object a preceding effect acted on. The
    # alternative is to repeat the zone search and hope it lands on the same
    # card, which is what one card did: it re-searched for "a face-up arrow in
    # arsenal" after flipping one, and could just as easily have counted a
    # different arrow that was already face up.
    from_ref = spec.get("ref")
    # The mirror: name what this target chose so the NEXT effect can say "it".
    record_as = spec.get("record_as")
    from engine.card_effects.dsl.condition_types import compile_condition
    filters = [compile_condition((f.get("type") or "none"), f)
               for f in (spec.get("filter") or []) if isinstance(f, dict)]

    def _fn(card, event, state, _c=controller, _z=zones, _n=want_name,
            _lim=limit, _f=filters, _ref=from_ref, _rec=record_as,
            _nref=name_ref):
        from engine.card_effects.ability_keywords import _ask_player, _controller_id
        from engine.context import get_ref, set_ref
        cid = _controller_id(card)
        if cid not in state.players:
            return []
        if _nref:
            found_name = get_ref(_nref)
            if found_name is None:
                found_name = (getattr(card, "dsl_chosen", None) or {}).get(_nref)
            if not found_name:
                # Nothing was named, so "cards with that name" names nothing —
                # returning the unfiltered pool would hit every card in the zone.
                return []
            _n = found_name
        if _c == "OPPONENT":
            pids = [3 - cid]
        elif _c in ("ANY", "ALL", "EACH"):
            pids = [cid, 3 - cid]
        else:
            pids = [cid]

        pool = []
        if _ref:
            found = get_ref(_ref)
            if found is not None:
                pool = list(found) if isinstance(found, list) else [found]
        else:
            for pid in pids:
                for zone in _z:
                    pool.extend(_object_zone_cards(state.players[pid], zone))

        if _n:
            def _flat(text):
                return "".join(ch for ch in str(text).lower() if ch.isalnum())
            wanted = _flat(_n)
            pool = [c for c in pool
                    if wanted in (_flat(getattr(c, "name", "") or ""),
                                  _flat(getattr(c, "slug", "") or ""))]
        for fn in _f:
            if fn is not None:
                pool = [c for c in pool if fn(c, event, state)]
        if not pool:
            return []

        if str(_lim).upper() in ("ALL", "EACH"):
            if _rec:
                set_ref(_rec, pool[0] if len(pool) == 1 else list(pool))
            return pool
        count = _resolve_amount(_lim, state, card)
        try:
            count = max(0, int(count))
        except (TypeError, ValueError):
            count = 1

        chosen = []
        remaining = list(pool)
        for _ in range(min(count, len(remaining))):
            pick = _ask_player(state, cid, [c.slug for c in remaining],
                               context="Choose a target card")
            obj = next((c for c in remaining if c.slug == pick), remaining[0])
            chosen.append(obj)
            remaining.remove(obj)
        if _rec:
            set_ref(_rec, chosen[0] if len(chosen) == 1 else list(chosen))
        return chosen

    return _fn


def _effect_player_id(state, card, spec, event=None) -> int | None:
    """Which player an effect's `player` names.

    Most effects resolve SELF/OPPONENT relative to the CONTROLLER, each with
    their own copy of the same expression. Two more relations exist and had no
    spelling at all:

      ACTIVE / TURN_PLAYER   whose turn it is — "at the beginning of EACH hero's
                             action phase, THEY draw a card" means the hero whose
                             phase it is, not the card's controller.
      EVENT_PLAYER / DREW    the player the event is about — "whenever a HERO
                             draws a card, THEY lose 1{h}" means whoever drew.

    Without these, a card whose text says "they" could only ever be written as
    the controller or their opponent, which is right half the time by accident.
    """
    from engine.card_effects.ability_keywords import _controller_id
    cid = _controller_id(card)
    want = str(spec or "SELF").upper()
    if want in ("OPPONENT", "DEFENDING", "DEFENDER", "THEM"):
        return (3 - cid) if cid in (1, 2) else None
    if want in ("ACTIVE", "TURN_PLAYER", "ACTIVE_PLAYER"):
        return getattr(state, "active_player", cid)
    if want in ("EVENT_PLAYER", "DREW", "TRIGGERING", "THEY"):
        data = getattr(event, "data", None)
        if isinstance(data, dict):
            for key in ("draw_player", "player_id", "target_player_id"):
                if data.get(key) is not None:
                    return data[key]
        return getattr(state, "active_player", cid)
    return cid


def _record_banished(cards: list) -> None:
    """Store what a BANISH just banished, so "if it's blue" has something to ask.

    Several cards read "banish the top card of their deck. If it's <colour>,
    ..." and BANISH recorded nothing at all, so the follow-up test had no
    subject and could only ever be answered from thin air. "banished" is the
    single most recent card (or the list, when more than one); "banished_cards"
    accumulates across the whole ability for "another card with the same
    colour" wordings.
    """
    if not cards:
        return
    from engine.context import get_ref, set_ref
    set_ref("banished", cards[0] if len(cards) == 1 else list(cards))
    prior = get_ref("banished_cards")
    set_ref("banished_cards", (list(prior) if isinstance(prior, list) else [])
            + list(cards))


def _zone_target_spec(target) -> tuple[str | None, str | None]:
    """Read an effect's "target" into (player, zone), either possibly None.

    Shared by BANISH and LOOK_AT, which is the point: they were given the same
    handful of spellings by the same authors, and a second parser would drift
    from this one the first time a new one appeared.

    Returns None for a part the target does not name, so the caller keeps its
    own default rather than a guess. A target this cannot parse — "INSTANT" is a
    card type, not a zone — yields (None, None) and stays visible to
    scripts/audit_params.py instead of being silently resolved to something
    plausible.
    """
    if not target:
        return (None, None)

    player = zone = None
    words: list[str] = []

    if isinstance(target, dict):
        controller = target.get("controller") or target.get("player")
        if isinstance(controller, str):
            words.append(controller)
        for key in ("type", "zone", "from_zone"):
            value = target.get(key)
            if isinstance(value, str):
                words.append(value)
    elif isinstance(target, str):
        words.append(target)
    else:
        return (None, None)

    blob = "_".join(words).strip().lower()
    if any(w in blob for w in _TARGET_OPPONENT):
        player = "OPPONENT"
    elif any(w in blob for w in _TARGET_SELF):
        player = "SELF"

    # Longest zone alias first: "top_deck" must win over the "deck" inside it,
    # or "their top deck" resolves to a prompted choice from the whole deck.
    for alias in sorted(_TARGET_ZONES, key=len, reverse=True):
        if alias in blob:
            zone = _TARGET_ZONES[alias]
            break

    return (player, zone)


def _damage_target_player(state, controller_id: int, target: str) -> int:
    """Which PLAYER a "deal N damage to <target>" names.

    Anything outside the recognised set resolved to the CONTROLLER, so every
    spelling an author reached for other than "OPPONENT" burned its own hero.
    Two live families did:

      "hero" / "target hero"   3 cards. In practice the other player.
      "ATTACKER"               zap_clappers deals to "the ATTACKING hero" from
                               a WHEN-THIS-DEFENDS trigger, so the controller is
                               the defender and self was exactly backwards.

    Only frost_hex_blue's "this deals 1 arcane damage to YOU" is genuinely
    self-inflicted. The vocabulary lives here rather than being spelled out at
    each call site: it was duplicated across DEAL_ARCANE and DEAL_GENERIC, and
    a fix applied to one of two copies is the shape this audit keeps finding.
    """
    tu = str(target or "").upper()
    if tu in ("ATTACKER", "ATTACKING_HERO", "ATTACKING"):
        combat = getattr(state, "combat", None)
        return getattr(combat, "attacker_id", None) or (3 - controller_id)
    if tu in ("OPPONENT", "DEFENDING", "DEFENDER", "HERO", "TARGET_HERO",
              "OPPOSING_HERO", "THEM", "THEY"):
        return 3 - controller_id
    return controller_id


class _ConditionProbe:
    """A minimal stand-in card used to ask a compiled condition about a PLAYER.

    Conditions resolve their player via _controller_id(card), so asking "does
    THIS hero have a card in their arsenal" for each hero in turn needs an
    object whose controller is that hero.
    """

    __slots__ = ("controller", "owner", "slug", "types", "subtypes", "zone")

    def __init__(self, player_id):
        self.controller = self.owner = player_id
        self.slug = ""
        self.types = []
        self.subtypes = []
        self.zone = None


def _matches_type_or_subtype(card, wanted) -> bool:
    """Does this card carry any of `wanted` as a TYPE or a SUBTYPE?

    "Instant" is a type while "Ally" and "Attack" are subtypes, and a card
    naming either means the same thing by it. Two search effects each carried
    their OWN copy of a types-only reading -- the same one-fact-two-stores
    shape this audit keeps finding -- so "search your deck for an ALLY" and
    "return an ALLY from your graveyard" both matched nothing at all.
    """
    if not wanted:
        return True
    want = {str(t).lower() for t in wanted}
    have = {str(t).lower() for t in (getattr(card, "types", None) or [])}
    have |= {str(t).lower() for t in (getattr(card, "subtypes", None) or [])}
    return bool(want & have)


def _names_self(raw) -> bool:
    """Does this target/ref spelling mean "this card"?

    The ref family (FLIP_REF, MOVE_REF, BANISH_REF, ...) resolves its object
    from a NAMED REF that an earlier effect stored. Three cards instead wrote
    `"target": "self"` for wordings whose object is the source card itself --
    "turn IT face-down", "put IT into your hero's soul". A bare string is not a
    canonical target dict, so the object lookup was skipped and the ref fell
    back to its default ("chosen"/"looked"), which nothing had set. Each of
    those cards did nothing at all.

    "self" is the natural word for it and appears throughout the corpus in
    other effects, so it is recognised here rather than rewritten away in the
    three cards -- the next author will reach for the same word.
    """
    return (isinstance(raw, str)
            and raw.strip().lower() in ("self", "this", "this_card", "source"))


def _deal_arcane_to_objects(state, card, amount, kind, max_targets,
                            ally_player="OPPONENT"):
    """Arcane damage to ALLIES (and, for "any target", heroes too).

    effect_deal_arcane resolves its player_id to that player's HERO and nothing
    else, so it cannot express "up to 2 target allies". This routes through the
    same deal_damage keyword with the ally card as the target object, which is
    what makes the ally death check at CR 1.10.2b see the damage.

    "UP TO" — the controller may take fewer, so `none` is always offered.
    """
    from engine.card_effects.ability_keywords import _ask_player, _controller_id
    from engine.effect_keywords import DamageType as _DT, deal_damage as _deal

    cid = _controller_id(card)
    if cid not in state.players or amount <= 0:
        return
    try:
        limit = max(0, int(max_targets))
    except (TypeError, ValueError):
        limit = 1

    def _allies_of(pid):
        return [c for c in state.players[pid].permanents.cards
                if "Ally" in ((getattr(c, "subtypes", None) or [])
                              + (getattr(c, "types", None) or []))]

    pool = []
    if kind in ("ANY", "ANY_TARGET"):
        for pid in (1, 2):
            hero = state.players[pid].hero
            if hero is not None:
                pool.append((f"hero:{pid}", pid, hero))
            for a in _allies_of(pid):
                pool.append((a.slug, pid, a))
    else:
        pid = (3 - cid) if ally_player in ("OPPONENT", "THEY", "THEM") else cid
        for a in _allies_of(pid):
            pool.append((a.slug, pid, a))

    for _ in range(limit):
        if not pool:
            return
        options = [label for label, _pid, _obj in pool] + ["none"]
        pick = _ask_player(state, cid, options,
                           context=f"Choose a target for {amount} arcane damage")
        if pick == "none":
            return
        entry = next((x for x in pool if x[0] == pick), pool[0])
        pool.remove(entry)
        _label, _pid, obj = entry
        _deal(state, amount, _DT.ARCANE, cid, obj, 'effect',
              damage_source_card=card)


#: The only two forms an Arakni hero can take. Anything else named as a
#: TRANSFORM_HERO mode is an authoring error, not a new form.
_HERO_TRANSFORM_MODES = {"random_agent_of_chaos", "return_to_brood"}


def _do_transform(state, sources, into_slug: str, player_id: int):
    """CR 8.5.36c — create the named token, then put the sources under it.

    effect_keywords.transform already implements 8.5.36b/d and takes the
    permanent as a Card, so this only has to bring that permanent into
    existence. (An earlier version of this re-implemented transform outright
    and was silently shadowed by the real one, which is exactly the failure
    mode this whole audit is about — check what exists before adding it.)
    """
    from engine.effect_keywords import create_token, transform as _ek_transform
    player = state.players.get(player_id)
    if player is None or not sources:
        return
    before = set(id(c) for c in player.permanents.cards)
    create_token(state, target_player_id=player_id, token_slug=into_slug,
                 number=1, source_player_id=player_id)
    perm = next((c for c in reversed(player.permanents.cards)
                 if c.slug == into_slug and id(c) not in before), None)
    if perm is None:
        return
    _ek_transform(state, list(sources), perm, source_player_id=player_id)


def apply_power_gain_replacements(state, amount, card=None):
    """THE choke point for "an attack would GAIN {p}".

    Flourish reads "the next time an attack would gain {p} this turn, instead it
    gains that much plus 2" — a replacement on the GAIN, which has to sit between
    deciding the amount and applying it. Power gains previously went straight
    into combat.attack_power from two places with nothing replaceable between.

    Two call sites is exactly the "hook every call site" shape that this whole
    effort keeps finding, so it is one function and a test asserts BOTH paths go
    through it. A third path added later that does not call this will silently
    escape the replacement.
    """
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return amount
    if amount <= 0:
        return amount
    pending = getattr(state, "_power_gain_replacements", None)
    if not pending:
        return amount
    for entry in list(pending):
        amount += int(entry.get("bonus", 0) or 0)
        pending.remove(entry)
        break          # one-shot: "the NEXT time"
    return amount


def compile_effect(etype: str, params: dict[str, Any]) -> Callable:
    """Return a (card, event, state)->None callable."""

    # Numeric "amount" authored as an integer-literal string ("2") crashes the
    # arithmetic/range() in many branches (draw N, deal N, discard N). Coerce a
    # pure-integer string to int once here; leave dynamic markers ("X",
    # "DEFENDING_CARD_COUNT") untouched for the branches that interpret them.
    if isinstance(params.get("amount"), str):
        try:
            params = {**params, "amount": int(params["amount"])}
        except (TypeError, ValueError):
            pass

    # ── declarative statics (read by the engine, never "resolved") ─────────
    # "You may play Rift Bind from your banished zone." A permission the engine
    # reads off the CardDef while the card sits in the zone (see
    # play._self_playable_from_banished); resolving it does nothing, so it is a
    # no-op here rather than a missing type that would fail the load.
    if etype in ("PLAYABLE_FROM_BANISHED", "DEFENSE_EQUALS", "RUNE_GATE",
                 "MATERIAL"):
        # MATERIAL (CR 3.0.14 sub-cards): "While this is under a permanent, that
        # permanent has <property>." Declarative for the same reason as the
        # others, but the reason is sharper here — the ability is CONTINUOUS and
        # conditioned on a relationship that can end. Resolving it once, at the
        # moment the sub-card went under, would grant a property that then
        # outlives the "while": banish the sub-card as a cost and the permanent
        # keeps phantasm forever.
        #
        # engine._setup_material_statics registers two derived continuous
        # effects that read these params off whatever is under a card at the
        # moment of each recalculation, so the grant cannot outlive its source.
        #   {"type":"MATERIAL","keyword":"Phantasm"}
        #   {"type":"MATERIAL","power":1}
        #   {"type":"MATERIAL","keyword":"Phantasm","except_slug":"miragai"}
        # RUNE_GATE (CR 8.3.27) is likewise declarative: play.rune_gate_available
        # reads it to offer the card from the banished zone for free when the
        # controller has Runechants >= its {r} cost.
        # DEFENSE_EQUALS likewise: a printed {d} that is an expression, read by
        # play._apply_dynamic_defense at the moment the value is consumed.
        def _fn(card, event, state):
            return None
        return _fn

    # ── life / damage ──────────────────────────────────────────────────────
    if etype == "GAIN_LIFE_PER_CARD_IN_HAND":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_gain_life, _controller_id
            cid = _controller_id(card)
            n = len(state.players[cid].hand.cards)
            if n > 0:
                effect_gain_life(state, cid, n)
        return _fn

    if etype == "LOSE_LIFE":
        amt = params.get("amount", 0)
        tgt = params.get("player", "SELF")
        def _fn(card, event, state, _a=amt, _t=tgt):
            from engine.card_effects.ability_keywords import effect_lose_life, _controller_id
            cid = _controller_id(card)
            _t = _t.upper()
            # "The WINNER loses 1{h}" — which player that is depends on how the
            # wager resolved, so it can only come from the event payload; SELF /
            # OPPONENT cannot express it.
            if _t in ("WAGER_WINNER", "WAGER_LOSER", "WINNER", "LOSER"):
                data = getattr(event, "data", None) or {}
                key = "winner" if _t in ("WAGER_WINNER", "WINNER") else "loser"
                tid = data.get(key)
                if tid is None:
                    return
            else:
                tid = _effect_player_id(state, card, _t, event)
                if tid is None:
                    return
            effect_lose_life(state, tid, _resolve_amount(_a, state, card)
                             if isinstance(_a, dict) else _a)
        return _fn

    if etype in ("DEAL_DAMAGE", "DEAL_PHYSICAL"):
        amt = params.get("amount", 0)
        tgt = params.get("target", "OPPONENT")
        def _fn(card, event, state, _a=amt, _t=tgt):
            from engine.card_effects.ability_keywords import effect_deal_damage, _controller_id
            cid = _controller_id(card)
            _t_upper = _t.upper()
            tid = (3 - cid) if _t_upper in ("OPPONENT", "DEFENDING", "DEFENDER", "ATTACKER") else cid
            effect_deal_damage(state, tid, _a, card, damage_type="physical")
        return _fn

    if etype == "DEAL_ARCANE":
        amt = params.get("amount", 0)
        tgt = params.get("target", "OPPONENT")
        # "up to 2 target ALLIES they control" / "up to any 2 targets".
        # effect_deal_arcane only ever damages a HERO, so `target: "ally"` fell
        # through to the not-the-opponent branch and singe_yellow dealt its
        # second point of arcane to ITS OWN CONTROLLER. `max_targets` was unread
        # on top of that, so it was one point, at the wrong hero.
        max_targets = _first(params, "max_targets", "targets", "up_to",
                             default=1)
        ally_player = str(_first(params, "player", "ally_controller",
                                 default="OPPONENT")).upper()

        def _fn(card, event, state, _a=amt, _t=tgt):
            from engine.card_effects.ability_keywords import effect_deal_arcane, _controller_id
            cid = _controller_id(card)
            tid = _damage_target_player(state, cid, _t)
            # "deal X arcane, where X is the number of Frostbites you control" —
            # an expression amount was passed through unresolved, and the damage
            # pipeline compares amount against an int, so it raised TypeError
            # mid-resolution rather than dealing anything.
            n = _resolve_amount(_a, state, card)
            try:
                n = max(0, int(n))
            except (TypeError, ValueError):
                n = 0
            if _t.upper() in ("ALLY", "ALLIES", "ANY", "ANY_TARGET"):
                _deal_arcane_to_objects(state, card, n, _t.upper(),
                                        max_targets, ally_player)
                return
            effect_deal_arcane(state, tid, n, card)
        return _fn

    # ── cards ──────────────────────────────────────────────────────────────
    if etype == "DRAW":
        amt = params.get("amount", 1)
        player_target = params.get("player", "SELF")
        def _fn(card, event, state, _a=amt, _pt=player_target):
            from engine.card_effects.ability_keywords import effect_draw
            tid = _effect_player_id(state, card, _pt, event)
            if tid is None:
                return
            # Draw counts are usually ints, but candidate JSON authors dynamic
            # markers ("intellect", "hand_size", "CHAIN_HIT_COUNT"). Resolve the
            # ones we can; an unknown marker draws 0 rather than crashing draw().
            n = _a
            if isinstance(n, str):
                marker = n.strip().upper()
                if marker == "INTELLECT":
                    n = getattr(state.players[tid], "intellect", 0)
                elif marker == "HAND_SIZE":
                    n = len(state.players[tid].hand.cards)
                elif marker == "CHAIN_HIT_COUNT":
                    n = len(getattr(state, "chain_links", []) or [])
                else:
                    try:
                        n = int(n)
                    except (TypeError, ValueError):
                        n = 0
            if isinstance(n, int) and n > 0:
                effect_draw(state, tid, n)
        return _fn

    if etype == "DISCARD":
        amt = params.get("amount", 1)
        player_target = params.get("player", "SELF")
        random_discard = params.get("random", False)
        # "discard a YELLOW card" / "an INSTANT card" / "a card with WATERY
        # GRAVE" — read nowhere, so every one of them discarded hand position 0
        # whether it matched or not.
        matches = _hand_card_filter(params)

        def _fn(card, event, state, _a=amt, _pt=player_target,
                _rand=random_discard, _m=matches):
            from engine.card_effects.ability_keywords import effect_discard, _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            # "discard your HAND" has no number, and was being written as
            # amount 0 — which discards nothing, so the card's whole cost
            # vanished. Spelling it out beats a magic 99: the count is however
            # many cards are actually held.
            if str(_a).upper() in ("ALL", "HAND"):
                n = len(state.players[tid].hand.cards)
            else:
                n = _resolve_amount(_a, state, card)
                try:
                    n = max(0, int(n))
                except (TypeError, ValueError):
                    n = 1
            bound = None if _m is None else (lambda c, _s=state: _m(c, _s))
            discarded = effect_discard(state, tid, n, random_discard=_rand,
                                       matches=bound)
            # "If you do, draw a card" — a filtered discard can find nothing,
            # and an empty hand discards nothing, so the payoff needs to know.
            if discarded:
                from engine.context import set_ref
                set_ref("discarded", discarded[0] if len(discarded) == 1
                        else list(discarded))
        return _fn

    if etype == "OPT":
        amt = params.get("amount", 1)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import effect_opt, _controller_id
            effect_opt(state, _controller_id(card), _a)
        return _fn

    if etype == "RELOAD":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_reload, _controller_id
            effect_reload(state, _controller_id(card))
        return _fn

    if etype == "BANISH":
        amt = params.get("amount", 1)
        # "target" is how 33 cards name WHOSE zone and WHICH zone to banish
        # from, and it was not read at all — so every one of them fell back to
        # the defaults below, TOP_DECK and SELF. That is not a weakened effect,
        # it is an inverted one: "banish the top card of THEIR deck" milled the
        # controller's OWN deck, and "banish a card from their graveyard" hit
        # the controller's deck instead. Seventeen cards were hurting the
        # player who played them.
        #
        # Explicit "player"/"from_zone" still win — they are the spelling the
        # handler already read, so cards authored against it keep their meaning.
        _t_player, _t_zone = _zone_target_spec(params.get("target"))
        from_zone = params.get("from_zone") or _t_zone or "TOP_DECK"
        player_target = params.get("player") or _t_player or "SELF"
        # "banish it face down" — hidden information, and not available to the
        # effects that reference banished cards. Dropping it banished face UP.
        face_down = bool(params.get("face_down"))
        # "banish a card with cost N or less" — an unread limit banished any
        # card at all, so a restricted effect became an unrestricted one.
        cost_limit = params.get("cost_limit", params.get("max_cost"))
        # "you MAY banish an attack action card from your hand WITH COST LESS
        # THAN ..." — the kind of card is a full DSL filter, and it is authored
        # on the target dict alongside the zone. Reusing _hand_card_filter means
        # "an Instant", "a yellow card" and a raw condition list all mean here
        # what they mean at every other filtered choice.
        _tspec = params.get("target")
        _fparams = dict(_tspec) if isinstance(_tspec, dict) else {}
        for _k in ("filter", "card_type", "card_types", "card_name", "color",
                   "keyword", "class_filter", "subtype", "subtypes"):
            if _k in params:
                _fparams[_k] = params[_k]
        card_filter = _hand_card_filter(_fparams) if _fparams else None
        # "You MAY banish" — without this the banish is compulsory, which for a
        # cost ("if you do, ...") silently forces the player to pay.
        optional = bool(_first(params, "optional", "may", "up_to",
                               default=False))
        # Where the banished card should be REMEMBERED, for the "if you do"
        # clause that follows. BANISH always sets the `banished` ref; a named
        # one survives alongside it.
        record_as = params.get("record_as")

        def _fn(card, event, state, _a=amt, _fz=from_zone, _pt=player_target,
                _fd=face_down, _cl=cost_limit, _filter=card_filter,
                _opt=optional, _rec=record_as):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import banish as _ek_banish
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            fz = _fz.upper()
            # amount may arrive as a dynamic token or a stray string; coerce to a
            # non-negative int so it can index/slice a zone (bad values -> no-op,
            # never a TypeError that aborts the game).
            _a = _resolve_amount(_a, state, card)
            try:
                _a = max(0, int(_a))
            except (TypeError, ValueError):
                _a = 0
            cap = None
            if _cl is not None:
                cap = _resolve_amount(_cl, state, card)
                try:
                    cap = int(cap)
                except (TypeError, ValueError):
                    cap = None

            def _ok(c, _cap=cap):
                if _filter is not None and not _filter(c, state):
                    return False
                if _cap is None:
                    return True
                cost = getattr(c, "raw_cost", None)
                if cost is None:
                    cost = getattr(c, "cost", None)
                try:
                    return int(cost or 0) <= _cap
                except (TypeError, ValueError):
                    return True

            _ZONES = {"TOP_DECK": "deck", "DECK": "deck", "HAND": "hand",
                      "GRAVEYARD": "graveyard", "ARSENAL": "arsenal",
                      # Soul is a real zone on Player and two cards banish from
                      # it; without it they fell through to "unknown zone" and
                      # banished nothing.
                      "SOUL": "soul"}
            zone_name = _ZONES.get(fz)
            if zone_name is None:
                return
            player = state.players[tid]
            banished = []
            if fz in ("TOP_DECK", "DECK"):
                # From the top of the deck nothing is chosen — it is whatever is
                # there — so a cost limit filters rather than prompts.
                for t in [c for c in player.deck.cards[:_a] if _ok(c)]:
                    _ek_banish(state, t, tid, origin_zone="deck", face_down=_fd)
                    banished.append(t)
            else:
                for _ in range(_a):
                    pool = [c for c in getattr(player, zone_name).cards if _ok(c)]
                    if not pool:
                        break
                    options = [c.slug for c in pool] + (["none"] if _opt else [])
                    pick = _ask_player(state, tid, options,
                                       context=f"Choose a card to banish from {zone_name}")
                    if pick == "none":
                        break
                    target = next((c for c in pool if c.slug == pick), None)
                    if target is None:
                        break
                    _ek_banish(state, target, tid, origin_zone=zone_name,
                               face_down=_fd)
                    banished.append(target)
            _record_banished(banished)
            if _rec and banished:
                from engine.context import set_ref
                set_ref(_rec, banished[0] if len(banished) == 1 else list(banished))
        return _fn

    if etype == "CHARGE":
        # CR 8.5.29. Nobody chose WHICH card: hand position 0 was charged, so a
        # player could lose the card they most wanted to keep. The one card in
        # the corpus that says "charge" says it as a COST, and that spelling
        # lives in cost_types.py where it can block legality.
        amount = params.get("amount", 1)

        def _fn(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import (
                _ask_player, _controller_id)
            from engine.effect_keywords import charge as _ek_charge
            cid = _controller_id(card)
            for _ in range(max(0, int(_a or 0))):
                hand = state.players[cid].hand.cards
                if not hand:
                    return
                if len(hand) == 1:
                    chosen = hand[0]
                else:
                    pick = _ask_player(state, cid, [c.slug for c in hand],
                                       context="Choose a card to charge to your "
                                               "hero's soul")
                    chosen = next((c for c in hand if c.slug == pick), hand[0])
                _ek_charge(state, chosen, cid, source_player_id=cid)
        return _fn

    # ── attack / combat ────────────────────────────────────────────────────
    if etype == "DOMINATE":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_dominate, _controller_id
            effect_dominate(state, _controller_id(card))
        return _fn

    if etype == "INTIMIDATE":
        # `amount` repeats it: "intimidate them that many times" (Bully Tactics),
        # "instead intimidate twice" (High Roller). It may be a dynamic
        # expression, so "that many times" resolves from what was actually paid.
        amt = params.get("amount", 1)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import effect_intimidate, _controller_id
            cid = _controller_id(card)
            try:
                times = int(_resolve_amount(_a, state, card))
            except (TypeError, ValueError):
                times = 1
            for _ in range(max(0, times)):
                effect_intimidate(state, 3 - cid)
        return _fn

    if etype in ("PAY_UP_TO", "MAY_PAY_UP_TO"):
        # "you may pay up to {r}{r}{r}. <do something> that many times."
        # The player chooses how much to pay (0 .. max, capped by what they
        # actually have), and the amount paid is stored for a LATER effect to
        # read as {"type": "PAID_AMOUNT"} — mirroring how ROLL stores
        # state._roll_result for ROLL_RESULT.
        max_amt = params.get("max", params.get("amount", 0))
        asset = (params.get("asset") or "RESOURCES").upper()
        def _fn(card, event, state, _max=max_amt, _asset=asset):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import lose, AssetType
            cid = _controller_id(card)
            player = state.players[cid]
            try:
                cap = int(_resolve_amount(_max, state, card))
            except (TypeError, ValueError):
                cap = 0
            available = player.resources if _asset == "RESOURCES" else getattr(
                player, _asset.lower(), 0)
            cap = max(0, min(cap, int(available or 0)))
            # Offered high-to-low so a default agent (which takes the first
            # option) pays the most, matching "you MAY pay up to" being an
            # upside — the same reasoning as offering `yes` before `no`.
            choice = _ask_player(state, cid, list(range(cap, -1, -1)),
                                 context=f"Pay up to {cap} {_asset.lower()}?")
            paid = int(choice) if isinstance(choice, int) else 0
            paid = max(0, min(paid, cap))
            if paid:
                lose(state, getattr(AssetType, _asset, AssetType.RESOURCES), paid,
                     source_player_id=cid, target_player_id=cid)
            state._paid_amount = paid
        return _fn

    if etype == "RETURN_TO_HAND":
        # Return a card to a hand.
        #
        # A "zone" parameter names the SOURCE to choose FROM. That was treated
        # as inert on the grounds that put_object resolves the origin from the
        # card itself -- true when the card is already known, and false when
        # the zone is the only thing that says WHICH card. patch_the_hole is
        # "Destroy this: return a card from your ARSENAL to your hand", and
        # with no ref and no target it fell through to "return THIS card",
        # bouncing the equipment it had just destroyed and leaving the arsenal
        # untouched.
        #
        # Without a target this returns THIS card, which is right for the
        # bounce-self cards and wrong for the four that name something else:
        # "return a Phoenix Flame from your graveyard to your hand" was
        # returning Inflame itself. A ref (from a preceding LOOK/SEARCH) takes
        # precedence over a target spec, since it names one specific card.
        ref = params.get("ref")
        target_fn = _compile_object_target(_object_target_spec(params.get("target")))
        to_owner = bool(params.get("to_owner"))
        from_zone = params.get("zone") or params.get("from_zone")

        def _fn(card, event, state, _r=ref, _tf=target_fn, _owner=to_owner,
                _fz=from_zone):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.context import get_ref
            from engine.effect_keywords import put_object
            cid = _controller_id(card)
            if _r:
                found = get_ref(_r)
                objects = ([] if not found
                           else (list(found) if isinstance(found, list) else [found]))
            elif _tf is not None:
                objects = _tf(card, event, state)
            elif _fz:
                zone = getattr(state.players[cid], str(_fz).lower(), None)
                pool = list(getattr(zone, "cards", None) or [])
                if not pool:
                    return
                if len(pool) == 1:
                    objects = pool
                else:
                    from engine.card_effects.ability_keywords import _ask_player
                    pick = _ask_player(state, cid, [c.slug for c in pool],
                                       context=f"Return a card from your {_fz} to hand")
                    objects = [next((c for c in pool if c.slug == pick), pool[0])]
            else:
                objects = [card]
            for obj in objects:
                # "to its OWNER's hand" — a card banished from the opponent's
                # arsenal goes back to them, not to the player who bounced it.
                dest = getattr(obj, "owner", cid) if _owner else cid
                put_object(state, target_card=obj, destination_zone="hand",
                           destination_player_id=dest, source_player_id=cid)
        return _fn

    if etype in ("PUT_HAND_CARD_BOTTOM", "PUT_HAND_CARD_TOP"):
        # Choose a card from hand and put it on the deck (no draw).
        # player:   "SELF" (default) | "OPPONENT" — whose hand is affected.
        # to:       "BOTTOM" (default) | "TOP" — where it lands. PUT_HAND_CARD_TOP
        #           is sugar for to="TOP".
        # optional: True (default) allows declining. Cards worded "they put a
        #           card…" are mandatory (e.g. Boulder Drop) and must pass false,
        #           or the affected player can simply refuse the effect.
        # amount:   how many cards to move (default 1). May be a dynamic
        #           expression — "put X cards from your hand on top of your deck,
        #           where X is ..." (Rushing River). One card is chosen at a
        #           time, so the player orders them by choice order, which is
        #           what "in any order" means.
        player_target = params.get("player", "SELF")
        to_top = (etype == "PUT_HAND_CARD_TOP"
                  or str(params.get("to", "BOTTOM")).upper() == "TOP")
        optional = params.get("optional", True)
        amount = params.get("amount", 1)
        # "position" is the natural third spelling of "to" and was not read, so
        # a card saying ON TOP OF YOUR DECK put its card on the BOTTOM — the
        # opposite end, and for a card whose point is setting up the next draw,
        # the opposite effect.
        if str(params.get("position", "")).upper() == "TOP":
            to_top = True
        def _fn(card, event, state, _pt=player_target, _top=to_top, _opt=optional,
                _a=amount):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id, DECLINE
            from engine.effect_keywords import put_object
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            where = "top" if _top else "bottom"
            try:
                count = int(_resolve_amount(_a, state, card))
            except (TypeError, ValueError):
                count = 0
            for _ in range(max(0, count)):
                if not player.hand.cards:
                    return
                options = [c.slug for c in player.hand.cards]
                if _opt:
                    options = options + [DECLINE]
                choice = _ask_player(state, tid, options,
                                     context=f"Choose a card to put on the {where} of your deck")
                if choice == DECLINE:
                    return
                target = player.hand.find(choice)
                if target is None:
                    return
                # position "top" → cards[0]; None → zone default (bottom, cards[-1])
                put_object(state, target, "deck",
                           destination_player_id=tid, source_player_id=tid,
                           position=("top" if _top else None))
                # "You MAY put a card from your hand on the bottom of your deck.
                # IF YOU DO, draw a card." The payoff has to know whether the
                # optional half happened; declining and having an empty hand
                # both mean it did not.
                from engine.context import set_ref
                set_ref("bottomed_from_hand", target)
        return _fn

    if etype in ("PUT_SELF_BOTTOM_DECK", "PUT_SELF_IN_ZONE"):
        # Move THIS card to a zone of its controller's.
        #
        # PUT_SELF_BOTTOM_DECK hard-coded "deck" and did not read `zone`, so
        # "when this hits, put it into your SOUL" put the card on the bottom of
        # the DECK instead — a card meant to fuel soul-count effects went back
        # into the deck to be drawn again. The bottom-deck spelling is kept
        # because replacement effects like Drone of Brutality use it and mean it.
        zone = _first(params, "zone", "to_zone", "destination",
                      default=("deck" if etype == "PUT_SELF_BOTTOM_DECK" else "soul"))
        zone = str(zone).lower()
        position = params.get("position")

        def _fn(card, event, state, _z=zone, _pos=position):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import put_object
            pid = _controller_id(card)
            # position=None → zone default (append = bottom, cards[-1])
            put_object(state, card, _z,
                       destination_player_id=pid, source_player_id=pid,
                       position=_pos)
        return _fn

    if etype == "SEARCH_BANISH_FACE_DOWN":
        # trap_door on-become: "you may search your deck for a card, banish it
        # face-down, then shuffle. If it's a trap, you may play it until the
        # start of your next turn." Optional (may fail to find).
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import shuffle as _shuffle, banish as _banish
            cid = _controller_id(card)
            controller = state.players[cid]
            eligible = list(controller.deck.cards)
            from engine.card_effects.ability_keywords import ask_optional, FAIL_TO_FIND
            pick = ask_optional(state, cid, [c.slug for c in eligible], sentinel=FAIL_TO_FIND,
                                context="Search your deck for a card to banish face-down (or fail to find)")
            if pick is not None:
                target = next((c for c in eligible if c.slug == pick), None)
                if target is not None:
                    _banish(state, target, cid, origin_zone="deck")
                    if target in controller.banished.cards:
                        target.is_public = False  # banished face-down
                    subtypes = [s.lower() for s in (target.subtypes or [])]
                    if "trap" in subtypes:
                        # "If it's a trap, you may play it from banished until the
                        # start of your next turn." Cleared in start_of_turn_refresh.
                        controller.playable_from_banished.append(target)
            _shuffle(state, cid)
        return _fn

    if etype == "SEARCH_DECK":
        # Search your deck for any card, put it in hand, then shuffle.
        # Player may "fail to find" (CR 8.5.19). Follows the nimby pattern.
        filter_types = params.get("filter_types", None)   # optional list of card types
        filter_slug_contains = params.get("slug_contains", None)  # optional substring
        # The search was hard-wired to "any card, into hand, exactly one". Real
        # search text almost always narrows all three — "an AURA card with cost
        # X or less, put it into the ARENA", "up to 4 traps ... into your hand"
        # — so every such card either searched for the wrong thing or invented
        # parameters that did nothing.
        subtype = params.get("subtype")
        # A nested `filter` (a condition dict or a list of them) and the plain
        # "card_type" spelling were both unread, so a search that names what it
        # is looking for matched ANY card and fetched whatever was first.
        nested_filter = params.get("filter")
        if isinstance(nested_filter, dict):
            for key in ("subtypes", "subtype", "card_type", "card_types",
                        "filter_types"):
                if nested_filter.get(key):
                    got = nested_filter[key]
                    subtype = subtype or (got[0] if isinstance(got, list) else got)
                    break
        if not subtype:
            subtype = _first(params, "card_type", "card_types")
            if isinstance(subtype, list):
                subtype = subtype[0] if subtype else None
        max_cost = params.get("max_cost")            # int or amount expression
        # "action": "BANISH" and "put_on_top"/"put_into_hand"/"put_into" are all
        # ways of naming the DESTINATION, and none were read — so every one of
        # them put the card into the hand instead of where the card said.
        destination = _first(params, "destination", "put_into", "to_zone",
                             default=None)
        if destination is None:
            action = str(params.get("action") or "").lower()
            if action in ("banish", "banished"):
                destination = "banished"
            elif params.get("put_on_top"):
                destination = "deck_top"
            elif params.get("put_into_hand"):
                destination = "hand"
            else:
                destination = "hand"
        count = params.get("amount", params.get("count", 1))
        # Restrict the pool to a set a preceding LOOK_AT stored ("look at the
        # top X+1 cards, choose up to 4 traps" searches THOSE, not the deck).
        from_ref = params.get("from_ref")

        card_class = params.get("card_class") or params.get("class")
        # "Search your deck for A PHOENIX FLAME" names one specific card, and
        # there was no way to say so -- six cards put the name in "target",
        # which is unread, so the search matched ANY card and fetched whatever
        # was on top of the eligible list. A search that names a card and
        # returns a different one is worse than a search that fails.
        want_name = _first(params, "name", "card_name", "target")
        if isinstance(want_name, dict):
            want_name = None      # a filter spec, not a name
        # "search your deck for a card with BLOOD DEBT". Authored as effect-level
        # "conditions", which the loader turns into a gate evaluated against the
        # SOURCE card -- so it asked whether Shadow of Blasmophet itself has
        # blood debt, not whether the card being searched for does.
        want_keyword = _first(params, "keyword", "with_keyword")
        # "search THEIR deck for any number of Inner Chi and banish them" —
        # whose deck is searched was not expressible at all, so a card that
        # raids the opponent's deck raided its own.
        whose = str(params.get("player") or "SELF").upper()

        def _fn(card, event, state, _ft=filter_types, _fsc=filter_slug_contains,
                _sub=subtype, _max=max_cost, _dest=destination, _n=count,
                _ref=from_ref, _cls=card_class, _name=want_name,
                _kw=want_keyword, _who=whose):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import shuffle as effect_shuffle
            cid = _controller_id(card)
            if _who in ("OPPONENT", "THEM", "DEFENDING", "DEFENDER"):
                cid = 3 - cid
            controller = state.players[cid]
            if _ref:
                from engine.context import get_ref
                pool = get_ref(_ref)
                eligible = list(pool) if isinstance(pool, list) else (
                    [pool] if pool is not None else [])
            else:
                eligible = list(controller.deck.cards)
            if _ft:
                eligible = [c for c in eligible
                            if _matches_type_or_subtype(c, _ft)]
            if _fsc:
                eligible = [c for c in eligible if _fsc in c.slug]
            if _kw:
                def _kw_norm(text):
                    return "".join(ch for ch in str(text).lower() if ch.isalnum())
                wanted_kw = _kw_norm(_kw)
                eligible = [c for c in eligible
                            if any(_kw_norm(k) == wanted_kw
                                   for k in (getattr(c, "keywords", None) or []))]
            if _name:
                def _flat(text):
                    return "".join(ch for ch in str(text).lower() if ch.isalnum())
                wanted = _flat(_name)
                eligible = [c for c in eligible
                            if wanted in (_flat(getattr(c, "name", "") or ""),
                                          _flat(getattr(c, "slug", "") or ""))]
            if _sub:
                want = str(_sub).lower()
                eligible = [c for c in eligible
                            if want in [s.lower() for s in (c.subtypes or [])]]
            if _cls:
                wc = str(_cls).lower()
                eligible = [c for c in eligible
                            if wc in [x.lower() for x in (c.classes or [])]]
            if _max is not None:
                cap = _resolve_amount(_max, state, card)
                try:
                    cap = int(cap)
                except (TypeError, ValueError):
                    cap = 0
                eligible = [c for c in eligible
                            if int(getattr(c, "cost", None) or 0) <= cap]
            try:
                limit = int(_resolve_amount(_n, state, card))
            except (TypeError, ValueError):
                limit = 1

            from engine.card_effects.ability_keywords import ask_optional, FAIL_TO_FIND
            from engine.effect_keywords import put_object
            chosen = []
            for _ in range(max(limit, 0)):
                if not eligible:
                    break
                pick = ask_optional(state, cid, [c.slug for c in eligible],
                                    sentinel=FAIL_TO_FIND,
                                    context=f"Search for a card to put into your {_dest} "
                                            "(or fail to find)")
                if pick is None:
                    break
                target = next((c for c in eligible if c.slug == pick), None)
                if target is None:
                    break
                eligible.remove(target)
                chosen.append(target)

            # "Search your deck for an arrow card, reveal it, THEN SHUFFLE your
            # deck AND put it on top." The shuffle comes BEFORE the placement,
            # and it was running after — so a card placed on top was immediately
            # randomised back into the deck. The old order made the whole effect
            # a no-op that could pass a test by luck, since a shuffle sometimes
            # leaves the card where it was.
            effect_shuffle(state, cid)

            for target in chosen:
                # Assign ownership before the move so put_object resolves dest correctly.
                target.owner = cid
                target.controller = cid
                # "deck_top" / "top_deck" is not a ZONE — put_object looks the
                # destination up by name on the Player and finds nothing, so
                # every "search your deck ... and put it ON TOP" left the card
                # wherever the shuffle had put it. It is the deck with a
                # position.
                _zone, _pos = _dest, None
                if str(_dest).lower() in ("deck_top", "top_deck", "top"):
                    _zone, _pos = "deck", "top"
                # is_public=True: searched cards are revealed when they move.
                put_object(state, target, _zone,
                           destination_player_id=cid, source_player_id=cid,
                           is_public=True, position=_pos)
        return _fn

    if etype == "SEARCH_GRAVEYARD":
        # Search your graveyard for a matching card and put it into hand (CR
        # 8.5.19 "fail to find" allowed). Unlike SEARCH_DECK the graveyard is a
        # public, ordered zone, so there is no shuffle afterward. Filters:
        #   slug_contains / name_contains — substring match (case-insensitive);
        #   filter_types — any of these card types.
        _raw_ft = _first(params, "filter_types", "card_types", "card_type",
                         "types", "type", "subtypes", "subtype")
        filter_types = ([_raw_ft] if isinstance(_raw_ft, str)
                        else list(_raw_ft) if _raw_ft else None)
        slug_contains = params.get("slug_contains", None)
        name_contains = params.get("name_contains", None)
        # WHERE the card goes. "put it into hand" is the common case and stays
        # the default, but two cards say something else and had no way to say
        # it: "shuffle an instant card from your graveyard into your DECK" and
        # "return an ally from your graveyard to the ARENA". Shuffling follows
        # from the deck destination unless a card overrides it.
        destination = str(_first(params, "destination", "to_zone", "to",
                                 default="hand")).lower()
        shuffle = params.get("shuffle")
        if shuffle is None:
            shuffle = destination in ("deck", "deck_bottom", "deck_top")

        def _fn(card, event, state, _ft=filter_types, _sc=slug_contains,
                _nc=name_contains, _dest=destination, _shuf=shuffle):
            from engine.card_effects.ability_keywords import (
                _controller_id, ask_optional, FAIL_TO_FIND)
            from engine.effect_keywords import put_object
            cid = _controller_id(card)
            controller = state.players[cid]
            eligible = list(controller.graveyard.cards)
            if _ft:
                eligible = [c for c in eligible
                            if _matches_type_or_subtype(c, _ft)]
            if _sc:
                eligible = [c for c in eligible if _sc.lower() in c.slug.lower()]
            if _nc:
                eligible = [c for c in eligible
                            if _nc.lower() in (getattr(c, "name", "") or "").lower()]
            if not eligible:
                return
            pick = ask_optional(state, cid, [c.slug for c in eligible], sentinel=FAIL_TO_FIND,
                                context="Search your graveyard for a card and put it into hand (or fail to find)")
            if pick is None:
                return
            target = next((c for c in eligible if c.slug == pick), None)
            if target is not None:
                target.owner = cid
                target.controller = cid
                _zone = {"arena": "permanents", "deck_top": "deck",
                         "deck_bottom": "deck"}.get(_dest, _dest)
                put_object(state, target, _zone,
                           destination_player_id=cid, source_player_id=cid,
                           is_public=True)
                if _shuf:
                    from engine.effect_keywords import shuffle as _ek_shuffle
                    _ek_shuffle(state, cid)
        return _fn

    if etype == "AMP":
        amt = params.get("amount", 1)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import effect_amp, _controller_id
            effect_amp(state, _controller_id(card), _a)
        return _fn

    if etype == "MARK":
        # CR 9.3 — marking always lands on an OPPOSING hero, which is why the
        # nine cards saying "mark target opposing hero" need no target at all.
        # "Mark target ARAKNI" is the exception: it names WHICH hero, and with
        # the target unread it marked whoever was opposite regardless.
        want_hero = params.get("hero") or params.get("hero_name")
        raw_target = params.get("target")
        if want_hero is None and isinstance(raw_target, str):
            cleaned = raw_target.lower().replace("target", "").strip()
            if cleaned and cleaned not in ("opponent", "opposing", "them",
                                           "opposing hero", "hero", "self"):
                want_hero = cleaned

        def _fn(card, event, state, _h=want_hero):
            from engine.card_effects.ability_keywords import effect_mark, _controller_id
            cid = _controller_id(card)
            target_id = 3 - cid
            if _h:
                hero = state.players[target_id].hero if target_id in state.players else None
                name = (getattr(hero, "name", "") or "") + " " + (getattr(hero, "slug", "") or "")
                if _h.lower() not in name.lower():
                    return
            effect_mark(state, target_id)
        return _fn

    if etype == "REVEAL_HAND_MARK_IF_TYPE":
        # "Target opposing hero reveals their hand. If a card of <card_type> is
        # revealed this way, mark them." Revealing sets the cards public; the
        # mark lands only when the named type is present.
        want_type = params.get("card_type", "AttackReaction")
        def _fn(card, event, state, _t=want_type):
            from engine.card_effects.ability_keywords import effect_mark, _controller_id
            cid = _controller_id(card)
            opp = state.players[3 - cid]
            for c in opp.hand.cards:
                c.is_public = True
            if any(_t in (getattr(c, "types", None) or []) for c in opp.hand.cards):
                effect_mark(state, 3 - cid)
        return _fn

    # ── tokens / permanents ────────────────────────────────────────────────
    if etype == "CREATE_TOKEN":
        # The token to create: authored under "token" (a slug), "token_name", or
        # "token_type" (a display name like "Seismic Surge"). Only "token" was
        # read, so cards using the name keys created an empty token; create_token
        # slugifies a display name, so pass whichever was given.
        token = _first(params, "token", "token_name", "token_type",
                       "token_slug", "subtype", default="")
        # "count" is the documented key, but "amount" is the natural one and is
        # what every other numeric effect uses — accept both, or "create X
        # tokens" silently creates one.
        count = params.get("count", params.get("amount", 1))
        # Whose control the token enters. Cards author it under "player" OR
        # "controller" (~13 usages used the latter, which was unread -> the token
        # wrongly defaulted to SELF). Opponent-side values: opponent/defending/
        # defender/target_hero (the hit hero).
        player_target = params.get("player") or params.get("controller") or "SELF"
        # e.g. "weapon_slot" to equip. "zone" is the other natural spelling
        # (5 nodes author it, meaning BANISHED or HAND), and it was unread — so
        # those tokens entered the default zone instead.
        destination = _first(params, "destination", "zone", "to_zone")
        # "create a Steam Counter token with 2 steam counters on it" — the
        # counters were dropped, so the token arrived bare and any ability
        # reading them saw none.
        counters = params.get("counters")
        def _fn(card, event, state, _tok=token, _cnt=count, _pt=player_target,
                _dest=destination, _counters=counters):
            from engine.effect_keywords import create_token as _ek_create_token
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in (
                "OPPONENT", "DEFENDING", "DEFENDER", "TARGET_HERO") else cid
            # count may be a dynamic expression: the bespoke string form
            # ("DEFENDING_CARD_COUNT"), or any amount expression dict such as
            # {"type": "PAID_AMOUNT"} for "create that many Might tokens".
            # Dict amounts were not resolved here at all, so they fell through
            # as a dict and compared <= 0, creating nothing.
            if isinstance(_cnt, str):
                n = 0
                if _cnt.upper() == "DEFENDING_CARD_COUNT" and state.combat is not None:
                    n = len(getattr(state.combat, "defending_cards", []) or [])
                _cnt = n
            elif isinstance(_cnt, dict):
                _cnt = _resolve_amount(_cnt, state, card)
            try:
                _cnt = int(_cnt)
            except (TypeError, ValueError):
                return
            if _cnt <= 0:
                return
            _ek_create_token(state, tid, _tok, _cnt, destination=_dest)
            if _counters:
                # Cards author this as {"steam": 2} or [{"type":"steam","amount":2}].
                pairs = []
                if isinstance(_counters, dict):
                    pairs = list(_counters.items())
                elif isinstance(_counters, list):
                    pairs = [(c.get("type") or c.get("counter"), c.get("amount", 1))
                             for c in _counters if isinstance(c, dict)]
                if pairs:
                    from engine.card_effects.ability_keywords import effect_put_counter
                    made = [c for c in state.players[tid].permanents.cards
                            if c.slug == _tok][-_cnt:]
                    for made_token in made:
                        for kind, qty in pairs:
                            if not kind:
                                continue
                            try:
                                qty = int(qty)
                            except (TypeError, ValueError):
                                qty = 1
                            effect_put_counter(state, made_token, str(kind), qty)
        return _fn

    if etype in ("PUT_COUNTER", "REMOVE_COUNTER"):
        # Cards author the counter kind under EITHER "counter_type" or "counter";
        # only "counter_type" was read, so ~47 usages put an empty-typed counter.
        ctype = params.get("counter_type") or params.get("counter") or ""
        amt = params.get("amount", 1)
        adding = etype == "PUT_COUNTER"
        # "target" was not read at all, so the counter always landed on the
        # SOURCE card. On the twelve cards that name another object that is not
        # a weakened effect: "put a -1{d} counter on an equipment they control"
        # put it on the attacking card instead. A target naming the source
        # ("self") is what already happened and stays a no-op here.
        target_fn = _compile_object_target(_object_target_spec(params.get("target")))

        def _fn(card, event, state, _ct=ctype, _a=amt, _tf=target_fn, _add=adding):
            from engine.card_effects.ability_keywords import (
                effect_put_counter, effect_remove_counter)
            targets = _tf(card, event, state) if _tf is not None else [card]
            n = _resolve_amount(_a, state, card)
            try:
                n = max(0, int(n))
            except (TypeError, ValueError):
                n = 1
            from engine.card_effects.ability_keywords import (
                DEFENSE_COUNTER_KINDS, _apply_defense_counter)
            for obj in targets:
                if _add:
                    if _ct in DEFENSE_COUNTER_KINDS:
                        # A -1{d} counter has to go on through the keyword path,
                        # or it is pure bookkeeping: effect_put_counter records
                        # the counter and nothing reduces the card's {d}, so
                        # every card that authored one had no effect at all.
                        _apply_defense_counter(state=state, card=obj, count=n)
                        continue
                    for _ in range(n):
                        effect_put_counter(state, obj, _ct)
                else:
                    effect_remove_counter(state, obj, _ct, n)
            # "put a counter on X. Then if IT ...": the follow-up needs to know
            # which object was counted. Without a ref the only thing a later
            # effect could test was the source card.
            if targets:
                from engine.context import set_ref
                set_ref("countered", targets[0] if len(targets) == 1 else list(targets))
        return _fn

    if etype == "WARD":
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import ward
            ward(state, card, _a)
        return _fn

    if etype == "ARCANE_BARRIER":
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import arcane_barrier
            arcane_barrier(state, card, _a)
        return _fn

    # ── flags / misc ───────────────────────────────────────────────────────
    if etype == "SET_FLAG":
        flag = params.get("flag", "")
        # "duration" is the natural spelling of "scope" and was unread.
        scope = str(_first(params, "scope", "duration", default="CURRENT")).upper()
        player_target = params.get("player", "SELF")
        # {"value": false} means CLEAR the flag, and it was not read — so eight
        # nodes that meant "this is no longer true" were SETTING it, the exact
        # opposite. An unread boolean is worse than an unread filter: it does
        # not weaken the effect, it inverts it.
        value = params.get("value", True)
        clear = value is False

        def _fn(card, event, state, _f=flag, _s=scope, _pt=player_target,
                _clear=clear):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            target = (player.next_turn_effects
                      if _s == "NEXT" and hasattr(player, "next_turn_effects")
                      else player.current_turn_effects)
            if _clear:
                while _f in target:
                    target.remove(_f)
                return
            target.append(_f)
        return _fn

    if etype == "INJECT_TRIGGER":
        # Compile inner effects/conditions at load time, create one-shot TriggerDef at runtime.
        # The inner trigger may be given as a nested dict — {"trigger_type": ...,
        # "conditions": [...], "effects": [...]} — which is REQUIRED when it has inner
        # conditions: the loader pops a top-level "conditions" key and treats it as an
        # effect-level gate (evaluated at registration, when there may be no attack),
        # but a nested dict's "conditions" survive and are evaluated per-hit as intended.
        trig_spec = params.get("trigger", "ON_HIT")
        if isinstance(trig_spec, dict):
            inner_trigger = (trig_spec.get("trigger_type")
                             or trig_spec.get("trigger") or "ON_HIT")
            inner_conditions_raw = trig_spec.get("conditions", [])
            inner_effects_raw = trig_spec.get("effects", [])
        else:
            inner_trigger = trig_spec
            inner_conditions_raw = params.get("conditions", [])
            inner_effects_raw = params.get("effects", [])
        # scope: COMBAT (default) = fire once, on the current attack ("this attack
        # gains: if it hits ..."). TURN / NEXT_TURN = persistent turn-scoped hook that
        # re-injects onto EVERY attack this turn ("whenever an attack hits a hero this
        # turn ..."); NEXT_TURN activates at the target player's next turn start.
        # player: SELF (default) / OPPONENT — which player's turn the hook lives on.
        scope = (params.get("scope") or "COMBAT").upper()
        player_target = (params.get("player") or "SELF").upper()

        inner_cond_specs = [(ic.get("type", "none"), ic) for ic in inner_conditions_raw]
        inner_eff_specs = [(ie.get("type", "").upper(), ie) for ie in inner_effects_raw]

        def _inject_fn(card, event, state,
                       _trig=inner_trigger,
                       _icond_specs=inner_cond_specs,
                       _ieff_specs=inner_eff_specs,
                       _scope=scope, _pt=player_target,
                       _conds_raw=inner_conditions_raw,
                       _effs_raw=inner_effects_raw):
            from engine.card_effects.triggers import TriggerDef

            _src_slug = getattr(card, "slug", "?")

            def _make_one_shot():
                # Compile inner conditions/effects now, not at module load: it avoids a
                # circular import, and defers any unimplemented inner condition/effect
                # type to when the trigger actually fires (so an unrelated card with an
                # unknown INNER type still loads, matching the inner-effect deferral).
                from engine.card_effects.dsl.condition_types import compile_condition as _cc
                compiled_conds = [_cc(ct, cp) for ct, cp in _icond_specs]
                compiled_effs = [(et, compile_effect(et, ep)) for et, ep in _ieff_specs]

                def _one_shot(c, ev, st, _iconds=compiled_conds, _ieffs=compiled_effs,
                              _src=_src_slug):
                    for cond_fn in _iconds:
                        if cond_fn is not None and not cond_fn(c, ev, st):
                            return
                    for et, eff_fn in _ieffs:
                        eff_fn(c, ev, st)
                        _track_injected_effect(_src, et)
                return _one_shot

            if _scope in ("TURN", "NEXT_TURN", "CHAIN"):
                # Persistent scoped hook: a plain-dict spec that
                # engine._apply_turn_attack_effects re-injects into every attack for
                # the duration. Raw (uncompiled) so snapshot_state stays serializable.
                #   TURN      -> Player.turn_attack_hooks   (cleared end of turn)
                #   NEXT_TURN -> Player.next_turn_attack_hooks (activates next turn)
                #   CHAIN     -> Player.chain_attack_hooks   (cleared at chain close)
                from engine.card_effects.ability_keywords import _controller_id
                cid = _controller_id(card)
                tid = (3 - cid) if _pt in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
                tgt = state.players[tid]
                hook = {"kind": "inject_trigger", "event": _trig,
                        "conditions": _conds_raw, "effects": _effs_raw,
                        "source_slug": _src_slug}
                if _scope == "NEXT_TURN":
                    tgt.next_turn_attack_hooks.append(hook)
                else:
                    (tgt.chain_attack_hooks if _scope == "CHAIN"
                     else tgt.turn_attack_hooks).append(hook)
                    # Cover the current attack too (the source card's own hit): its
                    # _apply_turn_attack_effects already ran before this ON_PLAY, so
                    # inject directly for it.
                    if state.combat is not None and tid == state.active_player:
                        td = TriggerDef(event_type=_trig, condition_fn=None,
                                        effect_fn=_make_one_shot(), is_optional=False)
                        if not hasattr(state.combat, 'injected_triggers'):
                            state.combat.injected_triggers = []
                        state.combat.injected_triggers.append(td)
                return

            # Default COMBAT scope: one-shot into the current combat.
            if not state.combat:
                return
            td = TriggerDef(event_type=_trig, condition_fn=None,
                            effect_fn=_make_one_shot(), is_optional=False)
            if not hasattr(state.combat, 'injected_triggers'):
                state.combat.injected_triggers = []
            state.combat.injected_triggers.append(td)
        return _inject_fn

    if etype == "MODIFY_ATTACKS_THIS_TURN":
        # Persistent turn-scoped attack-power modifier ("until start of your next
        # turn, attacks that target you have -1{p}"; "your attacks this turn get
        # +N"). Applies to every attack for the duration that matches `conditions`.
        # scope: TURN (default) / NEXT_TURN. player: SELF (default) / OPPONENT.
        amount = params.get("amount", 0)
        mod = (params.get("mod") or "add").lower()
        signed = -abs(amount) if mod in ("subtract", "sub", "minus") else amount
        scope = (params.get("scope") or "TURN").upper()
        player_target = (params.get("player") or "SELF").upper()
        # Per-attack filter for WHICH attacks the modifier applies to. Uses "filter"
        # (not "conditions") because the loader pops "conditions" and would evaluate
        # it once at registration; this filter must run per attack.
        conds_raw = params.get("filter", [])

        def _fn(card, event, state, _amt=signed, _scope=scope,
                _pt=player_target, _conds=conds_raw):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            tgt = state.players[tid]
            hook = {"kind": "power_mod", "amount": _amt, "conditions": _conds}
            if _scope == "NEXT_TURN":
                tgt.next_turn_attack_hooks.append(hook)
            else:
                tgt.turn_attack_hooks.append(hook)
        return _fn

    if etype == "REVEAL_TOP_DECK":
        # Reveal top N cards; gain gain_life{h} per card with cost >= cost_gte.
        amount = params.get("amount", 1)
        gain_life = params.get("gain_life", 0)
        cost_gte = params.get("cost_gte", None)
        # "Reveal the top 4 cards ... X is the number of cards with 6 or more
        # {p} revealed this way" — the gain_life/cost_gte pair above is one
        # hard-wired question about the revealed cards. `into` stores them so a
        # later effect in the same ability can ask any other question (see
        # COUNT_REF), instead of each new wording needing its own parameter.
        into = params.get("into")

        def _fn(card, event, state, _a=amount, _gl=gain_life, _cg=cost_gte, _into=into):
            from engine.card_effects.ability_keywords import effect_gain_life, _controller_id
            pid = _controller_id(card)
            revealed = state.players[pid].deck.cards[:_a]
            for c in revealed:
                c.is_public = True
            if _into:
                from engine.context import set_ref
                set_ref(_into, list(revealed))
                set_ref(_into + "_owner", pid)
            if _gl and _cg is not None:
                matching = sum(1 for c in revealed
                               if (getattr(c, 'cost', None) or 0) >= _cg)
                if matching:
                    effect_gain_life(state, pid, _gl * matching)
        return _fn

    if etype in ("PUT_INTO_ARSENAL", "PUT_ARSENAL"):
        # Deck (or a ref) INTO the arsenal — the opposite direction to
        # PUT_ARSENAL_BOTTOM, which is what four cards reached for because it
        # was the only arsenal effect that existed. It moves a card OUT of the
        # arsenal and defaults to the OPPONENT's, so "put it face up into YOUR
        # arsenal" was milling the opponent's arsenal instead.
        #
        #   {"type":"PUT_INTO_ARSENAL","from":"DECK_TOP","face_up":true}
        #   {"type":"PUT_INTO_ARSENAL","ref":"revealed","counter":"aim"}
        #
        # The arsenal holds one card and Zone.add drops the overflow, so putting
        # a card into an occupied arsenal is a silent no-op rather than a
        # replacement — which is why this reports what it moved under the ref
        # "arsenaled" for an "if you do" to test.
        ref = params.get("ref")
        source_zone = str(_first(params, "from", "from_zone", "source",
                                 default="DECK_TOP")).upper()
        face_up = params.get("face_up", True)
        counter = _first(params, "counter", "counter_type", "add_counter")
        who = str(params.get("player", "SELF")).upper()

        def _fn(card, event, state, _r=ref, _sz=source_zone, _up=face_up,
                _ct=counter, _w=who):
            from engine.card_effects.ability_keywords import (
                _controller_id, effect_put_counter)
            from engine.context import get_ref, set_ref
            from engine.effect_keywords import put_object
            cid = _controller_id(card)
            pid = (3 - cid) if _w in ("OPPONENT", "THEM") else cid
            player = state.players.get(pid)
            if player is None:
                return
            if _r:
                found = get_ref(_r)
                if found is None:
                    return
                pool = list(found) if isinstance(found, list) else [found]
            elif _sz in ("DECK_TOP", "TOP_OF_DECK", "DECK"):
                pool = player.deck.cards[:1]
            elif _sz == "HAND":
                # "Put a card FROM HAND face down into your arsenal" — the
                # player chooses which, unlike the deck-top form where the card
                # is determined. Optional callers wrap this in a MAY.
                pool = list(player.hand.cards)
                if len(pool) > 1:
                    from engine.card_effects.ability_keywords import _ask_player
                    pick = _ask_player(state, pid, [c.slug for c in pool],
                                       context="Choose a card to put into your arsenal")
                    pool = [next((c for c in pool if c.slug == pick), pool[0])]
            else:
                return
            if not pool:
                return
            moved = pool[0]
            put_object(state, moved, "arsenal", destination_player_id=pid,
                       source_player_id=pid)
            if moved not in player.arsenal.cards:
                # The arsenal was full; nothing moved, so nothing is reported.
                return
            moved.is_public = bool(_up)
            if hasattr(moved, "face_down"):
                moved.face_down = not bool(_up)
            if _ct:
                effect_put_counter(state, moved, str(_ct))
            set_ref("arsenaled", moved)
        return _fn

    if etype == "PUT_ARSENAL_BOTTOM":
        # Put the target player's arsenal card on the bottom of their deck.
        #
        # The default is OPPONENT because the three Disable printings — "put a
        # card from THEIR arsenal on the bottom of THEIR deck" — were the first
        # users. That makes silence mean "the opponent", so a card that says
        # "YOUR arsenal" and omits the key hits the wrong player: that is what
        # sunkwater_exoshell did, bottoming the opponent's card and then failing
        # its own "if you do".
        player_target = params.get("player", "OPPONENT")
        # A "card_type" filter restricts WHICH arsenal card is bottomed; it was
        # unread, so those nodes bottomed whatever happened to be there.
        want_type = _first(params, "card_type", "card_types", "filter_types")
        # "put a FACE-UP card from your arsenal on the bottom" — arsenal cards
        # are face down by default, so this is a real restriction and not
        # decoration. Unread, it bottomed a face-down card the text excludes.
        want_face_up = params.get("face_up")

        def _fn(card, event, state, _pt=player_target, _wt=want_type,
                _fu=want_face_up):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import put_object
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            arsenal = getattr(player, 'arsenal', None)
            if arsenal is None or not getattr(arsenal, 'cards', None):
                return
            pool = list(arsenal.cards)
            if _wt:
                wants = {str(t).lower() for t in
                         ([_wt] if isinstance(_wt, str) else _wt)}
                pool = [c for c in pool
                        if wants & {t.lower() for t in
                                    (getattr(c, "types", None) or [])
                                    + (getattr(c, "subtypes", None) or [])}]
            if _fu is not None:
                pool = [c for c in pool
                        if bool(getattr(c, "is_public", False)) is bool(_fu)]
            if pool:
                card_to_move = pool[0]
                # position=None → zone default (append = bottom, cards[-1])
                put_object(state, card_to_move, "deck",
                           destination_player_id=tid, source_player_id=tid,
                           position=None)
                # "IF YOU DO, draw a card" has to test whether a card actually
                # moved, not whether the arsenal was non-empty — the filters
                # above mean those are different questions, and the card that
                # asks it ("put a FACE-UP card ...") is exactly the one where
                # they differ.
                from engine.context import set_ref
                set_ref("bottomed", card_to_move)
        return _fn

    if etype == "DESTROY_DEFENDING":
        # "Destroy all cards defending this." The defenders are combat state —
        # not a zone and not the arena — so no object-target spec can name them.
        # Authored as DESTROY_TOKEN with target "defending", which destroyed a
        # token of the empty slug: nothing, on the wrong side.
        def _fn(card, event, state):
            from engine.effect_keywords import destroy as _ek_destroy
            combat = state.combat
            if combat is None:
                return
            for obj in list(getattr(combat, "defending_cards", None) or []):
                # The defending HERO is not a card that can be destroyed.
                if getattr(obj, "is_hero", False):
                    continue
                _ek_destroy(state, obj, card)
        return _fn

    if etype == "DESTROY_MATCHING":
        # "Destroy all equipment THEY control with -1{d} counters", "destroy all
        # cards in their arsenal", "destroy a defense reaction card in their
        # arsenal". These were authored as DESTROY_TOKEN, which is hard-wired to
        # the CONTROLLER's permanents and matches a token by slug — so they
        # destroyed the wrong player's things, or (naming no slug at all)
        # nothing.
        #
        # DESTROY_PERMANENT covers "destroy a <subtype> you control" and is
        # right for the three that are exactly that. This is for the rest: a
        # zone other than the arena, or a filter richer than a subtype.
        target_fn = _compile_object_target(_object_target_spec(params.get("target")))

        def _fn(card, event, state, _tf=target_fn):
            from engine.effect_keywords import destroy as _ek_destroy
            if _tf is None:
                return
            for obj in _tf(card, event, state):
                _ek_destroy(state, obj, card)
        return _fn

    if etype == "DESTROY_TOKEN":
        # Destroy one token of the given slug the ability's controller controls.
        # "token_type" (6 nodes) was not read, so those destroyed a token with
        # the empty slug — i.e. nothing. It also holds the printed NAME
        # ("Seismic Surge") where "token" holds the slug ("seismic_surge"), so
        # matching normalises both rather than comparing slugs only.
        token_slug = _first(params, "token", "token_type", "token_slug",
                            "token_name", default="")
        # "Destroy UP TO 3 Might tokens. Create a Toughness token FOR EACH TOKEN
        # DESTROYED THIS WAY." Both halves were wrong in the same direction:
        # this destroyed exactly ONE (max_destroy was unread) while the create
        # side made three unconditionally. Strictly better than printed.
        limit = _first(params, "max_destroy", "amount", "count", default=1)
        # "destroy a Seismic Surge token THEY control". The pool was hard-wired
        # to the ability's controller, so a card naming the opponent's tokens
        # destroyed its own -- and destroyed nothing at all when it had none,
        # which reads exactly like a token that was not there. DESTROY_PERMANENT
        # already spells this `player`; the two are now the same word.
        whose = str(params.get("player") or params.get("controller")
                    or "SELF").upper()

        def _fn(card, event, state, _slug=token_slug, _n=limit, _w=whose):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import destroy as _ek_destroy
            if not _slug:
                return
            want = _norm_amt(_slug)
            pid = _controller_id(card)
            if _w in ("OPPONENT", "DEFENDING", "DEFENDER", "THEM", "THEY"):
                pid = 3 - pid
            if pid not in state.players:
                return
            player = state.players[pid]
            try:
                n = max(0, int(_resolve_amount(_n, state, card)))
            except (TypeError, ValueError):
                n = 1
            destroyed = []
            for _ in range(n):
                tok = next((c for c in player.permanents.cards
                            if _norm_amt(getattr(c, "slug", "")) == want
                            or _norm_amt(getattr(c, "name", "")) == want), None)
                if tok is None:
                    break
                _ek_destroy(state, tok, None)
                destroyed.append(tok)
            # "for each token destroyed this way" needs the count, and "up to"
            # means it can be fewer than asked for.
            from engine.context import set_ref
            set_ref("destroyed", list(destroyed))
            set_ref("destroyed_count", len(destroyed))
        return _fn

    if etype in ("DESTROY_PERMANENT", "DESTROY_SELF"):
        target = params.get("target", "self")
        subtype = params.get("subtype")  # "destroy a <subtype> you control" (e.g. Aura)
        # "destroy an aura permanent with cost X or less", "destroy up to X aura
        # TOKENS", "destroy an aura THEY control". Every one of these was
        # unreachable: the pool was hard-wired to the controller's own
        # permanents, with no cost filter, no token filter and no count — so a
        # card naming any of them either destroyed the wrong thing or nothing.
        whose = (params.get("player") or ("SELF" if target == "self" else "SELF")).upper()
        max_cost = params.get("max_cost")   # int or an amount expression
        want_token = params.get("token")    # True: tokens only; False: non-tokens only
        count = params.get("amount", params.get("count", 1))
        # "Destroy UP TO X items" — "max" is the third spelling of up_to and was
        # unread, so the card destroyed exactly X with no option to stop.
        optional = bool(params.get("optional") or params.get("up_to")
                        or params.get("max"))
        # One vocabulary shared with the cost of the same name; see
        # _permanent_filter for why neither of them could say "a Gold".
        matches = _permanent_filter(params)

        def _fn(card, event, state, _t=target, _sub=subtype, _whose=whose,
                _max=max_cost, _tok=want_token, _n=count, _opt=optional,
                _m=matches):
            from engine.effect_keywords import destroy as _ek_destroy
            if (_t == "self" and not _sub and _max is None and _tok is None
                    and _m is None):
                # destroy() resolves the card's actual zone itself.
                _ek_destroy(state, card, None)
                return
            # Subtype target: destroy a chosen permanent of that subtype (by
            # default one the controller controls). No match -> destroy nothing
            # (a following "if you do" clause should be gated by the
            # CONTROLS_SUBTYPE condition or a MAY so it, too, falls out when
            # there is no legal target).
            from engine.card_effects.ability_keywords import _controller_id, _ask_player
            cid = _controller_id(card)
            if cid not in state.players:
                return
            if _whose in ("OPPONENT", "DEFENDING", "DEFENDER"):
                pids = [3 - cid]
            elif _whose in ("ANY", "ALL", "EACH"):
                pids = [cid, 3 - cid]
            else:
                pids = [cid]
            limit = _resolve_amount(_n, state, card)
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                limit = 1
            cap = None
            if _max is not None:
                cap = _resolve_amount(_max, state, card)
                try:
                    cap = int(cap)
                except (TypeError, ValueError):
                    cap = 0
            want = (_sub or "").lower()

            def _eligible(c):
                if _m is not None and not _m(c, state):
                    return False
                if want and want not in [s.lower() for s in (getattr(c, "subtypes", None) or [])]:
                    return False
                if _tok is not None and bool(getattr(c, "is_token", False)) is not bool(_tok):
                    return False
                if cap is not None:
                    # A token has no printed cost; "cost X or less" is satisfied
                    # by a costless permanent, so None reads as 0 rather than
                    # excluding it.
                    c_cost = getattr(c, "raw_cost", None)
                    if c_cost is None:
                        c_cost = getattr(c, "cost", None)
                    try:
                        c_cost = int(c_cost)
                    except (TypeError, ValueError):
                        c_cost = 0
                    if c_cost > cap:
                        return False
                return True

            destroyed = []
            for _ in range(max(limit, 0)):
                cands = [c for pid in pids
                         for c in state.players[pid].permanents.cards
                         if _eligible(c)]
                if not cands:
                    break
                if len(cands) == 1 and not _opt:
                    chosen = cands[0]
                else:
                    options = [c.slug for c in cands] + (["none"] if _opt else [])
                    pick = _ask_player(state, cid, options,
                                       context=f"Choose a {_sub or 'permanent'} to destroy")
                    if pick == "none":
                        break
                    chosen = next((c for c in cands if c.slug == pick), cands[0])
                _ek_destroy(state, chosen, card)
                destroyed.append(chosen)
            if destroyed:
                from engine.context import set_ref
                set_ref("destroyed", list(destroyed))
        return _fn

    if etype == "MODIFY_DEFENSE_VALUE":
        amt = params.get("amount", 0)
        # "mod" was not read at all, so every node ADDED. 27 of the 34 that
        # author it say "add" and were unaffected, but 6 say "subtract" and one
        # says "set" — those 7 moved defence the wrong way, which is worse than
        # doing nothing: a card meant to REDUCE the defending total was
        # increasing it.
        mod = (params.get("mod") or "add").lower()

        # "UP TO ONE TARGET DEFENDING ACTION CARD gets +3{d}" is not the same
        # effect as "the defending total gets +3", and every node here was the
        # latter. With one defender the numbers agree; they part company exactly
        # where the card is restrictive — a +3 meant for a defending ACTION card
        # was applied to a block made entirely of equipment, which has no legal
        # target at all.
        #
        #   "target": {"zone": "DEFENDING", "amount": 1, "filter": [...]}
        #
        # The DEFENDING pool is the declared defenders, so it is written here
        # rather than through _object_zone_cards (which is per-player zones and
        # has no notion of a combat).
        raw_target = params.get("target")
        target_spec = raw_target if isinstance(raw_target, dict) else None
        from engine.card_effects.dsl.condition_types import compile_condition as _cc
        target_filters = [_cc((f.get("type") or "none"), f)
                          for f in ((target_spec or {}).get("filter") or [])
                          if isinstance(f, dict)]
        target_limit = (target_spec or {}).get("amount", 1)

        if target_spec is not None:
            def _fn_target(card, event, state, _a=amt, _m=mod,
                           _f=target_filters, _lim=target_limit):
                from engine.card_effects.ability_keywords import (
                    _ask_player, _controller_id)
                combat = state.combat
                if not combat:
                    return
                delta = _resolve_amount(_a, state, card)
                try:
                    delta = int(delta)
                except (TypeError, ValueError):
                    return
                pool = list(getattr(combat, "defending_cards", None) or [])
                for fn in _f:
                    if fn is not None:
                        pool = [c for c in pool if fn(c, event, state)]
                if not pool:
                    # "UP TO one target" with no legal target does nothing. The
                    # untargeted version raised the total anyway.
                    return
                if str(_lim).upper() in ("ALL", "EACH"):
                    chosen = pool
                else:
                    try:
                        count = max(0, int(_resolve_amount(_lim, state, card)))
                    except (TypeError, ValueError):
                        count = 1
                    chosen, remaining = [], list(pool)
                    cid = _controller_id(card)
                    for _ in range(min(count, len(remaining))):
                        pick = _ask_player(state, cid,
                                           [c.slug for c in remaining],
                                           context="Choose a defending card")
                        obj = next((c for c in remaining if c.slug == pick),
                                   remaining[0])
                        chosen.append(obj)
                        remaining.remove(obj)
                for obj in chosen:
                    if _m in ("set", "="):
                        obj.defense = delta
                    elif _m in ("subtract", "sub", "minus", "-"):
                        obj.defense = max(0, (obj.defense or 0) - delta)
                    else:
                        obj.defense = (obj.defense or 0) + delta
                combat.total_defense = sum((c.defense or 0)
                                           for c in combat.defending_cards)
            return _fn_target

        # Writing total_defense directly did not survive: _resolve_damage
        # recomputes it as sum(card.defense) immediately before damage, so every
        # adjustment to the defence total was discarded a moment after it was
        # made. Recorded on combat.defense_mods, which the recalculation
        # re-applies — the same shape power_mods already had on the attack side.
        def _fn(card, event, state, _a=amt, _m=mod):
            combat = state.combat
            if not combat:
                return
            delta = _resolve_amount(_a, state, card) if isinstance(_a, dict) else _a
            try:
                delta = int(delta)
            except (TypeError, ValueError):
                delta = 0
            # A recalculation-time static must not accumulate: it re-runs on
            # every pass and would stack with its own earlier applications.
            if getattr(event, "type", None) != "recalculate_total_defense":
                combat.defense_mods.append((_m, delta))
            current = getattr(combat, 'total_defense', 0) or 0
            if _m in ("set", "="):
                combat.total_defense = delta
            elif _m in ("subtract", "sub", "minus", "-"):
                combat.total_defense = max(0, current - delta)
            else:
                combat.total_defense = current + delta
        return _fn

    if etype == "MODIFY_DEFENSE":
        # "This gets +1{d}" / "cards defending this get -1{d}" — the DEFENDING
        # CARD's own value, as opposed to MODIFY_DEFENSE_VALUE, which moves the
        # total. Applied during _recalculate_total_defense, which resets each
        # defender to its base first, so a static may re-apply freely.
        #
        # The card modified is combat.defense_recalc_card, the defender being
        # evaluated: a static on some OTHER object ("cards defending your
        # Mechanologist attacks get -1{d}") has to say which defender it means,
        # and its own source card is not it.
        amt = params.get("amount", 0)
        mod = (params.get("mod") or "add").lower()

        def _fn(card, event, state, _a=amt, _m=mod):
            combat = state.combat
            if not combat:
                return
            target = getattr(combat, "defense_recalc_card", None)
            if target is None:
                # Outside a recalculation the only sensible subject is the
                # ability's own card, which is the "THIS gets +1{d}" case.
                target = card
            if target is None:
                return
            delta = _resolve_amount(_a, state, card) if isinstance(_a, dict) else _a
            try:
                delta = int(delta)
            except (TypeError, ValueError):
                delta = 0
            current = target.defense or 0
            if _m in ("set", "="):
                target.defense = max(0, delta)
            elif _m in ("subtract", "sub", "minus", "-"):
                target.defense = max(0, current - delta)
            else:
                target.defense = max(0, current + delta)
        return _fn

    if etype == "ADD_DEFEND":
        # Add the ability's source card to the active chain link as a defending
        # card (e.g. Quickdodge Flexors activating from the legs zone). Optional
        # `defense` sets its {d} for this chain link before it is credited to
        # total defense.
        defense = params.get("defense")
        # "You may add AN ACTION CARD FROM YOUR ARSENAL to the active chain link
        # as a defending card" — a DIFFERENT object, not the source. With no
        # target this could only ever add the card whose ability it is, so the
        # one card that names another added itself instead (and its own
        # authoring, SELECT_FROM_REF over a ref nothing sets, added nothing).
        raw_target = params.get("target")
        object_fn = (_compile_object_target(_object_target_spec(raw_target))
                     if isinstance(raw_target, dict) else None)

        def _fn(card, event, state, _d=defense, _of=object_fn):
            if not state.combat:
                return
            from engine.effect_keywords import add_defend
            targets = _of(card, event, state) if _of is not None else [card]
            for obj in targets:
                if _d is not None:
                    obj.defense = _d
                    obj.base_defense = _d
                add_defend(state, obj)
        return _fn

    if etype == "RETURN_DR_FROM_GRAVEYARD":
        # Return a defense reaction card from any graveyard to its owner's hand.
        # Searches controller's graveyard first, then opponent's.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import put_object
            cid = _controller_id(card)
            for pid in (cid, 3 - cid):
                player = state.players.get(pid)
                if not player:
                    continue
                for c in list(getattr(player.graveyard, 'cards', [])):
                    types = [t.lower() for t in (getattr(c, 'types', None) or [])]
                    subtypes = [st.lower() for st in (getattr(c, 'subtypes', None) or [])]
                    if 'defense reaction' in types or 'defense_reaction' in subtypes:
                        owner_pid = c.owner if c.owner is not None else pid
                        put_object(state, c, "hand",
                                   destination_player_id=owner_pid, source_player_id=pid)
                        return
        return _fn

    if etype == "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA":
        # +N per distinct aura name IN THE ARENA (both players' auras, not just
        # the controller's — Overcrowded reads "among aura tokens in the
        # arena"). stat: "power" (default) applies to attack power; "defense"
        # applies to the defending total, for the "or defends" half.
        per = params.get("per", params.get("amount", 1))
        stat = params.get("stat", "power")
        # Same unread "mod" as MODIFY_DEFENSE_VALUE: 3 nodes say "subtract" and
        # 2 say "set", and all of them were adding.
        mod = (params.get("mod") or "add").lower()

        def _fn(card, event, state, _per=per, _stat=stat, _m=mod):
            names = set()
            for pl in state.players.values():
                auras = getattr(pl, "auras", None)
                if auras:
                    names |= {getattr(c, "slug", "") for c in auras.cards}
            n = len(names)
            if not n or state.combat is None:
                return
            delta = n * _per
            if _stat == "defense":
                current = getattr(state.combat, "total_defense", 0) or 0
                if _m in ("set", "="):
                    state.combat.total_defense = delta
                elif _m in ("subtract", "sub", "minus", "-"):
                    state.combat.total_defense = max(0, current - delta)
                else:
                    state.combat.total_defense = current + delta
            else:
                current = state.combat.attack_power or 0
                if _m in ("set", "="):
                    state.combat.attack_power = delta
                elif _m in ("subtract", "sub", "minus", "-"):
                    state.combat.attack_power = max(0, current - delta)
                else:
                    state.combat.attack_power = current + delta
        return _fn

    if etype == "CROWD_BOO":
        player_target = params.get("player", "SELF")
        def _fn(card, event, state, _pt=player_target):
            from engine.card_effects.ability_keywords import effect_crowd_boos, _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            effect_crowd_boos(state, tid)
        return _fn

    if etype in ("CROWD_CHEER", "CROWD_CHEERS"):
        # "the crowd cheers you" (CR 8.5.57). Cards used to hand-roll this as
        # SET_FLAG CROWD_CHEERS, which never reached the keyword function, so a
        # cheer was invisible to every other card and to replacement effects.
        # Defaults to SELF — the crowd cheers YOU, mirroring CROWD_BOO.
        player_target = params.get("player", "SELF")
        def _fn(card, event, state, _pt=player_target):
            from engine.card_effects.ability_keywords import effect_crowd_cheers, _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            effect_crowd_cheers(state, tid)
        return _fn

    if etype == "DEAL_GENERIC":
        amt = params.get("amount", 0)
        tgt = params.get("target", "OPPONENT")
        def _fn(card, event, state, _a=amt, _t=tgt):
            from engine.card_effects.ability_keywords import _controller_id, effect_deal_damage
            cid = _controller_id(card)
            tid = _damage_target_player(state, cid, _t)
            effect_deal_damage(state, tid, _a, card, damage_type="generic")
        return _fn

    if etype == "QUEUE_NEXT_MARKED_DAGGER_HIT_DRAW":
        # Savor Bloodshed: "The next time you hit a marked hero with a dagger this
        # turn, draw a card." Queued as a current-turn flag consumed at the attack
        # step (engine handles next_marked_dagger_hit_draw_N).
        amount = params.get("amount", 1)
        def _fn(card, event, state, _n=amount):
            from engine.card_effects.ability_keywords import _controller_id
            state.players[_controller_id(card)].current_turn_effects.append(
                f"next_marked_dagger_hit_draw_{_n}")
        return _fn

    if etype == "COPY_BANISHED_STEALTH_ATTACK":
        # Take Up the Mantle (marked rider): "you may banish an attack action card
        # with stealth from your graveyard. If you do, the target becomes a copy of
        # the banished card" — copies the banished card's printed profile onto the
        # current attack (name/base stats/keywords/abilities slug).
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import banish as _banish
            cid = _controller_id(card)
            controller = state.players[cid]
            target = state.combat.attack_card if state.combat else None
            if target is None:
                return
            stealth = [c for c in controller.graveyard.cards
                       if 'attack' in [s.lower() for s in (c.subtypes or [])]
                       and any(k.lower() == 'stealth' for k in (c.keywords or []))]
            if not stealth:
                return
            from engine.card_effects.ability_keywords import ask_optional
            pick = ask_optional(state, cid, [c.slug for c in stealth],
                                context="Banish a stealth attack from your graveyard to copy it?")
            if pick is None:
                return
            src = next((c for c in stealth if c.slug == pick), None)
            if src is None:
                return
            _banish(state, src, cid, origin_zone="graveyard")
            # "becomes a copy": adopt the banished card's slug/name/profile so its
            # DSL abilities and printed values apply to the attack. Save the
            # target's printed identity first so the copy can revert: CR 3.0.9 —
            # when the attack leaves the combat chain (an arena zone) into the
            # graveyard it resets to a new object with no relation to its previous
            # existence, i.e. its original card, not the copied one. Without the
            # revert the graveyard keeps a mislabelled duplicate of the copied card.
            _COPY_ATTRS = ("slug", "name", "base_power", "power", "base_defense",
                           "defense", "types", "subtypes", "keywords")
            _orig = {a: getattr(target, a, None) for a in _COPY_ATTRS}
            target.slug = src.slug
            target.name = src.name
            target.base_power = src.base_power
            target.power = src.power
            target.base_defense = src.base_defense
            target.defense = src.defense
            target.types = list(src.types or [])
            target.subtypes = list(src.subtypes or [])
            target.keywords = list(src.keywords or [])

            def _revert_copy(ev, s, _t=target, _o=_orig):
                for attr, val in _o.items():
                    setattr(_t, attr, val)
                s.event_manager.unregister("combat_chain_close", _revert_copy)
            state.event_manager.register("combat_chain_close", _revert_copy)

            from engine.engine import _recalculate_attack_power
            _recalculate_attack_power(state)
        return _fn

    if etype == "DAGGER_DEALS_DAMAGE":
        # "Target dagger you control deals N damage to them. If damage is dealt
        # this way, the dagger has hit." (Pain in the Backside — unlike Flick
        # Knives the dagger is not destroyed, and the active attacking dagger
        # is a legal target.) Registering the hit fires the dagger's own ON_HIT,
        # which is what "the dagger has hit" enables (e.g. marked-dagger draws).
        amount = params.get("amount", 1)
        def _fn(card, event, state, _amt=amount):
            from engine.card_effects.ability_keywords import (
                _controller_id, effect_deal_damage, ask_optional)
            from engine.card_effects.dsl import dispatch as _dsl_dispatch
            cid = _controller_id(card)
            player = state.players[cid]
            daggers = [d for zone in (player.weapon1, player.weapon2) for d in zone.cards
                       if 'dagger' in [s.lower() for s in (getattr(d, 'subtypes', None) or [])]]
            if not daggers:
                return
            pick = ask_optional(state, cid, [d.slug for d in daggers],
                                context="Which dagger you control deals damage?")
            if pick is None:
                return
            dagger = next((d for d in daggers if d.slug == pick), None)
            if dagger is None:
                return
            effect_deal_damage(state, 3 - cid, _amt, dagger, damage_type="generic")
            # "the dagger has hit" — fire its ON_HIT (not destroyed).
            _dsl_dispatch(state, "ON_HIT", dagger.slug, card=dagger, event=None)
            # Bite adds "Destroy the dagger", which needs to name WHICH dagger
            # was chosen. Recording it lets a following DESTROY_REF say so
            # without this effect growing a destroy of its own — and without
            # Bite borrowing DAGGER_DEALS_DAMAGE_AND_DESTROY, which carries
            # Flick Knives' "isn't on the active chain link" restriction that
            # Bite does not have.
            from engine.context import set_ref
            set_ref("dagger", dagger)
        return _fn

    if etype == "DAGGER_DEALS_DAMAGE_AND_DESTROY":
        # Flick Knives: "Target dagger you control that isn't on the active chain
        # link deals N damage to target hero. If damage is dealt this way, the
        # dagger has hit. Destroy the dagger."
        amount = params.get("amount", 1)
        def _fn(card, event, state, _amt=amount):
            from engine.card_effects.ability_keywords import (
                _ask_player, _controller_id, effect_deal_damage)
            from engine.effect_keywords import destroy as _destroy
            from engine.card_effects.dsl import dispatch as _dsl_dispatch
            cid = _controller_id(card)
            player = state.players[cid]
            active = state.combat.attack_card if state.combat else None
            daggers = [d for zone in (player.weapon1, player.weapon2) for d in zone.cards
                       if d is not active
                       and 'dagger' in [s.lower() for s in (getattr(d, 'subtypes', None) or [])]]
            if not daggers:
                return
            from engine.card_effects.ability_keywords import ask_optional
            pick = ask_optional(state, cid, [d.slug for d in daggers],
                                context="Which dagger you control deals damage?")
            if pick is None:
                return
            dagger = next((d for d in daggers if d.slug == pick), None)
            if dagger is None:
                return
            effect_deal_damage(state, 3 - cid, _amt, dagger, damage_type="generic")
            # "the dagger has hit" — fire its ON_HIT; then destroy it.
            _dsl_dispatch(state, "ON_HIT", dagger.slug, card=dagger, event=None)
            _destroy(state, dagger, card)
        return _fn

    if etype == "STEAL_AURA_TOKEN":
        token_slug = params.get("token", "")
        def _fn(card, event, state, _slug=token_slug):
            from engine.card_effects.ability_keywords import effect_steal_token, _controller_id
            cid = _controller_id(card)
            effect_steal_token(state, cid, 3 - cid)
        return _fn

    if etype == "RETRIEVE_DAGGER":
        # Pay 1{r} to retrieve a dagger from your graveyard into the appropriate weapon slot.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import retrieve
            cid = _controller_id(card)
            player = state.players[cid]
            daggers = [c for c in player.graveyard.cards
                       if "dagger" in [s.lower() for s in (getattr(c, 'subtypes', None) or [])]]
            if not daggers or player.resources < 1:
                return
            retrieve(state, daggers[0], cid, chose_to_pay=True)
        return _fn

    if etype == "DESTROY_ARSENAL":
        # Destroy the target player's arsenal card. `target` is the other
        # spelling of WHOSE arsenal; it happened to name the default on the one
        # card that used it, but a card writing "self" would silently have hit
        # the opponent instead.
        player_target = _first(params, "player", "target", default="OPPONENT")
        def _fn(card, event, state, _pt=player_target):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import destroy
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            for c in list(getattr(player.arsenal, 'cards', [])):
                destroy(state, c, None)
        return _fn

    # ── new canonical effect types ─────────────────────────────────────────

    if etype == "CLASH":
        # "Clash with the attacking hero", optionally repeated, with role-based
        # outcome effects. opponent: ATTACKING_HERO (default) → the attacker in
        # combat, else the plain opponent. Outcome specs are small dicts:
        #   {"action": "create_token"|"discard", "who": ROLE, ...}
        # ROLE ∈ WINNER, LOSER, SWEEPER, SELF, OPPONENT.
        opponent_kind = params.get("opponent", "ATTACKING_HERO").upper()
        repeat = params.get("repeat", 1)
        reveal_dest = params.get("reveal_dest", "top").lower()
        on_winner = params.get("on_winner", [])
        on_loser = params.get("on_loser", [])
        on_sweep = params.get("on_sweep", [])

        def _run_outcome(spec, state, role_players):
            who = spec.get("who", "SELF").upper()
            pid = role_players.get(who)
            if pid is None:
                return
            action = spec.get("action", "")
            if action == "create_token":
                from engine.effect_keywords import create_token as _ct
                _ct(state, target_player_id=pid, token_slug=spec.get("token", ""),
                    number=spec.get("number", 1))
            elif action == "discard":
                from engine.card_effects.ability_keywords import effect_discard
                effect_discard(state, pid, count=spec.get("amount", 1),
                               random_discard=spec.get("random", True))

        def _fn(card, event, state, _opp=opponent_kind, _rep=repeat, _rd=reveal_dest,
                _ow=on_winner, _ol=on_loser, _os=on_sweep):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import clash as _clash
            cid = _controller_id(card)
            if _opp == "ATTACKING_HERO" and state.combat is not None:
                opp = state.combat.attacker_id
            else:
                opp = 3 - cid
            winners = []
            for _ in range(_rep):
                ev = _clash(state, cid, opp)
                winner = ev.winner_id
                winners.append(winner)
                revealed = {cid: ev.card1, opp: ev.card2}
                # "You may put YOUR revealed card on the bottom of its owner's
                # deck" is about one specific card, and reveal_dest:"bottom"
                # bottoms BOTH unconditionally. Naming them lets a card act on
                # whichever one it means, optionally.
                from engine.context import set_ref
                if ev.card1 is not None:
                    set_ref("clash_revealed_self", ev.card1)
                if ev.card2 is not None:
                    set_ref("clash_revealed_opponent", ev.card2)
                loser = None
                if winner is not None:
                    loser = opp if winner == cid else cid
                roles = {"SELF": cid, "OPPONENT": opp,
                         "WINNER": winner, "LOSER": loser}
                if winner is not None:
                    for spec in _ow:
                        _run_outcome(spec, state, roles)
                    for spec in _ol:
                        _run_outcome(spec, state, roles)
                # Move revealed cards to the bottom between clashes if instructed.
                if _rd == "bottom":
                    for pid_, rc in revealed.items():
                        if rc is not None:
                            owner = state.players[rc.owner]
                            if rc in owner.deck.cards:
                                owner.deck.cards.remove(rc)
                                owner.deck.add_bottom(rc)
            # Sweep: one hero won every clash.
            if _os and _rep >= 2 and winners and all(w == winners[0] and w is not None
                                                     for w in winners):
                sweeper = winners[0]
                roles = {"SELF": cid, "OPPONENT": opp, "SWEEPER": sweeper,
                         "WINNER": sweeper, "LOSER": (opp if sweeper == cid else cid)}
                for spec in _os:
                    _run_outcome(spec, state, roles)
        return _fn

    if etype == "PAY_OR_DAMAGE":
        # "Deals N damage to you unless you pay {r}..." — the controller may pay
        # the resources to avoid the damage (e.g. Bloodrot Pox). Also models the
        # payoff form "you may pay {r}. If you do, X" (damage 0 + on_success).
        #
        # The pay amount is authored under "resources", "resource_cost",
        # "resource", or "amount". "resource" is sometimes a resource *name*
        # ("RESOURCE_POINTS") rather than a quantity, in which case the quantity
        # lives in "amount" — taking the name as the amount raised a TypeError
        # on the `>=` below, so only numeric values are accepted as the cost.
        def _first_num(*keys):
            for k in keys:
                v = params.get(k)
                if isinstance(v, bool):
                    continue
                if isinstance(v, int) or isinstance(v, float):
                    return v
                if isinstance(v, str):
                    try:
                        return int(v)
                    except ValueError:
                        continue
            return 0
        resources = _first_num("resources", "resource_cost", "resource", "amount")
        dmg = params.get("damage", 0)
        if not isinstance(dmg, (int, float)) or isinstance(dmg, bool):
            dmg = 0
        # Compiled eagerly so a bad on_success spec fails at JSON load time like
        # every other effect, instead of raising mid-game only for the players
        # who choose to pay.
        on_success = [compile_effect((e.get("type") or "").upper(),
                                     {k: v for k, v in e.items() if k != "type"})
                      for e in (params.get("on_success") or [])]
        def _fn(card, event, state, _r=resources, _d=dmg, _win=on_success):
            from engine.card_effects.ability_keywords import (
                _ask_player, _controller_id, effect_deal_damage)
            cid = _controller_id(card)
            player = state.players[cid]
            # Paying buys nothing when there is no damage to avoid and no
            # payoff — don't offer a prompt that can only waste resources.
            if _d <= 0 and not _win:
                return
            paid = False
            if player.resources >= _r:
                choice = _ask_player(state, cid, ["pay", "take_damage"],
                                     context=f"Pay {_r} to avoid {_d} damage?")
                if str(choice) == "pay":
                    player.resources -= _r
                    paid = True
            if paid:
                for fn in _win:
                    if fn is not None:
                        fn(card, event, state)
            else:
                effect_deal_damage(state, cid, _d, card, damage_type="generic")
        return _fn

    if etype in ("FREEZE", "UNFREEZE"):
        # CR 8.5.34 / 8.5.37. There was no FREEZE effect at all, so none of the
        # 30 corpus cards that freeze could be written — and the keyword itself
        # was inert until _legality_check started reading the counter.
        #
        #   {"type":"FREEZE","target":{...}}   the canonical object target
        #   {"type":"FREEZE","ref":"chosen"}   what an earlier effect stored
        unfreeze = etype == "UNFREEZE"
        ref = params.get("ref")
        target_fn = _compile_object_target(_object_target_spec(params.get("target")))

        def _fn(card, event, state, _un=unfreeze, _r=ref, _tf=target_fn):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.context import get_ref
            from engine.effect_keywords import freeze as _freeze, unfreeze as _unfreeze
            cid = _controller_id(card)
            if _r:
                found = get_ref(_r)
                objects = ([] if found is None
                           else (list(found) if isinstance(found, list) else [found]))
            elif _tf is not None:
                objects = _tf(card, event, state)
            else:
                objects = []
            for obj in objects:
                if _un:
                    _unfreeze(state, obj)
                else:
                    _freeze(state, obj, source_player_id=cid)
        return _fn

    if etype in ("SUPPRESS_HIT_TRIGGERS", "HIT_EFFECTS_DONT_TRIGGER"):
        # "Effects don't trigger if an attack hits you this turn" / "... when an
        # attack hits this chain link". Suppression of the TRIGGERED LAYERS
        # only: the damage is dealt as normal, which is why this is a flag read
        # at the ON_HIT dispatch point rather than anything that touches the
        # damage pipeline.
        #
        #   scope:  "TURN" (default) — a marker on the player being hit
        #           "CHAIN"          — a flag on the current combat
        #   player: "SELF" (default) | "OPPONENT" — who is protected
        scope = str(params.get("scope") or "TURN").upper()
        who = str(params.get("player") or "SELF").upper()

        def _fn(card, event, state, _scope=scope, _w=who):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.engine import HIT_TRIGGERS_SUPPRESSED
            cid = _controller_id(card)
            pid = (3 - cid) if _w in ("OPPONENT", "THEM") else cid
            if _scope == "CHAIN":
                if state.combat is not None:
                    state.combat.suppress_hit_triggers = True
                return
            player = state.players.get(pid)
            if player is not None and HIT_TRIGGERS_SUPPRESSED not in player.current_turn_effects:
                player.current_turn_effects.append(HIT_TRIGGERS_SUPPRESSED)
        return _fn

    if etype == "PAY_OR_ELSE":
        # "<player> discards a card unless they pay N" (generic: pay N resources or
        # else run on_failure). `player` picks who pays/suffers (SELF default /
        # OPPONENT). on_failure is a list of effect specs resolved when unpaid; their
        # own `player` params are relative to the SAME source card, so e.g. a DISCARD
        # with player=OPPONENT hits the same target that was asked to pay.
        # The cost is normally resources, but "destroy this UNLESS you remove a
        # steam counter from it" pays in counters instead — set counter_type and
        # the amount comes from `amount` (the recurring Crank/steam pattern).
        counter_type = params.get("counter_type") or params.get("counter")
        if counter_type:
            resources = 0
            counters_due = int(params.get("amount", 1) or 1)
        else:
            resources = params.get("resources", params.get("amount", 0))
            counters_due = 0
        player_target = (params.get("player") or "SELF").upper()
        # Eager, so a bad on_failure spec fails at load like every other effect
        # rather than only for the players who decline.
        on_fail = [compile_effect((e.get("type") or "").upper(),
                                  {k: v for k, v in e.items() if k != "type"})
                   for e in params.get("on_failure", [])]

        def _fn(card, event, state, _r=resources, _pt=player_target, _fail=on_fail,
                _ct=counter_type, _cn=counters_due):
            from engine.card_effects.ability_keywords import (
                _ask_player, _controller_id, effect_remove_counter)
            cid = _controller_id(card)
            tid = (3 - cid) if _pt in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            paid = False
            if _ct:
                have = player.counters.get((card.slug, card.zone, _ct), 0)
                if have >= _cn:
                    choice = _ask_player(
                        state, tid, ["pay", "decline"],
                        context=f"Remove {_cn} {_ct} counter(s) to avoid the effect?")
                    if str(choice) == "pay":
                        effect_remove_counter(state, card, _ct, _cn)
                        paid = True
            elif _r > 0 and player.resources >= _r:
                choice = _ask_player(state, tid, ["pay", "decline"],
                                     context=f"Pay {_r} to avoid the effect?")
                if str(choice) == "pay":
                    player.resources -= _r
                    paid = True
            if not paid:
                for fn in _fail:
                    if fn is not None:
                        fn(card, event, state)
        return _fn

    if etype == "PUT_CARDS_BOTTOM":
        # Put all cards from the given zones on the bottom of the controller's
        # deck (e.g. Inertia token: hand + arsenal → bottom of deck).
        # "zone" (5 nodes) was not read, so those fell through to the DEFAULT
        # hand+arsenal — a card meant to bottom its revealed cards was emptying
        # the player's hand instead. A wrong default is more damaging than none.
        # "target" is a fifth spelling of the same two facts — whose cards, and
        # from where — and it was unread, so "put a card from THEIR arsenal on
        # the bottom of THEIR deck" emptied the CONTROLLER's own hand and
        # arsenal instead. There was no `player` param at all to fall back on.
        _t_player, _t_zone = _zone_target_spec(params.get("target"))
        from_zones = _first(params, "from_zones", "zones", "zone", "from_zone")
        if from_zones is None:
            from_zones = ([_t_zone.lower()] if _t_zone else ["hand", "arsenal"])
        if isinstance(from_zones, str):
            from_zones = [from_zones]
        from_zones = [str(z).lower() for z in from_zones]
        who = str(params.get("player") or _t_player or "SELF").upper()
        # "put A CARD on the bottom" is not "put every card in the zone on the
        # bottom". Defaulting to everything is right for the Inertia token
        # (hand + arsenal → bottom) and wrong for the cards that name one.
        count = params.get("amount", params.get("count"))
        # "Look at the top card of your deck. YOU MAY put IT on the bottom."
        # Two things neither of the cards saying that could express. `ref`
        # bottoms the object a preceding effect stored (LOOK_AT stores under
        # "looked"): naming the zone instead does not work, because "top_deck"
        # is not a Player attribute — one card bottomed nothing at all, and the
        # other, naming no zone, fell through to the hand+arsenal default and
        # bottomed a card from EACH. And `optional` was unread, so "you may"
        # was mandatory.
        from_ref = _first(params, "ref", "target_ref", "cards")
        optional = bool(params.get("optional"))

        def _fn(card, event, state, _zones=from_zones, _w=who, _n=count,
                _ref=from_ref, _opt=optional):
            from engine.card_effects.ability_keywords import (
                DECLINE, _ask_player, _controller_id, ask_yes_no)
            cid = _controller_id(card)
            tid = (3 - cid) if _w in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            if _ref:
                from engine.context import get_ref
                found = get_ref(_ref)
                if found is None:
                    return
                objects = list(found) if isinstance(found, list) else [found]
                if not objects:
                    return
                if _opt and not ask_yes_no(
                        state, cid, context="Put it on the bottom of the deck?"):
                    return
                for obj in objects:
                    owner = state.players.get(getattr(obj, "owner", tid), player)
                    src = getattr(owner, (getattr(obj, "zone", "") or "").lower(),
                                  None)
                    if src is not None:
                        src.remove(obj)
                    owner.deck.add_bottom(obj)
                return
            if _opt and not ask_yes_no(
                    state, cid, context="Put a card on the bottom of the deck?"):
                return
            limit = None
            if _n is not None and str(_n).upper() not in ("ALL", "EACH"):
                try:
                    limit = max(0, int(_resolve_amount(_n, state, card)))
                except (TypeError, ValueError):
                    limit = None
            moved = 0
            for zone_name in _zones:
                zone = getattr(player, zone_name, None)
                if zone is None:
                    continue
                pool = list(zone.cards)
                if limit is not None:
                    # The card's controller chooses which one moves, even when
                    # the cards belong to the opponent.
                    while pool and moved < limit:
                        pick = _ask_player(state, cid, [c.slug for c in pool],
                                           context=f"Choose a card to put on the "
                                                   f"bottom of the deck from {zone_name}")
                        obj = next((c for c in pool if c.slug == pick), pool[0])
                        pool.remove(obj)
                        zone.remove(obj)
                        player.deck.add_bottom(obj)
                        moved += 1
                    continue
                for c in pool:
                    zone.remove(c)
                    player.deck.add_bottom(c)
        return _fn

    # ── composable primitives ──────────────────────────────────────────────
    # These exist so a card sentence can be assembled in JSON instead of
    # compiled into one Python function named after the card. See
    # engine/context.py for how "into"/"ref" are scoped.

    if etype == "LOOK_AT":
        # Look at cards without moving them, storing them under "into" for a
        # later effect to act on. Unlike LOOK this does NOT pop cards out of
        # the deck — the card stays put until something acts on the ref.
        #   zone:   DECK_TOP (default) | ARSENAL | HAND
        #   player: OPPONENT (default) | SELF
        #   amount: how many (default 1) or "ALL"; a single card (amount 1, no
        #           filter) is stored unwrapped, otherwise a list
        #   filter: optional {keyword, face_down, subtype} — a filter always
        #           scans the whole zone and always stores a list
        # "target" is how 12 cards name the zone and whose it is, and it was not
        # read — so all of them fell through to the defaults, DECK_TOP and
        # OPPONENT. Five say "look at the top card of YOUR deck" and were
        # looking at the opponent's: not a dead effect, an information leak in
        # the wrong direction.
        #
        # The parser is shared with BANISH: the same authors gave both effects
        # the same handful of spellings, and a second one would drift from it.
        # Its canonical TOP_DECK is spelled DECK_TOP in this handler's own zone
        # map, so it is translated rather than either name being "fixed".
        _t_player, _t_zone = _zone_target_spec(params.get("target"))
        if _t_zone == "TOP_DECK":
            _t_zone = "DECK_TOP"
        zone = str(params.get("zone") or _t_zone or "DECK_TOP").upper()
        who = str(params.get("player") or _t_player or "OPPONENT").upper()
        amount = params.get("amount", 1)
        into = params.get("into", "looked")
        filt = params.get("filter") or {}
        def _fn(card, event, state, _z=zone, _w=who, _n=amount, _into=into, _f=filt):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.context import set_ref
            cid = _controller_id(card)
            tid = (3 - cid) if _w in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            zone_map = {"DECK_TOP": player.deck, "ARSENAL": getattr(player, "arsenal", None),
                        "HAND": player.hand}
            z = zone_map.get(_z)
            source = list(getattr(z, "cards", []) if z is not None else [])
            if _f:
                # A filter examines the whole zone, not just the top slice.
                kw = _f.get("keyword")
                sub = _f.get("subtype")
                want_fd = _f.get("face_down")
                def _ok(c):
                    if kw and not any(k.lower() == kw.lower() for k in (c.keywords or [])):
                        return False
                    if sub and sub.lower() not in [s.lower() for s in (c.subtypes or [])]:
                        return False
                    if want_fd is not None and bool(getattr(c, "is_public", False)) == bool(want_fd):
                        return False
                    return True
                pool = [c for c in source if _ok(c)]
                set_ref(_into, pool)
            elif str(_n).upper() == "ALL":
                set_ref(_into, source)
            else:
                pool = source[:_n]
                set_ref(_into, pool[0] if _n == 1 and pool else (pool if _n != 1 else None))
            set_ref(_into + "_owner", tid)
        return _fn

    if etype == "DESTROY_REF":
        # Destroy whatever a previous effect stored under "ref".
        ref = params.get("ref", "looked")
        def _fn(card, event, state, _r=ref):
            from engine.context import get_ref
            from engine.effect_keywords import destroy as _ek_destroy
            target = get_ref(_r)
            if target is None:
                return
            for obj in (target if isinstance(target, list) else [target]):
                _ek_destroy(state, obj, card)
        return _fn

    if etype == "MOVE_REF":
        # Move a referenced card to a zone.
        #   ref:      what to move
        #   to_zone:  destination zone name (e.g. "deck", "hand", "graveyard")
        #   position: "top" | "bottom" (default) — only meaningful for the deck
        #   player:   SELF | OPPONENT | OWNER (default) — whose zone
        ref = params.get("ref", "looked")
        # "to" is the obvious short spelling and was unread, so those nodes
        # silently moved the card to the DECK regardless of what they said.
        to_zone = _first(params, "to_zone", "to", "destination", default="deck")
        position = _first(params, "position", "order", default="bottom")
        who = params.get("player", "OWNER").upper()
        # "from"/"zone" name the ORIGIN, which put_object resolves from the card
        # itself. They are deliberately NOT in the destination list above —
        # reading them there would move the card to where it already is — and
        # deliberately not touched here either: a bare params.get() would mark
        # them "read" for the audit without honouring them, which is the same
        # lie as an allowlist entry that is not true. They are declared inert in
        # scripts/audit_params.py instead, where the reason is visible.

        self_target = _names_self(params.get("target"))

        def _fn(card, event, state, _r=ref, _z=to_zone, _pos=position, _w=who,
                _self=self_target):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import put_object
            from engine.context import get_ref
            target = card if _self else get_ref(_r)
            if not target:
                return
            cid = _controller_id(card)
            for obj in (target if isinstance(target, list) else [target]):
                if _w == "OWNER":
                    dest_pid = obj.owner
                elif _w in ("OPPONENT", "DEFENDING", "DEFENDER"):
                    dest_pid = 3 - cid
                else:
                    dest_pid = cid
                put_object(state, obj, _z, destination_player_id=dest_pid,
                           source_player_id=cid,
                           position=("top" if str(_pos).lower() == "top" else None))
        return _fn

    if etype == "PUT_COUNTER_REF":
        # Put counters on a referenced card (vs PUT_COUNTER, which targets the
        # ability's own source).
        ref = params.get("ref", "chosen")
        counter_type = params.get("counter_type", "power")
        amount = params.get("amount", 1)
        def _fn(card, event, state, _r=ref, _ct=counter_type, _a=amount):
            from engine.card_effects.ability_keywords import effect_put_counter
            from engine.context import get_ref
            target = get_ref(_r)
            if not target:
                return
            for obj in (target if isinstance(target, list) else [target]):
                for _ in range(_a):
                    effect_put_counter(state, obj, _ct)
        return _fn

    if etype == "FLIP_MATCHING":
        # "Turn a card in their banished zone face-down." FLIP_REF needs an
        # earlier effect to have stored the card, and these cards have none —
        # they were authored as BANISH_REF, which both names the wrong action
        # (they turn a card over, they do not banish it) and reads a ref nobody
        # set, so nothing happened at all.
        face_up = params.get("face_up", False)
        target_fn = _compile_object_target(_object_target_spec(params.get("target")))

        def _fn(card, event, state, _up=face_up, _tf=target_fn):
            if _tf is None:
                return
            for obj in _tf(card, event, state):
                obj.is_public = bool(_up)
                if hasattr(obj, "face_down"):
                    obj.face_down = not bool(_up)
        return _fn

    if etype == "FLIP_REF":
        # Turn a referenced face-down card face-up (or vice versa). Arsenal and
        # banished-face-down cards track visibility via is_public.
        # "Turn a face down arrow in your arsenal face up" chooses the card
        # itself — there is no earlier effect to have stored it — so this takes
        # the canonical object target as well as a ref. Three cards named a
        # target here and got neither: the ref defaulted to "chosen", which
        # nothing had set, and the effect returned without flipping anything.
        raw_target = params.get("target")
        object_fn = (_compile_object_target(_object_target_spec(raw_target))
                     if isinstance(raw_target, dict) else None)
        self_target = _names_self(raw_target)
        ref = params.get("ref", "chosen")
        face_up = params.get("face_up", True)
        def _fn(card, event, state, _r=ref, _up=face_up, _of=object_fn,
                _self=self_target):
            from engine.context import get_ref
            if _self:
                objects = [card] if card is not None else []
            elif _of is not None:
                objects = _of(card, event, state)
            else:
                target = get_ref(_r)
                if not target:
                    return
                objects = target if isinstance(target, list) else [target]
            for obj in objects:
                obj.is_public = bool(_up)
                if hasattr(obj, "face_down"):
                    obj.face_down = not bool(_up)
        return _fn

    if etype == "SELECT_FROM_REF":
        # Choose a subset of a referenced list of cards.
        #   ref:       list to choose from
        #   mode:      SAME_NAME — pick a name, take every copy of it (the
        #              "banish 1 or more cards with the same name" pattern)
        #              ANY       — pick individual cards, up to `max`
        #   min/max:   how many to take (ANY mode)
        #   into:      where the chosen cards go
        #   rest_into: the complement, so a later effect can act on "the rest"
        #              without recomputing the difference
        ref = params.get("ref", "looked")
        mode = params.get("mode", "ANY").upper()
        want_min = params.get("min", 1)
        want_max = params.get("max")
        into = params.get("into", "chosen")
        rest_into = params.get("rest_into")
        def _fn(card, event, state, _r=ref, _m=mode, _min=want_min,
                _max=want_max, _into=into, _rest=rest_into):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id, STOP
            from engine.context import get_ref, set_ref
            pool = get_ref(_r) or []
            if not isinstance(pool, list):
                pool = [pool]
            pool = list(pool)
            cid = _controller_id(card)
            chosen: list = []
            if _m == "SAME_NAME":
                groups: dict = {}
                for c in pool:
                    groups.setdefault(c.name, []).append(c)
                if groups:
                    options = list(groups)
                    pick = _ask_player(state, cid, options,
                                       context="Select all copies of which name?")
                    chosen = list(groups[pick if pick in groups else options[0]])
            else:
                limit = _max if _max is not None else len(pool)
                remaining = list(pool)
                while remaining and len(chosen) < limit:
                    options = [c.slug for c in remaining]
                    if len(chosen) >= _min:
                        options = options + [STOP]
                    pick = _ask_player(state, cid, options, context="Select a card")
                    if pick == STOP:
                        break
                    target = next((c for c in remaining if c.slug == pick), remaining[0])
                    remaining.remove(target)
                    chosen.append(target)
            set_ref(_into, chosen)
            if _rest:
                set_ref(_rest, [c for c in pool if c not in chosen])
        return _fn

    if etype == "MOVE_MATCHING":
        # Move chosen objects to a zone, where the choice is a target spec
        # rather than a ref an earlier effect stored. MOVE_REF covers "then put
        # IT on the bottom"; this covers "put target <card matching X> from
        # <zone> on top of your deck", which has no earlier effect to reference.
        to_zone = _first(params, "to_zone", "to", "destination", default="deck")
        position = _first(params, "position", "order", default="bottom")
        target_fn = _compile_object_target(_object_target_spec(params.get("target")))

        def _fn(card, event, state, _z=to_zone, _pos=position, _tf=target_fn):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import put_object
            if _tf is None:
                return
            cid = _controller_id(card)
            for obj in _tf(card, event, state):
                put_object(state, obj, destination_zone=str(_z).lower(),
                           destination_player_id=getattr(obj, "owner", cid),
                           position=str(_pos).lower())
        return _fn

    if etype in ("PUT_REF_BOTTOM", "PUT_REF_TOP"):
        # Put a referenced card (or list) on the bottom/top of a deck — the common
        # "then put it on the bottom of your deck" rider after a look/reveal. A thin
        # convenience over MOVE_REF's deck path (which many authors reach for by name).
        ref = params.get("ref", "looked")
        pos = "top" if etype == "PUT_REF_TOP" else "bottom"
        who = params.get("player", "OWNER").upper()
        def _fn(card, event, state, _r=ref, _pos=pos, _w=who):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import put_object
            from engine.context import get_ref
            target = get_ref(_r)
            if not target:
                return
            cid = _controller_id(card)
            for obj in (target if isinstance(target, list) else [target]):
                if _w == "OWNER":
                    dest_pid = obj.owner
                elif _w in ("OPPONENT", "DEFENDING", "DEFENDER"):
                    dest_pid = 3 - cid
                else:
                    dest_pid = cid
                put_object(state, obj, "deck", destination_player_id=dest_pid,
                           source_player_id=cid,
                           position=("top" if _pos == "top" else None))
        return _fn

    if etype in ("TAP", "TAP_SELF", "TAP_TARGET"):
        # "{t} them" / "tap this". Goes through effect_keywords.tap (CR 8.5.55)
        # rather than setting card.tapped, so the TapEvent is emitted and a
        # replacement effect can intercept it — and so "already tapped" fails
        # rather than silently succeeding.
        #
        #   {"type":"TAP","target":"OPPONENT_HERO"}    — "{t} them"
        #   {"type":"TAP","target":"SELF"}             — the source card
        #
        # TAP_SELF is the spelling one card authored; it was never an effect
        # type, so the whole of goon_battery_blue failed to LOAD and every
        # ability on it, not just this one, was absent from the game.
        # "{t} THEM OR AN ALLY THEY CONTROL" is a choice between objects, which
        # no fixed string can name. A dict target is the canonical object spec
        # every other targeting effect now takes, so the card picks from a pool
        # rather than being pinned to one of the shorthands below.
        raw_target = params.get("target")
        object_fn = (_compile_object_target(_object_target_spec(raw_target))
                     if isinstance(raw_target, dict) else None)
        target = str(raw_target
                     or ("SELF" if etype == "TAP_SELF" else "OPPONENT_HERO")).upper()

        def _fn(card, event, state, _t=target, _of=object_fn):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import tap as _tap
            cid = _controller_id(card)
            if _of is not None:
                for obj in _of(card, event, state):
                    if obj is not None:
                        _tap(state, obj, source_player_id=cid)
                return
            if _t in ("SELF", "THIS", "SOURCE"):
                obj = card
            elif _t in ("OPPONENT_HERO", "DEFENDING_HERO", "THEM", "OPPONENT"):
                obj = state.players[3 - cid].hero
            elif _t in ("YOUR_HERO", "OWN_HERO"):
                obj = state.players[cid].hero
            else:
                return
            if obj is not None:
                _tap(state, obj, source_player_id=cid)
        return _fn

    if etype == "TAP_REF":
        # Tap (or, with untap:true, untap) a referenced card — "tap target ...".
        ref = params.get("ref", "chosen")
        untap = params.get("untap", False)
        def _fn(card, event, state, _r=ref, _u=untap):
            from engine.context import get_ref
            target = get_ref(_r)
            if not target:
                return
            for obj in (target if isinstance(target, list) else [target]):
                obj.tapped = not bool(_u)
        return _fn

    if etype in ("CONDITIONAL", "CONDITIONAL_EFFECT", "IF"):
        # Branch: run `then` effects if every `when` condition holds, else `else`.
        # Use "when" for the test (NOT "conditions" — the loader pops that key and
        # turns it into an effect-level gate, which would skip the whole branch and
        # never reach `else`). Inner specs are compiled lazily so an unimplemented
        # inner type defers to fire-time rather than breaking load.
        # "condition" is the third natural spelling of the test, and it was not
        # read — so six cards supplied a condition, got an EMPTY when-list, and
        # `ok` stayed True: the `then` branch ran every single time. An
        # unread test on a branch is the worst shape of unread parameter, because
        # the effect still happens and looks intended.
        when_raw = _first(params, "when", "if", "condition", default=[])
        # A single condition may be given bare rather than in a list.
        if isinstance(when_raw, dict):
            when_raw = [when_raw]
        then_raw = params.get("then", params.get("effects", []))
        else_raw = params.get("else", params.get("else_effects", []))
        def _fn(card, event, state, _w=when_raw, _t=then_raw, _e=else_raw):
            from engine.card_effects.dsl.condition_types import compile_condition as _cc
            ok = True
            for c in _w:
                fn = _cc((c.get("type") or "none"), c)
                if fn is not None and not fn(card, event, state):
                    ok = False
                    break
            for spec in (_t if ok else _e):
                compile_effect((spec.get("type") or "").upper(), spec)(card, event, state)
        return _fn

    if etype == "BANISH_REF":
        # Banish whatever a previous effect stored under "ref". Goes through the
        # canonical banish keyword (CR 8.5.1) so the event fires and replacement
        # effects can intercept it.
        # origin_zone must be passed or banish() leaves the card in place: it
        # only removes from the origin when told which one. LOOK_AT peeks
        # without moving cards, so unlike the old LOOK-then-banish pairing the
        # card is still in its zone when we get here.
        ref = params.get("ref", "chosen")
        # "zone" is the other natural spelling of the ORIGIN, and it was unread —
        # so those nodes passed None and banish() left the card in place while
        # also adding it to the banished zone: present in both at once.
        origin = _first(params, "from_zone", "zone", "from")
        face_down = bool(params.get("face_down"))

        def _fn(card, event, state, _r=ref, _origin=origin, _fd=face_down):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.context import get_ref
            from engine.effect_keywords import banish as _ek_banish
            target = get_ref(_r)
            if not target:
                return
            cid = _controller_id(card)
            for obj in (target if isinstance(target, list) else [target]):
                zone = _origin or getattr(obj, "zone", None)
                _ek_banish(state, obj, cid, origin_zone=zone, face_down=_fd)
        return _fn

    if etype == "REORDER_REF":
        # "Put the rest on top of their deck in any order." The controller
        # orders the referenced cards; the first chosen ends up on top.
        ref = params.get("ref", "rest")
        who = params.get("player", "OPPONENT").upper()
        def _fn(card, event, state, _r=ref, _w=who):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.context import get_ref
            cards = get_ref(_r) or []
            if not isinstance(cards, list) or len(cards) < 1:
                return
            cid = _controller_id(card)
            tid = (3 - cid) if _w in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            deck = state.players[tid].deck
            remaining = [c for c in cards if c in deck.cards]
            if not remaining:
                return
            ordered = []
            while remaining:
                if len(remaining) == 1:
                    ordered.append(remaining.pop())
                    break
                pick = _ask_player(state, cid, [c.slug for c in remaining],
                                   context="Choose the next card to place on top")
                target = next((c for c in remaining if c.slug == pick), remaining[0])
                remaining.remove(target)
                ordered.append(target)
            for c in ordered:
                deck.cards.remove(c)
            for c in reversed(ordered):
                c.zone = "deck"
                deck.cards.insert(0, c)
        return _fn

    if etype == "MAY":
        # "You may X. If you do, Y." — an optional block of sub-effects.
        #
        # Conditions gate whether the choice is offered at all; declining runs
        # nothing in the block, which is what makes "if you do" fall out for
        # free rather than needing its own conditional plumbing.
        # A "conditions" list on the MAY itself is popped by the loader into
        # EffectDef.conditions, so it already gates whether this effect runs at
        # all — the prompt is not even offered when it fails. Sub-effects are
        # compiled here, so their own "conditions" must be honoured explicitly;
        # compiling them without this would silently drop the gate.
        prompt = params.get("prompt", "Use this optional ability?")
        # A single sub-effect is often authored as "effect": {...} instead of
        # the list form; without this the block compiled empty and accepting
        # the prompt did nothing at all.
        sub_specs = params.get("effects") or []
        if not sub_specs and isinstance(params.get("effect"), dict):
            sub_specs = [params["effect"]]
        from engine.card_effects.dsl.condition_types import compile_condition

        def _compile_block(specs):
            out = []
            for spec in specs or []:
                sub_params = {k: v for k, v in spec.items() if k != "type"}
                gate_specs = sub_params.pop("conditions", []) or []
                gates = [compile_condition(g.get("type", "").upper(),
                                           {k: v for k, v in g.items() if k != "type"})
                         for g in gate_specs]
                out.append((compile_effect(spec.get("type", "").upper(), sub_params), gates))
            return out

        subs = _compile_block(sub_specs)
        # "Lose 2{h} UNLESS you discard a card" — declining is not always free.
        # Without an else block the penalty had to be authored as a separate
        # effect with its own inverted condition, and there is nothing to invert
        # against: the choice is not recorded anywhere.
        alts = _compile_block(params.get("else") or params.get("else_effects"))
        # "You may PAY {r}. If you do, this gets +1{p}." The cost was not read,
        # so the prompt was free and the bonus unconditional — the card was
        # strictly stronger than printed. A cost inside a MAY is not the same as
        # an ability-level cost: it gates the OPTION, not the ability, so it
        # belongs here rather than in AbilityDef.costs.
        from engine.card_effects.dsl.cost_types import compile_cost
        cost_specs = params.get("cost") or params.get("costs") or []
        if isinstance(cost_specs, dict):
            cost_specs = [cost_specs]
        costs = [compile_cost(str(c.get("type") or "").upper(),
                              {k: v for k, v in c.items() if k != "type"})
                 for c in cost_specs if isinstance(c, dict)]

        def _fn(card, event, state, _s=subs, _p=prompt, _alt=alts, _costs=costs):
            from engine.card_effects.ability_keywords import ask_yes_no, _controller_id
            cid = _controller_id(card)
            # Not payable => the option is not on the table, and the else block
            # (the "unless you ..." penalty) is what happens.
            payable = all(check is None or check(card, event, state)
                          for check, _pay in _costs)
            take_it = payable and ask_yes_no(state, cid, context=_p)
            if take_it:
                for _check, pay in _costs:
                    if pay is not None:
                        pay(card, event, state)
            chosen = _s if take_it else _alt
            for fn, gates in chosen:
                if fn is None:
                    continue
                if all(g is None or g(card, event, state) for g in gates):
                    fn(card, event, state)
        return _fn

    if etype == "TRANSCEND":
        # CR 8.5.48 — "**transcend**": put the transcend source into its owner's
        # hand with its back-face active. The source is THIS card unless the JSON
        # names another. Routed through the canonical keyword function so the
        # transcend event is emitted (ON_TRANSCEND listeners) and "you have
        # transcended this turn" is recorded; 13 checker cards read that.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import transcend as _transcend
            if card is None:
                return
            _transcend(state, card, _controller_id(card))
        return _fn

    if etype == "TRANSFORM":
        # CR 8.5.36 — "**transform** up to 1 ash you control into an Aether
        # Ashwing", "transform target Mechanologist head, chest, arms, legs,
        # weapon and 3 Hyper Drivers into Nitro Mechanoid".
        #
        # Three cards authored this as TRANSFORM_HERO, which is Arakni's
        # "become a random Agent of Chaos" and does something else entirely —
        # a real type doing the WRONG thing, which no type-name audit can catch
        # and which the unread `to`/`from` parameters were the only hint of.
        #
        # `from` names what to consume (a token slug or subtype); `amount` how
        # many; `to` what to become. 8.5.36d makes it all-or-nothing, which the
        # keyword enforces.
        into = _first(params, "to", "into", "transform_to", "token",
                      "target_token", default="")
        source = _first(params, "from", "source", "subtype", default="")
        amount = _first(params, "amount", "count", "max_count", default=1)
        optional = bool(params.get("up_to", True))
        # One permanent per source ("into Aether AshwingS") vs all sources under
        # one permanent ("into Nitro Mechanoid"). The card text distinguishes
        # them by pluralising the target, and they are different board states.
        each = bool(params.get("each"))

        # "transform target Mechanologist head, chest, arms, legs, weapon AND 3
        # Hyper Drivers into Nitro Mechanoid" — several different requirements
        # at once, and equipment lives in the slot zones, never in `permanents`.
        # Authored as "sources": [{"zone": "head"}, ..., {"from": "hyper_driver",
        # "amount": 3}]. 8.5.36d applies across the whole set: if any part is
        # missing, nothing transforms.
        source_specs = params.get("sources")

        def _fn(card, event, state, _into=into, _src=source, _a=amount,
                _opt=optional, _specs=source_specs, _each=each):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            cid = _controller_id(card)
            if cid not in state.players or not _into:
                return
            player = state.players[cid]

            def _match(c, want):
                return (not want
                        or _norm_amt(getattr(c, "slug", "")) == want
                        or _norm_amt(getattr(c, "name", "")) == want
                        or want in {_norm_amt(x) for x in (getattr(c, "subtypes", None) or [])})

            if _specs:
                gathered = []
                for spec in _specs:
                    zone_name = (spec.get("zone") or "permanents").lower()
                    zone = getattr(player, zone_name, None)
                    if zone is None:
                        return
                    want_s = _norm_amt(spec.get("from") or spec.get("subtype") or "")
                    try:
                        n = int(spec.get("amount", spec.get("count", 1)))
                    except (TypeError, ValueError):
                        n = 1
                    picks = [c for c in zone.cards
                             if _match(c, want_s) and c not in gathered][:n]
                    if len(picks) < n:
                        return          # 8.5.36d — a missing part fails it all
                    gathered.extend(picks)
                if gathered:
                    _do_transform(state, gathered, str(_into), cid)
                return

            want = _norm_amt(_src)
            pool = [c for c in player.permanents.cards if _match(c, want)]
            try:
                need = int(_resolve_amount(_a, state, card)
                           if isinstance(_a, dict) else _a)
            except (TypeError, ValueError):
                need = 1
            if len(pool) < need and not _opt:
                return          # 8.5.36d — cannot complete, so nothing happens
            need = min(need, len(pool)) if _opt else need
            chosen = []
            for _ in range(max(need, 0)):
                remaining = [c for c in pool if c not in chosen]
                if not remaining:
                    break
                if len(remaining) == 1:
                    pick_card = remaining[0]
                else:
                    options = [c.slug for c in remaining] + (["none"] if _opt else [])
                    pick = _ask_player(state, cid, options,
                                       context=f"Choose a {_src or 'permanent'} to transform")
                    if pick == "none":
                        return
                    pick_card = next((c for c in remaining if c.slug == pick),
                                     remaining[0])
                chosen.append(pick_card)
            if len(chosen) < need and not _opt:
                return
            if not chosen:
                return
            if _each:
                # "transform up to 3 ash into Aether AshwingS" — plural, so each
                # ash becomes its own Ashwing. Passing all three to one call
                # would instead stack them under a SINGLE Ashwing, which is a
                # different board state and a strictly worse one for the player.
                for one in chosen:
                    _do_transform(state, [one], str(_into), cid)
            else:
                _do_transform(state, chosen, str(_into), cid)
        return _fn

    if etype == "TRANSFORM_HERO":
        # Arakni: "become a random Agent of Chaos" / "return to the brood".
        # choose=true lets the controller pick the form (e.g. Mask of Deceit when
        # the attacking hero is marked) instead of a random one.
        # `target`/`form` are read as spellings of `mode` because both cards
        # that got this wrong reached for `target`. An unrecognised form RAISES
        # rather than falling back to the default: invoke_azvolai_red authored
        # "target": "Ash" meaning the PERMANENT transform, and a silent default
        # turned the controller's hero into an Agent of Chaos. A load failure
        # names the card; a wrong default is invisible.
        mode = str(_first(params, "mode", "target", "form",
                          default="random_agent_of_chaos")).lower()
        if mode not in _HERO_TRANSFORM_MODES:
            raise ValueError(
                f"TRANSFORM_HERO mode {mode!r} is not a hero form (expected one "
                f"of {sorted(_HERO_TRANSFORM_MODES)}). Transforming a PERMANENT "
                f"into a token is the TRANSFORM effect, which takes from/to.")
        choose = params.get("choose", False)
        def _fn(card, event, state, _m=mode, _ch=choose):
            from engine.card_effects.ability_keywords import (
                _controller_id, become_agent_of_chaos, return_to_brood)
            pid = _controller_id(card)
            if _m == "return_to_brood":
                return_to_brood(state, pid)
            else:
                become_agent_of_chaos(state, pid, choose=_ch)
        return _fn

    if etype == "SET_BASE_POWER":
        # "Target attack action card you control has N base {p}" (e.g. Kayo).
        # The target is an attack action card the controller controls in the
        # current combat — the active attack OR a card they're defending with.
        # If several qualify, the controller chooses. Only attack ACTION cards
        # qualify (no weapons).
        amount = params.get("amount", 0)
        def _fn(card, event, state, _amt=amount):
            from engine.card_effects.ability_keywords import (
                _controller_id, controlled_attack_action_cards, _ask_player)
            if not state.combat:
                return
            cid = _controller_id(card)
            candidates = controlled_attack_action_cards(state, cid)
            if not candidates:
                return
            # Prefer the target declared at activation (CR 5.1.4) if it is a
            # legal candidate; otherwise use the sole candidate or ask.
            declared = getattr(event, 'target', None) if event is not None else None
            target = next((c for c in candidates if c is declared), None)
            if target is None:
                if len(candidates) == 1:
                    target = candidates[0]
                else:
                    pick = _ask_player(state, cid, [c.slug for c in candidates],
                                       context="Choose the attack action card to set to "
                                               f"{_amt} base power")
                    target = next((c for c in candidates if c.slug == pick), candidates[0])
            target.base_power = _amt
            # When the target is the active attack, recalculate rather than
            # overwrite: setting BASE power (stage 7) must leave later "+{p}"
            # modifiers (stage 8, e.g. Reckless Arithmetic's rolled +X on
            # power_mods) applied on top. Base 6 + rolled 3 = 9, not 6.
            if target is state.combat.attack_card:
                state.combat.base_attack_power = _amt
                from engine import engine as _E
                _E._recalculate_attack_power(state)
        return _fn

    if etype == "REPLACE_NEXT_POWER_GAIN":
        # "The next time an attack would gain {p} this turn, INSTEAD it gains
        # that much plus 2." A replacement on the gain, consumed by the first
        # gain of the turn — see apply_power_gain_replacements.
        try:
            bonus = int(params.get("amount", 0))
        except (TypeError, ValueError):
            bonus = 0

        def _fn(card, event, state, _b=bonus):
            if not hasattr(state, "_power_gain_replacements"):
                state._power_gain_replacements = []
            state._power_gain_replacements.append({"bonus": _b})
        return _fn

    if etype in ("MAKE_NEXT_DAMAGE_UNPREVENTABLE", "UNPREVENTABLE_NEXT"):
        # "The next <source> effect that would deal damage this turn CAN'T BE
        # PREVENTED." DamageEvent.unpreventable already existed and effects.py
        # already honoured it — nothing ever SET it, and the flag was read once
        # before the replacement loop, so setting it mid-loop was ignored.
        # Registered as a STANDARD replacement, which runs before PREVENTION.
        source_slug = _norm_amt(params.get("source_slug") or params.get("source") or "")
        # "{p} damage can't be prevented THIS COMBAT CHAIN" is not "the NEXT
        # damage": it holds for every hit on the chain, and only for PHYSICAL
        # damage. step_between_red authored that clause as WARD, which PREVENTS
        # damage -- the exact opposite of what the card says.
        scope = str(_first(params, "scope", "duration",
                           default="next")).lower()
        want_type = _norm_amt(_first(params, "damage_type", "type", default=""))

        def _fn(card, event, state, _slug=source_slug, _scope=scope,
                _wt=want_type):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effects import ReplacementEffect, ReplacementType
            cid = _controller_id(card)
            used = {"done": False}

            # A chain-scoped clause has to stop when the chain does. The combat
            # object is captured by identity: once state.combat is a different
            # object (or None) the chain it named is over.
            chain = id(getattr(state, "combat", None)) if _scope in (
                "combat_chain", "chain", "this_combat_chain") else None

            def _cond(ev, st, _s=_slug, _u=used, _cid=cid, _sc=_scope,
                      _chain=chain, _t=_wt):
                if not isinstance(ev, dict):
                    return False
                if _chain is not None:
                    if id(getattr(st, "combat", None)) != _chain:
                        return False
                elif _u["done"]:
                    return False
                if ev.get("type") != "damage" or (ev.get("amount") or 0) <= 0:
                    return False
                if ev.get("source_player_id") != _cid:
                    return False
                if _t:
                    dt = ev.get("damage_type")
                    if _norm_amt(getattr(dt, "value", dt)) != _t:
                        return False
                if _s:
                    src = ev.get("damage_source_card") or ev.get("source_card")
                    return _norm_amt(getattr(src, "slug", "") or "") == _s
                return True

            def _repl(ev, st, _u=used, _sc=_scope):
                # A chain-scoped clause must NOT burn itself on the first hit.
                if _sc not in ("combat_chain", "chain", "this_combat_chain"):
                    _u["done"] = True
                ev["unpreventable"] = True
                return ev

            state.effect_manager.add_replacement(ReplacementEffect(
                source_card=card, replacement_type=ReplacementType.STANDARD,
                condition_fn=_cond, replace_fn=_repl, owner_id=cid))
        return _fn

    if etype == "MODIFY_ATTACK":
        mod = params.get("mod", "add")
        amt = params.get("amount", 0)
        def _fn(card, event, state, _mod=mod, _a=amt):
            if not state.combat:
                return
            val = _resolve_amount(_a, state, card)
            if _mod not in ("set", "multiply"):
                # A GAIN, so it is replaceable ("instead it gains that much
                # plus 2"). Setting or multiplying is not a gain.
                val = apply_power_gain_replacements(state, val, card)
            # WHILE_STATIC abilities re-run this on every _recalculate_attack_power
            # (event type 'recalculate_attack_power'); those must apply transiently
            # in the stage-8 window and NOT accumulate on power_mods.
            if getattr(event, "type", None) == "recalculate_attack_power":
                if _mod == "set":
                    state.combat.attack_power = val
                elif _mod == "multiply":
                    state.combat.attack_power = (state.combat.attack_power or 0) * val
                else:
                    state.combat.attack_power = (state.combat.attack_power or 0) + val
                return
            # One-shot trigger (e.g. Reckless Arithmetic's "when this attacks,
            # +X{p}"): record on the CombatState so it is re-applied on every
            # future recalculation and survives the defend/damage steps (the
            # amount is fixed now, e.g. the rolled X), AND apply it to the live
            # power now for immediate visibility. A later recalc re-derives from
            # base + power_mods, so this immediate bump is not double-counted.
            state.combat.power_mods.append((_mod, val))
            if _mod == "set":
                state.combat.attack_power = val
            elif _mod == "multiply":
                state.combat.attack_power = (state.combat.attack_power or 0) * val
            else:
                state.combat.attack_power = (state.combat.attack_power or 0) + val
        return _fn

    if etype == "DOUBLE_BASE_POWER":
        # "This card's base {p} is doubled." Modeled as adding the current base
        # power to the attack (doubling base = +base to the total). Authored as a
        # WHILE_STATIC so it re-applies on every recalculation and stacks on top of
        # a SET-base effect in timestamp order — e.g. Kayo sets base 6, then this
        # adds 6 → 12. Gate with SOURCE_IS_ATTACK so it only affects this card's
        # own attack.
        def _fn(card, event, state):
            combat = state.combat
            if not combat or not combat.attack_card:
                return
            base = combat.attack_card.base_power or 0
            combat.attack_power = (combat.attack_power or 0) + base
        return _fn

    if etype == "CREATE_MIGHT_PER_GOLD":
        # Visit the Goldmane Estate: "if you control 3 or more Gold, create that
        # many Might tokens." Counts real Gold tokens AND permanents that count as
        # a Gold (subtype match, e.g. Aurum Aegis).
        threshold = params.get("threshold", 3)
        def _fn(card, event, state, _th=threshold):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import create_token as _ct
            cid = _controller_id(card)
            player = state.players[cid]
            n = 0
            for zn in ('permanents', 'head', 'chest', 'arms', 'legs',
                       'weapon1', 'weapon2'):
                z = getattr(player, zn, None)
                if not z:
                    continue
                for t in z.cards:
                    if (getattr(t, 'slug', '') == 'gold'
                            or 'gold' in [s.lower() for s in (getattr(t, 'subtypes', None) or [])]):
                        n += 1
            if n >= _th:
                _ct(state, target_player_id=cid, token_slug='might', number=n)
        return _fn

    if etype == "REVEAL_REVILED_FROM_INVENTORY":
        # Outside Interference: "You may reveal a Reviled attack action card from
        # your inventory and put it into your hand."
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            cid = _controller_id(card)
            controller = state.players[cid]
            inv = getattr(controller, 'inventory', None)
            if inv is None:
                return
            reviled = [c for c in inv.cards
                       if 'reviled' in [t.lower() for t in (c.types or [])]
                       and 'attack' in [s.lower() for s in (c.subtypes or [])]]
            if not reviled:
                return
            from engine.card_effects.ability_keywords import ask_optional
            pick = ask_optional(state, cid, [c.slug for c in reviled],
                                context="Reveal a Reviled attack action from your inventory?")
            if pick is None:
                return
            target = next((c for c in reviled if c.slug == pick), reviled[0])
            inv.remove(target)
            target.is_public = True
            controller.hand.add(target)
        return _fn

    if etype in ("GRANT_PLAY_FROM_BANISHED", "PLAYABLE_FROM_BANISHED_REF"):
        # "If you do, it gets +1{p} and you MAY PLAY IT THIS TURN" — the payoff
        # half of a banish-then-play card, acting on the card the BANISH just
        # took rather than re-searching the zone for something that matches.
        #
        # mounting_anger_red re-filtered the whole banished zone for each half,
        # so with two eligible cards sitting there it could pump one and
        # unlock a different one. `player.playable_from_banished` is the list
        # play.py actually consults; SET_FLAG appends a STRING to
        # current_turn_effects and nothing reads it, so the card's own "you may
        # play it" clause reached the game state nowhere at all.
        ref_name = _first(params, "ref", "record_as", "target_ref",
                          default="banished")
        power_mod = _first(params, "power_mod", "power", "amount", default=0)

        def _fn(card, event, state, _ref=ref_name, _pm=power_mod):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.context import get_ref
            cid = _controller_id(card)
            if cid not in state.players:
                return
            target = get_ref(_ref)
            if isinstance(target, list):
                targets = list(target)
            elif target is None:
                return
            else:
                targets = [target]
            try:
                bump = int(_resolve_amount(_pm, state, card))
            except (TypeError, ValueError):
                bump = 0
            for obj in targets:
                if obj is None:
                    continue
                if bump:
                    # The card is not on the chain yet, so a combat-scoped power
                    # modifier has nothing to attach to; the bump has to travel
                    # with the OBJECT until it is played.
                    for attr in ("base_power", "power"):
                        cur = getattr(obj, attr, None)
                        if cur is not None:
                            setattr(obj, attr, cur + bump)
                state.players[cid].playable_from_banished.append(obj)
        return _fn

    if etype == "BANISH_OPP_TOP_GRANT_PLAY":
        # Infiltrate: "banish the top card of their deck. You may play it until
        # the end of your next turn." The banished card is the opponent's; the
        # attacker (this card's controller) may play it from banish. The exact
        # two-turn deadline is approximated by the start-of-turn clear of
        # playable_from_banished.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import banish as _banish
            cid = _controller_id(card)
            opp = state.players[3 - cid]
            if not opp.deck.cards:
                return
            top = opp.deck.cards[0]
            _banish(state, top, cid, origin_zone="deck")
            if top in opp.banished.cards:
                state.players[cid].playable_from_banished.append(top)
        return _fn

    if etype == "BANISH_TRAP_FROM_GRAVEYARD_PLAYABLE":
        # Under the Trap-Door: "Banish target trap from your graveyard. If you do,
        # you may play it this turn, and if it would be put into the graveyard
        # this turn, instead banish it." The graveyard->banish rider IS modeled
        # below via the gy_to_banish_<object_id> flag that engine._to_graveyard
        # honours (an earlier version of this comment wrongly said it was not).
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import banish as _banish
            cid = _controller_id(card)
            controller = state.players[cid]
            traps = [c for c in controller.graveyard.cards
                     if "trap" in [s.lower() for s in (c.subtypes or [])]]
            if not traps:
                return
            from engine.card_effects.ability_keywords import ask_optional
            pick = ask_optional(state, cid, [c.slug for c in traps],
                                context="Banish a trap from your graveyard to play it this turn?")
            if pick is None:
                return
            target = next((c for c in traps if c.slug == pick), None)
            if target is None:
                return
            _banish(state, target, cid, origin_zone="graveyard")
            if target in controller.banished.cards:
                controller.playable_from_banished.append(target)
                # "if it would be put into the graveyard this turn, instead banish
                # it" — engine._to_graveyard honours this per-card, turn-scoped flag.
                controller.current_turn_effects.append(f"gy_to_banish_{target.object_id}")
        return _fn

    if etype == "REDUCE_TOKEN_CREATION_THIS_TURN":
        # Ripple Away: "If an action card effect would create 1 or more tokens this
        # turn, instead it creates that many minus 1 of each of those tokens."
        # Registers a turn-scoped replacement that decrements CreateTokenEvent.number.
        def _fn(card, event, state):
            from engine.effects import ReplacementEffect, ReplacementType
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            controller = state.players[cid]
            flag = "ripple_away_active"
            if flag not in controller.current_turn_effects:
                controller.current_turn_effects.append(flag)
            def _cond(ev, s, _cid=cid, _flag=flag):
                if not (isinstance(ev, dict) and 'target_player_id' in ev
                        and (ev.get('number') or 0) >= 1
                        and _flag in s.players[_cid].current_turn_effects):
                    return False
                # Only "an action card effect" — check the card whose ability is
                # currently creating the token.
                from engine.context import current_effect_source
                src = current_effect_source()
                return src is not None and 'Action' in (getattr(src, 'types', None) or [])
            def _repl(ev, s):
                ev['number'] = max(0, (ev.get('number') or 0) - 1)
                return ev
            state.effect_manager.add_replacement(ReplacementEffect(
                source_card=card, replacement_type=ReplacementType.STANDARD,
                condition_fn=_cond, replace_fn=_repl, owner_id=cid))
        return _fn

    if etype == "MAY_DESTROY_SILVERS_TO_EQUIP":
        # Blacktek Whisperers graveyard static: "you may destroy N Silvers you
        # control. If you do, equip this (from the graveyard)."
        amount = params.get("amount", 2)
        def _fn(card, event, state, _n=amount):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import destroy as _destroy, equip as _equip
            cid = _controller_id(card)
            player = state.players[cid]
            silvers = [t for zn in ('permanents', 'items', 'tokens')
                       for t in getattr(player, zn, player.permanents).cards
                       if getattr(t, 'slug', '') == 'silver']
            # de-dupe (items can be a view of permanents)
            seen, uniq = set(), []
            for s in silvers:
                if id(s) not in seen:
                    seen.add(id(s)); uniq.append(s)
            if len(uniq) < _n:
                return
            from engine.card_effects.ability_keywords import ask_yes_no
            if not ask_yes_no(state, cid,
                              context=f"Destroy {_n} Silvers to equip Blacktek Whisperers?"):
                return
            for s in uniq[:_n]:
                _destroy(state, s, card)
            slot = next((sl for sl in ("head", "chest", "arms", "legs")
                         if sl.title() in (card.subtypes or [])), "arms")
            _equip(state, card, slot, cid)
        return _fn

    if etype == "GRANT_SUBTYPE":
        # "This counts as a <subtype>" (e.g. Aurum Aegis counts as a Gold). Adds
        # the subtype to this card so subtype-aware checks (CONTROLS_TOKEN_TYPE)
        # see it. Applied on equip; the subtype persists while the card is in play.
        subtype = params.get("subtype", "")
        def _fn(card, event, state, _sub=subtype):
            if not _sub:
                return
            subs = list(card.subtypes or [])
            if _sub not in subs:
                subs.append(_sub)
                card.subtypes = subs
        return _fn

    if etype in ("BLOCK_DEFENSE_REACTIONS", "NO_DEFENSE_REACTIONS"):
        # "Defense reaction cards can't be played this chain link."
        #
        # combat.no_defense_reactions is READ in four places -- play.py's
        # reaction-step offer and _defense_reaction_legal_check, and actions.py
        # for hand and arsenal -- and was SET BY NOTHING. The three cards with
        # this text wrote a dead SET_FLAG instead, under TWO different names
        # (DEFENSE_REACTION_BLOCKED and command_and_conquer_no_dr), so they
        # looked implemented and blocked nothing.
        #
        # Same shape as DamageEvent.unpreventable: the reader existed, the
        # writer did not.
        def _fn(card, event, state):
            if state.combat is not None:
                state.combat.no_defense_reactions = True
        return _fn

    if etype in ("RESTRICT_DEFENDERS", "RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT"):
        # "This can't be defended by <X>." The filter names the cards that may
        # NOT defend; get_defendable_cards drops anything matching it.
        #
        #   {"type":"RESTRICT_DEFENDERS","equipment":true}       — Lay Waste
        #   {"type":"RESTRICT_DEFENDERS","non_head_equipment":true} — Headbutt
        #   {"type":"RESTRICT_DEFENDERS","subtype":"Attack",
        #    "cost_lt":{"type":"COUNT_PERMANENT","subtype":"Evo",
        #               "zone":"EQUIPMENT"}}                     — Heavy Artillery
        #
        # RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT stays as sugar for Headbutt's
        # filter, but it is no longer the only shape available — eight cards had
        # used it to mean six different things, because it was all there was.
        spec = {k: v for k, v in params.items() if k != "type"}
        # Headbutt's spelling with no filter of its own means its own filter.
        # Written as a membership test rather than `etype == "..."`, which the
        # shadowed-type scan reads as a SECOND registration of the name — and
        # that check earns its false positives: a duplicate handler is dead code
        # that cards silently route past.
        _is_headbutt_sugar = etype.endswith("HEAD_EQUIPMENT")
        if _is_headbutt_sugar and not spec:
            spec = {"non_head_equipment": True}

        def _fn(card, event, state, _spec=spec):
            combat = state.combat
            if combat is None:
                return
            resolved = dict(_spec)
            # A threshold may be an expression ("cost less than X, where X is
            # the number of Evos you have equipped"), and it is fixed at the
            # moment the restriction is created.
            for key in ("cost_lt", "cost_lte", "cost_gt", "cost_gte"):
                if isinstance(resolved.get(key), dict):
                    try:
                        resolved[key] = int(_resolve_amount(resolved[key], state, card))
                    except (TypeError, ValueError):
                        resolved.pop(key)
            if resolved not in combat.defender_restrictions:
                combat.defender_restrictions.append(resolved)
        return _fn

    if etype == "CRUSH_MINUS_DEF_OPP_HEAD":
        # Headbutt's Crush: "put a -1{d} counter on a head they have equipped,
        # then if it has 0{d}, destroy it." Applies to the defending hero's head.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import destroy as _destroy
            opp = state.players[3 - _controller_id(card)]
            head = opp.head.cards[0] if opp.head.cards else None
            if head is None:
                return
            # Was also decrementing base_defense — the PRINTED value — which
            # is the only thing the defence recalc resets to, so a second
            # Crush permanently rewrote the card. The counter is the record.
            from engine.card_effects.ability_keywords import _apply_defense_counter
            _apply_defense_counter(head, state, 1)
            if (head.defense or 0) <= 0:
                _destroy(state, head, card)
        return _fn

    if etype == "MODIFY_ATTACK_PER_HIGH_DEFENDER":
        # Show of Strength: "This gets -1{p} for each card with 6 or more {p}
        # defending it." Authored as a WHILE_STATIC, so it re-evaluates each
        # recalculation as defenders are declared. Gate with SOURCE_IS_ATTACK.
        per = params.get("amount", -1)
        threshold = params.get("threshold", 6)
        def _fn(card, event, state, _per=per, _th=threshold):
            combat = state.combat
            if not combat:
                return
            n = sum(1 for d in combat.defending_cards if (d.power or 0) >= _th)
            if n:
                combat.attack_power = (combat.attack_power or 0) + _per * n
        return _fn

    if etype == "CLASH_DESTROY_TOP_OR_COUNTER":
        # Miller's Grindstone: "When this hits a hero, clash with them. If you win,
        # destroy the top card of their deck. If they win, put a -1{p} counter on
        # this." (Miller's is the attacker; its controller clashes the defender.)
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import clash as _clash, destroy as _destroy
            cid = _controller_id(card)
            opp = 3 - cid
            ev = _clash(state, cid, opp)
            if ev.winner_id == cid:
                deck = state.players[opp].deck
                if deck.cards:
                    _destroy(state, deck.cards[0], card)
            elif ev.winner_id == opp:
                card.counters["power"] = card.counters.get("power", 0) - 1
        return _fn

    if etype == "EACH_HERO_ARSENAL_FROM_ZONE_THEN_DISCARD":
        # Codex of Frailty / Inertia: "Each hero puts a card [from graveyard /
        # top of deck] face down into their arsenal. Each hero that does, discards
        # a card." source: "graveyard" (attack action cards) | "deck" (top card).
        # "zone" is the same thing as "source" and was unread, so those nodes
        # fell through to the deck default and took the top card instead of the
        # graveyard card the text names.
        source = _first(params, "source", "zone", "from_zone", default="deck")
        # "THEN DISCARD" is in the NAME, so it fired for every card using this
        # type -- including the two Promise of Plenty variants, whose text says
        # nothing about discarding. Both players were made to discard at random,
        # a symmetric invented downside that hurt the caster too. Codex of
        # Frailty and Inertia DO discard, so the default stays True and the
        # cards that do not say it turn it off.
        do_discard = params.get("discard", True)
        # The handler already stamps the card face down (and arsenal.add does
        # too), so `face_down` names what happens -- read it anyway rather than
        # declaring it inert, because an exemption is a claim about behaviour
        # that goes stale, and a card saying face_down:false deserves an answer.
        face_down = bool(params.get("face_down", True))
        # "each hero WHO DOESN'T HAVE A CARD IN THEIR ARSENAL" is the built-in
        # arsenal-limit check below; a card spelling it out explicitly gets it
        # compiled and applied per player rather than silently ignored.
        cond_spec = params.get("condition")
        cond_fn = None
        if isinstance(cond_spec, dict) and cond_spec.get("type"):
            from engine.card_effects.dsl.condition_types import compile_condition
            cond_fn = compile_condition(cond_spec["type"], cond_spec)

        def _fn(card, event, state, _src=source, _disc=do_discard,
                _fd=face_down, _cond=cond_fn):
            from engine.card_effects.ability_keywords import _ask_player, effect_discard
            for pid, player in state.players.items():
                if len(player.arsenal.cards) >= getattr(player, 'arsenal_limit', 1):
                    continue
                if _cond is not None:
                    # The gate asks about THIS hero, so it is evaluated with a
                    # stand-in whose controller is that player.
                    probe = _ConditionProbe(pid)
                    try:
                        if not _cond(probe, event, state):
                            continue
                    except Exception:
                        pass
                target = None
                if _src == "graveyard":
                    attacks = [c for c in player.graveyard.cards
                               if 'attack' in [s.lower() for s in (c.subtypes or [])]]
                    if not attacks:
                        continue
                    from engine.card_effects.ability_keywords import ask_optional
                    pick = ask_optional(state, pid, [c.slug for c in attacks],
                                        context="Put an attack action from your graveyard facedown into arsenal?")
                    if pick is None:
                        continue
                    target = next((c for c in attacks if c.slug == pick), None)
                    if target is not None:
                        player.graveyard.remove(target)
                else:  # top of deck
                    if not player.deck.cards:
                        continue
                    target = player.deck.cards.pop(0)
                if target is None:
                    continue
                player.arsenal.add(target)
                target.face_down = _fd
                target.is_public = not _fd
                if _disc and player.hand.cards:
                    # "each hero that does, discards a card"
                    effect_discard(state, pid, 1, random_discard=True)
        return _fn

    if etype == "EACH_HERO_SHUFFLE_TOP_TO_ARSENAL":
        # Schism of Chaos: "each hero shuffles, then puts the top card of their
        # deck facedown into their arsenal."
        def _fn(card, event, state):
            from engine.effect_keywords import shuffle as _shuffle
            for pid, player in state.players.items():
                _shuffle(state, pid)
                limit = getattr(player, 'arsenal_limit', 1)
                if player.deck.cards and len(player.arsenal.cards) < limit:
                    top = player.deck.cards.pop(0)
                    player.arsenal.add(top)
                    top.face_down = True
                    top.is_public = False
        return _fn

    if etype == "MODIFY_NEXT_ATTACK":
        mod = params.get("mod", "add")
        amt = params.get("amount", 0)
        # "filter" holds raw condition specs describing which future attacks qualify.
        # Using "filter" (not "conditions") so the loader does not pop these as
        # EffectDef gate conditions — they are pass-through data for the engine.
        filter_specs = params.get("filter", [])
        # scope: "TURN" (default) | "CHAIN". "This combat chain" is narrower than
        # "this turn" — a chain-scoped one-shot must not survive into the next
        # attack chain of the same turn. Cleared at chain close.
        scope = str(params.get("scope") or "TURN").upper()

        def _fn(card, event, state, _mod=mod, _a=amt, _filt=filter_specs,
                _scope=scope):
            # Queue on the card's controller, not the turn player — an
            # instant-speed card using this effect must buff its own controller.
            from engine.card_effects.ability_keywords import _controller_id
            player = state.players[_controller_id(card)]
            if not hasattr(player, 'dsl_queued_attack_mods'):
                player.dsl_queued_attack_mods = []
            player.dsl_queued_attack_mods.append({
                "mod": _mod,
                "amount": _resolve_amount(_a, state, card),
                "filter": _filt,
                "scope": _scope,
            })
        return _fn

    if etype in ("GRANT_INSTANT_TIMING", "PLAY_NEXT_AS_INSTANT"):
        # "You may play your next <X> this turn AS THOUGH IT WERE AN INSTANT."
        # Instant TIMING, not an instant ability: the card skips the action-speed
        # restriction. One-shot, filtered the same way the other queues are.
        filter_specs = params.get("filter", [])

        def _fn(card, event, state, _f=filter_specs):
            from engine.card_effects.ability_keywords import _controller_id
            player = state.players[_controller_id(card)]
            if not hasattr(player, 'dsl_instant_timing_grants'):
                player.dsl_instant_timing_grants = []
            player.dsl_instant_timing_grants.append({"filter": _f})
        return _fn

    if etype in ("MODIFY_NEXT_DEFENSE", "GRANT_NEXT_DEFENSE"):
        # "The next action card they defend with this combat chain gets -1{d}",
        # "the next action card you defend with gets +1{d}". A card used to
        # DEFEND passes through neither the attack queue (consumed by attacks)
        # nor the play-time queue (consumed by cards being played), so this had
        # no queue at all and could only be written turn-long — weakening or
        # strengthening EVERY block instead of one.
        #
        # `player`: SELF (default) or OPPONENT — the defender whose next block is
        # affected, which for "they defend with" is the opponent.
        amount = params.get("amount", 0)
        filter_specs = params.get("filter", [])
        who = str(params.get("player") or "SELF").upper()
        scope = str(params.get("scope") or "TURN").upper()

        def _fn(card, event, state, _a=amount, _f=filter_specs, _w=who, _s=scope):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            pid = (3 - cid) if _w in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            if pid not in state.players:
                return
            player = state.players[pid]
            if not hasattr(player, 'dsl_queued_defense_mods'):
                player.dsl_queued_defense_mods = []
            player.dsl_queued_defense_mods.append({
                "amount": _resolve_amount(_a, state, card),
                "filter": _f,
                "scope": _s,
            })
        return _fn

    if etype in ("MODIFY_NEXT_CARD_COST", "MODIFY_NEXT_CARD", "GRANT_NEXT_CARD"):
        # "The NEXT blue card you play this turn costs {r} less to play."
        # Queued as a one-shot on the controller and consumed by the first card
        # matching "filter" — the only correct shape for "next". As a turn-long
        # flag plus a flag-gated cost modifier it would discount EVERY blue card
        # for the rest of the turn.
        #
        # "on_consume" effects run against the card that used the reduction,
        # which is how "...THAT card deals 1 more damage" can name a card nobody
        # has chosen yet.
        #
        # `keyword`/`keywords` grant to that card instead of (or as well as)
        # reducing its cost: "the next blue ACTION card you play this turn gets
        # go again" names cards that may never attack, so the ATTACK queue
        # (GRANT_NEXT_ATTACK) cannot express it — that queue is only consumed
        # when an attack is made.
        amount = params.get("amount", 1)
        filter_specs = params.get("filter", [])
        on_consume = params.get("on_consume", [])

        keywords = params.get("keywords") or (
            [params["keyword"]] if params.get("keyword") else [])

        # "The next 3 Draconic cards you play this turn cost {r} less" — one
        # entry with three uses, not three entries and not a turn-long effect.
        # Without it the reduction applies once and the other two are lost.
        try:
            uses = int(params.get("uses", 1) or 1)
        except (TypeError, ValueError):
            uses = 1

        # "is Draconic" / "is Illusionist in addition to its other class types"
        grant_classes = params.get("grant_classes") or (
            [params["grant_class"]] if params.get("grant_class") else [])
        # A whole ABILITY granted to whichever card consumes this (see
        # Card.granted_abilities). Raw dicts; compiled when they fire.
        grant_abilities = params.get("grant_abilities") or (
            [params["grant_ability"]] if params.get("grant_ability") else [])

        # "Your next attack WITH IT this turn costs {r} less to activate" — the
        # queue matches on card PROPERTIES, which cannot distinguish one sword
        # from an identical one. `object_ref` names an object a preceding effect
        # stored (SHARPEN stores "sharpened") and pins the entry to THAT object.
        object_ref = params.get("object_ref")

        def _fn(card, event, state, _a=amount, _f=filter_specs, _oc=on_consume,
                _kw=keywords, _uses=uses, _gc=grant_classes,
                _ga=grant_abilities, _oref=object_ref):
            from engine.card_effects.ability_keywords import _controller_id
            player = state.players[_controller_id(card)]
            if not hasattr(player, 'dsl_queued_card_mods'):
                player.dsl_queued_card_mods = []
            object_id = None
            if _oref:
                from engine.context import get_ref
                found = get_ref(_oref)
                if isinstance(found, list):
                    found = found[0] if found else None
                if found is None:
                    # The object this was about does not exist, so there is
                    # nothing to reduce. Queueing an unpinned entry here would
                    # silently widen it to every card the filter matches.
                    return
                object_id = getattr(found, "object_id", None)
            player.dsl_queued_card_mods.append({
                "object_id": object_id,
                # RAW, not resolved. "Costs {r} less FOR EACH RUNECHANT YOU
                # CONTROL" has to be counted when the card is PLAYED — Runechants
                # are created and spent between queueing and playing — so
                # resolving here would freeze a number that is already stale.
                "amount": _a,
                "filter": _f,
                "on_consume": _oc,
                "keywords": list(_kw),
                "grant_classes": list(_gc),
                "grant_abilities": list(_ga),
                "uses": _uses,
            })
        return _fn

    if etype in ("BOOST_NEXT_DAMAGE", "MODIFY_NEXT_DAMAGE"):
        # "The FIRST TIME that card would deal damage this turn, INSTEAD it
        # deals that much plus 1." A replacement (CR 6.4), not a trigger: the
        # damage has to be changed on the way out, and only once.
        try:
            bonus = int(params.get("amount", 1))
        except (TypeError, ValueError):
            bonus = 1

        _bdtype = str(params.get("damage_type") or "").lower()

        def _fn(card, event, state, _b=bonus, _bdtype=_bdtype):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effects import ReplacementEffect, ReplacementType
            cid = _controller_id(card)
            used = {"done": False}
            target = card

            def _cond(ev, s, _t=target, _u=used, _dt=_bdtype):
                if _u["done"] or not isinstance(ev, dict):
                    return False
                if ev.get("type") not in ("damage", None) and "amount" not in ev:
                    return False
                src = ev.get("source_card") or ev.get("damage_source_card")
                if src is not _t or (ev.get("amount") or 0) <= 0:
                    return False
                if _dt:
                    have = ev.get("damage_type")
                    have = getattr(have, "value", have)
                    return str(have).lower() == _dt
                return True

            def _repl(ev, s, _b=_b, _u=used):
                _u["done"] = True
                ev["amount"] = (ev.get("amount") or 0) + _b
                return ev

            state.effect_manager.add_replacement(ReplacementEffect(
                source_card=card, replacement_type=ReplacementType.STANDARD,
                condition_fn=_cond, replace_fn=_repl, owner_id=cid))
        return _fn

    if etype == "GRANT_KEYWORD_TO_PLAYED":
        # "Instant cards you play THIS TURN get go again", "Until end of turn,
        # face up arrow cards played from arsenal gain go again."
        #
        # Distinct from GRANT_NEXT_ATTACK in both directions: it covers EVERY
        # matching card for the rest of the turn rather than the next one, and
        # it applies when a card is PLAYED rather than when an attack is
        # declared. Both cards using it had been written as a SET_FLAG plus a
        # flag-gated STATIC — and nothing dispatches a plain STATIC, so the
        # flag was set and read by nothing.
        #
        # The grant is turn-scoped state on the player, matched by the same
        # filter mechanism as the cost reductions, and consulted by
        # engine._resolve_layer where a played card's effective keywords decide
        # whether it returns an action point.
        keyword = params.get("keyword", "")
        kw = ("Go Again" if str(keyword).lower().replace("_", " ") == "go again"
              else keyword)
        filter_specs = params.get("filter", [])

        def _fn(card, event, state, _kw=kw, _filt=filter_specs):
            from engine.card_effects.ability_keywords import _controller_id
            player = state.players[_controller_id(card)]
            if not hasattr(player, "dsl_play_keyword_grants"):
                player.dsl_play_keyword_grants = []
            player.dsl_play_keyword_grants.append({"keyword": _kw,
                                                   "filter": _filt})
        return _fn

    if etype in ("GRANT_NEXT_ATTACK", "GRANT_NEXT_ATTACK_KEYWORD"):
        # "Your next attack this turn gets <keyword>" (Agility token, Driving
        # Blade). Queued on the same one-shot list as MODIFY_NEXT_ATTACK and
        # consumed by _apply_turn_attack_effects on the first attack matching
        # "filter" — the ONLY correct shape for "next", since a SET_FLAG plus a
        # flag-gated static grants the keyword to every attack for the rest of
        # the turn.
        keyword = params.get("keyword", "")
        kw = "Go Again" if str(keyword).lower().replace("_", " ") == "go again" else keyword
        filter_specs = params.get("filter", [])
        # scope: "TURN" (default) | "CHAIN" — see MODIFY_NEXT_ATTACK.
        scope = str(params.get("scope") or "TURN").upper()

        def _fn(card, event, state, _kw=kw, _filt=filter_specs, _scope=scope):
            from engine.card_effects.ability_keywords import _controller_id
            player = state.players[_controller_id(card)]
            if not hasattr(player, 'dsl_queued_attack_mods'):
                player.dsl_queued_attack_mods = []
            player.dsl_queued_attack_mods.append({
                "mod": "grant_keyword",
                "keyword": _kw,
                "filter": _filt,
                "scope": _scope,
            })
        return _fn

    if etype == "RESTRICT_NEXT_ATTACK_DEFENDERS":
        # "The NEXT attack action card you play this turn can't be defended by
        # more than 2 non-block cards" (Confidence). RESTRICT_DEFENDERS applies
        # to the attack ALREADY on the chain; this queues the same restriction
        # on the one-shot next-attack list so it lands on exactly one attack.
        #
        # The restriction dict is the shape actions._restriction_blocks reads,
        # including the max_defenders COUNT limit (every other key names WHICH
        # cards may not defend; that one names HOW MANY).
        restriction = {k: v for k, v in params.items()
                       if k not in ("filter", "scope", "type")}
        filter_specs = params.get("filter", [])
        scope = str(params.get("scope") or "TURN").upper()

        def _fn(card, event, state, _r=restriction, _filt=filter_specs, _scope=scope):
            from engine.card_effects.ability_keywords import _controller_id
            player = state.players[_controller_id(card)]
            if not hasattr(player, "dsl_queued_attack_mods"):
                player.dsl_queued_attack_mods = []
            player.dsl_queued_attack_mods.append({
                "mod": "restrict_defenders",
                "restriction": dict(_r),
                "filter": _filt,
                "scope": _scope,
            })
        return _fn

    if etype == "GAIN":
        asset = params.get("asset")
        keyword = params.get("keyword")
        amt = params.get("amount", 0)
        # "THEY draw a card, THEY gain {r}, THEY gain 1{h}" — every asset gain
        # resolved to the CONTROLLER, so a card handing resources to the
        # OPPONENT handed them to itself. `player` was authored and unread.
        who = params.get("player", "SELF")
        # "they gain +1{i} UNTIL END OF TURN" — unread, so an intellect gain
        # that should last a turn was permanent.
        duration = str(params.get("duration") or "").upper()
        if asset:
            def _fn(card, event, state, _asset=asset, _a=amt, _w=who, _d=duration):
                from engine.card_effects.ability_keywords import _controller_id
                cid = _effect_player_id(state, card, _w, event)
                if cid is None:
                    cid = _controller_id(card)
                val = _resolve_amount(_a, state, card)
                if _asset == "RESOURCE_POINTS":
                    from engine.card_effects.ability_keywords import effect_gain_resources
                    effect_gain_resources(state, cid, val)
                elif _asset in ("LIFE_POINTS", "LIFE", "HEALTH", "HEALTH_POINTS"):
                    # "gain N{h}" — cards author the life asset under several
                    # names; all mean gain that much life. Only LIFE_POINTS was
                    # handled before, so HEALTH/HEALTH_POINTS/LIFE (~19 cards)
                    # silently gained nothing.
                    from engine.card_effects.ability_keywords import effect_gain_life
                    effect_gain_life(state, cid, val)
                elif _asset == "ACTION_POINTS":
                    from engine.effect_keywords import gain as _ek_gain, AssetType as _AssetType
                    _ek_gain(state, _AssetType.ACTION_POINTS, val,
                             source_player_id=cid, target_player_id=cid)
                elif _asset == "CHI_POINTS":
                    from engine.effect_keywords import gain as _ek_gain, AssetType as _AssetType
                    _ek_gain(state, _AssetType.CHI, val,
                             source_player_id=cid, target_player_id=cid)
                elif _asset in ("INTELLECT", "INTELLECT_POINTS"):
                    # Intellect is a Player stat with no gain() asset type, so
                    # it fell through every branch above and did nothing — and
                    # the card that needs it authored the keyword form, which
                    # grants "INTELLECT" to the combat's KEYWORD list instead.
                    player = state.players.get(cid)
                    if player is None:
                        return
                    try:
                        n = int(val)
                    except (TypeError, ValueError):
                        return
                    player.intellect += n
                    if _d in ("END_OF_TURN", "THIS_TURN", "TURN"):
                        # Restored in the end-phase cleanup. Without this the
                        # gain is permanent, which for intellect means a
                        # permanently larger draw-up every turn after.
                        pending = list(getattr(player, "dsl_pending_stat_restores",
                                               None) or [])
                        pending.append(("intellect", n))
                        player.dsl_pending_stat_restores = pending
            return _fn
        if keyword:
            kw = canonical_keyword(keyword)

            def _fn(card, event, state, _kw=kw):
                # Go again is not a keyword the combat merely carries -- it is
                # "gain 1 action point" (CR 8.3.5), and outside combat there is
                # no keyword list to put it on. Both spellings ({"type":
                # "GO_AGAIN"} and {"type": "GAIN", "keyword": "GO_AGAIN"}) mean
                # the same rule, so they go through the same code.
                if _kw == "Go Again":
                    _grant_go_again(card, state)
                    return
                if state.combat and _kw not in (state.combat.keywords or []):
                    state.combat.grant_keyword(_kw)
            return _fn

    if etype == "GO_AGAIN":
        # Go again is "gain 1 action point" (CR 8.3.5), and the rule splits on
        # WHAT has it:
        #
        #   8.3.5b  an ability of an ATTACK on the active chain link -- the AP
        #           arrives at the Resolution Step, so the keyword goes onto the
        #           combat and the engine pays it out later.
        #   8.3.5a  an ability of a NON-ATTACK LAYER -- the controller gains the
        #           AP once the other resolution abilities have resolved.
        #
        # Only the first was implemented, and the second is what every activated
        # equipment ability is: 33 abilities printing "Go again" wrote to
        # state.combat.keywords, which is None in the action phase, so the AP
        # was silently dropped and the activation ended the player's turn early.
        # "Is there a combat" is exactly the discriminator the rule uses -- a
        # weapon ATTACK activation does have one and keeps the 8.3.5b path.
        #
        # CR 8.3.5c: an object cannot have two go agains, and an effect granting
        # a second one fails. The combat path has always honoured that; the
        # action-point path must not pay twice for one resolution either.
        return lambda card, event, state: _grant_go_again(card, state)

    if etype == "ROLL":
        # Cards author the die size as "faces" or "sides". Effects that consume
        # the result ("gain action points equal to half the number rolled") are
        # authored under "on_success" and run after the roll — they read the
        # result through _resolve_amount's ROLL_RESULT/HALF tokens.
        faces = params.get("faces", params.get("sides", 6))
        after = [compile_effect((e.get("type") or "").upper(),
                                {k: v for k, v in e.items() if k != "type"})
                 for e in (params.get("on_success") or [])]
        def _fn(card, event, state, _f=faces, _after=after):
            from engine.card_effects.ability_keywords import roll_die, _controller_id
            cid = _controller_id(card)
            result = roll_die(state, cid, faces=_f)
            state._roll_result = result
            # "If you've rolled a 6 on a die this turn" (a recurring Kayo
            # template) reads back across every roll in the turn, not just this
            # one — record it turn-scoped so any later card can check the flag.
            if result == 6:
                player = state.players[cid]
                if "DIE_ROLLED_SIX" not in player.current_turn_effects:
                    player.current_turn_effects.append("DIE_ROLLED_SIX")
            for fn in _after:
                if fn is not None:
                    fn(card, event, state)
        return _fn

    if etype == "APPLY_CONTINUOUS":
        target = params.get("target", "")
        # Single modification authored as "effect": {...} rather than the
        # "modifications" list (the recalc consumer reads the list only).
        modifications = params.get("modifications") or []
        if not modifications and isinstance(params.get("effect"), dict):
            modifications = [params["effect"]]
        span = params.get("span", "THIS_TURN")
        filter_raw = params.get("filter")
        def _fn(card, event, state, _tgt=target, _mods=modifications,
                _span=span, _filt=filter_raw):
            player = state.active()
            if not hasattr(player, 'dsl_continuous_effects'):
                player.dsl_continuous_effects = []
            player.dsl_continuous_effects.append({
                "target": _tgt,
                "modifications": _mods,
                "span": _span,
                "filter": _filt,
            })
        return _fn

    if etype == "DISCARD_RANDOM":
        amt = params.get("amount", 1)
        who = str(params.get("player", "SELF")).upper()

        def _fn(card, event, state, _a=amt, _w=who):
            from engine.card_effects.ability_keywords import effect_discard, _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _w in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            got = effect_discard(state, tid, _a, random_discard=True)
            # "If a card with 6 or more {p} IS DISCARDED THIS WAY" — the payoff
            # asks about the card that was actually discarded. The card that
            # needs it asked CARD_IN_ZONE instead, i.e. whether such a card was
            # merely IN HAND, which is a different question and one that stays
            # true after the discard misses.
            if got:
                from engine.context import set_ref
                set_ref("discarded", got[0] if len(got) == 1 else list(got))
        return _fn

    if etype == "REMOVE_COUNTERS":
        # "counter" is the other spelling and was unread HERE, though the COST
        # of the same name reads it — and audit_params merges the two
        # namespaces by name, so the cost's reading masked the effect's gap.
        ctype = params.get("counter_type") or params.get("counter") or ""
        amt = params.get("amount", 1)
        target_fn = _compile_object_target(_object_target_spec(params.get("target")))

        def _fn(card, event, state, _ct=ctype, _a=amt, _tf=target_fn):
            from engine.card_effects.ability_keywords import effect_remove_counter
            targets = _tf(card, event, state) if _tf is not None else [card]
            n = _resolve_amount(_a, state, card)
            try:
                n = max(0, int(n))
            except (TypeError, ValueError):
                n = 1
            for obj in targets:
                effect_remove_counter(state, obj, _ct, n)
        return _fn

    if etype in ("CHOOSE_VALUE", "NAME_A_CARD", "CHOOSE_COLOR"):
        # "As you play this, CHOOSE A COLOR" / "name a card" — a player choice
        # of an abstract VALUE, remembered for a later clause to read. Distinct
        # from CHOOSE, which picks between EFFECT options: the two cards that
        # said choice_type were authored as CHOOSE with no `options`, so the
        # handler returned immediately and neither card did anything at all.
        #
        #   {"type":"CHOOSE_VALUE","choice_type":"COLOR","into":"chosen_color"}
        #   {"type":"CHOOSE_VALUE","choice_type":"CARD_NAME","into":"named_card"}
        kind = str(_first(params, "choice_type", "kind", default="COLOR")).upper()
        into = params.get("into") or ("named_card" if kind in ("CARD_NAME", "NAME")
                                      else "chosen_color")
        apply_to_self = bool(params.get("apply_to_self"))

        def _fn(card, event, state, _k=kind, _into=into, _self=apply_to_self):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.context import set_ref
            cid = _controller_id(card)
            if _k in ("CARD_NAME", "NAME"):
                # Any card name in the game is nameable, so the options are the
                # names the player can actually see and act on: their own cards
                # plus everything already public.
                seen = []
                for pid, player in state.players.items():
                    for zone in player.all_zones():
                        for c in zone.cards:
                            if pid == cid or getattr(c, "is_public", False):
                                name = getattr(c, "name", None)
                                if name and name not in seen:
                                    seen.append(name)
                if not seen:
                    return
                choice = _ask_player(state, cid, seen, context="Name a card")
            else:
                choice = _ask_player(state, cid, ["red", "yellow", "blue"],
                                     context="Choose a colour")
            set_ref(_into, choice)
            # A reference scope lasts one ability execution, and "name a card"
            # is read by LATER abilities on the same permanent ("whenever a card
            # with that name is banished WHILE THIS IS IN THE ARENA"). So the
            # choice is also stamped on the object, which is what actually
            # remembers it.
            store = dict(getattr(card, "dsl_chosen", None) or {})
            store[_into] = choice
            card.dsl_chosen = store
            if _self and _k not in ("CARD_NAME", "NAME"):
                # "THIS gets the chosen color." Colour is what every
                # colour-reading condition in the corpus asks about (they read
                # `color` first, then base_color), so setting it is what makes
                # the choice mean anything. The card's printed PITCH value is a
                # separate quantity and the text does not mention it, so it is
                # deliberately left alone rather than guessed at.
                card.color = str(choice).capitalize()
        return _fn

    if etype == "CHOOSE":
        choose_amt = params.get("amount", 1)
        options_raw = params.get("options", [])
        # An option is either a bare list of effect specs, or a named block
        # {"name": "Head Jab", "effects": [...]} — cards use both. Iterating the
        # dict form as a list yielded its KEYS and crashed on `str.get`.
        compiled_options, labels = [], []
        for i, opt in enumerate(options_raw):
            if isinstance(opt, dict):
                specs = opt.get("effects") or []
                labels.append(str(opt.get("name") or i))
            else:
                specs = opt or []
                labels.append(str(i))
            compiled_options.append(
                [compile_effect((e.get("type") or "").upper(),
                                {k: v for k, v in e.items() if k != "type"})
                 for e in specs])

        def _fn(card, event, state, _n=choose_amt, _opts=compiled_options, _labels=labels):
            if not _opts:
                return
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            cid = _controller_id(card)
            pick = _ask_player(state, cid, _labels, context="Choose an effect")
            idx = _labels.index(pick) if pick in _labels else 0
            for eff_fn in _opts[idx]:
                if eff_fn is not None:
                    eff_fn(card, event, state)
        return _fn

    # ── attack / wager ─────────────────────────────────────────────────────
    if etype in ("ATTACK", "ATTACKING"):
        # "Action - [cost]: Attack" on a weapon/hero. The attack is represented by
        # an ATTACK-PROXY on the stack (CR 1.6.2b / 11.0): an activated-layer
        # StackEntry whose card is the source, which the engine's combat step
        # (_combat_phase_iter -> _attack_step) resolves as a real attack — never a
        # shortcut into combat. NOTE: a weapon with printed power + activation_cost
        # is already offered its attack by play._add_weapon_attacks (which builds
        # the same proxy), and play._add_hero_dsl_activations SKIPS abilities whose
        # effect is ATTACK, so this _fn does not double-fire on weapon activation;
        # it is the proxy-builder for any context that invokes the effect directly
        # (e.g. a granted extra attack).
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.state import StackEntry
            pid = _controller_id(card)
            entry = StackEntry(
                player_id=pid, card=card, layer_type='activated',
                layer_position=len(state.stack_entries) + 1,
            )
            entry.pitched_for_attack = []
            state.stack_entries.append(entry)
        return _fn

    if etype == "SHARPEN":
        # "**Sharpen** target sword you control (twice)." Put a +1{p} counter on
        # a weapon you control; 41 corpus cards use the keyword, and a further
        # group asks "if the weapon has been SHARPENED this turn", so the turn
        # event is recorded here and nowhere else — a power counter arriving by
        # any other route is not sharpening.
        #
        # _recalculate_attack_power already adds card.counters['power'] to an
        # attacking card, so the counter needs no separate power plumbing.
        amount = params.get("amount", params.get("count", 1))
        subtype = params.get("subtype", "Sword")

        def _fn(card, event, state, _a=amount, _sub=subtype):
            from engine.card_effects.ability_keywords import (
                _ask_player, _controller_id, effect_put_counter)
            from engine.effect_keywords import _record_turn_event
            cid = _controller_id(card)
            if cid not in state.players:
                return
            player = state.players[cid]
            want = str(_sub).lower()
            candidates = [c for z in (player.weapon1, player.weapon2)
                          for c in z.cards
                          if want in [x.lower() for x in (getattr(c, "subtypes", None) or [])]]
            if not candidates:
                return
            # "Sharpen target sword you control. If IT has 1 or more +1{p}
            # counters, your next attack WITH IT this turn costs {r} less."
            # Everything after the first sentence is about the SAME object, and
            # the only way to say so is to name it.
            if len(candidates) == 1:
                target = candidates[0]
            else:
                pick = _ask_player(state, cid, [c.slug for c in candidates],
                                   context=f"Choose a {_sub} to sharpen")
                target = next((c for c in candidates if c.slug == pick), candidates[0])
            try:
                times = int(_resolve_amount(_a, state, card)
                            if isinstance(_a, dict) else _a)
            except (TypeError, ValueError):
                times = 1
            # "The next time you would sharpen a sword this turn, instead
            # sharpen it an ADDITIONAL time" (swordmasters_path_blue). Held as
            # a turn-scoped marker so the existing end-phase cleanup of
            # current_turn_effects expires it -- no new engine bookkeeping, and
            # no way for it to leak into the next turn. Consumed once.
            marker = "sharpen_extra"
            if marker in player.current_turn_effects:
                player.current_turn_effects.remove(marker)
                times += 1
            for _ in range(max(times, 0)):
                effect_put_counter(state, target, "power", 1)
                _record_turn_event(state, cid, "sharpen",
                                   getattr(target, "slug", None))
            from engine.context import set_ref
            set_ref("sharpened", target)
        return _fn

    if etype in ("SHARPEN_EXTRA_NEXT_TIME", "REPLACE_NEXT_SHARPEN"):
        # "The next time you would sharpen a sword this turn, instead sharpen
        # it an additional time." A replacement on the sharpen, consumed by the
        # next SHARPEN. Stored as a turn-scoped marker (see SHARPEN) so it
        # expires with the turn through machinery that already exists.
        amount = params.get("amount", 1)

        def _fn(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            if cid not in state.players:
                return
            try:
                n = int(_resolve_amount(_a, state, card)
                        if isinstance(_a, dict) else _a)
            except (TypeError, ValueError):
                n = 1
            for _ in range(max(n, 0)):
                state.players[cid].current_turn_effects.append("sharpen_extra")
        return _fn

    if etype == "WAGER":
        # CR 8.5.46: Wager — a continuous effect on the current attack. If the
        # attack hits, the controller wins and creates the prize token; otherwise
        # the opponent wins it. Resolves automatically at chain-link resolution
        # (engine._resolve_wagers), so this only registers the wager + prize.
        prize = params.get("prize") or params.get("token")
        def _fn(card, event, state, _prize=prize):
            from engine.card_effects.ability_keywords import add_wager, _controller_id
            # The source card is passed so a non-token payoff ("the winner loses
            # 1{h}") can be dispatched back to it when the wager resolves.
            add_wager(state, _controller_id(card), _prize, source=card)
        return _fn

    if etype == "PREVENT_DAMAGE":
        # "Prevent the next N damage that would be dealt to you." Registers a
        # one-shot PREVENTION replacement effect (CR 6.4.10) on the controller,
        # so the engine's damage pipeline (effect_manager.apply_replacements)
        # reduces the next damage event to this hero by up to N and then consumes
        # the shield. Used from injected ON_DAMAGE reactions like Steadfast.
        # The amount may be an EXPRESSION: "prevent the next X arcane damage,
        # where X is the damage dealt by Dampen". Coercing to int at compile
        # time turned those into 0 — a shield that prevents nothing.
        _raw_amount = params.get("amount", 0)
        _dtype = str(params.get("damage_type") or "").lower()
        # "the next time a SHADOW source would deal damage" — a class/talent
        # restriction on the SOURCE, not the target. Without it the shield
        # absorbs damage from any source, which is strictly stronger.
        _src_class = _norm_amt(params.get("source_class") or params.get("source_talent") or "")

        def _fn(card, event, state, _raw=_raw_amount, _dtype=_dtype,
                _src_class=_src_class):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effects import ReplacementEffect, ReplacementType
            cid = _controller_id(card)
            try:
                _amt = int(_resolve_amount(_raw, state, card)
                           if isinstance(_raw, dict) else _raw)
            except (TypeError, ValueError):
                _amt = 0
            if _amt <= 0:
                return
            def _cond(ev, st, _cid=cid, _dt=_dtype, _src_class=_src_class):
                if not (ev.get("type") == "damage"
                        and ev.get("amount", 0) > 0
                        and not ev.get("unpreventable", False)
                        and ev.get("target_player_id") == _cid):
                    return False
                # "prevent 2 of that {p} damage" / "3 arcane damage" — the type
                # was not read, so a card that only prevents ONE kind of damage
                # was preventing every kind.
                if _dt:
                    have = ev.get("damage_type")
                    have = getattr(have, "value", have)
                    if str(have).lower() != _dt:
                        return False
                if _src_class:
                    src = ev.get("damage_source_card") or ev.get("source_card")
                    traits = {_norm_amt(x) for x in
                              (getattr(src, "classes", None) or [])
                              + (getattr(src, "talents", None) or [])}
                    if _src_class not in traits:
                        return False
                return True
            def _replace(ev, st, _a=_amt):
                prevented = min(_a, ev.get("amount", 0))
                ev["amount"] = ev.get("amount", 0) - prevented
                return ev
            state.effect_manager.add_replacement(ReplacementEffect(
                source_card=card,
                replacement_type=ReplacementType.PREVENTION,
                condition_fn=_cond,
                replace_fn=_replace,
                owner_id=cid,
                prevention_amount=_amt,
                is_shielding=False,
            ))
        return _fn

    if etype == "PLAY_ACTIVATE_ATTACK":
        # "Play that card as an attack, and it's activated" — a granted extra
        # attack sourced from a card the surrounding effect located (e.g. Bonds
        # of Ancestry's injected trigger, which searches for a Gustwave). Modeling
        # the full free-play-into-combat grant is out of scope; this documented
        # best-effort resolves a stored "ref" (when the caller left one) and, if
        # it is an attack card in a play-adjacent zone, builds the same ATTACK
        # proxy the ATTACK effect uses so it enters the combat step normally.
        # With no usable ref it no-ops rather than crashing the game — the card
        # remains loadable and audit-safe.
        ref = params.get("ref", "chosen")
        def _fn(card, event, state, _r=ref):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.context import get_ref
            from engine.state import StackEntry
            target = get_ref(_r)
            if not target:
                return
            obj = target[0] if isinstance(target, list) else target
            if obj is None:
                return
            pid = _controller_id(card)
            entry = StackEntry(
                player_id=pid, card=obj, layer_type='activated',
                layer_position=len(state.stack_entries) + 1,
            )
            entry.pitched_for_attack = []
            state.stack_entries.append(entry)
        return _fn

    # Unknown effect types are authoring errors — fail at JSON load time
    # rather than silently no-opping (fail-open let bad JSON go unnoticed).
    raise ValueError(f"Unknown DSL effect type: {etype!r} (params: {params!r})")

"""Cards whose only ability was a plain STATIC, which nothing dispatches.

`ABILITY_TYPE_TO_EVENT` has no entry for `STATIC`, so `dispatch_event` never
matches one; its only readers are the four DECLARATIVE effects the engine
consults directly off the CardDef. Every other effect authored under a STATIC
was dead code that looked implemented — 145 cards.

`WHILE_STATIC` is the ability type that IS dispatched: the engine emits
`recalculate_attack_power` at the end of `_recalculate_attack_power`, and
`_dsl_recalc_listener` fans it out to the attack card, both heroes, and every
in-play permanent.

These tests go through that real path — `_setup_dsl_listeners` included, since
without it the event is emitted into a void and every assertion below would
read as "the buff does nothing" no matter how the card were authored. Each
buffed case is paired with the unbuffed one, because an ability that fires
unconditionally passes every positive test on its own.
"""
import copy

import pytest

import engine.engine as E
from engine.card import Card, CardDB
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState, Zone
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    return st


def _card(slug, owner=1):
    base = DB.get(slug)
    assert base is not None, f"unknown slug {slug}"
    c = copy.deepcopy(base)
    c.owner = c.controller = owner
    return c


def _attack_with(st, card, pid=1):
    """Run the real attack-power path with `card` as the attacking card."""
    power = card.base_power or 0
    st.combat = CombatState(attacker_id=pid, link_id=1, attack_power=power,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = power
    E._apply_turn_attack_effects(st, card)
    E._register_card_continuous_effects(st, card)
    E._recalculate_attack_power(st)
    return st.combat.attack_power


def _token(st, pid, slug, name, subtypes=("Token",)):
    t = Card(slug=slug, name=name, types=["Token"], subtypes=list(subtypes))
    t.owner = t.controller = pid
    st.players[pid].permanents.add(t)
    return t


def _pitch(st, pid, slug, cost=0, pitch=1):
    c = Card(slug=slug, name=slug, types=["Action"])
    c.owner = c.controller = pid
    c.cost = c.base_cost = cost      # not raw_cost: the filters read `cost`
    c.pitch = pitch
    st.players[pid].pitch.add(c)
    return c


# --- flex_strength: "If this has 6 or more {p}, it gets +3{p}" --------------
# The blue printing asked COUNTER_GTE "power" — a count of +1{p} COUNTERS, not
# the card's {p}. It could not have fired on a card with no counters on it.

@pytest.mark.parametrize("slug", ["flex_strength_red", "flex_strength_blue"])
def test_flex_strength_buffs_a_six_power_attack(slug):
    st = _state()
    card = _card(slug)
    base = card.base_power or 0
    got = _attack_with(st, card)
    if base >= 6:
        assert got == base + 3
    else:
        assert got == base, "buffed an attack with less than 6 power"


def test_flex_strength_blue_does_not_need_power_counters():
    # The specific defect: with COUNTER_GTE the card needed six power COUNTERS.
    st = _state()
    card = _card("flex_strength_blue")
    card.counters = {}
    base = card.base_power or 0
    if base >= 6:
        assert _attack_with(st, card) == base + 3


# --- power_play_red: "If this was played from arsenal, it gets +5{p}" -------

def test_power_play_buffs_only_when_played_from_arsenal():
    st = _state()
    from_hand = _card("power_play_red")
    from_hand.played_from_zone = from_hand.prev_zone = "hand"
    base = from_hand.base_power or 0
    assert _attack_with(st, from_hand) == base

    st2 = _state()
    from_arsenal = _card("power_play_red")
    from_arsenal.played_from_zone = from_arsenal.prev_zone = "arsenal"
    assert _attack_with(st2, from_arsenal) == base + 5


# --- rising_power_yellow: "If you've drawn a card this turn, +1{p}" --------

def test_rising_power_needs_a_draw_this_turn():
    st = _state()
    card = _card("rising_power_yellow")
    base = card.base_power or 0
    assert _attack_with(st, card) == base

    st2 = _state()
    from engine.effect_keywords import record_turn_event_for_player
    record_turn_event_for_player(st2.players[1], "draw")
    assert _attack_with(st2, _card("rising_power_yellow")) == base + 1


# --- old_leather_and_vim_red: "a Toughness OR Vigor token" -----------------
# The conditions ALSO required Toughness outside the OR, so a Vigor token alone
# — half of what the card names — did not qualify.

def test_old_leather_and_vim_accepts_vigor_alone():
    st = _state()
    _token(st, 1, "vigor", "Vigor")
    card = _card("old_leather_and_vim_red")
    assert _attack_with(st, card) == (card.base_power or 0) + 1


def test_old_leather_and_vim_accepts_toughness_alone():
    st = _state()
    _token(st, 1, "toughness", "Toughness")
    card = _card("old_leather_and_vim_red")
    assert _attack_with(st, card) == (card.base_power or 0) + 1


def test_old_leather_and_vim_needs_one_of_them():
    st = _state()
    card = _card("old_leather_and_vim_red")
    assert _attack_with(st, card) == (card.base_power or 0)


# --- little_big_foot_red: "two or more cards with cost 3 or more" ----------
# The cost filter was authored as `card_condition`, which CARD_IN_ZONE does not
# read — so it counted every card in the pitch zone regardless of cost. A
# dropped filter does not disable a condition, it makes it too permissive.

def test_little_big_foot_ignores_cheap_pitch_cards():
    st = _state()
    _pitch(st, 1, "cheap_a", cost=0)
    _pitch(st, 1, "cheap_b", cost=1)
    card = _card("little_big_foot_red")
    assert _attack_with(st, card) == (card.base_power or 0), \
        "two cheap cards triggered a 'cost 3 or more' condition"


def test_little_big_foot_counts_expensive_pitch_cards():
    st = _state()
    _pitch(st, 1, "dear_a", cost=3)
    _pitch(st, 1, "dear_b", cost=4)
    card = _card("little_big_foot_red")
    assert _attack_with(st, card) == (card.base_power or 0) + 6


# --- goon_beatdown_blue: "If you control 3 or more auras, +3{p}" ----------

def test_goon_beatdown_needs_three_auras():
    st = _state()
    for i in range(2):
        _token(st, 1, f"aura_{i}", "Aura", subtypes=["Aura"])
    card = _card("goon_beatdown_blue")
    assert _attack_with(st, card) == (card.base_power or 0)

    _token(st, 1, "aura_2", "Aura", subtypes=["Aura"])
    card2 = _card("goon_beatdown_blue")
    assert _attack_with(st, card2) == (card2.base_power or 0) + 3


# --- battalion_barque_red: "2 or more blue cards in your pitch zone" ------

def test_battalion_barque_counts_blue_pitch_only():
    st = _state()
    _pitch(st, 1, "red_a", pitch=1)
    _pitch(st, 1, "red_b", pitch=1)
    card = _card("battalion_barque_red")
    assert _attack_with(st, card) == (card.base_power or 0), \
        "red pitch cards satisfied a 'blue cards' condition"

    st2 = _state()
    _pitch(st2, 1, "blue_a", pitch=3)
    _pitch(st2, 1, "blue_b", pitch=3)
    card2 = _card("battalion_barque_red")
    assert _attack_with(st2, card2) == (card2.base_power or 0) + 2


# --- droplet_blue: "If you've played ANOTHER blue card this turn, +2{p}" ---

def test_droplet_needs_a_second_blue_play():
    from engine.effect_keywords import record_turn_event_for_player
    st = _state()
    record_turn_event_for_player(st.players[1], "play", "blue")   # itself only
    card = _card("droplet_blue")
    assert _attack_with(st, card) == (card.base_power or 0), \
        "Droplet counted its own play as 'another blue card'"

    st2 = _state()
    for _ in range(2):
        record_turn_event_for_player(st2.players[1], "play", "blue")
    card2 = _card("droplet_blue")
    assert _attack_with(st2, card2) == (card2.base_power or 0) + 2


# --- arakni_web_of_deceit: a HERO static over "YOUR attacks" ---------------
# Not SOURCE_IS_ATTACK: the buffed card is the attack, not the hero.

def _stealth_attack(st, pid=1, marked=True):
    atk = Card(slug="stealth_atk", name="Stealth Atk",
               types=["Action"], subtypes=["Attack"])
    atk.owner = atk.controller = pid
    atk.power = atk.base_power = 3
    # On the attack CARD, not only on CombatState: _recalculate_attack_power
    # rebuilds combat.keywords from the card each time, so a keyword set only on
    # the combat state is erased before any WHILE_STATIC gets to read it.
    atk.keywords = ["Stealth"]
    st.combat = CombatState(attacker_id=pid, link_id=1, attack_power=3,
                            attack_card=atk, keywords=["Stealth"])
    st.combat.base_attack_power = 3
    E._apply_turn_attack_effects(st, atk)
    E._register_card_continuous_effects(st, atk)
    E._recalculate_attack_power(st)
    return st.combat.attack_power


def test_arakni_web_of_deceit_buffs_stealth_against_a_marked_hero():
    from engine.card_effects import ability_keywords
    st = _state()
    hero = _card("arakni_web_of_deceit")
    st.players[1].hero = hero
    st.players[1].hero_zone.add(hero)
    # effect_mark takes the player being MARKED, not the one doing the marking.
    ability_keywords.effect_mark(st, 2)
    assert _stealth_attack(st) == 4


def test_arakni_web_of_deceit_does_nothing_unmarked():
    st = _state()
    hero = _card("arakni_web_of_deceit")
    st.players[1].hero = hero
    st.players[1].hero_zone.add(hero)
    assert _stealth_attack(st) == 3


# ===========================================================================
# Batch F: dead statics whose condition ALSO said something other than the card
# ===========================================================================

# --- baalghor: "attack action cards played FROM YOUR BANISHED ZONE get +3{p}"
# The condition was CARD_IN_ZONE banished — "is there an action card sitting in
# my banished zone", which says nothing about the attack being made.

def _hero_attack(st, hero_slug, played_from, power=3, pid=1, subtypes=("Attack",)):
    hero = _card(hero_slug, pid)
    st.players[pid].hero = hero
    st.players[pid].hero_zone.add(hero)
    atk = Card(slug="atk", name="Atk", types=["Action"], subtypes=list(subtypes))
    atk.owner = atk.controller = pid
    atk.power = atk.base_power = power
    atk.played_from_zone = atk.prev_zone = played_from
    return _attack_with(st, atk, pid), atk


def test_baalghor_buffs_only_attacks_played_from_banish():
    st = _state()
    # A banished action present but the attack came from hand: the old condition
    # was satisfied by exactly this and buffed anyway.
    stray = Card(slug="stray", name="Stray", types=["Action"])
    stray.owner = stray.controller = 1
    st.players[1].banished.add(stray)
    got, _ = _hero_attack(st, "baalghor_omen_of_the_end", "hand")
    assert got == 3, "an unrelated card in the banished zone buffed a hand attack"

    st2 = _state()
    got2, _ = _hero_attack(st2, "baalghor_omen_of_the_end", "banished")
    assert got2 == 6


# --- "while this is defended by less than 2 non-equipment cards, +1{p}" ----

def _defend_with(st, n_hand, n_equipment=0):
    for i in range(n_hand):
        d = Card(slug=f"blocker_{i}", name="Blocker", types=["Action"])
        d.owner = d.controller = 2
        st.combat.defending_cards.append(d)
    for i in range(n_equipment):
        d = Card(slug=f"gear_{i}", name="Gear", types=["Equipment"])
        d.owner = d.controller = 2
        st.combat.defending_cards.append(d)
    E._recalculate_attack_power(st)
    return st.combat.attack_power


@pytest.mark.parametrize("slug", ["barraging_brawnhide_blue", "stony_woottonhog_red"])
def test_defended_by_less_than_two_non_equipment(slug):
    st = _state()
    card = _card(slug)
    base = card.base_power or 0
    assert _attack_with(st, card) == base + 1, "undefended is fewer than two"
    assert _defend_with(st, n_hand=1) == base + 1
    assert _defend_with(st, n_hand=1) == base, \
        "a second non-equipment defender did not switch the buff off"


@pytest.mark.parametrize("slug", ["barraging_brawnhide_blue", "stony_woottonhog_red"])
def test_equipment_defenders_do_not_count(slug):
    # "NON-equipment cards" — two pieces of equipment must leave the buff on.
    st = _state()
    card = _card(slug)
    base = card.base_power or 0
    _attack_with(st, card)
    assert _defend_with(st, n_hand=0, n_equipment=2) == base + 1, \
        "equipment defenders were counted against a non-equipment condition"


# --- spreading_flames: base {p} < number of Draconic chain links you control -

def _draconic_link(st, pid=1):
    from engine.state import ChainLink
    link = ChainLink(chainlink_id=len(st.chain_links) + 1, attacker_id=pid,
                     attack_slug="drake", attack_power=2, net_damage=2,
                     keywords=[], from_weapon=False, talents=["Draconic"])
    st.chain_links.append(link)
    return link


def test_spreading_flames_compares_base_power_to_a_live_count():
    # Spreading Flames is itself an attack action card (Draconic Ninja Action -
    # Attack), so it is the attacking card rather than a permanent in play.
    st = _state()
    card = _card("spreading_flames_red")
    base = card.base_power or 0

    # No Draconic chain links: base is not less than 0.
    assert _attack_with(st, card) == base

    for _ in range(base + 1):
        _draconic_link(st)
    assert _attack_with(st, _card("spreading_flames_red")) == base + 1,         "base power below the Draconic chain-link count should qualify"


def test_spreading_flames_ignores_non_draconic_attacks():
    st = _state()
    for _ in range(6):
        _draconic_link(st)
    atk = Card(slug="plain", name="Plain", types=["Action"], subtypes=["Attack"])
    atk.owner = atk.controller = 1
    atk.power = atk.base_power = 2
    atk.classes = ["Guardian"]
    # Dispatched to the attack card itself; a non-Draconic attack must not
    # pick up the buff even with the chain-link count satisfied.
    assert _attack_with(st, atk) == 2


# ===========================================================================
# Batch G: "this gets **go again**" under a dead STATIC
# ===========================================================================

def _kw(st):
    return {k.lower() for k in (st.combat.keywords or [])}


@pytest.mark.xfail(strict=True, reason=(
    "The card DB's `keywords` list includes keywords the card only gains "
    "CONDITIONALLY: Out Muscle is listed as GoAgain and Over the Top as "
    "Overpower, though both texts grant them only while a condition holds. The "
    "engine treats every printed keyword as unconditional, so these cards have "
    "the keyword ON at all times and the condition can never take it away — an "
    "always-on buff, which is worse than the dead static it replaced. Fixing it "
    "means teaching the engine that a keyword a card grants conditionally is "
    "not also printed on it unconditionally. 18 implemented cards."))
def test_over_the_top_gains_overpower_only_above_its_base():
    st = _state()
    card = _card("over_the_top_red")
    _attack_with(st, card)
    assert "overpower" not in _kw(st), \
        "gained overpower at base power, with nothing added"

    st2 = _state()
    card2 = _card("over_the_top_red")
    card2.power = (card2.base_power or 0) + 1
    st2.combat = CombatState(attacker_id=1, link_id=1,
                             attack_power=card2.power, attack_card=card2,
                             keywords=[])
    st2.combat.base_attack_power = card2.base_power or 0
    st2.combat.power_mods.append(("add", 1))
    E._recalculate_attack_power(st2)
    assert "overpower" in _kw(st2)


@pytest.mark.xfail(strict=True, reason=(
    "The card DB's `keywords` list includes keywords the card only gains "
    "CONDITIONALLY: Out Muscle is listed as GoAgain and Over the Top as "
    "Overpower, though both texts grant them only while a condition holds. The "
    "engine treats every printed keyword as unconditional, so these cards have "
    "the keyword ON at all times and the condition can never take it away — an "
    "always-on buff, which is worse than the dead static it replaced. Fixing it "
    "means teaching the engine that a keyword a card grants conditionally is "
    "not also printed on it unconditionally. 18 implemented cards."))
@pytest.mark.parametrize("slug", ["out_muscle_blue", "out_muscle_red"])
def test_out_muscle_loses_go_again_to_a_big_enough_defender(slug):
    st = _state()
    card = _card(slug)
    power = _attack_with(st, card)
    assert "go again" in _kw(st), "undefended, so nothing has equal or greater power"

    small = Card(slug="small", name="Small", types=["Action"])
    small.owner = small.controller = 2
    small.power = max(0, power - 1)
    st.combat.defending_cards.append(small)
    E._recalculate_attack_power(st)
    assert "go again" in _kw(st), "a weaker defender switched go again off"

    big = Card(slug="big", name="Big", types=["Action"])
    big.owner = big.controller = 2
    big.power = power
    st.combat.defending_cards.append(big)
    E._recalculate_attack_power(st)
    assert "go again" not in _kw(st), \
        "a defender with equal power should remove go again"


def test_cinderskin_devotion_counts_draconic_chain_links_not_permanents():
    st = _state()
    # The old condition counted PERMANENTS with a "Draconic" subtype. Put one
    # there: it must not satisfy a chain-link condition.
    _token(st, 1, "drake_perm", "Drake", subtypes=["Draconic"])
    card = _card("cinderskin_devotion_blue")
    _attack_with(st, card)
    assert "go again" not in _kw(st), \
        "a Draconic permanent satisfied a Draconic CHAIN LINK condition"

    st2 = _state()
    _draconic_link(st2)
    _draconic_link(st2)
    _attack_with(st2, _card("cinderskin_devotion_blue"))
    assert "go again" in _kw(st2)


def test_blistering_assault_reads_the_pitch_zone():
    st = _state()
    _pitch(st, 1, "red_card", pitch=1)
    _attack_with(st, _card("blistering_assault_blue"))
    assert "go again" not in _kw(st)

    st2 = _state()
    _pitch(st2, 1, "yellow_card", pitch=2)
    _attack_with(st2, _card("blistering_assault_blue"))
    assert "go again" in _kw(st2)


def test_vigor_rush_needs_a_non_attack_action_played_this_turn():
    from engine.effect_keywords import record_turn_event_for_player
    st = _state()
    record_turn_event_for_player(st.players[1], "play", "attack_action")
    _attack_with(st, _card("vigor_rush_blue"))
    assert "go again" not in _kw(st), \
        "an ATTACK action satisfied a NON-attack action condition"

    st2 = _state()
    record_turn_event_for_player(st2.players[1], "play", "non_attack_action")
    _attack_with(st2, _card("vigor_rush_blue"))
    assert "go again" in _kw(st2)


def test_cards_printing_go_again_no_longer_duplicate_it_in_json():
    """The duplicate statics are gone; the printed keyword still does the work."""
    from engine.card_effects.dsl.loader import get_card
    for slug in ("flex_claws_red", "loan_shark_yellow", "poisoned_blade_blue"):
        card = DB.get(slug)
        assert any(k.lower().replace(" ", "") == "goagain"
                   for k in (card.keywords or [])), \
            f"{slug} no longer prints Go again — the deletion was wrong"
        cd = get_card(slug)
        statics = [a for a in cd.abilities
                   if (a.ability_type or "").upper() == "STATIC"]
        assert not statics, f"{slug} still carries a dead STATIC"


# ===========================================================================
# Dead TRIGGERS: the same failure one level up
# ===========================================================================
# ON_ENTER_PLAY was in TRIGGER_TO_EVENT, so cards using it loaded and looked
# implemented — but no engine code ever emitted the event, so dispatch_event
# was never called with it. 25 implemented cards, including Loan Shark, whose
# entire text is "when this enters the arena, create 2 Gold tokens".


def test_on_enter_play_actually_fires():
    st = _state()
    card = _card("loan_shark_yellow")
    card.zone = "hand"
    st.players[1].permanents.add(card)
    golds = [c for c in st.players[1].permanents.cards if c.slug == "gold"]
    assert len(golds) == 2, \
        f"Loan Shark created {len(golds)} Gold tokens; the card says 2"


def test_enters_the_arena_with_counters():
    st = _state()
    card = _card("teklo_core_blue")
    card.zone = "hand"
    st.players[1].permanents.add(card)
    assert card.counters.get("steam") == 2


def test_moving_between_arena_zones_is_not_a_new_entry():
    """A card already in the arena must not re-fire its entry trigger."""
    st = _state()
    card = _card("loan_shark_yellow")
    card.zone = "hand"
    st.players[1].permanents.add(card)
    st.players[1].permanents.remove(card)
    card.zone = "permanents"
    card.prev_zone = "permanents"
    st.players[1].permanents.add(card)
    golds = [c for c in st.players[1].permanents.cards if c.slug == "gold"]
    assert len(golds) == 2, \
        f"re-adding a card already in the arena created {len(golds)} Gold — " \
        "an arena-to-arena move is not an entry"


def test_teklo_core_survives_while_it_has_steam():
    """COUNTER_GTE 0 is true for every card at all times.

    Teklo Core's "when it has no steam counters, destroy it" was authored as
    COUNTER_GTE steam 0 — so it destroyed itself at the start of every turn no
    matter how many counters it had, which is the whole card.
    """
    from engine.card_effects.dsl import dispatch
    st = _state()
    card = _card("teklo_core_blue")
    card.zone = "hand"
    st.players[1].permanents.add(card)
    assert card.counters.get("steam") == 2

    dispatch(st, "START_OF_TURN", card.slug, card=card, event=None)
    assert card in st.players[1].permanents.cards, \
        "Teklo Core destroyed itself while it still had steam counters"


def test_counter_lte_and_gte_read_the_card_not_a_stale_zone_key():
    """effect_put_counter writes a card tally AND a (slug, ZONE, kind) key.

    The zone-keyed one goes stale the moment the card moves — an aim counter
    put on a card in the arsenal is unfindable once it reaches the combat
    chain — so the card's own tally has to be the authority.
    """
    from engine.card_effects.ability_keywords import effect_put_counter
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _state()
    card = _card("infecting_shot_blue")
    card.zone = "arsenal"
    effect_put_counter(st, card, "aim")
    card.zone = "combat chain"          # the move that used to lose the counter

    gte = compile_condition("COUNTER_GTE", {"counter": "aim", "amount": 1})
    lte = compile_condition("COUNTER_LTE", {"counter": "aim", "amount": 0})
    assert gte(card, None, st) is True
    assert lte(card, None, st) is False

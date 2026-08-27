"""Mechanics that replaced flags nothing ever set.

Every condition here was previously a FLAG_SET on a private name no code wrote,
so the ability was permanently false and CAN NEVER FIRE. The pattern repeated
because the DSL had no way to express the question, not because the engine
lacked the information — in most of these the state was already there and only
a way to ask was missing.

Grouped by the question each card was actually asking.
"""
import copy

import pytest

from engine.card import Card, CardDB
from engine.card_effects.dsl import dispatch
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.effect_types import _resolve_amount
from engine.card_effects.dsl.loader import load_all_cards
from engine.effect_keywords import TURN_EVENT_MARKER, roll
from engine.state import CombatState
from tests.conftest import _make_state
from tests.conftest import _card_json

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    return st


def _card(slug, owner=1):
    base = DB.get(slug)
    assert base is not None, f"unknown slug {slug}"
    c = copy.deepcopy(base)
    c.owner = c.controller = owner
    return c


def _attacking(st, power=3, pid=1, card=None):
    atk = card or Card(slug="atk", name="atk", types=["Action"], subtypes=["Attack"])
    atk.owner = atk.controller = pid
    atk.power = atk.base_power = power
    st.combat = CombatState(attacker_id=pid, link_id=1, attack_power=power,
                            attack_card=atk, keywords=[])
    st.combat.base_attack_power = power
    return atk


# --- "if you have rolled a 5 or 6 on a die this turn" -----------------------

def test_rolling_records_the_face_as_a_turn_event():
    st = _state()
    import random
    roll(st, num_dice=1, faces=6, source_player_id=1, rng=random.Random(0))
    markers = [m for m in st.players[1].current_turn_effects
               if m.startswith(f"{TURN_EVENT_MARKER}roll")]
    assert markers, "roll() recorded nothing, so 'if you've rolled an N' is dead"


def _stock_hand(st, pid=2, n=4):
    for i in range(n):
        c = Card(slug=f"h{i}", name=f"h{i}", types=["Action"])
        c.owner = c.controller = pid
        st.players[pid].hand.add(c)


def test_high_roller_intimidates_once_without_a_roll():
    # Intimidate (CR 8.5.10) banishes a random card from the opponent's hand,
    # so the count of cards it removes is the observable difference between
    # intimidating once and twice.
    st = _state()
    _stock_hand(st)
    card = _card("high_roller_yellow")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert len(st.players[2].hand.cards) == 3


def test_high_roller_intimidates_twice_after_a_five_or_six():
    st = _state()
    _stock_hand(st)
    from engine.effect_keywords import _record_turn_event
    _record_turn_event(st, 1, "roll", "6")
    card = _card("high_roller_yellow")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert len(st.players[2].hand.cards) == 2,         "'instead intimidate twice' removed the same one card as intimidating once"


def test_reckless_charge_draws_only_after_a_six():
    st = _state()
    cond = compile_condition("EVENT_THIS_TURN", {"event": "roll", "qualifier": "6"})
    card = _card("reckless_charge_blue")
    assert cond(card, None, st) is False
    from engine.effect_keywords import _record_turn_event
    _record_turn_event(st, 1, "roll", "6")
    assert cond(card, None, st) is True


def test_rolling_a_three_does_not_answer_the_six_question():
    st = _state()
    from engine.effect_keywords import _record_turn_event
    _record_turn_event(st, 1, "roll", "3")
    cond = compile_condition("EVENT_THIS_TURN", {"event": "roll", "qualifier": "6"})
    assert cond(_card("reckless_charge_blue"), None, st) is False


# --- "if you've controlled a <token> this turn" -----------------------------

def test_a_token_entering_the_arena_records_control():
    st = _state()
    tok = Card(slug="seismic_surge", name="Seismic Surge", types=["Token"],
               subtypes=["Item"])
    tok.owner = tok.controller = 1
    st.players[1].permanents.add(tok)
    cond = compile_condition("EVENT_THIS_TURN",
                             {"event": "controlled", "qualifier": "seismicsurge"})
    assert cond(_card("aftershock_red"), None, st) is True


def test_control_is_broader_than_creation():
    # A token that was already there at the start of the turn was never created
    # this turn, but you did control it. The turn-start sweep is what makes the
    # commonest case — the token has simply been sitting there — answer yes.
    st = _state()
    tok = Card(slug="seismic_surge", name="Seismic Surge", types=["Token"],
               subtypes=["Item"])
    tok.owner = tok.controller = 1
    st.players[1].permanents.cards.append(tok)   # bypass Zone.add: no entry event
    cond = compile_condition("EVENT_THIS_TURN",
                             {"event": "controlled", "qualifier": "seismicsurge"})
    assert cond(_card("aftershock_red"), None, st) is False
    import engine.engine as E
    E.start_of_turn_refresh_player(st, 1)
    assert cond(_card("aftershock_red"), None, st) is True


def test_a_token_you_never_controlled_does_not_count():
    st = _state()
    cond = compile_condition("EVENT_THIS_TURN",
                             {"event": "controlled", "qualifier": "seismicsurge"})
    assert cond(_card("aftershock_red"), None, st) is False


# --- "the first time ... this turn" (once_per_turn) -------------------------

def test_once_per_turn_ability_fires_once():
    st = _state()
    hero = _card("briar")
    st.players[1].hero_zone.add(hero)
    atk = _attacking(st, card=Card(slug="a", name="a", types=["Action"],
                                   subtypes=["Attack"]))
    atk.owner = atk.controller = 1
    for _ in range(3):
        dispatch(st, "ON_DEAL_DAMAGE", hero.slug, card=hero, event=None)
    made = [c for c in st.players[1].permanents.cards
            if "earth" in (c.slug or "").lower()]
    assert len(made) == 1, f"expected exactly one Embodiment of Earth, got {len(made)}"


def test_once_per_turn_resets_next_turn():
    st = _state()
    hero = _card("briar")
    st.players[1].hero_zone.add(hero)
    atk = _attacking(st, card=Card(slug="a", name="a", types=["Action"],
                                   subtypes=["Attack"]))
    atk.owner = atk.controller = 1
    dispatch(st, "ON_DEAL_DAMAGE", hero.slug, card=hero, event=None)
    st.players[1].current_turn_effects = []          # a new turn
    dispatch(st, "ON_DEAL_DAMAGE", hero.slug, card=hero, event=None)
    made = [c for c in st.players[1].permanents.cards
            if "earth" in (c.slug or "").lower()]
    assert len(made) == 2


def test_a_failed_condition_does_not_burn_the_once_per_turn_use():
    # "The first time X happens" means the first time it ACTUALLY happens. If a
    # trigger whose conditions failed consumed the use, the ability would be
    # dead for the turn without ever having fired.
    st = _state()
    hero = _card("briar")
    st.players[1].hero_zone.add(hero)
    # No combat at all -> the attack conditions fail.
    dispatch(st, "ON_DEAL_DAMAGE", hero.slug, card=hero, event=None)
    assert not [c for c in st.players[1].permanents.cards
                if "earth" in (c.slug or "").lower()]
    atk = _attacking(st, card=Card(slug="a", name="a", types=["Action"],
                                   subtypes=["Attack"]))
    atk.owner = atk.controller = 1
    dispatch(st, "ON_DEAL_DAMAGE", hero.slug, card=hero, event=None)
    assert len([c for c in st.players[1].permanents.cards
                if "earth" in (c.slug or "").lower()]) == 1


# --- "your SECOND non-attack action card each turn" (exact count) -----------

def test_exact_count_fires_on_the_second_only():
    st = _state()
    card = _card("briar")
    cond = compile_condition("EVENT_THIS_TURN",
                             {"event": "play", "qualifier": "non_attack_action",
                              "count": 2, "exact": True})
    from engine.effect_keywords import _record_turn_event
    _record_turn_event(st, 1, "play", "non_attack_action")
    assert cond(card, None, st) is False, "fired on the first"
    _record_turn_event(st, 1, "play", "non_attack_action")
    assert cond(card, None, st) is True, "did not fire on the second"
    _record_turn_event(st, 1, "play", "non_attack_action")
    assert cond(card, None, st) is False, \
        "still true on the third — 'the second' became 'the second and after'"


# --- "another Illusionist aura you control" (exclude_self) ------------------

def test_controls_subtype_excludes_the_asking_card():
    # Without exclude_self, Sigil of Solitude sees ITSELF and destroys itself at
    # the start of every turn.
    st = _state()
    sigil = _card("sigil_of_solitude_red")
    sigil.subtypes = ["Aura"]
    sigil.classes = ["Illusionist"]
    st.players[1].permanents.add(sigil)
    cond = compile_condition("CONTROLS_SUBTYPE",
                             {"subtype": "Aura", "card_class": "Illusionist",
                              "exclude_self": True})
    assert cond(sigil, None, st) is False


def test_controls_subtype_sees_another_matching_aura():
    st = _state()
    sigil = _card("sigil_of_solitude_red")
    sigil.subtypes = ["Aura"]
    sigil.classes = ["Illusionist"]
    st.players[1].permanents.add(sigil)
    other = Card(slug="other_aura", name="Other", types=["Action"],
                 subtypes=["Aura"])
    other.owner = other.controller = 1
    other.classes = ["Illusionist"]
    st.players[1].permanents.add(other)
    cond = compile_condition("CONTROLS_SUBTYPE",
                             {"subtype": "Aura", "card_class": "Illusionist",
                              "exclude_self": True})
    assert cond(sigil, None, st) is True


def test_controls_subtype_respects_the_class():
    st = _state()
    sigil = _card("sigil_of_solitude_red")
    sigil.subtypes = ["Aura"]
    sigil.classes = ["Illusionist"]
    st.players[1].permanents.add(sigil)
    other = Card(slug="wizard_aura", name="W", types=["Action"], subtypes=["Aura"])
    other.owner = other.controller = 1
    other.classes = ["Wizard"]
    st.players[1].permanents.add(other)
    cond = compile_condition("CONTROLS_SUBTYPE",
                             {"subtype": "Aura", "card_class": "Illusionist",
                              "exclude_self": True})
    assert cond(sigil, None, st) is False


# --- "a Runeblade or Wizard HERO" (not the attack's class) -----------------

def test_target_hero_class_reads_the_defending_hero():
    st = _state()
    st.players[2].hero.classes = ["Wizard"]
    _attacking(st, pid=1)
    cond = compile_condition("TARGET_HERO_CLASS_IN",
                             {"classes": ["Runeblade", "Wizard"]})
    assert cond(_card("mage_hunter_arrow_red"), None, st) is True


def test_target_hero_class_is_false_for_another_class():
    st = _state()
    st.players[2].hero.classes = ["Guardian"]
    _attacking(st, pid=1)
    cond = compile_condition("TARGET_HERO_CLASS_IN",
                             {"classes": ["Runeblade", "Wizard"]})
    assert cond(_card("mage_hunter_arrow_red"), None, st) is False


# --- "played or activated an attack reaction THIS CHAIN LINK" ---------------

def test_reaction_this_link_is_false_with_no_reaction():
    st = _state()
    _attacking(st, pid=2)          # player 2 attacks, player 1 defends
    cond = compile_condition("REACTION_THIS_LINK",
                             {"kind": "attack_reaction", "player": "ATTACKING"})
    assert cond(_card("hunted_or_hunter_red"), None, st) is False


def test_reaction_this_link_sees_the_attackers_reaction():
    st = _state()
    _attacking(st, pid=2)
    st.combat.reactions_this_link.append((2, "attack_reaction"))
    cond = compile_condition("REACTION_THIS_LINK",
                             {"kind": "attack_reaction", "player": "ATTACKING"})
    assert cond(_card("hunted_or_hunter_red"), None, st) is True


def test_reaction_record_does_not_survive_into_the_next_chain_link():
    # The whole reason this is chain-link scoped: a turn-scoped record would let
    # a reaction from the turn's first attack keep answering yes forever.
    st = _state()
    _attacking(st, pid=2)
    st.combat.reactions_this_link.append((2, "attack_reaction"))
    _attacking(st, pid=2)          # a new attack builds a new CombatState
    cond = compile_condition("REACTION_THIS_LINK",
                             {"kind": "attack_reaction", "player": "ATTACKING"})
    assert cond(_card("hunted_or_hunter_red"), None, st) is False


# --- the migration guard ---------------------------------------------------

@pytest.mark.parametrize("slug", [
    "aftershock_red", "auric_shards_yellow", "break_ground_red", "briar",
    "cash_out_blue", "dashing_flashfoot_yellow", "downswing_red",
    "envelop_in_darkness_red", "grandstand_legplates", "high_roller_yellow",
    "hunted_or_hunter_red", "imposing_visage_blue", "infuse_alloy_yellow",
    "lesson_in_lava_yellow", "loan_shark_yellow", "mage_hunter_arrow_red",
    "pound_town_blue", "reel_in_blue", "reckless_charge_blue", "rift_bind_blue",
    "sigil_of_solitude_red", "song_of_sinew_yellow", "vaporize__shock_yellow",
])
def test_no_dead_flag_remains(slug):
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    path = _card_json(root, f"{slug}.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    abilities = json.dumps(raw.get("abilities", []))
    assert "FLAG_SET" not in abilities, (
        f"{slug} still gates on a flag; every flag these cards used was written "
        "by nothing, so the ability could never fire"
    )

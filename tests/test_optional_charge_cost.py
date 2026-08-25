""""You MAY charge your hero's soul" — 27 cards, and no way to say it.

The top entry in scripts/mechanic_backlog.py: 27 unimplemented cards share

    As an additional cost to play this, you may **charge** your hero's soul.
    If a **yellow** card is **charged** this way, <payoff>.

Two things were missing, and the second is the interesting one.

  optional      An additional cost that is optional must NEVER block the play.
                The CHARGE cost added for v_for_valor_yellow is mandatory --
                correct there, since that card's charge is part of a colon
                cost -- so `can_pay` refused the play on an empty hand.

  "this way"    The payoff asks WHAT was charged, not merely whether a charge
                happened. A turn-scoped marker (the shape used for
                sharpen_extra and looking_for_a_scrap) is wrong here: it would
                leak to the next card played in the same turn. "This way" is
                per-play, so the charged card's colour is stamped on the card
                being played.

Note the distinction from "if you've CHARGED THIS TURN" (saving_grace_yellow),
which really is a turn event and a different question.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.cost_types import compile_cost
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

YELLOW = "amplifying_arrow_yellow"
RED = "brutal_assault_red"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state(agent=None):
    st = _make_state()
    st.card_db = DB
    pick = agent or (lambda s, o, context="": o[0])
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def _pick(slug):
    return lambda s, o, context="": slug if slug in o else (o[0] if o else None)


def test_the_fixtures_are_the_colours_they_claim():
    """Card.color is None on real cards; the printing lives on base_color."""
    assert (DB.get(YELLOW).base_color or "").lower() == "yellow"
    assert (DB.get(RED).base_color or "").lower() == "red"


# --- optionality ------------------------------------------------------------

def test_an_optional_charge_never_blocks_the_play():
    """An empty hand must not make the card unplayable."""
    st = _state()
    can_pay, _pay = compile_cost("CHARGE", {"amount": 1, "optional": True})

    assert can_pay(_card(RED), None, st) is True


def test_a_mandatory_charge_still_blocks():
    """v_for_valor_yellow's charge IS part of its cost and must keep blocking."""
    st = _state()
    can_pay, _pay = compile_cost("CHARGE", {"amount": 1})

    assert can_pay(_card(RED), None, st) is False


def test_declining_charges_nothing():
    st = _state(agent=lambda s, o, context="": None)
    _can, pay = compile_cost("CHARGE", {"amount": 1, "optional": True})
    held = _card(YELLOW)
    st.players[1].hand.add(held)
    source = _card(RED)

    pay(source, None, st)

    assert held in st.players[1].hand.cards, "it charged unasked"
    assert st.players[1].soul.cards == []


# --- "charged THIS WAY" -----------------------------------------------------

def test_paying_records_the_colour_of_the_charged_card():
    st = _state(agent=_pick(YELLOW))
    _can, pay = compile_cost("CHARGE", {"amount": 1, "optional": True})
    st.players[1].hand.add(_card(YELLOW))
    source = _card(RED)

    pay(source, None, st)

    assert compile_condition("CHARGED_THIS_WAY", {"color": "yellow"})(
        source, None, st) is True


def test_a_different_colour_does_not_satisfy_the_gate():
    st = _state(agent=_pick(RED))
    _can, pay = compile_cost("CHARGE", {"amount": 1, "optional": True})
    st.players[1].hand.add(_card(RED))
    source = _card(RED)

    pay(source, None, st)

    assert compile_condition("CHARGED_THIS_WAY", {"color": "yellow"})(
        source, None, st) is False


def test_the_gate_is_false_when_nothing_was_charged():
    st = _state()
    source = _card(RED)

    assert compile_condition("CHARGED_THIS_WAY", {"color": "yellow"})(
        source, None, st) is False


def test_it_does_not_leak_to_another_card_played_this_turn():
    """"THIS WAY" is per-play. A turn-scoped marker — the shape used for
    sharpen_extra — would hand the payoff to the next card too."""
    st = _state(agent=_pick(YELLOW))
    _can, pay = compile_cost("CHARGE", {"amount": 1, "optional": True})
    st.players[1].hand.add(_card(YELLOW))
    paid_card = _card(RED)

    pay(paid_card, None, st)
    other_card = _card(RED)

    fn = compile_condition("CHARGED_THIS_WAY", {"color": "yellow"})
    assert fn(paid_card, None, st) is True
    assert fn(other_card, None, st) is False, (
        "a second card played this turn inherited the charge payoff")


# --- the cards --------------------------------------------------------------

def _attacking(st, slug):
    card = _card(slug, 1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=card, keywords=[])
    return card


@pytest.mark.parametrize("slug", ["beaming_bravado_red", "beaming_bravado_blue",
                                  "beaming_bravado_yellow"])
def test_beaming_bravado_gets_the_power_only_for_a_yellow_charge(slug):
    st = _state()
    card = _attacking(st, slug)
    before = st.combat.attack_power

    # No charge at all.
    run_ability(get_card(slug).abilities[0], card, None, st)
    assert st.combat.attack_power == before, "it buffed with nothing charged"

    # A RED card charged: still no payoff.
    card.dsl_charged_color = "red"
    run_ability(get_card(slug).abilities[0], card, None, st)
    assert st.combat.attack_power == before, "a red charge paid out"

    # A YELLOW card charged.
    card.dsl_charged_color = "yellow"
    run_ability(get_card(slug).abilities[0], card, None, st)
    assert st.combat.attack_power == before + 1


def _hit(st):
    """Fire the real hit event, so an INJECTED on-hit trigger has to actually
    be registered and fire — running the play ability alone only injects it."""
    from engine.state import Event
    st.combat.hit = True
    st.event_manager.emit(Event(type="hit", data={}), st)


def test_light_the_way_grants_go_again_only_on_hit_after_a_yellow_charge():
    st = _state()
    card = _attacking(st, "light_the_way_red")
    card.dsl_charged_color = "yellow"

    run_ability(get_card("light_the_way_red").abilities[0], card, None, st)
    assert not any("go again" in str(k).lower()
                   for k in (st.combat.keywords or [])), (
        "go again arrived before the hit")

    _hit(st)

    assert any("go again" in str(k).lower()
               for k in (st.combat.keywords or [])), st.combat.keywords


def test_light_the_way_does_nothing_without_the_yellow_charge():
    st = _state()
    card = _attacking(st, "light_the_way_red")

    run_ability(get_card("light_the_way_red").abilities[0], card, None, st)
    _hit(st)

    assert not any("go again" in str(k).lower()
                   for k in (st.combat.keywords or []))


def test_glaring_impact_grants_overpower_after_a_yellow_charge():
    st = _state()
    card = _attacking(st, "glaring_impact_blue")
    card.dsl_charged_color = "yellow"

    run_ability(get_card("glaring_impact_blue").abilities[0], card, None, st)

    assert any("overpower" in str(k).lower()
               for k in (st.combat.keywords or [])), st.combat.keywords


def test_every_charge_card_declares_the_cost_as_a_COST():
    """An additional cost modelled as an ON_PLAY effect makes the card playable
    when it cannot pay — the rule this project keeps re-learning."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    for slug in ("beaming_bravado_red", "beaming_bravado_blue",
                 "beaming_bravado_yellow", "light_the_way_red",
                 "glaring_impact_blue"):
        raw = json.loads(next(root.rglob(f"{slug}.json")).read_text(encoding="utf-8"))
        play = raw["abilities"][0]
        # Cost and payoff live on ONE ability: an ability carrying only a cost
        # has an empty effects list, which resolves as a no-op and is caught by
        # test_card_json_hygiene::test_every_ability_has_effects.
        assert play.get("effects"), f"{slug}'s PLAY ability has no effects"
        costs = [c.get("type") for c in play.get("additional_cost", [])]
        assert "CHARGE" in costs, f"{slug} does not declare CHARGE as a cost: {costs}"
        # Keyed on the `type` FIELD, not a substring: "CHARGE" also occurs
        # inside "CHARGED_THIS_WAY", which is the gate, not a second charge.
        # The same substring-for-type slip cost two cards in the sharpen sweep.
        def types_of(node, out):
            if isinstance(node, dict):
                if isinstance(node.get("type"), str):
                    out.add(node["type"])
                for v in node.values():
                    types_of(v, out)
            elif isinstance(node, list):
                for v in node:
                    types_of(v, out)
        used = set()
        types_of(play.get("effects", []), used)
        assert "CHARGE" not in used, f"{slug} also charges as an effect: {used}"

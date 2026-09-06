"""A gated go again, an additional cost, and the one word that decides both.

    "As an additional cost to play Barraging Big Horn, discard a random card.
     While Barraging Big Horn is defended by less than 2 NON-EQUIPMENT cards,
     it has go again."

THE COST IS CARD-LEVEL. play.py checks a card-level `cost` for legality and
pays it once when the card is played, which is what an additional cost is. As
an ON_PLAY EFFECT it would not block anything -- the card would be playable
with an empty hand and simply discard nothing. As an ABILITY-level
`additional_cost` on the static below it would be paid on every dispatch, and a
WHILE_STATIC is dispatched on every attack-power recalculation, so one attack
would empty the hand (that is the Breakneck Battery lesson,
tests/test_costs_are_not_repaid.py).

"NON-EQUIPMENT" IS THE LOAD-BEARING WORD. Equipment defends for free every
turn, so counting it would make the gate almost always false and the card
almost never have go again -- a card that reads as an upside and plays as a
downside. The two-equipment case below is the one that separates a correct
implementation from a plausible one.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import (conditional_keywords, get_card,
                                            load_all_cards)
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

CARD = "barraging_big_horn_blue"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


@pytest.fixture(scope="module")
def fodder():
    """A real equipment card and a real non-equipment card that can defend."""
    import io, json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    idx = json.load(io.open(root / "card_data" / "slug_index.json",
                            encoding="utf-8"))["by_slug"]
    equip = next(s for s, e in idx.items()
                 if "Equipment" in (e.get("types") or []) and DB.get(s))
    card = next(s for s, e in idx.items()
                if "Action" in (e.get("types") or [])
                and "Equipment" not in (e.get("types") or [])
                and (e.get("defense") or 0) > 0 and DB.get(s))
    return equip, card


def _attack_defended_by(slugs):
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="", **kw: o[0]      # noqa: E731
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    attacker = _card(CARD)
    power = attacker.raw_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=attacker, keywords=[])
    st.combat.base_attack_power = power
    st.combat.defending_cards = [_card(s, 2) for s in slugs]
    E._apply_turn_attack_effects(st, attacker)
    E._register_card_continuous_effects(st, attacker)
    E._recalculate_attack_power(st)
    return st


def _go_again(st):
    return "goagain" in {str(k).lower().replace(" ", "").replace("_", "")
                         for k in (st.combat.keywords or [])}


def test_the_two_probes_are_what_they_claim(fodder):
    """Guards the equipment test below: if the 'equipment' probe stopped being
    equipment it would count as a normal defender and the test would pass for
    the wrong reason."""
    equip, card = fodder
    assert "Equipment" in (DB.get(equip).types or [])
    assert "Equipment" not in (DB.get(card).types or [])


def test_undefended_it_has_go_again():
    assert _go_again(_attack_defended_by([]))


def test_one_non_equipment_defender_is_still_less_than_two(fodder):
    _equip, card = fodder
    assert _go_again(_attack_defended_by([card]))


def test_two_non_equipment_defenders_take_it_away(fodder):
    _equip, card = fodder
    assert not _go_again(_attack_defended_by([card, card]))


def test_equipment_defenders_do_not_count(fodder):
    """THE ONE THAT MATTERS. Equipment defends every turn at no cost, so an
    implementation that counted it would take go again away in the ordinary
    case and the card would almost never have it."""
    equip, _card_slug = fodder
    assert _go_again(_attack_defended_by([equip, equip, equip]))


def test_the_printed_go_again_is_stripped():
    """Without the strip the gate is decoration: the DB lists GoAgain
    unconditionally because it flattens the sentence, so the attack would have
    it no matter how it was defended."""
    assert "GoAgain" in (DB.get(CARD).keywords or [])
    assert "goagain" in conditional_keywords(CARD)


def test_the_discard_is_a_cost_and_not_an_effect():
    """A cost blocks the play; an effect does not. Asserted on the compiled
    card, because the difference is invisible in resolution: both spellings
    discard a card when the card resolves, and only one of them stops an empty
    hand from playing it."""
    card = get_card(CARD)
    assert getattr(card, "play_cost", None), (
        "the additional cost is not compiled as a play cost, so it cannot "
        "block the play")
    for ability in card.abilities:
        assert not getattr(ability, "additional_costs", None), (
            "an ability-level additional cost on a WHILE_STATIC is paid on "
            "every attack-power recalculation")

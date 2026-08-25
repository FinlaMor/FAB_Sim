"""Three cards that never fired, and would have peeked at the wrong deck.

"When this is put or turned face up in arsenal, look at the top N cards of YOUR
deck, then put them back in any order." Three defects, stacked:

  wrong trigger   ON_ENTER_PLAY fires on ARENA entry. An arsenal is not the
                  arena, so the ability never fired at all. The vocabulary has
                  ON_PUT_FACEUP_IN_ARSENAL for exactly this wording.
  wrong player    LOOK_AT defaults `player` to OPPONENT. A card saying "the top
                  of YOUR deck" peeked at the opponent's -- not a dead effect
                  but an information leak in the wrong direction, which is the
                  worse failure of the two.
  missing clause  "then put them back in any order" had no implementation at
                  all; REORDER_REF acts on the ref LOOK_AT stores, and it too
                  defaults to OPPONENT.

The default-to-OPPONENT on both effects is the recurring shape: a default that
encodes the first caller's meaning, silently wrong for everyone after.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

CARDS = ["spire_sniping_red", "spire_sniping_yellow", "scouting_shot_red"]
FILLER = "brutal_assault_red"
OTHER = "amplifying_arrow_yellow"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def _stock(st):
    """Distinct cards on top of each deck, so 'which deck' is observable."""
    mine = [_card(FILLER, 1) for _ in range(3)]
    for c in mine:
        st.players[1].deck.add(c)
    theirs = [_card(OTHER, 2) for _ in range(3)]
    for c in theirs:
        st.players[2].deck.add(c)
    return mine, theirs


# --- the cards --------------------------------------------------------------

@pytest.mark.parametrize("slug", CARDS)
def test_the_trigger_is_the_arsenal_one(slug):
    """ON_ENTER_PLAY fires on arena entry; an arsenal is not the arena, so the
    ability could never fire."""
    trigs = [a.trigger for a in get_card(slug).abilities]
    assert "ON_PUT_FACEUP_IN_ARSENAL" in trigs, trigs
    assert "ON_ENTER_PLAY" not in trigs, trigs


# "which deck does it look at" lives in test_look_at_target_honoured.py, whose
# parametrized guard these three cards were added to rather than duplicated
# here.


@pytest.mark.parametrize("slug", ["spire_sniping_red", "spire_sniping_yellow"])
def test_the_looked_cards_stay_in_the_controllers_deck(slug):
    """"then put them back in any order" — back, not away."""
    st = _state()
    mine, _ = _stock(st)
    before = len(st.players[1].deck.cards)

    run_ability(get_card(slug).abilities[0], _card(slug, 1), None, st)

    assert len(st.players[1].deck.cards) == before
    assert all(c in st.players[1].deck.cards for c in mine)


@pytest.mark.parametrize("slug", ["spire_sniping_red", "spire_sniping_yellow"])
def test_the_reorder_clause_is_implemented(slug):
    types = []

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("type"), str):
                types.append(node["type"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    walk(json.loads(next(root.rglob(f"{slug}.json")).read_text(encoding="utf-8"))
         .get("abilities"))
    assert "REORDER_REF" in types, (
        f"{slug} looks at cards and never puts them back in any order: {types}")

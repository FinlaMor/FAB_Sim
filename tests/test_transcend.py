"""Transcend (CR 8.5.48) — wired end to end for the first time.

Transcend existed in the engine as TWO implementations with ZERO callers: the
canonical `effect_keywords.transcend` and a divergent
`ability_keywords.effect_transcend` that moved the card by hand, set a bespoke
attribute, emitted no event and recorded nothing. There was also no DSL effect
type, so no card could transcend at all.

26 cards depend on it — 13 sources that grant it and 13 checkers asking "if
you've transcended this turn", every checker having invented its own flag, two of
them MISSPELLED (TRANSCEDED, TRANSCEDED_THIS_TURN), so they could not even have
collided into working by accident.
"""
import copy

import pytest

from engine.card import Card, CardDB
from engine.card_effects.dsl import dispatch
from engine.card_effects.dsl.loader import load_all_cards
from engine.effect_keywords import TURN_EVENT_MARKER, transcend
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

MARKER = f"{TURN_EVENT_MARKER}transcend"



def _card_json(root, name):
    """The implemented card file called `name`, ignoring pipeline artifacts.

    rglob walks EVERYTHING under the json tree, and in the pipeline worktree
    that tree also holds .drafts/, .review/ and .triage/ results filed under
    the same slug. Taking the first match there picked up a review verdict --
    a JSON object with no "abilities" -- so tests that pass here failed in the
    worktree for a reason that had nothing to do with the card.
    """
    hits = [p for p in root.rglob(name)
            if not any(part.startswith(".") for part in p.parts)]
    assert hits, f"no implemented card file for {name}"
    return hits[0]

def _state():
    st = _make_state()
    st.card_db = DB
    return st


def _card(slug, owner=1):
    base = DB.get(slug)
    assert base is not None, f"unknown slug {slug}"
    c = copy.deepcopy(base)
    c.owner = c.controller = owner
    return c


# --- the canonical keyword -------------------------------------------------

def test_transcend_puts_the_source_in_its_owners_hand():
    st = _state()
    card = _card("a_drop_in_the_ocean_blue")
    st.players[1].arsenal.add(card)
    transcend(st, card, 1)
    assert card in st.players[1].hand.cards


def test_transcend_activates_the_back_face():
    # CR 9.1.5b: the back face stays active for the rest of the game.
    st = _state()
    card = _card("a_drop_in_the_ocean_blue")
    st.players[1].arsenal.add(card)
    transcend(st, card, 1)
    assert card.counters.get("__back_face_active__") == 1


def test_transcend_records_the_turn_event():
    # CR 8.5.48a: "the player that controls the effect is considered to have
    # transcended" — this is what all 13 checker cards read.
    st = _state()
    card = _card("a_drop_in_the_ocean_blue")
    st.players[1].arsenal.add(card)
    assert MARKER not in st.players[1].current_turn_effects
    transcend(st, card, 1)
    assert MARKER in st.players[1].current_turn_effects


def test_transcend_records_against_the_transcending_player_only():
    st = _state()
    card = _card("a_drop_in_the_ocean_blue")
    st.players[1].arsenal.add(card)
    transcend(st, card, 1)
    assert MARKER not in st.players[2].current_turn_effects


def test_duplicate_implementation_now_delegates():
    # ability_keywords.effect_transcend was a second, divergent implementation.
    # It must now produce the SAME observable outcome as the canonical one.
    from engine.card_effects.ability_keywords import effect_transcend
    st = _state()
    card = _card("a_drop_in_the_ocean_blue")
    st.players[1].arsenal.add(card)
    assert effect_transcend(st, 1, card) is True
    assert card in st.players[1].hand.cards
    assert card.counters.get("__back_face_active__") == 1
    assert MARKER in st.players[1].current_turn_effects


# --- the checkers ----------------------------------------------------------

def test_moon_chakra_prevents_3_without_a_transcend():
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _state()
    card = _card("moon_chakra_red")
    cond = compile_condition("EVENT_THIS_TURN", {"event": "transcend"})
    assert cond(card, None, st) is False


def test_moon_chakra_condition_true_after_transcending():
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _state()
    src = _card("a_drop_in_the_ocean_blue")
    st.players[1].arsenal.add(src)
    transcend(st, src, 1)
    card = _card("moon_chakra_red")
    cond = compile_condition("EVENT_THIS_TURN", {"event": "transcend"})
    assert cond(card, None, st) is True


@pytest.mark.parametrize("slug", [
    "moon_chakra_red", "tide_chakra_yellow", "wind_chakra_red", "twelve_petal_kasaya",
])
def test_no_misspelled_transcend_flag_remains(slug):
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    path = _card_json(root, f"{slug}.json")
    abilities = json.dumps(json.loads(path.read_text(encoding="utf-8"))["abilities"])
    assert "FLAG_SET" not in abilities, f"{slug} still reads an invented flag"
    for misspelling in ("TRANSCEDED", "TRANSCENDED", "TRANSCEND_THIS_TURN"):
        assert f'"{misspelling}"' not in abilities


# --- the ON_TRANSCEND trigger ----------------------------------------------

def test_on_transcend_fires_for_equipment():
    # "Whenever you transcend, you may gain {r}" (Twelve Petal Kasaya). The boo
    # and cheer listeners dispatch to the HERO only; this card is chest
    # equipment, so a hero-only dispatch would never reach it.
    from engine.engine import _setup_dsl_listeners
    st = _state()
    _setup_dsl_listeners(st)
    kasaya = _card("twelve_petal_kasaya")
    st.players[1].chest.add(kasaya)
    src = _card("a_drop_in_the_ocean_blue")
    st.players[1].arsenal.add(src)

    before = st.players[1].resources
    transcend(st, src, 1)
    assert st.players[1].resources == before + 1


def test_on_transcend_does_not_fire_for_the_other_player():
    from engine.engine import _setup_dsl_listeners
    st = _state()
    _setup_dsl_listeners(st)
    kasaya = _card("twelve_petal_kasaya", owner=1)
    st.players[1].chest.add(kasaya)
    src = _card("a_drop_in_the_ocean_blue", owner=2)
    st.players[2].arsenal.add(src)

    before = st.players[1].resources
    transcend(st, src, 2)          # player 2 transcends
    assert st.players[1].resources == before


# --- the source ------------------------------------------------------------

def test_drop_in_the_ocean_no_longer_uses_the_arakni_transform():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    path = _card_json(root, "a_drop_in_the_ocean_blue.json")
    abilities = json.dumps(json.loads(path.read_text(encoding="utf-8"))["abilities"])
    assert "TRANSFORM_HERO" not in abilities
    assert "TRANSCEND" in abilities


def test_drop_in_the_ocean_transcends_only_after_another_blue_card():
    # "If you've played ANOTHER blue card this turn" -> the card's own play
    # counts, so one blue play must NOT be enough.
    st = _state()
    card = _card("a_drop_in_the_ocean_blue")
    st.players[1].arsenal.add(card)
    st.players[1].current_turn_effects.append(f"{TURN_EVENT_MARKER}play:blue")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert card not in st.players[1].hand.cards, "transcended on its own play alone"


def test_drop_in_the_ocean_transcends_after_a_second_blue_card():
    st = _state()
    card = _card("a_drop_in_the_ocean_blue")
    st.players[1].arsenal.add(card)
    for _ in range(2):
        st.players[1].current_turn_effects.append(f"{TURN_EVENT_MARKER}play:blue")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert card in st.players[1].hand.cards
    assert MARKER in st.players[1].current_turn_effects

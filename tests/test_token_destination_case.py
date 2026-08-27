"""A token destination in caps aborted the game.

Zone names are Player ATTRIBUTES, so they are lowercase; every other parameter
in this DSL is authored in caps. `create_token` looked the destination up with
`getattr(controller, event.destination)` and raised ValueError when it missed,
so a card writing the natural `{"zone": "BANISHED"}` did not misbehave -- it
stopped the game mid-resolution.

The corpus proves the convention was never settled: of eight CREATE_TOKEN nodes
naming a destination, two say "BANISHED" and one says "banished", two say
"HAND" and one says "hand". Half the cards were written against each spelling
and only one half worked.

Case is not information here. Folding it in the canonical function fixes every
caller at once, which is the point of having a canonical function; the
alternative was 985 cards each guessing which convention this one parameter
follows.

Found by the corpus review pass on blessing_of_qi_red, and confirmed by running
the card rather than by reading the report -- `harmony_of_the_hunt_blue` was
reported for the same defect and does not raise.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.effect_keywords import create_token
from tests.conftest import _make_state
from tests.conftest import card_json_files

load_all_cards()
DB = CardDB()

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


@pytest.mark.parametrize("zone", ["banished", "BANISHED", "hand", "HAND"])
def test_a_destination_works_in_either_case(zone):
    st = _state()

    create_token(st, source_player_id=1, target_player_id=1,
                 token="crouching_tiger", destination=zone)

    landed = getattr(st.players[1], zone.lower()).cards
    assert landed, f"nothing reached {zone.lower()} for destination {zone!r}"


def test_an_unknown_destination_still_raises():
    """Folding case must not turn a typo into a silent no-op -- a destination
    that names no zone is an authoring error and should still be loud."""
    st = _state()
    with pytest.raises(ValueError):
        create_token(st, source_player_id=1, target_player_id=1,
                     token="crouching_tiger", destination="NOT_A_ZONE")


def test_a_real_token_is_still_a_token():
    """The fix must not stop tokens BEING tokens: Frostbite is types=['Token']
    in the card DB, and CR 3.0.12a still has it cease to exist on entering the
    banished zone."""
    st = _state()
    create_token(st, source_player_id=1, target_player_id=1, token="frostbite")
    made = [c for c in st.players[1].permanents.cards + st.players[1].tokens.cards
            if "frostbite" in (c.slug or "")]
    assert made, "no Frostbite was created"
    assert "Token" in (made[0].types or []), made[0].types


def test_crouching_tiger_is_created_as_a_card_and_stays_banished():
    """The release notes are explicit: "Crouching Tiger is a CARD... it spawns
    into the game", and "if you do not play it the turn it was created, it
    REMAINS in the banished zone". Stamped as a token it hit CR 3.0.12a and
    ceased to exist on arrival -- silently, in no zone, with no error."""
    st = _state()

    create_token(st, source_player_id=1, target_player_id=1,
                 token="crouching_tiger", destination="banished")

    banished = [c.slug for c in st.players[1].banished.cards]
    assert "crouching_tiger" in banished, banished
    tiger = st.players[1].banished.cards[0]
    assert "Token" not in (tiger.types or []), (
        f"created as a token, so CR 3.0.12a clears it: {tiger.types}")


def test_blessing_of_qi_puts_a_crouching_tiger_in_the_banished_zone():
    """It raised ValueError: unknown destination zone 'BANISHED', and once that
    was folded it created nothing anywhere -- the Tiger was stamped as a token
    and CR 3.0.12a cleared it on arrival.

    Asserting the Tiger LANDS, not merely that nothing raised: "it did not
    throw" is what the silent version already satisfied.
    """
    st = _state()
    src = copy.deepcopy(DB.get("blessing_of_qi_red"))
    src.owner = src.controller = 1

    for ab in get_card("blessing_of_qi_red").abilities:
        run_ability(ab, src, None, st)

    assert "crouching_tiger" in [c.slug for c in st.players[1].banished.cards], (
        "the card resolved without error and created nothing, in any zone")


def test_every_authored_token_destination_resolves():
    """Derived from the corpus: every destination any card names must exist on
    a Player, whatever case it is written in."""
    from engine.state import Player

    bad = []
    for path in card_json_files(JSON_ROOT):
        rel = path.relative_to(JSON_ROOT)
        if (path.stem.endswith("_work_queue")
                or any(p.startswith(".") or p == "needs_review"
                       for p in rel.parts)):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "CREATE_TOKEN":
                    z = (node.get("destination") or node.get("zone")
                         or node.get("to_zone"))
                    # weapon_slot is handled by its own branch, not getattr.
                    if z and str(z).lower() not in ("tokens", "weapon_slot"):
                        if not hasattr(Player, str(z).lower()):
                            probe = _state().players[1]
                            if getattr(probe, str(z).lower(), None) is None:
                                bad.append(f"{raw.get('slug')}: {z}")
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(raw.get("abilities"))
    assert bad == [], f"token destinations that name no player zone: {bad}"

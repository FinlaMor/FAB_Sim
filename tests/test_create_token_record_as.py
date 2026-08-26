"""Two printed clauses nested inside a node that does not read them.

Blessing of Qi: "At the start of your turn, destroy this, then create a
Crouching Tiger in your banished zone. IT GAINS +3{p} AND YOU MAY PLAY IT THIS
TURN."

Both halves of that last sentence lived inside the CREATE_TOKEN node, under an
`effects` key. CREATE_TOKEN reads token, count, player/controller, destination
and counters -- and nothing else. So the +3{p} never applied and the
play-permission never reached `player.playable_from_banished`; the card created
a 0-power token in the banished zone and stopped.

This is the unread-parameter class in its most deceptive form. The nested node
LOOKS like structure the interpreter walks -- `effects` is exactly the key that
holds child effects elsewhere -- so nothing about the JSON reads as wrong, and
scripts/audit_params.py does not flag it because `effects` is a container key
it recurses through rather than a leaf parameter.

GRANT_PLAY_FROM_BANISHED already did both halves (it takes a ref and a
power_mod). What was missing was a way to NAME the token that was just created,
so CREATE_TOKEN now takes `record_as`.

Crouching Tiger's printed power is 0, so the +3 makes it 3 -- worth stating,
because "power == 3" looks like an unchanged default until you check the
printed value.
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
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _run():
    st = _state()
    src = copy.deepcopy(DB.get("blessing_of_qi_red"))
    src.owner = src.controller = 1
    run_ability(get_card("blessing_of_qi_red").abilities[0], src, None, st)
    return st


def _tiger(st):
    found = [c for c in st.players[1].banished.cards
             if c.slug == "crouching_tiger"]
    assert found, [c.slug for c in st.players[1].banished.cards]
    return found[0]


# --- the premise ------------------------------------------------------------

def test_crouching_tiger_is_printed_with_zero_power():
    """So +3 lands on 0 and the result is 3. Without this the power assertion
    below would pass on a token that was never modified."""
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    assert (idx["crouching_tiger"].get("power") or 0) == 0


# --- both clauses -----------------------------------------------------------

def test_the_token_reaches_the_banished_zone():
    st = _run()

    assert [c.slug for c in st.players[1].banished.cards] == ["crouching_tiger"]


def test_it_gains_the_printed_three_power():
    st = _run()
    assert _tiger(st).power == 3, (
        "the +3{p} was nested under a key CREATE_TOKEN does not read")


def test_you_may_play_it_this_turn():
    st = _run()
    playable = [getattr(c, "slug", c)
                for c in (getattr(st.players[1], "playable_from_banished", None) or [])]
    assert "crouching_tiger" in playable, (
        f"the play-permission never reached the player: {playable}")


# --- the mechanism ----------------------------------------------------------

def test_record_as_names_the_created_token():
    """The generic half: a card can now act on what it just created instead of
    re-searching the zone and hoping to land on the same object."""
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.context import get_ref, pop_refs, push_refs

    st = _state()
    src = copy.deepcopy(DB.get("blessing_of_qi_red"))
    src.owner = src.controller = 1
    fn = compile_effect("CREATE_TOKEN", {"token": "gold", "record_as": "made"})

    push_refs()
    try:
        fn(src, None, st)
        made = get_ref("made")
    finally:
        pop_refs()

    assert made is not None and getattr(made, "slug", None) == "gold", made


def test_no_card_nests_effects_inside_create_token():
    """The shape that hid this. CREATE_TOKEN reads no `effects` key, so a
    nested one is dropped in silence."""
    root = ROOT / "engine" / "card_effects" / "json"
    bad = []
    for path in root.rglob("*.json"):
        rel = path.relative_to(root)
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
                if node.get("type") == "CREATE_TOKEN" and "effects" in node:
                    bad.append(raw.get("slug"))
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(raw.get("abilities"))
    assert bad == [], f"CREATE_TOKEN with a nested effects key, silently dropped: {bad}"

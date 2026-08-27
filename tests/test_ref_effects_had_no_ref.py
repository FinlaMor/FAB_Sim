"""Ten ref effects were handed a `target` and acted on a ref nobody set.

DESTROY_REF and BANISH_REF act on `get_ref(ref)`. Ten nodes were given a
`target` instead — which neither handler reads — and in EVERY case no earlier
effect in the same ability sets a ref at all. Reference scopes are per ability
execution (interpreter.run_ability pushes one), so there was nothing to fall
back on: all ten returned before doing anything.

This is the quietest shape in the whole sweep. The effect is not aimed at the
wrong object, the way BANISH's unread target aimed at the caster's own deck —
it is aimed at NO object. Nothing happens, nothing is logged, and the card looks
implemented.

Two of them also named the wrong ACTION: "turn a card in their banished zone
face-down" was authored as BANISH_REF, but the card is already banished — the
effect turns it over, which is what hides it from the effects that reference
banished cards.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import load_all_cards, get_card
from tests.conftest import _card_json, _make_state, card_json_files

load_all_cards()
DB = CardDB()

FILLER = "wounded_bull_red"


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    return c


def _stock(st, pid, zone, n=3, slug=FILLER):
    cards = [_card(slug, owner=pid) for _ in range(n)]
    getattr(st.players[pid], zone).cards = cards
    return cards


def _run_type(slug, etype, card, st):
    """Compile and run the card's node of `etype`, wherever it is nested."""
    import json
    from pathlib import Path
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.context import push_refs, pop_refs

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(_card_json(root, f"{slug}.json").read_text(encoding="utf-8"))
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == etype:
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(raw.get("abilities", []))
    assert found, f"{slug} has no {etype} node"
    push_refs()
    try:
        for spec in found:
            compile_effect(etype, {k: v for k, v in spec.items()
                                   if k not in ("type", "conditions")})(card, None, st)
    finally:
        pop_refs()


@pytest.mark.parametrize("slug,victim,spared", [
    ("grind_them_down_blue", 2, 1),
    ("scrub_the_deck_blue", 2, 1),
    ("burly_bones_blue", 1, 2),
    ("burly_bones_red", 1, 2),
])
def test_destroy_the_top_card_of_the_right_deck(slug, victim, spared):
    """"destroy the top card of their deck" / "of your deck"."""
    st = _state()
    _stock(st, 1, "deck", 4)
    _stock(st, 2, "deck", 4)

    _run_type(slug, "DESTROY_MATCHING", _card(slug), st)

    assert len(st.players[victim].deck.cards) == 3, f"{slug} destroyed nothing"
    assert len(st.players[spared].deck.cards) == 4, (
        f"{slug} destroyed the wrong player's card")


def test_deck_top_is_the_top_card_not_the_whole_deck():
    """DECK_TOP must not resolve to the whole deck.

    That would turn "destroy the top card" into a prompt to choose any card in
    it — a different effect, and an information leak, since choosing requires
    seeing the options.
    """
    from engine.card_effects.dsl.effect_types import _object_zone_cards
    st = _state()
    cards = _stock(st, 1, "deck", 5)

    assert _object_zone_cards(st.players[1], "DECK_TOP") == cards[:1]
    assert len(_object_zone_cards(st.players[1], "DECK")) == 5


@pytest.mark.parametrize("slug", ["blessing_of_qi_red", "great_library_of_solana"])
def test_destroy_this_destroys_the_source(slug):
    st = _state()
    source = _card(slug)
    st.players[1].permanents.cards.append(source)

    _run_type(slug, "DESTROY_PERMANENT", source, st)

    assert source not in st.players[1].permanents.cards


def test_lay_to_rest_turns_a_banished_card_face_down_without_moving_it():
    """"turn a card in THEIR banished zone face-down" — a flip, not a banish."""
    st = _state()
    theirs = _stock(st, 2, "banished", 2)
    for c in theirs:
        c.is_public = True
    mine = _stock(st, 1, "banished", 2)
    for c in mine:
        c.is_public = True

    _run_type("lay_to_rest_blue", "FLIP_MATCHING", _card("lay_to_rest_blue"), st)

    assert len(st.players[2].banished.cards) == 2, "the card was moved, not flipped"
    assert sum(1 for c in theirs if not c.is_public) == 1
    assert all(c.is_public for c in mine), "it flipped the caster's own banished card"


def test_robe_of_repentance_only_flips_a_blood_debt_card():
    st = _state()
    debt = _card(FILLER, owner=1)
    debt.keywords = ["BloodDebt"]
    debt.is_public = True
    plain = _card(FILLER, owner=1)
    plain.is_public = True
    st.players[1].banished.cards = [debt, plain]

    _run_type("robe_of_repentance", "FLIP_MATCHING", _card("robe_of_repentance"), st)

    assert debt.is_public is False
    assert plain.is_public is True, "the blood-debt filter was not applied"


def test_bite_destroys_the_dagger_it_chose():
    """"Destroy the dagger" — the one the preceding effect picked."""
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.context import push_refs, pop_refs

    st = _state()
    dagger = _card("beckoning_mistblade", owner=1)
    other = _card("beckoning_mistblade", owner=1)
    st.players[1].weapon1.cards = [dagger]
    st.players[1].weapon2.cards = [other]
    st.player_agents[1] = lambda s, o, context="": o[0]

    source = _card("bite_blue")
    push_refs()
    try:
        compile_effect("DAGGER_DEALS_DAMAGE", {"amount": 1})(source, None, st)
        from engine.context import get_ref
        chosen = get_ref("dagger")
        assert chosen is not None, "the dagger effect recorded no choice"
        compile_effect("DESTROY_REF", {"ref": "dagger"})(source, None, st)
    finally:
        pop_refs()

    remaining = st.players[1].weapon1.cards + st.players[1].weapon2.cards
    assert chosen not in remaining, "the chosen dagger survived"
    assert len(remaining) == 1, "it destroyed more than the one dagger"


def test_bite_does_not_borrow_flick_knives_restriction():
    """DAGGER_DEALS_DAMAGE_AND_DESTROY carries "isn't on the active chain link",
    which Bite does not print. A restriction the card does not have is worse
    than none, because it actually fires."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    for slug in ("bite_blue", "bite_red"):
        # Check the ABILITIES, not the file text: the _comment explains why this
        # type was not used and would match a naive substring search.
        raw = json.loads(_card_json(root, f"{slug}.json").read_text(encoding="utf-8"))
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

        walk(raw.get("abilities", []))
        assert "DAGGER_DEALS_DAMAGE_AND_DESTROY" not in types, (slug, types)


def test_no_ref_effect_is_left_pointing_at_a_ref_nobody_sets():
    """The class this batch closes: a REF effect with a `target` and no earlier
    effect in its ability storing a ref."""
    import json
    from pathlib import Path

    REF_SETTERS = {"LOOK_AT", "REVEAL_TOP_DECK", "SEARCH_DECK", "SELECT_FROM_REF",
                   "CHOOSE", "SEARCH_BANISH_FACE_DOWN", "BANISH", "LOOK",
                   "REVEAL", "DAGGER_DEALS_DAMAGE"}
    REF_EFFECTS = {"DESTROY_REF", "BANISH_REF"}

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    offenders = []
    for path in card_json_files(root):
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") for p in path.parts):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        for ability in raw.get("abilities") or []:
            effects = ability.get("effects") or []
            prior = set()
            for eff in effects:
                if not isinstance(eff, dict):
                    continue
                if eff.get("type") in REF_EFFECTS and "target" in eff:
                    if not (prior & REF_SETTERS):
                        offenders.append(f"{path.stem}:{eff['type']}")
                prior.add(eff.get("type"))
    assert not offenders, (
        f"REF effect with a target and no ref set before it — does nothing: "
        f"{sorted(set(offenders))}")

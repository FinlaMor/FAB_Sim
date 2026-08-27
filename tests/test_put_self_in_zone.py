""""Put it into your SOUL" put it on the bottom of the deck.

PUT_SELF_BOTTOM_DECK hard-coded "deck" and did not read `zone`, so Herald of
Triumph's "when this hits, put it into your soul" sent the card back into the
DECK — to be drawn again — instead of into the soul, where it would fuel every
soul-count effect the Illusionist heroes are built around.

The bottom-deck spelling is kept, because replacement effects like Drone of
Brutality use it and mean it. PUT_SELF_IN_ZONE is the same handler reading the
zone the card names.

A later review pass found the same defect on SIX more cards (four flagged by
the reviewer, six by sweeping every card whose printed text says "into your
soul"). The per-card guard below was added then: the spelling check alone
passes for a card that names no zone at all, which is exactly how these six
survived -- a MISSING parameter and an IGNORED one look identical from the
card's side, and audit_params can only see the second.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.loader import load_all_cards, get_card
from tests.conftest import _make_state
from tests.conftest import card_json_files

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    return st


def _card(slug, owner=1, zone=None):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    if zone is not None:
        c.zone = zone
    return c


def test_herald_goes_to_the_soul_not_the_deck():
    st = _state()
    card = _card("herald_of_triumph_blue", zone="graveyard")
    st.players[1].graveyard.cards = [card]
    deck_before = len(st.players[1].deck.cards)

    for eff in get_card("herald_of_triumph_blue").abilities[0].effects:
        eff.fn(card, None, st)

    assert card in st.players[1].soul.cards, "it did not reach the soul"
    assert len(st.players[1].deck.cards) == deck_before, (
        "it went into the deck instead")


def test_the_bottom_deck_spelling_still_means_the_deck():
    """Replacement effects like Drone of Brutality use it and mean it."""
    st = _state()
    card = _card("wounded_bull_red", zone="hand")
    st.players[1].hand.cards = [card]
    deck_before = len(st.players[1].deck.cards)

    compile_effect("PUT_SELF_BOTTOM_DECK", {})(card, None, st)

    assert len(st.players[1].deck.cards) == deck_before + 1
    assert card not in st.players[1].soul.cards


def test_the_zone_is_read_when_given():
    st = _state()
    card = _card("wounded_bull_red", zone="hand")
    st.players[1].hand.cards = [card]

    compile_effect("PUT_SELF_IN_ZONE", {"zone": "banished"})(card, None, st)

    assert card in st.players[1].banished.cards


def test_no_card_asks_put_self_bottom_deck_for_another_zone():
    """The shape that hid this: a zone named on the one effect that ignored it."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    offenders = []
    for path in card_json_files(root):
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") for p in path.parts):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "PUT_SELF_BOTTOM_DECK":
                    zone = str(node.get("zone") or "deck").lower()
                    if zone != "deck":
                        offenders.append(f"{path.stem}: zone={zone}")
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(raw.get("abilities", []))
    assert not offenders, (
        f"PUT_SELF_BOTTOM_DECK named a zone other than the deck: {offenders}")


#: Cards whose printed text says "into your (hero's) soul".
SOUL_CARDS = ["herald_of_protection_red", "rising_solartide_red",
              "herald_of_ravages_blue", "herald_of_ravages_red",
              "ray_of_hope_yellow", "rising_solartide_blue"]


@pytest.mark.parametrize("slug", SOUL_CARDS)
def test_the_card_really_says_soul(slug):
    """The premise. If the printed text changes, this fails loudly instead of
    endorsing whatever zone the JSON names."""
    import json
    import re
    from pathlib import Path

    idx = json.load(open(Path(__file__).resolve().parent.parent
                         / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    text = idx[slug].get("functionalText") or ""
    assert re.search(r"into (your|their|its owner'?s?) (hero'?s? )?soul",
                     text, re.I), text


def test_no_card_saying_soul_moves_itself_anywhere_else():
    """Derived from the printed text, not a hardcoded list, so it keeps probing
    as cards are added.

    The spelling guard above catches a card that names the WRONG zone on the
    bottom-deck effect. It cannot catch one that names NO zone, which is how
    six cards saying "put it into your soul" quietly bottomed themselves.
    """
    import json
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    idx = json.load(open(Path(__file__).resolve().parent.parent
                         / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    soul = re.compile(r"into (your|their|its owner'?s?) (hero'?s? )?soul", re.I)
    bad = []
    for path in card_json_files(root):
        rel = path.relative_to(root)
        if (path.stem.endswith("_work_queue")
                or path.name in ("review_queue.json", "triage_queue.json")
                or any(p.startswith(".") or p == "needs_review" for p in rel.parts)):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = raw.get("slug")
        if not soul.search(idx.get(slug, {}).get("functionalText") or ""):
            continue

        def walk(node, out):
            if isinstance(node, dict):
                t = node.get("type")
                if t in ("PUT_SELF_BOTTOM_DECK", "PUT_SELF_IN_ZONE"):
                    default = "deck" if t == "PUT_SELF_BOTTOM_DECK" else "soul"
                    out.append(str(node.get("zone") or default).lower())
                for v in node.values():
                    walk(v, out)
            elif isinstance(node, list):
                for v in node:
                    walk(v, out)

        zones = []
        walk(raw.get("abilities"), zones)
        if zones and any(z != "soul" for z in zones):
            bad.append(f"{slug}: {zones}")
    assert bad == [], (
        "cards whose text says 'into your soul' that move themselves "
        f"elsewhere: {bad}")

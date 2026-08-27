"""A prevention that names no damage type absorbs every kind of damage.

`PREVENT_DAMAGE` filters on `damage_type` only when one is present. Three cards
whose printed text names a type omitted it:

  blessing_of_serenity_red     "the next time your hero would be dealt {p}
  blessing_of_serenity_yellow  damage this turn, prevent N" -- PHYSICAL only.
  misfire_dampener             "prevent the next 1 ARCANE damage".

So each shielded against anything, including the damage type the card does not
mention. Strictly stronger than printed, and invisible to every automated check
the project has: the parameter is not ignored, it is absent.

`blessing_of_serenity_blue` -- the same card, one colour along -- authors
`damage_type: "physical"` correctly. A colour variant that differs
STRUCTURALLY from its siblings is the cheapest signal available that one of
them is wrong, and it is what pointed at this.

Distinct from tests/test_prevention_keyword_amounts.py, which is about the
AMOUNT that Ward N / Arcane Barrier N register.
"""
import copy
import json
import pathlib
import re

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.effect_keywords import DamageType, deal_damage
from tests.conftest import _make_state
from tests.conftest import card_json_files

load_all_cards()
DB = CardDB()

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
HERO = "kayo_strong_arm"
OTHER_HERO = "gravy_bones"


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
    st.players[1].hero = _card(HERO, 1)
    st.players[2].hero = _card(OTHER_HERO, 2)
    return st


def _hit(st, dtype, amount=3):
    before = st.players[1].life
    deal_damage(st, amount, dtype, 2, st.players[1].hero, 'effect')
    return before - st.players[1].life


# --- blessing_of_serenity: physical only ------------------------------------

@pytest.mark.parametrize("slug,prevented", [("blessing_of_serenity_red", 3),
                                            ("blessing_of_serenity_yellow", 2),
                                            ("blessing_of_serenity_blue", 1)])
def test_it_prevents_the_physical_damage_it_names(slug, prevented):
    st = _state()
    run_ability(get_card(slug).abilities[0], _card(slug, 1), None, st)

    lost = _hit(st, DamageType.PHYSICAL, amount=5)

    assert lost == 5 - prevented, f"lost {lost}, expected {5 - prevented}"


@pytest.mark.parametrize("slug", ["blessing_of_serenity_red",
                                  "blessing_of_serenity_yellow",
                                  "blessing_of_serenity_blue"])
def test_it_does_not_shield_arcane(slug):
    """"{p} damage" is PHYSICAL. Untyped, these absorbed arcane too."""
    st = _state()
    run_ability(get_card(slug).abilities[0], _card(slug, 1), None, st)

    assert _hit(st, DamageType.ARCANE, amount=5) == 5, (
        f"{slug} shielded arcane damage it never mentions")


# --- misfire_dampener: arcane only ------------------------------------------

def test_misfire_dampener_prevents_arcane():
    st = _state()
    source = _card("misfire_dampener", 1)
    st.players[1].permanents.add(source)

    run_ability(get_card("misfire_dampener").abilities[0], source, None, st)

    assert _hit(st, DamageType.ARCANE, amount=3) < 3


def test_misfire_dampener_does_not_shield_physical():
    st = _state()
    source = _card("misfire_dampener", 1)
    st.players[1].permanents.add(source)

    run_ability(get_card("misfire_dampener").abilities[0], source, None, st)

    assert _hit(st, DamageType.PHYSICAL, amount=3) == 3, (
        "it shielded physical damage; the card says arcane")


# --- the guard --------------------------------------------------------------

def test_no_typed_prevention_omits_its_damage_type():
    """Derived from the printed text, so it keeps probing as cards are added.

    A card whose clause names {p} or arcane and whose PREVENT_DAMAGE carries no
    damage_type shields everything — stronger than printed, and undetectable by
    audit_params because the parameter is absent rather than unread.
    """
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    bad = []
    for path in card_json_files(JSON_ROOT):
        rel = path.relative_to(JSON_ROOT)
        if (path.stem.endswith("_work_queue")
                or path.name in ("review_queue.json", "triage_queue.json")
                or any(p.startswith(".") or p == "needs_review" for p in rel.parts)):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = raw.get("slug")
        text = idx.get(slug, {}).get("functionalText") or ""
        low = text.lower()
        if "prevent" not in low:
            continue
        if not ("{p}" in text or "arcane damage" in low):
            continue

        found = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "PREVENT_DAMAGE":
                    found.append(node.get("damage_type"))
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(raw.get("abilities"))
        if found and any(d is None for d in found):
            bad.append(slug)
    assert bad == [], (
        f"cards whose text names a damage type but whose PREVENT_DAMAGE does "
        f"not: {bad}")

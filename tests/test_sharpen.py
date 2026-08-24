"""Six cards say "sharpen" and none of them sharpened anything.

Found by pointing Ox Alpha at the implemented corpus as a REVIEWER rather than
an author: it flagged edict_of_steel_red and hala_bladesaint_of_the_vow, and a
sweep for cards whose printed text says "sharpen" against cards using the
SHARPEN effect type turned up six.

The mechanic was never missing -- effect_types.SHARPEN puts a "power" counter
on a sword and records the turn event, and _recalculate_attack_power already
adds card.counters['power'] to an attacking card. Six cards simply reached for
something else:

  edict_of_steel_red        STEAL_AURA_TOKEN -- stole a token from the OPPONENT
                            and sharpened nothing.
  hala / hala_bladesaint_   GAIN keyword "SHARPEN". Sharpen is an EFFECT, not a
  of_the_vow                keyword, so this appended a string to
                            combat.keywords and put no counter anywhere. Both
                            also charged an invented PITCH and never tapped,
                            against a printed cost of {r}{r}{r} plus {t}.
  sharpening_sparks_red     SET_FLAG "SHARPENED" -- a flag nothing reads.
  beckon_steel_blue         PUT_COUNTER of a kind literally named "SHARPEN",
                            which is not the kind SHARPEN uses ("power"), so
                            its own 3-counter gate could never see it. It also
                            sharpened on resolution when the text puts the
                            sharpen inside the on-hit.
  swordmasters_path_blue    "the next time you would sharpen, sharpen an
                            additional time" was left unimplemented.

MY OWN SWEEP WAS WRONG FIRST. Searching the JSON for the string "SHARPEN"
matched `GAIN keyword: "SHARPEN"` -- the defect itself -- and so reported
hala_bladesaint_of_the_vow as already using the mechanic. Keying on the `type`
field instead found six rather than four. A substring search over JSON answers
a different question from a search over compiled types.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

# A real Sword weapon, so the SHARPEN subtype filter has something to find.
SWORD = "dawnblade"
PLAIN = "brutal_assault_red"


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


def _sword(st, pid=1):
    w = _card(SWORD, pid)
    assert "Sword" in (w.subtypes or []), (
        f"{SWORD} is not a Sword; the fixture proves nothing")
    st.players[pid].weapon1.add(w)
    return w


def _counters(card):
    return (getattr(card, "counters", None) or {}).get("power", 0)


# --- the mechanic -----------------------------------------------------------

def test_sharpen_puts_a_power_counter_on_the_sword():
    st = _state()
    sword = _sword(st)

    compile_effect("SHARPEN", {"subtype": "Sword", "amount": 1})(
        _card(PLAIN), None, st)

    assert _counters(sword) == 1


def test_the_extra_marker_makes_the_next_sharpen_sharpen_twice():
    st = _state()
    sword = _sword(st)

    compile_effect("SHARPEN_EXTRA_NEXT_TIME", {"amount": 1})(_card(PLAIN), None, st)
    compile_effect("SHARPEN", {"subtype": "Sword", "amount": 1})(
        _card(PLAIN), None, st)

    assert _counters(sword) == 2


def test_the_extra_marker_is_consumed_once():
    """"The NEXT time you would sharpen" — not every sharpen this turn."""
    st = _state()
    sword = _sword(st)

    compile_effect("SHARPEN_EXTRA_NEXT_TIME", {"amount": 1})(_card(PLAIN), None, st)
    for _ in range(2):
        compile_effect("SHARPEN", {"subtype": "Sword", "amount": 1})(
            _card(PLAIN), None, st)

    assert _counters(sword) == 3, "1+1 extra, then 1 = 3"


def test_the_extra_marker_expires_with_the_turn():
    """It rides current_turn_effects so the existing end-phase cleanup clears
    it — nothing new to remember to reset."""
    st = _state()
    sword = _sword(st)
    compile_effect("SHARPEN_EXTRA_NEXT_TIME", {"amount": 1})(_card(PLAIN), None, st)

    E._end_phase_iter(st)
    compile_effect("SHARPEN", {"subtype": "Sword", "amount": 1})(
        _card(PLAIN), None, st)

    assert _counters(sword) == 1, "the bonus survived the turn"


# --- the cards --------------------------------------------------------------

@pytest.mark.parametrize("slug", ["edict_of_steel_red", "hala",
                                  "hala_bladesaint_of_the_vow"])
def test_the_card_sharpens_a_sword(slug):
    st = _state()
    sword = _sword(st)

    run_ability(get_card(slug).abilities[0], _card(slug, 1), None, st)

    assert _counters(sword) == 1, f"{slug} put no power counter on the sword"


def test_edict_does_not_steal_from_the_opponent():
    """It was STEAL_AURA_TOKEN: an invented theft in place of the sharpen."""
    from engine.effect_keywords import create_token

    st = _state()
    _sword(st)
    create_token(st, target_player_id=2, token_slug="runechant", number=1,
                 source_player_id=2)
    theirs = [c.slug for c in st.players[2].permanents.cards]

    run_ability(get_card("edict_of_steel_red").abilities[0],
                _card("edict_of_steel_red", 1), None, st)

    assert [c.slug for c in st.players[2].permanents.cards] == theirs, (
        "it stole a token from the opponent")


def test_edict_creates_the_flurry_only_after_a_counter_lands():
    st = _state()
    _sword(st)

    run_ability(get_card("edict_of_steel_red").abilities[0],
                _card("edict_of_steel_red", 1), None, st)

    assert any(c.slug == "flurry" for c in st.players[1].permanents.cards)


def test_edict_creates_no_flurry_with_no_sword_to_sharpen():
    """"If IT has 1 or more +1{p} counters" is about the sword just sharpened.
    With no sword, nothing is sharpened and the gate must not pay out."""
    st = _state()

    run_ability(get_card("edict_of_steel_red").abilities[0],
                _card("edict_of_steel_red", 1), None, st)

    assert not any(c.slug == "flurry" for c in st.players[1].permanents.cards)


@pytest.mark.parametrize("slug", ["hala", "hala_bladesaint_of_the_vow"])
def test_hala_taps_and_does_not_pitch(slug):
    """Printed cost is {r}{r}{r}, {t}. It charged an invented pitch of a hand
    card and never tapped."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(next(root.rglob(f"{slug}.json")).read_text(encoding="utf-8"))
    ab = raw["abilities"][0]
    costs = [c.get("type") for c in ab.get("cost", [])]
    assert "TAP_SELF" in costs, f"{slug} never taps: {costs}"
    assert "PITCH" not in costs, f"{slug} charges an invented pitch: {costs}"
    assert ab.get("activation_cost") == 3


# --- sharpening_sparks_red / beckon_steel_blue ------------------------------

def _weapon_attack(st):
    sword = _sword(st)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=sword, keywords=[])
    st.combat.from_weapon = True
    return sword


def test_sharpening_sparks_pumps_the_attack():
    st = _state()
    _weapon_attack(st)
    before = st.combat.attack_power

    run_ability(get_card("sharpening_sparks_red").abilities[0],
                _card("sharpening_sparks_red", 1), None, st)

    assert st.combat.attack_power == before + 2


def test_sharpening_sparks_does_not_sharpen_before_the_hit():
    """"WHEN THIS HITS, sharpen this sword" — not on resolution."""
    st = _state()
    sword = _weapon_attack(st)

    run_ability(get_card("sharpening_sparks_red").abilities[0],
                _card("sharpening_sparks_red", 1), None, st)

    assert _counters(sword) == 0


def test_beckon_steel_does_not_sharpen_before_the_hit():
    """It sharpened on resolution; the text puts the sharpen inside the
    on-hit."""
    st = _state()
    sword = _weapon_attack(st)

    run_ability(get_card("beckon_steel_blue").abilities[0],
                _card("beckon_steel_blue", 1), None, st)

    assert _counters(sword) == 0


def test_beckon_steel_uses_the_counter_kind_sharpen_writes():
    """Its gate asked for counters of a kind named "SHARPEN"; SHARPEN writes
    "power", so the gate could never see its own counters."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    blob = json.dumps(json.loads(
        next(root.rglob("beckon_steel_blue.json")).read_text(encoding="utf-8")))
    assert '"SHARPEN"' not in blob.replace('"type": "SHARPEN"', ""), (
        "a counter kind named SHARPEN is still referenced")


# --- the guard --------------------------------------------------------------

def test_every_card_saying_sharpen_uses_the_sharpen_effect():
    """Derived from the card text, so it keeps probing as cards are added.

    Keyed on the `type` field: a substring search for "SHARPEN" also matches
    `GAIN keyword: "SHARPEN"`, which is the defect, and so reports a broken
    card as a healthy one.
    """
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    json_root = root / "engine" / "card_effects" / "json"
    idx = json.load(open(root / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]

    def types_of(node, out):
        if isinstance(node, dict):
            t = node.get("type")
            if isinstance(t, str):
                out.add(t)
            for v in node.values():
                types_of(v, out)
        elif isinstance(node, list):
            for v in node:
                types_of(v, out)

    bad = []
    for path in json_root.rglob("*.json"):
        rel = path.relative_to(json_root)
        if (path.stem.endswith("_work_queue") or path.name == "review_queue.json"
                or any(p.startswith(".") or p == "needs_review" for p in rel.parts)):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = raw.get("slug")
        if "sharpen" not in (idx.get(slug, {}).get("functionalText") or "").lower():
            continue
        used = set()
        types_of(raw.get("abilities"), used)
        # A card may PERFORM a sharpen or MODIFY one (swordmasters_path_blue
        # only says "the next time you would sharpen ... sharpen an additional
        # time"), so the whole family counts.
        family = {"SHARPEN", "SHARPEN_EXTRA_NEXT_TIME", "REPLACE_NEXT_SHARPEN"}
        if not (used & family):
            bad.append(slug)
    assert bad == [], (
        f"cards whose text says sharpen but which use nothing from the "
        f"sharpen family: {bad}")

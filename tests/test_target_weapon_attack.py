""""Target WEAPON attack" pumped any attack at all.

Found by Ox Alpha while implementing biting_blade_blue: it noticed the existing
`biting_blade_red` had no weapon filter on the half that says "Target weapon
attack gains +3{p}", and said so in its comment. Sweeping the corpus for cards
whose printed text says "target weapon attack" turned up four:

  biting_blade_red             no target filter -- pumped any attack
  in_the_swing_blue            no target filter
  glint_the_quicksilver_blue   no target filter (its clause GRANTS GO AGAIN
                               rather than pumping, which is why a
                               MODIFY_ATTACK-shaped sweep missed it)
  ironsong_response_blue       did nothing at all for TWO independent reasons.
                               Its Reprise clause was DEFENDS_WITH_OTHER_HAND_
                               CARD, which asks whether THIS CARD is defending
                               beside another hand card -- but this is an
                               ATTACK REACTION played by the attacker, so it is
                               never defending. And it HAD a target filter that
                               matched nothing:
                               ATTACK_SUBTYPE_IN {"subtypes": ["weapon"]}.
                               A weapon's subtypes are ['TwoHanded', 'Hammer'];
                               "Weapon" is a TYPE. The filter was false for
                               every attack in the game, so the card did
                               nothing at all.

Types-vs-subtypes is the third occurrence of that trap in this audit, so
ATTACK_SUBTYPE_IN now matches types and subtypes alike (and the combat's
from_weapon flag, which is the reliable signal when the attack card is not the
weapon object itself).

Two sweeps were needed to find all four, which is the lesson: a sweep keyed on
one effect shape (MODIFY_ATTACK) misses the card that expresses the same clause
another way, and a whole-file string search for "ATTACK_IS_WEAPON" passes on a
card whose filter sits in a DIFFERENT ability (biting_blade_red's Reprise half).
"""
import copy
import json
import pathlib

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
ACTION_ATTACK = "brutal_assault_red"
WEAPON = "anothos"


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


def _attacking(st, slug, from_weapon):
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=_card(slug, 1), keywords=[])
    st.combat.from_weapon = from_weapon
    return st.combat


# --- the condition family ---------------------------------------------------

def test_weapon_is_a_type_not_a_subtype():
    """The premise of the defect. If this ever changes, the fix below is moot
    and this test says so instead of silently passing."""
    anothos = DB.get(WEAPON)
    assert "Weapon" in (anothos.types or [])
    assert "weapon" not in [s.lower() for s in (anothos.subtypes or [])]


def test_attack_subtype_in_matches_a_type():
    st = _state()
    _attacking(st, WEAPON, from_weapon=True)
    fn = compile_condition("ATTACK_SUBTYPE_IN", {"subtypes": ["weapon"]})

    assert fn(_card(ACTION_ATTACK), None, st) is True


def test_attack_subtype_in_still_matches_a_real_subtype():
    st = _state()
    _attacking(st, WEAPON, from_weapon=True)
    fn = compile_condition("ATTACK_SUBTYPE_IN", {"subtypes": ["hammer"]})

    assert fn(_card(ACTION_ATTACK), None, st) is True


def test_attack_subtype_in_rejects_a_non_weapon():
    st = _state()
    _attacking(st, ACTION_ATTACK, from_weapon=False)
    fn = compile_condition("ATTACK_SUBTYPE_IN", {"subtypes": ["weapon"]})

    assert fn(_card(ACTION_ATTACK), None, st) is False


# --- the four cards ---------------------------------------------------------

WEAPON_CARDS = ["biting_blade_red", "in_the_swing_blue",
                "glint_the_quicksilver_blue", "ironsong_response_blue"]


def _prime(st, slug):
    """Satisfy each card's own non-target gate so the target filter is what
    decides the outcome."""
    if slug == "in_the_swing_blue":
        from engine.effect_keywords import _record_turn_event
        for _ in range(2):
            _record_turn_event(st, 1, "attack", "weapon")
    if slug == "ironsong_response_blue":
        # REPRISE reads combat.defender_used_hand_card (CR 8.4.3).
        st.combat.defender_used_hand_card = True


@pytest.mark.parametrize("slug", WEAPON_CARDS)
def test_it_does_nothing_to_a_non_weapon_attack(slug):
    st = _state()
    _attacking(st, ACTION_ATTACK, from_weapon=False)
    _prime(st, slug)
    before = st.combat.attack_power
    kws = list(st.combat.keywords)

    run_ability(get_card(slug).abilities[0], _card(slug, 1), None, st)

    assert st.combat.attack_power == before, (
        f"{slug} pumped an ACTION attack: {before} -> {st.combat.attack_power}")
    assert list(st.combat.keywords) == kws, (
        f"{slug} granted a keyword to an ACTION attack")


@pytest.mark.parametrize("slug", WEAPON_CARDS)
def test_it_does_something_to_a_weapon_attack(slug):
    """The control: without this, "did nothing to a non-weapon" is satisfied by
    a card that does nothing to anything — which is exactly what
    ironsong_response_blue was doing."""
    st = _state()
    _attacking(st, WEAPON, from_weapon=True)
    _prime(st, slug)
    before = st.combat.attack_power
    kws = list(st.combat.keywords)

    run_ability(get_card(slug).abilities[0], _card(slug, 1), None, st)

    changed = (st.combat.attack_power != before
               or list(st.combat.keywords) != kws)
    assert changed, f"{slug} did nothing to a WEAPON attack either"


# --- the guard --------------------------------------------------------------

def test_no_card_saying_target_weapon_attack_lacks_a_weapon_filter():
    """Derived, not hardcoded: a guard that names its own examples stops
    probing once those examples are fixed."""
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    bad = []
    for path in JSON_ROOT.rglob("*.json"):
        if (path.stem.endswith("_work_queue")
                or any(p.startswith(".") or p == "needs_review"
                       for p in path.relative_to(JSON_ROOT).parts)):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = raw.get("slug")
        text = (idx.get(slug, {}).get("functionalText") or "").lower()
        if "target weapon attack" not in text:
            continue
        for ab in raw.get("abilities", []):
            if not ab.get("effects"):
                continue
            tgt = json.dumps(ab.get("target", {}))
            # Either spelling is fine; what matters is that SOME weapon
            # restriction sits on the ability that carries the clause.
            if "ATTACK_IS_WEAPON" in tgt or "weapon" in tgt.lower():
                break
        else:
            bad.append(slug)
    assert bad == [], (
        "cards whose text says \"target weapon attack\" with no weapon "
        f"restriction on any ability: {bad}")

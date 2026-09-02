"""Three cards whose narrowing was written down and never read.

`scripts/audit_params.py` finds JSON keys no compiler branch consumes. It cannot
say what the omission DOES, and that is the interesting part: in all three cases
below the dropped key was the half of the clause that says WHEN, so the card
kept its payoff and lost its condition. A card that does its thing more often
than printed looks like a working card in every test that only checks the thing
happens.

    teklo_plasma_pistol         COUNTER_GTE amount 0 -- "at least zero steam
                                counters", true always, for "if there are NO
                                steam counters"
    vigorous_engagement_yellow  DURING_TURN {"condition": "DEFENDED_BY_ATTACK_
                                ACTION_CARD"} -- DURING_TURN reads phase and
                                player; the string was dropped and the token
                                was created against an undefended attack
    ray_of_hope_yellow          HEALTH_LT_OPP {"opponent_subtypes": ["shadow"]}
                                -- the handler read no parameters at all, so
                                "an opposing SHADOW hero" became "the opponent"

The teklo one is not a new class. condition_types already carries a comment
about COUNTER_GTE 0 -- it was found on Teklo Core, destroying itself every turn,
and COUNTER_EQ was added for it. This card had the identical node and was
missed, so the sweep below runs over the whole corpus rather than over the one
card, and pins that there are no others.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card, CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_combat, _make_state, owned_card, tokens_controlled

load_all_cards()
DB = CardDB()
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"


def _state():
    st = _make_state()
    st.card_db = DB
    return st


# --- teklo_plasma_pistol -----------------------------------------------------

def _teklo(st, steam):
    card = owned_card(1, "teklo_plasma_pistol", types=["Weapon"])
    card.counters = {"steam": steam}
    st.players[1].weapon1.add(card)
    return card


def _recharge(st, card):
    ab = [a for a in get_card("teklo_plasma_pistol").abilities
          if any(e.effect_type == "PUT_COUNTER" for e in a.effects)][0]
    return all(cond.fn is None or cond.fn(card, None, st) for cond in ab.conditions)


def test_teklo_recharges_only_when_it_has_no_steam():
    st = _state()
    assert _recharge(st, _teklo(st, 0)), "cannot recharge an empty pistol"

    st2 = _state()
    assert not _recharge(st2, _teklo(st2, 1)), (
        "the pistol recharged while it already had steam; 'if there are no "
        "steam counters' was an at-least-zero test")


def test_no_card_still_asks_for_at_least_zero_counters():
    """The always-true node, swept corpus-wide. A threshold of 0 on a GTE is
    never what a card means -- every phrasing that reaches for it is 'no
    counters', which is COUNTER_EQ 0."""
    def walk(node, out):
        if isinstance(node, dict):
            if node.get("type") == "COUNTER_GTE" and \
                    node.get("min", node.get("amount", 1)) in (0, "0"):
                out.append(node)
            for v in node.values():
                walk(v, out)
        elif isinstance(node, list):
            for v in node:
                walk(v, out)
        return out

    offenders = []
    for path in JSON_ROOT.rglob("*.json"):
        rel = path.relative_to(JSON_ROOT)
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") or p == "needs_review" for p in rel.parts):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict) and walk(raw.get("abilities"), []):
            offenders.append(raw.get("slug"))
    assert not offenders, (
        "COUNTER_GTE with a threshold of 0 is always true: " + ", ".join(offenders))


# --- vigorous_engagement_yellow ----------------------------------------------

def _defender(pid, types, subtypes):
    c = Card(slug="d", name="Defender", raw_types=types)
    c.types, c.subtypes = types, subtypes
    c.owner = c.controller = pid
    return c


def _vigorous(st):
    card = owned_card(1, "vigorous_engagement_yellow")
    ab = get_card("vigorous_engagement_yellow").abilities[0]
    run_ability(ab, card, None, st)


def test_vigor_token_needs_an_attack_action_defender():
    st = _state()
    st.combat = _make_combat(attacker_id=1)
    st.combat.defending_cards = [_defender(2, ["Action"], ["Attack"])]
    _vigorous(st)
    assert tokens_controlled(st, 1, "vigor"), (
        "no Vigor token against an attack action defender")


def test_no_vigor_token_when_the_attack_is_undefended():
    st = _state()
    st.combat = _make_combat(attacker_id=1)
    st.combat.defending_cards = []
    _vigorous(st)
    assert not tokens_controlled(st, 1, "vigor"), (
        "the Vigor token was created against an UNDEFENDED attack; the "
        "'if it's defended by' clause is being dropped")


def test_no_vigor_token_for_a_defender_that_is_not_an_attack_action():
    """Equipment and non-attack actions both defend. Neither is an attack
    action card, and matching on the Attack subtype alone would let an Attack
    Reaction through."""
    st = _state()
    st.combat = _make_combat(attacker_id=1)
    st.combat.defending_cards = [_defender(2, ["Equipment"], []),
                                 _defender(2, ["Attack Reaction"], [])]
    _vigorous(st)
    assert not tokens_controlled(st, 1, "vigor")


# --- ray_of_hope_yellow ------------------------------------------------------

def _ray_condition(st):
    ab = [a for a in get_card("ray_of_hope_yellow").abilities
          if a.ability_type.upper() == "TRIGGERED"][0]
    card = owned_card(1, "ray_of_hope_yellow")
    return all(c.fn is None or c.fn(card, None, st) for c in ab.conditions)


def _opp_hero(st, classes):
    hero = Card(slug="opp_hero", name="Opp Hero", raw_types=["Hero"])
    hero.classes = classes
    hero.owner = hero.controller = 2
    st.players[2].hero = hero


def test_ray_of_hope_needs_an_opposing_shadow_hero():
    st = _state()
    st.players[1].life, st.players[2].life = 5, 20
    _opp_hero(st, ["Shadow"])
    assert _ray_condition(st), "a Shadow opponent on more life did not qualify"

    st2 = _state()
    st2.players[1].life, st2.players[2].life = 5, 20
    _opp_hero(st2, ["Guardian"])
    assert not _ray_condition(st2), (
        "Ray of Hope qualified against a NON-Shadow hero; the opponent_subtypes "
        "narrowing is being dropped")


def test_ray_of_hope_still_needs_to_be_on_less_life():
    st = _state()
    st.players[1].life, st.players[2].life = 20, 5
    _opp_hero(st, ["Shadow"])
    assert not _ray_condition(st), (
        "the life comparison was lost while adding the class filter")

"""Six more out of the gated-go-again backlog: Combo, Lightning Bond, and one
that reads its own power.

    rising_knee_thrust_blue     Combo - "if Leg Tap was the last attack"
    whelming_gustwave_red       Combo - "if Surging Strike was the last attack"
    vengeance_never_rests_blue  Combo - "if Edge of Autumn was the last attack"
    rushing_river_blue          Combo - "if Torrent of Tempo was the last attack"
    arc_bending_red             Lightning Bond - "if a Lightning card was pitched"
    chain_of_brutality_red      "if this has 6 or more {p}"

All six had the RIGHT CONDITION already authored and only the wrong ability
shape, so the printed GoAgain applied unconditionally and the gate did nothing.
That is the whole backlog's signature: the card compiles, the condition is real
and correct, and it is never consulted.

WHY THESE ARE SAFE TO READ CONTINUOUSLY (CR 6.2.3d), which is the judgement
this conversion actually requires:

  Combo         which card was the previous link is settled before this attack
                is announced and cannot change while it is on the chain.
  Lightning     what paid for a card is stamped at the moment it is played.
  Bond
  Chain of      NOT merely safe -- continuous is the CORRECT reading here. The
  Brutality     condition is about the card's CURRENT power, a pump can raise it
                after declaration, and go again is paid at the Resolution Step
                (CR 8.3.5b). The ON_ATTACK trigger froze the answer too early.

ONLY THE GO AGAIN MOVED. "+1{p} when this attacks" and "draw a card if it hits"
really are timed events and keep their triggers, so each of these files is now
a mix of shapes on purpose. The tests below check the other clauses survived,
because the conversion rewrote whole files and the last one of these to lose a
clause (soup_up_red's Galvanize) would have gone unnoticed.
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
from engine.card_effects.dsl.loader import (_kw_key, conditional_keywords,
                                            load_all_cards)
from engine.state import ChainLink
from tests.conftest import (_card_json, _make_state, attack_with, owned_card,
                            recalculate_attack)

load_all_cards()
DB = CardDB()
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

#: slug -> the card its Combo names
COMBOS = {
    "rising_knee_thrust_blue": "leg_tap_red",
    "whelming_gustwave_red": "surging_strike_red",
    "vengeance_never_rests_blue": "edge_of_autumn_red",
    "rushing_river_blue": "torrent_of_tempo_red",
}
CONVERTED = list(COMBOS) + ["arc_bending_red", "chain_of_brutality_red"]


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _go_again(st):
    return any(_kw_key(k) == "goagain" for k in st.combat.keywords)


def _attacking(st, slug, power=None):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = 1
    return attack_with(st, c, power=power)


def _previous_link(st, slug):
    """The previous attack on the chain. A link is appended AFTER its damage
    resolves, so during a new attack chain_links[-1] IS the previous attack."""
    st.chain_links.append(ChainLink(
        chainlink_id=1, attacker_id=1, attack_slug=slug, attack_power=3,
        net_damage=3, keywords=[], from_weapon=False, hit=True))


def _raw(slug):
    return json.loads(_card_json(JSON_ROOT, slug + ".json")
                      .read_text(encoding="utf-8"))


# --- the printed keyword must be stripped, or the gate is decoration ---------

@pytest.mark.parametrize("slug", CONVERTED)
def test_the_printed_keyword_is_conditional_now(slug):
    assert "goagain" in conditional_keywords(slug), (
        slug + " still has an unconditional printed go again")


@pytest.mark.parametrize("slug", CONVERTED)
def test_the_grant_uses_the_only_shape_that_strips(slug):
    granting = []
    for ab in _raw(slug)["abilities"]:
        for eff in ab.get("effects", []):
            name = eff.get("keyword") if eff.get("type") == "GAIN" else eff.get("type")
            if _kw_key(str(name or "")) == "goagain":
                granting.append(ab)
                break
    assert granting, slug + " no longer grants go again at all"
    for ab in granting:
        assert ab["ability_type"] == "WHILE_STATIC", ab["ability_type"]
        types = [c.get("type") for c in ab.get("conditions", [])]
        assert "SOURCE_IS_ATTACK" in types, types


# --- Combo ------------------------------------------------------------------

@pytest.mark.parametrize("slug,combo_piece", sorted(COMBOS.items()))
def test_combo_grants_go_again_after_the_named_card(slug, combo_piece):
    st = _state()
    _previous_link(st, combo_piece)
    _attacking(st, slug)

    recalculate_attack(st)

    assert _go_again(st), (
        combo_piece + " was the last attack, so the Combo is on")


@pytest.mark.parametrize("slug", sorted(COMBOS))
def test_combo_withholds_go_again_after_a_different_card(slug):
    st = _state()
    _previous_link(st, "wounding_blow_red")
    _attacking(st, slug)

    recalculate_attack(st)

    assert not _go_again(st), (
        "go again after the WRONG combo piece -- the gate is decoration again")


@pytest.mark.parametrize("slug", sorted(COMBOS))
def test_combo_withholds_go_again_as_the_first_attack(slug):
    """No previous link at all, which is how these cards are played most of the
    time."""
    st = _state()
    _attacking(st, slug)

    recalculate_attack(st)

    assert not _go_again(st), (
        "go again as the FIRST attack of the chain -- there is no combo piece")


@pytest.mark.parametrize("slug,combo_piece", sorted(COMBOS.items()))
def test_the_combo_name_is_matched_across_printings(slug, combo_piece):
    """LAST_CHAIN_ATTACK strips a colour suffix so "Leg Tap" matches every
    printing. If it stopped doing that, only the red one would combo and the
    positive tests above would still pass."""
    st = _state()
    _previous_link(st, combo_piece.replace("_red", "_blue"))
    _attacking(st, slug)

    recalculate_attack(st)

    assert _go_again(st), (
        "the blue printing of " + combo_piece + " did not satisfy the Combo")


# --- the other clauses survived the rewrite ---------------------------------

@pytest.mark.parametrize("slug,amount", [("rising_knee_thrust_blue", 2),
                                         ("whelming_gustwave_red", 1),
                                         ("rushing_river_blue", 1)])
def test_the_combo_power_bonus_still_applies(slug, amount):
    st = _state()
    _previous_link(st, COMBOS[slug])
    card = _attacking(st, slug)
    base = card.base_power or 0

    from engine.card_effects.dsl.interpreter import run_ability
    from engine.card_effects.dsl.loader import get_card
    for ab in get_card(slug).abilities:
        if ab.ability_type == "TRIGGERED" and ab.trigger == "ON_ATTACK":
            run_ability(ab, card, None, st)

    assert recalculate_attack(st) == base + amount, (
        "the Combo power bonus was lost when the go again moved out")


def test_rushing_river_keeps_its_injected_on_hit_trigger():
    abilities = _raw("rushing_river_blue")["abilities"]
    injects = [e for a in abilities for e in a.get("effects", [])
               if e.get("type") == "INJECT_TRIGGER"]
    assert injects, "the draw-and-put-back clause was lost in the conversion"
    inner = injects[0]["trigger"]["effects"]
    assert [e["type"] for e in inner] == ["DRAW", "PUT_HAND_CARD_TOP"]
    assert all(e["amount"] == {"type": "COUNT_CHAIN_LINKS", "hit": True}
               for e in inner), (
        "X is the number of attacks that have HIT this chain; a literal or an "
        "invented string here resolves to 0 and draws nothing")


def test_whelming_gustwave_keeps_its_draw_on_hit():
    hits = [a for a in _raw("whelming_gustwave_red")["abilities"]
            if a.get("trigger") == "ON_HIT"]
    assert hits, "the 'if this hits, draw a card' clause was lost"
    assert "LAST_CHAIN_ATTACK" in [c["type"] for c in hits[0]["conditions"]], (
        "the draw is no longer gated on the Combo, so it now fires on every hit")


def test_vengeance_never_rests_still_declares_its_missing_clause():
    """Its banish-and-replay half is unimplementable in the DSL. The conversion
    must not have quietly dropped the note saying so -- that note is the only
    record that the card is incomplete."""
    raw = _raw("vengeance_never_rests_blue")
    assert "NEEDS_NEW_DSL" in raw["_comment"]
    assert not any(e.get("type") == "BANISH"
                   for a in raw["abilities"] for e in a.get("effects", [])), (
        "a BANISH came back; the previous attempt banished the HERO")


# --- Lightning Bond ---------------------------------------------------------

def _pitched(card, **traits):
    pitched = owned_card(1, "pitched", types=["Action"])
    for key, value in traits.items():
        setattr(pitched, key, value)
    card.pitched_for_this = [pitched]
    return card


def test_arc_bending_grants_go_again_for_a_lightning_pitch():
    st = _state()
    _pitched(_attacking(st, "arc_bending_red"), classes=["Lightning"])

    recalculate_attack(st)

    assert _go_again(st), "a Lightning card paid for this, so the bond is on"


def test_arc_bending_withholds_go_again_for_another_pitch():
    st = _state()
    _pitched(_attacking(st, "arc_bending_red"), classes=["Ice"])

    recalculate_attack(st)

    assert not _go_again(st), (
        "go again off an ICE pitch -- the Lightning Bond is decoration again")


def test_arc_bending_withholds_go_again_with_nothing_pitched():
    st = _state()
    _attacking(st, "arc_bending_red")

    recalculate_attack(st)

    assert not _go_again(st), "go again with nothing pitched to play it"


def test_arc_bending_keeps_its_damage_clause():
    """The main text is a damage bump for Lightning/Elemental attacks, still
    modelled as a power modifier and still not right -- but losing it entirely
    would be worse, and the file's note is the record of the gap."""
    raw = _raw("arc_bending_red")
    assert any(e.get("type") == "MODIFY_ATTACKS_THIS_TURN"
               for a in raw["abilities"] for e in a.get("effects", []))
    assert "damage-replacement primitive" in raw["_comment"], (
        "the note recording that this clause is an approximation was lost")


# --- "if this has 6 or more {p}" -------------------------------------------

def _pump(card, amount):
    """Raise the attack's power the way the engine does, through a CR 6.3
    staged effect on the card.

    Writing combat.attack_power directly does NOT work and the reason matters:
    _recalculate_attack_power assigns the staged power BEFORE it dispatches the
    statics, so an injected value is overwritten and the condition reads the
    printed 2. That ordering is the whole point of this conversion -- the
    condition now sees the FINAL power rather than a guess made at declaration.
    """
    from engine.card import CardEffect
    card.effects = list(getattr(card, "effects", None) or [])
    card.effects.append(CardEffect(prop="power", stage=7, substage=5,
                                   fn=lambda v, _a=amount: (v or 0) + _a))
    return card


def test_chain_of_brutality_grants_go_again_at_six_power():
    st = _state()
    card = copy.deepcopy(DB.get("chain_of_brutality_red"))
    card.owner = card.controller = 1
    assert (card.base_power or 0) < 6, (
        "premise: its printed power is below the threshold, so the clause is "
        "only ever reached by pumping it")
    attack_with(st, _pump(card, 6 - (card.base_power or 0)))

    assert recalculate_attack(st) == 6, "premise: the pump landed"
    assert _go_again(st), "6 power, so go again is due"


def test_chain_of_brutality_withholds_go_again_below_six():
    st = _state()
    card = copy.deepcopy(DB.get("chain_of_brutality_red"))
    card.owner = card.controller = 1
    attack_with(st, _pump(card, 5 - (card.base_power or 0)))

    assert recalculate_attack(st) == 5, "premise: one short of the threshold"
    assert not _go_again(st), (
        "go again at 5 power -- the 6-power gate is decoration again")


def test_chain_of_brutality_counts_a_pump_applied_after_declaration():
    """The reason WHILE_STATIC is the CORRECT reading and not merely the
    convenient one. Power raised after the attack was announced has to count,
    because go again is paid at the Resolution Step (CR 8.3.5b). The old
    ON_ATTACK trigger answered once, at declaration, and could not change its
    mind."""
    st = _state()
    card = copy.deepcopy(DB.get("chain_of_brutality_red"))
    card.owner = card.controller = 1
    attack_with(st, card)
    recalculate_attack(st)
    assert not _go_again(st), "premise: it starts below the threshold"

    _pump(card, 6 - (card.base_power or 0))
    E._register_card_continuous_effects(st, card)

    assert recalculate_attack(st) == 6
    assert _go_again(st), (
        "pumped to 6 after declaration and still no go again -- the condition "
        "is frozen at declaration again")


def test_chain_of_brutality_keeps_its_on_hit_clause():
    hits = [a for a in _raw("chain_of_brutality_red")["abilities"]
            if a.get("trigger") == "ON_HIT"]
    assert hits, "the 'next attack action has 6 base power' clause was lost"
    types = [c["type"] for c in hits[0]["conditions"]]
    assert "ATTACK_TARGET_IS_HERO" in types, (
        "the hero gate went missing again; the DSL ON_HIT listener fires for "
        "any damaged target, so this would trigger off allies and permanents")
    assert "SELF_ATTACK_POWER_GTE" in types


# --- premise ----------------------------------------------------------------

def test_the_printed_text_still_says_what_these_assert():
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]

    def text(slug):
        return (idx[slug].get("functionalText") or "").lower()

    assert "leg tap was the last attack" in text("rising_knee_thrust_blue")
    assert "surging strike was the last attack" in text("whelming_gustwave_red")
    assert "edge of autumn was the last attack" in text("vengeance_never_rests_blue")
    assert "torrent of tempo was the last attack" in text("rushing_river_blue")
    assert "lightning card was pitched to play this" in text("arc_bending_red")
    assert "6 or more {p}" in text("chain_of_brutality_red")
    for slug in CONVERTED:
        printed = [str(k).lower() for k in (idx[slug].get("keywords") or [])]
        assert "goagain" in printed, (
            slug + " no longer PRINTS go again, so there is nothing to strip "
            "and this whole file is measuring nothing")

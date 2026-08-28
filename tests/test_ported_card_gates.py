"""Behavioural cover for cards the pipeline authored and the gate adopted.

95 cards were ported into this repo on the strength of compilation, six defect
sweeps, a review verdict and the corpus suite. That is more than the drafts
had and less than the hand-written corpus is held to: Civic Duty's wrong-player
token was caught this week by a behavioural test and by NO audit, because a
token was created, nothing errored and nothing was empty -- it simply belonged
to the wrong hero.

So these assert what the audits structurally cannot: that a gate actually
gates, in BOTH directions. A condition that is present in the JSON and always
true is indistinguishable from a correct one until something plays the card.

Two cards, chosen because each gates on something an audit cannot evaluate:

    fight_from_behind_red       "if you have less {h} than each other hero"
    challenge_the_alpha_yellow  "when this attacks a BRUTE hero"

The negative case is the one that matters. An ungated effect passes the
positive test every time.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import Card, CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _card_json, _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _src(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _cheered(state, pid):
    return "crowd_cheered" in state.players[pid].current_turn_effects


# --- "if you have less {h} than each other hero" -----------------------------

def test_fight_from_behind_cheers_when_behind_on_life():
    st = _state()
    st.players[1].life = 5
    st.players[2].life = 20
    src = _src("fight_from_behind_red")

    run_ability(get_card("fight_from_behind_red").abilities[0], src, None, st)

    assert _cheered(st, 1), "behind on life, so the crowd should cheer"


def test_fight_from_behind_is_silent_when_ahead():
    """The half an audit cannot see: the condition is PRESENT either way."""
    st = _state()
    st.players[1].life = 20
    st.players[2].life = 5
    src = _src("fight_from_behind_red")

    run_ability(get_card("fight_from_behind_red").abilities[0], src, None, st)

    assert not _cheered(st, 1), (
        "cheered while AHEAD on life -- the health gate is not gating")


def test_fight_from_behind_also_triggers_on_defence():
    """"When this attacks OR DEFENDS" is two abilities in the JSON, and a card
    that implemented only the first would pass every attack-side test."""
    raw = json.loads(_card_json(ROOT / "engine" / "card_effects" / "json",
                                "fight_from_behind_red.json")
                     .read_text(encoding="utf-8"))
    triggers = [a.get("trigger") for a in raw["abilities"]]
    assert "ON_ATTACK" in triggers and "ON_DEFEND" in triggers, triggers

    st = _state()
    st.players[1].life = 5
    st.players[2].life = 20
    src = _src("fight_from_behind_red")
    defend = next(a for a in get_card("fight_from_behind_red").abilities
                  if (a.trigger or "").upper() == "ON_DEFEND")

    run_ability(defend, src, None, st)

    assert _cheered(st, 1), "the defend half never fires"


# --- "when this attacks a BRUTE hero" ---------------------------------------

def _attack_state(opp_classes):
    st = _state()
    st.players[2].hero.classes = list(opp_classes)
    attack = Card(slug="challenge_the_alpha_yellow",
                  name="Challenge the Alpha", types=["Action"],
                  subtypes=["Attack"])
    attack.owner = attack.controller = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=attack, keywords=[], from_weapon=False)
    return st, attack


def test_challenge_the_alpha_pumps_against_a_brute():
    st, attack = _attack_state(["Brute"])
    src = _src("challenge_the_alpha_yellow")

    before = st.combat.attack_power
    run_ability(get_card("challenge_the_alpha_yellow").abilities[0],
                src, None, st)

    assert st.combat.attack_power == before + 2, (
        f"expected +2 against a Brute hero, got "
        f"{st.combat.attack_power - before}")


def test_challenge_the_alpha_does_nothing_against_another_class():
    """An ungated MODIFY_ATTACK passes the positive test and fails only here."""
    st, attack = _attack_state(["Wizard"])
    src = _src("challenge_the_alpha_yellow")

    before = st.combat.attack_power
    run_ability(get_card("challenge_the_alpha_yellow").abilities[0],
                src, None, st)

    assert st.combat.attack_power == before, (
        "pumped against a Wizard hero -- the Brute gate is not gating")


# --- the premise -------------------------------------------------------------

def test_the_printed_text_still_says_what_these_assert():
    """If a card's text is corrected upstream these should fail loudly rather
    than keep asserting behaviour the card no longer describes."""
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    assert "less {h} than each other hero" in (
        idx["fight_from_behind_red"].get("functionalText") or "")
    assert "brute hero" in (
        idx["challenge_the_alpha_yellow"].get("functionalText") or "").lower()

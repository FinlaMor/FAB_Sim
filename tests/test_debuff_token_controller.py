"""Debuff tokens landed on the player who inflicted them.

`CREATE_TOKEN` defaults its controller to SELF. Four cards say "under **their**
control" or "under **target hero's** control" about a DEBUFF and never named a
player, so the token was created under the attacker's own control:

  sedation_shot_blue    Inertia bottoms your hand AND arsenal at end of turn.
                        The card punished the player who played it.
  death_touch_blue      two defects at once. "a Frailty, Inertia, OR Bloodrot
  death_touch_yellow    Pox token" is a CHOICE OF ONE and the JSON created ALL
                        THREE -- three debuffs, all on the attacker.
  frail_swingline_blue  Frailty gives -1{p} to its controller's attacks.

`quickening_sand_blue` reads identically ("under target hero's control") and is
DELIBERATELY LEFT ALONE: Quicken is a BENEFIT ("destroy this and the attack
gains go again"), so targeting yourself is the sensible play and the default is
correct. Fixing by pattern rather than by reading each token's text would have
broken it — the phrasing does not determine the answer, the token does.

Separately, the `confidence` token had no JSON file anywhere, so
create_token's require_card raised MissingCardImplementation and ABORTED THE
GAME whenever Pleiades' crowd-cheer trigger resolved.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

PLAIN = "brutal_assault_red"
HERO = "kayo_strong_arm"
OTHER_HERO = "gravy_bones"
DEBUFFS = {"frailty", "inertia", "bloodrot_pox"}


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state(agent=None):
    st = _make_state()
    st.card_db = DB
    pick = agent or (lambda s, o, context="": o[0])
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    st.players[1].hero = _card(HERO, 1)
    st.players[2].hero = _card(OTHER_HERO, 2)
    return st


def _hit(st, slug):
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=_card(slug, 1), keywords=[])
    st.combat.hit = True
    return st.combat


def _tokens(st, pid):
    return {c.slug for c in st.players[pid].permanents.cards}


# --- the debuffs land on the hero that was hit ------------------------------

def test_sedation_shot_inertia_goes_to_the_hero_it_hit():
    st = _state()
    _hit(st, "sedation_shot_blue")

    run_ability(get_card("sedation_shot_blue").abilities[1],
                _card("sedation_shot_blue", 1), None, st)

    assert "inertia" in _tokens(st, 2), f"opponent has {_tokens(st, 2)}"
    assert "inertia" not in _tokens(st, 1), (
        "the attacker gave itself Inertia, which bottoms its own hand and "
        "arsenal at end of turn")


@pytest.mark.parametrize("slug", ["death_touch_blue", "death_touch_yellow"])
def test_death_touch_debuffs_the_hero_it_hit(slug):
    st = _state()
    _hit(st, slug)

    run_ability(get_card(slug).abilities[0], _card(slug, 1), None, st)

    assert _tokens(st, 2) & DEBUFFS, f"opponent has {_tokens(st, 2)}"
    assert not (_tokens(st, 1) & DEBUFFS), (
        f"the attacker debuffed itself: {_tokens(st, 1)}")


@pytest.mark.parametrize("slug", ["death_touch_blue", "death_touch_yellow"])
def test_death_touch_creates_exactly_one_token(slug):
    """"a Frailty, Inertia, OR Bloodrot Pox token" — the JSON created all
    three."""
    st = _state()
    _hit(st, slug)

    run_ability(get_card(slug).abilities[0], _card(slug, 1), None, st)

    made = [c for c in st.players[2].permanents.cards if c.slug in DEBUFFS]
    assert len(made) == 1, f"created {[c.slug for c in made]}"


@pytest.mark.parametrize("want", ["Inertia", "Bloodrot Pox"])
def test_death_touch_honours_the_choice(want):
    st = _state(agent=lambda s, o, context="": want if want in o else o[0])
    _hit(st, "death_touch_blue")

    run_ability(get_card("death_touch_blue").abilities[0],
                _card("death_touch_blue", 1), None, st)

    expected = want.lower().replace(" ", "_")
    assert expected in _tokens(st, 2), (
        f"chose {want} but got {_tokens(st, 2)}")


def test_frail_swingline_frailty_goes_to_the_opponent():
    st = _state()

    run_ability(get_card("frail_swingline_blue").abilities[0],
                _card("frail_swingline_blue", 1), None, st)

    assert "frailty" in _tokens(st, 2)
    assert "frailty" not in _tokens(st, 1), (
        "it gave itself -1{p} on its own attacks")


# --- the benefit is deliberately NOT flipped --------------------------------

def test_quickening_sand_still_gives_itself_the_quicken():
    """Same printed phrasing, opposite correct answer: Quicken is a BENEFIT.
    A pattern-based fix would have flipped this one too."""
    st = _state()

    run_ability(get_card("quickening_sand_blue").abilities[0],
                _card("quickening_sand_blue", 1), None, st)

    assert "quicken" in _tokens(st, 1), (
        "the controller lost its own Quicken to the opponent")
    assert "quicken" not in _tokens(st, 2)


def test_quicken_really_is_a_benefit():
    """The premise of the test above. If Quicken's text ever changes, this
    says so rather than silently endorsing the wrong controller."""
    import json
    from pathlib import Path
    idx = json.load(open(Path(__file__).resolve().parent.parent
                         / "card_data" / "slug_index.json", encoding="utf-8"))["by_slug"]
    text = (idx["quicken"].get("functionalText") or "").lower()
    assert "gains **go again**" in text or "go again" in text


# --- the token that aborted the game ----------------------------------------

def test_the_confidence_token_has_an_implementation():
    """create_token calls require_card, which raised MissingCardImplementation
    and aborted the game when Pleiades' trigger resolved."""
    assert get_card("confidence") is not None


def test_creating_a_confidence_token_does_not_raise():
    from engine.effect_keywords import create_token

    st = _state()
    create_token(st, target_player_id=1, token_slug="confidence", number=1,
                 source_player_id=1)

    assert "confidence" in _tokens(st, 1)

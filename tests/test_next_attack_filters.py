"""'Your next <filtered> attack this turn gets +N' — cards that invented a flag.

Eight cards each rolled a private flag (CUT_DEEP_ACTIVE, NEXT_ARROW_ATTACK,
TARGET_MARKED, ...) for a shape the DSL already expressed: MODIFY_NEXT_ATTACK
with a `filter`, which savor_bloodshed_red already used correctly. Nothing new
was needed here — only using the existing effect.

The flag versions were not merely dead. Authored as a flag-gated STATIC they
would, if the flag were ever set, buff EVERY attack for the rest of the turn
instead of only the next one — so the negative "second attack is not buffed"
assertions below are the point of the exercise, not padding.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import Card
from engine.card_effects.dsl import dispatch, load_all_cards
from engine.state import CombatState, GameState, Player, Step

load_all_cards()


def _hero(pid: int) -> Card:
    c = Card(slug="test_hero", name="H", types=["Hero"], base_life=40, base_intellect=4)
    c.owner = c.controller = pid
    return c


def _state() -> GameState:
    return GameState(
        players={1: Player(1, _hero(1)), 2: Player(2, _hero(2))},
        active_player=1,
        player_agents={1: lambda *a, **k: None, 2: lambda *a, **k: None},
        step=Step.ACTION, turn_number=1, combat=None, done=False, winner=None,
    )


def _play(state: GameState, slug: str):
    c = Card(slug=slug, name=slug, types=["Action"])
    c.owner = c.controller = 1
    dispatch(state, "ON_PLAY", slug, card=c)


def _attack(state: GameState, slug="atk", classes=(), subtypes=("Attack",), power=3):
    a = Card(slug=slug, name=slug, types=["Action"], subtypes=list(subtypes))
    a.owner = a.controller = 1
    a.classes = list(classes)
    a.power = power
    a.zone = "combat_chain"
    a.effects = []
    state.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                               attack_card=a, keywords=[], from_weapon=False)
    E._apply_turn_attack_effects(state, a)
    return a


def _power(a: Card) -> int:
    val = a.power
    for eff in a.effects:
        if getattr(eff, "prop", None) == "power":
            val = eff.fn(val)
    return val


# slug -> (bonus, matching attack kwargs, non-matching attack kwargs)
CASES = {
    "cut_deep_yellow":          (3, {"subtypes": ["Dagger", "Attack"]}, {"subtypes": ["Attack"]}),
    "call_in_the_big_guns_red": (3, {"subtypes": ["Arrow", "Attack"]},  {"subtypes": ["Attack"]}),
    "spellbane_trap_red":       (3, {"subtypes": ["Arrow", "Attack"]},  {"subtypes": ["Attack"]}),
    "swordmasters_path_blue":   (1, {"subtypes": ["Sword", "Attack"]},  {"subtypes": ["Attack"]}),
    "bonebreaker_bellow_red":   (3, {"classes": ["Brute"]},             {"classes": ["Ninja"]}),
    "angelic_descent_yellow":   (2, {"subtypes": ["Angel", "Attack"]},  {"subtypes": ["Attack"]}),
}


@pytest.mark.parametrize("slug", sorted(CASES))
def test_matching_attack_is_buffed(slug):
    bonus, match, _ = CASES[slug]
    st = _state()
    _play(st, slug)
    a = _attack(st, **match)
    assert _power(a) == a.power + bonus


@pytest.mark.parametrize("slug", sorted(CASES))
def test_non_matching_attack_is_not_buffed(slug):
    _, _, miss = CASES[slug]
    st = _state()
    _play(st, slug)
    a = _attack(st, **miss)
    assert _power(a) == a.power


@pytest.mark.parametrize("slug", sorted(CASES))
def test_only_the_next_matching_attack_is_buffed(slug):
    # The regression the flag versions would have caused: a flag-gated STATIC
    # buffs every attack for the rest of the turn. "Next" means exactly one.
    bonus, match, _ = CASES[slug]
    st = _state()
    _play(st, slug)
    first = _attack(st, **match)
    second = _attack(st, **match)
    assert _power(first) == first.power + bonus
    assert _power(second) == second.power


def test_public_bounty_buffs_only_an_attack_on_a_marked_hero():
    st = _state()
    _play(st, "public_bounty_yellow")
    # The mark lives in class_counters — Player.marked is a SEPARATE, older
    # boolean that effect_mark does not write and OPPONENT_IS_MARKED does not
    # read, so asserting on it would pass or fail for the wrong reason.
    assert st.players[2].class_counters.get("marked", 0) > 0
    a = _attack(st)
    assert _power(a) == a.power + 2


def test_public_bounty_does_not_buff_when_the_hero_is_not_marked():
    st = _state()
    _play(st, "public_bounty_yellow")
    st.players[2].class_counters["marked"] = 0   # mark removed before the attack
    a = _attack(st)
    assert _power(a) == a.power


# --- thump_blue: condition was always-true, not merely dead ------------------

def test_thump_has_no_dominate_at_base_power():
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _state()
    a = _attack(st, slug="thump_blue", power=4)
    st.combat.base_attack_power = 4
    cond = compile_condition("ATTACK_POWER_GT_BASE", {})
    assert cond(a, None, st) is False


def test_thump_condition_true_once_pumped_above_base():
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _state()
    a = _attack(st, slug="thump_blue", power=4)
    st.combat.base_attack_power = 4
    st.combat.attack_power = 6
    cond = compile_condition("ATTACK_POWER_GT_BASE", {})
    assert cond(a, None, st) is True


def test_old_thump_condition_was_always_true():
    # SELF_ATTACK_POWER_GTE coerces a non-numeric amount to 0, so the old
    # authoring read ">= 0" and granted dominate unconditionally. Pinned so the
    # replacement is not mistaken for an equivalent rewrite.
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _state()
    a = _attack(st, slug="thump_blue", power=4)
    st.combat.base_attack_power = 4
    old = compile_condition("SELF_ATTACK_POWER_GTE", {"amount": "BASE_ATTACK_POWER"})
    assert old(a, None, st) is True          # the bug
    new = compile_condition("ATTACK_POWER_GT_BASE", {})
    assert new(a, None, st) is False         # the fix


# --- migration guard --------------------------------------------------------

@pytest.mark.parametrize("slug", sorted(CASES) + ["public_bounty_yellow", "thump_blue"])
def test_no_invented_flag_remains(slug):
    import json
    root = ROOT / "engine" / "card_effects" / "json"
    path = [p for p in root.rglob(f"{slug}.json") if ".quarantine" not in p.parts][0]
    abilities = json.dumps(json.loads(path.read_text(encoding="utf-8"))["abilities"])
    assert "FLAG_SET" not in abilities, f"{slug} still reads an invented flag"

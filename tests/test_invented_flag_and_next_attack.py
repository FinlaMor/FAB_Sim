"""An invented flag, a duplicated printed keyword, and a ref nobody stores.

quickening_sand_blue carried all three at once:

  * Its PLAY half GAINed Go Again, which the card PRINTS. A duplicate of
    something that already works.
  * Its defend trigger was gated on FLAG_SET "GO_AGAIN" — an invented flag
    nothing sets — where the card says "when this defends an ATTACK WITH go
    again". That is a property of the ATTACK, read off combat.keywords by
    ATTACK_HAS_KEYWORD, not a flag on the player.
  * Its effect was SELECT_FROM_REF on a ref named "hero_or_ally" that nothing
    stores, where the card says "{t} target hero or ally".

billowing_mist_blue's "your next attack this turn gets +1{p}" was a plain
STATIC. MODIFY_NEXT_ATTACK queues a one-shot and only needs to run when the card
is played; nothing dispatches a STATIC, so the queue entry was never made.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import load_all_cards, get_card
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    return c


def _defend_against(st, keywords):
    atk = _card("wounded_bull_red", owner=1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=atk, keywords=list(keywords))
    st.combat.base_attack_power = 3


def test_quickening_sand_taps_when_the_attack_has_go_again():
    st = _state()
    _defend_against(st, ["Go Again"])
    hero = st.players[2].hero
    hero.tapped = False

    run_ability(get_card("quickening_sand_blue").abilities[1],
                _card("quickening_sand_blue", owner=1), None, st)

    assert hero.tapped is True, "defending a go-again attack tapped nothing"


def test_quickening_sand_does_nothing_against_a_plain_attack():
    """The half an invented always-false flag would have got right by accident,
    and an always-TRUE condition would get wrong."""
    st = _state()
    _defend_against(st, [])
    hero = st.players[2].hero
    hero.tapped = False

    run_ability(get_card("quickening_sand_blue").abilities[1],
                _card("quickening_sand_blue", owner=1), None, st)

    assert hero.tapped is False, "it tapped against an attack without go again"


def test_the_keyword_match_is_spelling_tolerant():
    """combat.keywords stores "Go Again"; JSON writes "go again"."""
    st = _state()
    _defend_against(st, ["go_again"])
    hero = st.players[2].hero
    hero.tapped = False

    run_ability(get_card("quickening_sand_blue").abilities[1],
                _card("quickening_sand_blue", owner=1), None, st)

    assert hero.tapped is True, "snake_case go_again did not match"


def test_quickening_sand_no_longer_regrants_a_printed_keyword():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(next(root.rglob("quickening_sand_blue.json"))
                     .read_text(encoding="utf-8"))
    for ability in raw.get("abilities") or []:
        for eff in ability.get("effects") or []:
            kw = str(eff.get("keyword") or "").lower().replace("_", " ")
            assert kw != "go again", (
                "it grants a keyword the card already prints")


def test_no_card_reads_a_flag_named_after_a_keyword():
    """"GO_AGAIN" as a FLAG is always invented: keywords live on the card and in
    combat.keywords, and nothing ever writes a flag by that name."""
    import json
    from pathlib import Path

    KEYWORD_FLAGS = {"go_again", "goagain", "dominate", "overpower", "intimidate"}
    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    offenders = []
    for path in root.rglob("*.json"):
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") for p in path.parts):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") in ("FLAG_SET", "SET_FLAG"):
                    flag = str(node.get("flag") or "").lower()
                    if flag in KEYWORD_FLAGS:
                        offenders.append(f"{path.stem}: {node.get('flag')}")
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(raw.get("abilities", []))
    assert not offenders, f"flag named after a keyword, so nothing sets it: {offenders}"


def test_billowing_mist_queues_a_next_attack_bonus():
    st = _state()
    card = _card("billowing_mist_blue")

    for eff in get_card("billowing_mist_blue").abilities[0].effects:
        eff.fn(card, None, st)

    queued = getattr(st.players[1], "dsl_queued_attack_mods", [])
    assert queued, "playing it queued no next-attack bonus"


def test_billowing_mist_bonus_applies_to_the_next_attack_only():
    st = _state()
    card = _card("billowing_mist_blue")
    for eff in get_card("billowing_mist_blue").abilities[0].effects:
        eff.fn(card, None, st)

    def _power():
        atk = _card("wounded_bull_red")
        base = atk.base_power or 0
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=base,
                                attack_card=atk, keywords=[])
        st.combat.base_attack_power = base
        E._apply_turn_attack_effects(st, atk)
        E._register_card_continuous_effects(st, atk)
        E._recalculate_attack_power(st)
        return st.combat.attack_power - base

    assert _power() == 1, "the next attack was not buffed"
    assert _power() == 0, "every attack was buffed, not the next one"

"""Tests for the JSON DSL interpreter (Step 2 of effect redesign)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from engine.card import Card
from engine.card_effects.dsl import dispatch, load_all_cards, get_card
from engine.card_effects.dsl.loader import compile_card
from engine.card_effects.dsl.schema import CardDef, AbilityDef, EffectDef
from engine.state import CombatState, GameState, Player, Step


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hero(pid: int = 1) -> Card:
    c = Card(slug="test_hero", name="Test Hero", types=["Hero"],
             base_life=40, base_intellect=4)
    c.owner = pid
    c.controller = pid
    return c


def _make_player(pid: int = 1) -> Player:
    return Player(pid, _make_hero(pid))


def _mock_agent(state, options, **kwargs):
    return options[0] if options else None


def _make_state() -> GameState:
    p1 = _make_player(1)
    p2 = _make_player(2)
    return GameState(
        players={1: p1, 2: p2},
        active_player=1,
        player_agents={1: _mock_agent, 2: _mock_agent},
        step=Step.ACTION,
        turn_number=1,
        combat=None,
        done=False,
        winner=None,
    )


def _make_card(slug: str = "test", owner: int = 1) -> Card:
    c = Card(slug=slug, name=slug, types=["Action"])
    c.owner = owner
    c.controller = owner
    c.zone = "hand"
    return c


def _make_deck_card(slug: str, owner: int = 1, power: int = 1) -> Card:
    c = Card(slug=slug, name=slug, types=["Action"])
    c.owner = owner
    c.controller = owner
    c.power = power
    return c


def _make_combat(attacker_id: int = 1, power: int = 5) -> CombatState:
    ac = _make_card("atk", attacker_id)
    return CombatState(
        attacker_id=attacker_id, link_id=1,
        attack_power=power, attack_card=ac, keywords=[],
    )


# ---------------------------------------------------------------------------
# compile_card tests
# ---------------------------------------------------------------------------

def test_compile_card_basic():
    raw = {
        "slug": "test-card",
        "abilities": [
            {
                "ability_type": "TRIGGERED",
                "trigger": "ON_HIT",
                "effects": [{"type": "DRAW", "amount": 1}],
            }
        ],
    }
    card_def = compile_card(raw)
    assert card_def.slug == "test-card"
    assert len(card_def.abilities) == 1
    ab = card_def.abilities[0]
    assert ab.ability_type == "TRIGGERED"
    assert ab.trigger == "ON_HIT"
    assert len(ab.effects) == 1
    assert ab.effects[0].effect_type == "DRAW"
    assert ab.effects[0].fn is not None


def test_compile_card_with_conditions():
    raw = {
        "slug": "test-reprise",
        "abilities": [
            {
                "ability_type": "TRIGGERED",
                "trigger": "ON_HIT",
                "conditions": [{"type": "REPRISE"}],
                "effects": [{"type": "DRAW", "amount": 1}],
            }
        ],
    }
    card_def = compile_card(raw)
    ab = card_def.abilities[0]
    assert len(ab.conditions) == 1
    assert ab.conditions[0].condition_type == "REPRISE"
    assert ab.conditions[0].fn is not None


def test_compile_card_no_abilities():
    raw = {"slug": "vanilla-card", "abilities": []}
    card_def = compile_card(raw)
    assert card_def.slug == "vanilla-card"
    assert card_def.abilities == []


def test_compile_all_effect_types_no_crash():
    """Every named effect type should compile without raising."""
    effect_types = [
        {"type": "LOSE_LIFE", "amount": 1},
        {"type": "DEAL_DAMAGE", "amount": 1},
        {"type": "DEAL_PHYSICAL", "amount": 1},
        {"type": "DEAL_ARCANE", "amount": 1},
        {"type": "DRAW", "amount": 1},
        {"type": "DISCARD", "amount": 1},
        {"type": "OPT", "amount": 1},
        {"type": "RELOAD"},
        {"type": "BANISH", "amount": 1},
        {"type": "CHARGE"},
        {"type": "DOMINATE"},
        {"type": "INTIMIDATE"},
        {"type": "AMP", "amount": 1},
        {"type": "MARK"},
        {"type": "CREATE_TOKEN", "token": "vigor"},
        {"type": "PUT_COUNTER", "counter_type": "energy"},
        {"type": "REMOVE_COUNTER", "counter_type": "energy"},
        {"type": "SET_FLAG", "flag": "test_flag"},
        {"type": "MODIFY_ATTACK", "mod": "add", "amount": 2},
        {"type": "MODIFY_NEXT_ATTACK", "mod": "add", "amount": 1},
        {"type": "GAIN", "asset": "LIFE_POINTS", "amount": 1},
        {"type": "GAIN", "asset": "RESOURCE_POINTS", "amount": 1},
        {"type": "GAIN", "asset": "ACTION_POINTS", "amount": 1},
        {"type": "GAIN", "keyword": "go_again"},
        {"type": "ROLL", "faces": 6},
        {"type": "APPLY_CONTINUOUS", "target": "PLAYER_ATTACKS", "modifications": [], "span": "THIS_TURN"},
        {"type": "DISCARD_RANDOM", "amount": 1},
        {"type": "REMOVE_COUNTERS", "counter_type": "energy", "amount": 1},
    ]
    raw = {
        "slug": "all-effects-test",
        "abilities": [
            {
                "ability_type": "PLAY",
                "effects": effect_types,
            }
        ],
    }
    card_def = compile_card(raw)
    for eff in card_def.abilities[0].effects:
        assert callable(eff.fn), f"Effect {eff.effect_type} did not produce a callable"


def test_compile_unknown_effect_type_raises():
    """Unknown effect types are authoring errors and must fail at compile time."""
    import pytest
    from engine.card_effects.dsl.effect_types import compile_effect
    with pytest.raises(ValueError, match="Unknown DSL effect type"):
        compile_effect("UNKNOWN_XYZ", {})


def test_compile_all_condition_types_no_crash():
    """Every named condition type should compile without raising."""
    conditions = [
        {"type": "IN_COMBAT"},
        {"type": "ATTACK_IS_WEAPON"},
        {"type": "ATTACK_IS_NOT_WEAPON"},
        {"type": "WEAPON_SUBTYPE_IN", "values": ["HAMMER"]},
        {"type": "ATTACK_COST_GTE", "amount": 2},
        {"type": "DEFENDER_USED_HAND_CARD"},
        {"type": "REPRISE"},
        {"type": "CRUSH"},
        {"type": "COMBO", "combo_names": []},
        {"type": "SURGE", "amount": 1},
        {"type": "RUPTURE"},
        {"type": "HEALTH_GT_OPP"},
        {"type": "IS_ACTIVE_PLAYER"},
        {"type": "HAS_KEYWORD", "keyword": "go_again"},
        {"type": "CARD_IN_ZONE", "zone": "hand"},
        {"type": "COUNTER_GTE", "counter_type": "energy", "min": 1},
        {"type": "FLAG_SET", "flag": "test"},
        {"type": "OR", "any": [{"type": "ATTACK_IS_WEAPON"}, {"type": "ATTACK_IS_NOT_WEAPON"}]},
        {"type": "AND", "all": [{"type": "IN_COMBAT"}]},
        {"type": "NOT", "inner_type": "IN_COMBAT"},
        {"type": "none"},
    ]
    from engine.card_effects.dsl.condition_types import compile_condition
    for cond_raw in conditions:
        ctype = cond_raw.get("type", "none")
        params = {k: v for k, v in cond_raw.items() if k != "type"}
        result = compile_condition(ctype, params)
        assert result is None or callable(result), f"Condition {ctype} didn't produce callable/None"


def test_compile_unknown_condition_type_raises():
    """Unknown condition types are authoring errors and must fail at compile time."""
    import pytest
    from engine.card_effects.dsl.condition_types import compile_condition
    with pytest.raises(ValueError, match="Unknown DSL condition type"):
        compile_condition("UNKNOWN_COND_XYZ", {})


# ---------------------------------------------------------------------------
# load_all_cards (from temp dir)
# ---------------------------------------------------------------------------

def test_load_all_cards_from_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        set_dir = Path(tmpdir) / "wtr"
        set_dir.mkdir()
        card_json = {
            "slug": "test-strike-red",
            "abilities": [
                {
                    "ability_type": "TRIGGERED",
                    "trigger": "ON_HIT",
                    "effects": [{"type": "DRAW", "amount": 1}],
                }
            ],
        }
        (set_dir / "test-strike-red.json").write_text(json.dumps(card_json))
        try:
            count = load_all_cards(Path(tmpdir))
            assert count == 1
            assert get_card("test-strike-red") is not None
        finally:
            # Restore the real card registry for later tests.
            load_all_cards()


def test_load_skips_missing_slug():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "bad.json").write_text(json.dumps({"abilities": []}))
        count = load_all_cards(Path(tmpdir))
        assert count == 0


def test_load_skips_malformed_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "bad.json").write_text("{not valid json")
        count = load_all_cards(Path(tmpdir))
        assert count == 0


def test_load_nonexistent_dir():
    count = load_all_cards(Path("/nonexistent/path/xyz"))
    assert count == 0


# ---------------------------------------------------------------------------
# dispatch — MODIFY_ATTACK on hit
# ---------------------------------------------------------------------------

def test_dispatch_modify_attack_on_triggered_hit():
    """TRIGGERED ON_HIT ability fires and applies MODIFY_ATTACK."""
    state = _make_state()
    state.combat = _make_combat(power=5)
    card = _make_card("test-hit-card", 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "test-hit-card.json").write_text(json.dumps({
            "slug": "test-hit-card",
            "abilities": [
                {
                    "ability_type": "TRIGGERED",
                    "trigger": "ON_HIT",
                    "effects": [{"type": "MODIFY_ATTACK", "mod": "add", "amount": 3}],
                }
            ],
        }))
        load_all_cards(Path(tmpdir))

    dispatch(state, "ON_HIT", "test-hit-card", card=card)
    assert state.combat.attack_power == 8  # 5 + 3


# ---------------------------------------------------------------------------
# dispatch — DRAW on play
# ---------------------------------------------------------------------------

def test_dispatch_draw_on_play():
    state = _make_state()
    for i in range(3):
        state.players[1].deck.add(_make_deck_card(f"d{i}"))
    card = _make_card("draw-card", 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "draw-card.json").write_text(json.dumps({
            "slug": "draw-card",
            "abilities": [
                {"ability_type": "PLAY",
                 "effects": [{"type": "DRAW", "amount": 2}]},
            ],
        }))
        load_all_cards(Path(tmpdir))

    dispatch(state, "ON_PLAY", "draw-card", card=card)
    assert len(state.players[1].hand.cards) == 2


# ---------------------------------------------------------------------------
# dispatch — MODIFY_ATTACK power bonus (ATTACK_REACTION)
# ---------------------------------------------------------------------------

def test_dispatch_power_bonus():
    state = _make_state()
    state.combat = _make_combat(power=5)
    card = _make_card("power-card", 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "power-card.json").write_text(json.dumps({
            "slug": "power-card",
            "abilities": [
                {"ability_type": "ATTACK_REACTION",
                 "effects": [{"type": "MODIFY_ATTACK", "mod": "add", "amount": 3}]},
            ],
        }))
        load_all_cards(Path(tmpdir))

    dispatch(state, "ON_PLAY", "power-card", card=card)
    assert state.combat.attack_power == 8


# ---------------------------------------------------------------------------
# dispatch — ability-level condition blocks all effects
# ---------------------------------------------------------------------------

def test_dispatch_condition_blocks_effect():
    """IS_ACTIVE_PLAYER condition should not fire for non-active player."""
    state = _make_state()
    state.active_player = 1
    state.combat = _make_combat()
    card = _make_card("cond-card", 2)  # player 2's card, active is player 1

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "cond-card.json").write_text(json.dumps({
            "slug": "cond-card",
            "abilities": [
                {
                    "ability_type": "TRIGGERED",
                    "trigger": "ON_HIT",
                    "conditions": [{"type": "IS_ACTIVE_PLAYER"}],
                    "effects": [{"type": "MODIFY_ATTACK", "mod": "add", "amount": 2}],
                }
            ],
        }))
        load_all_cards(Path(tmpdir))

    dispatch(state, "ON_HIT", "cond-card", card=card)
    assert state.combat.attack_power == 5  # unchanged


def test_dispatch_condition_passes():
    """IS_ACTIVE_PLAYER condition passes for the active player."""
    state = _make_state()
    state.active_player = 1
    for i in range(2):
        state.players[1].deck.add(_make_deck_card(f"d{i}"))
    card = _make_card("cond-card", 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "cond-card.json").write_text(json.dumps({
            "slug": "cond-card",
            "abilities": [
                {
                    "ability_type": "TRIGGERED",
                    "trigger": "ON_HIT",
                    "conditions": [{"type": "IS_ACTIVE_PLAYER"}],
                    "effects": [{"type": "DRAW", "amount": 1}],
                }
            ],
        }))
        load_all_cards(Path(tmpdir))

    dispatch(state, "ON_HIT", "cond-card", card=card)
    assert len(state.players[1].hand.cards) == 1


# ---------------------------------------------------------------------------
# dispatch — INJECT_TRIGGER
# ---------------------------------------------------------------------------

def test_dispatch_inject_trigger():
    """INJECT_TRIGGER appends a TriggerDef to combat.injected_triggers."""
    state = _make_state()
    state.combat = _make_combat(power=5)
    card = _make_card("test-inject-card", 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "test-inject-card.json").write_text(json.dumps({
            "slug": "test-inject-card",
            "abilities": [
                {
                    "ability_type": "ATTACK_REACTION",
                    "effects": [
                        {"type": "MODIFY_ATTACK", "mod": "add", "amount": 4},
                        {
                            "type": "INJECT_TRIGGER",
                            "trigger": "ON_HIT",
                            "consumed": True,
                            "effects": [
                                {"type": "DISCARD", "player": "DEFENDING", "amount": 1}
                            ],
                        },
                    ],
                }
            ],
        }))
        load_all_cards(Path(tmpdir))

    dispatch(state, "ON_PLAY", "test-inject-card", card=card)
    assert state.combat.attack_power == 9  # 5 + 4
    assert len(_attached_on_hit_triggers(state)) == 1


# ---------------------------------------------------------------------------
# dispatch — OR condition
# ---------------------------------------------------------------------------

def test_or_condition_passes():
    """OR condition passes when any sub-condition is true."""
    state = _make_state()
    state.combat = _make_combat(power=5)
    card = _make_card("or-card", 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "or-card.json").write_text(json.dumps({
            "slug": "or-card",
            "abilities": [
                {
                    "ability_type": "TRIGGERED",
                    "trigger": "ON_HIT",
                    "conditions": [
                        {
                            "type": "OR",
                            "any": [
                                {"type": "ATTACK_IS_WEAPON"},
                                {"type": "ATTACK_IS_NOT_WEAPON"},
                            ],
                        }
                    ],
                    "effects": [{"type": "MODIFY_ATTACK", "mod": "add", "amount": 1}],
                }
            ],
        }))
        load_all_cards(Path(tmpdir))

    dispatch(state, "ON_HIT", "or-card", card=card)
    assert state.combat.attack_power == 6  # 5 + 1


# ---------------------------------------------------------------------------
# dispatch — unknown slug → no crash
# ---------------------------------------------------------------------------

def test_dispatch_unknown_slug_no_crash():
    state = _make_state()
    dispatch(state, "ON_HIT", "nonexistent-card-xyz")  # must not raise


# ---------------------------------------------------------------------------
# dispatch — wrong event type → ability does not fire
# ---------------------------------------------------------------------------

def test_dispatch_wrong_event_no_effect():
    state = _make_state()
    state.combat = _make_combat(power=5)
    card = _make_card("hit-card", 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "hit-card.json").write_text(json.dumps({
            "slug": "hit-card",
            "abilities": [
                {"ability_type": "TRIGGERED", "trigger": "ON_HIT",
                 "effects": [{"type": "MODIFY_ATTACK", "mod": "add", "amount": 3}]},
            ],
        }))
        load_all_cards(Path(tmpdir))

    dispatch(state, "ON_ATTACK", "hit-card", card=card)
    assert state.combat.attack_power == 5  # unchanged


# ---------------------------------------------------------------------------
# load_all_cards is idempotent
# ---------------------------------------------------------------------------

def test_load_all_cards_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "c.json").write_text(json.dumps({
            "slug": "my-card",
            "abilities": [],
        }))
        c1 = load_all_cards(Path(tmpdir))
        c2 = load_all_cards(Path(tmpdir))
        assert c1 == c2 == 1
        assert get_card("my-card") is not None


# ---------------------------------------------------------------------------
# combo_check helpers
# ---------------------------------------------------------------------------

def _make_chain_link(slug: str, power: int = 5, hit: bool = False):
    from engine.state import ChainLink
    return ChainLink(
        chainlink_id=0, attacker_id=1,
        attack_slug=slug, attack_power=power,
        net_damage=0, keywords=[], from_weapon=False, hit=hit,
    )


def test_combo_check_strips_color_suffix():
    from engine.card_effects.ability_keywords import combo_check
    state = _make_state()
    state.chain_links.append(_make_chain_link("surging_strike_red"))
    assert combo_check(state, ["surging_strike"])
    assert combo_check(state, ["surging_strike_red"])
    assert not combo_check(state, ["open_the_center"])


def test_combo_check_no_links_returns_false():
    from engine.card_effects.ability_keywords import combo_check
    state = _make_state()
    assert not combo_check(state, ["surging_strike"])


# ---------------------------------------------------------------------------
# WTR card JSON integration tests
# ---------------------------------------------------------------------------

WTR_JSON = Path(__file__).parent.parent / "engine" / "card_effects" / "json" / "wtr"


def _load_wtr():
    # Load the full json tree (superset of WTR). Loading only the WTR subdir
    # would leave the module-global card registry without tokens etc. and
    # pollute later test modules.
    return load_all_cards()


# ── sigil_of_solace_red ───────────────────────────────────────────────────────

def test_sigil_of_solace_red_gains_3_life():
    _load_wtr()
    state = _make_state()
    initial = state.players[1].life
    card = _make_card("sigil_of_solace_red", 1)
    dispatch(state, "ON_PLAY", "sigil_of_solace_red", card=card)
    assert state.players[1].life == initial + 3


# ── pummel_red ────────────────────────────────────────────────────────────────

def test_pummel_red_action_card_power_and_inject():
    """Non-weapon action card with cost>=2: +4p and inject ON_HIT discard trigger."""
    _load_wtr()
    state = _make_state()
    atk_card = _make_card("smash_the_ceiling_red", 1)
    atk_card.cost = 3
    state.combat = CombatState(
        attacker_id=1, link_id=1,
        attack_power=5, attack_card=atk_card, keywords=[],
        from_weapon=False,
    )
    pummel = _make_card("pummel_red", 1)
    dispatch(state, "ON_PLAY", "pummel_red", card=pummel)
    assert state.combat.attack_power == 9  # 5 + 4
    assert len(_attached_on_hit_triggers(state)) == 1


def test_pummel_red_hammer_weapon_power_no_inject():
    """Hammer weapon: target filter passes, +4p applied."""
    _load_wtr()
    state = _make_state()
    hammer = _make_card("smash_attack_red", 1)
    hammer.subtypes = ["Hammer"]
    state.combat = CombatState(
        attacker_id=1, link_id=1,
        attack_power=5, attack_card=hammer, keywords=[],
        from_weapon=True,
    )
    pummel = _make_card("pummel_red", 1)
    dispatch(state, "ON_PLAY", "pummel_red", card=pummel)
    assert state.combat.attack_power == 9  # 5 + 4


def test_pummel_red_no_effect_on_cheap_action():
    """Non-weapon action with cost<2: target filter fails, no effects fire."""
    _load_wtr()
    state = _make_state()
    cheap = _make_card("cheap_strike_red", 1)
    cheap.cost = 1
    state.combat = CombatState(
        attacker_id=1, link_id=1,
        attack_power=5, attack_card=cheap, keywords=[],
        from_weapon=False,
    )
    pummel = _make_card("pummel_red", 1)
    dispatch(state, "ON_PLAY", "pummel_red", card=pummel)
    assert state.combat.attack_power == 5  # unchanged


# ── disable_blue ──────────────────────────────────────────────────────────────

def test_disable_blue_moves_opponent_arsenal_on_crush():
    _load_wtr()
    state = _make_state()
    arsenal_card = _make_card("banished_card", 2)
    state.players[2].arsenal.add(arsenal_card)
    card = _make_card("disable_blue", 1)
    dispatch(state, "ON_CRUSH", "disable_blue", card=card)
    assert len(state.players[2].arsenal.cards) == 0
    assert arsenal_card in state.players[2].deck.cards


def test_disable_blue_no_crash_when_arsenal_empty():
    _load_wtr()
    state = _make_state()
    card = _make_card("disable_blue", 1)
    dispatch(state, "ON_CRUSH", "disable_blue", card=card)  # must not raise


# ── anothos ───────────────────────────────────────────────────────────────────

def test_anothos_while_static_bonus_with_two_pitch_cards():
    # WHILE_STATIC fires on the RECALC_ATTACK_POWER bridge; anothos needs 2+
    # cards with cost >= 3 in the pitch zone.
    _load_wtr()
    state = _make_state()
    state.combat = _make_combat(power=5)
    for i in range(2):
        c = _make_card(f"pitched_{i}", 1)
        c.cost = 3
        state.players[1].pitch.add(c)
    card = _make_card("anothos", 1)
    dispatch(state, "RECALC_ATTACK_POWER", "anothos", card=card)
    assert state.combat.attack_power == 7  # 5 + 2


def test_anothos_while_static_no_bonus_with_one_pitch_card():
    _load_wtr()
    state = _make_state()
    state.combat = _make_combat(power=5)
    c = _make_card("pitched_0", 1)
    c.cost = 3
    state.players[1].pitch.add(c)
    card = _make_card("anothos", 1)
    dispatch(state, "RECALC_ATTACK_POWER", "anothos", card=card)
    assert state.combat.attack_power == 5  # unchanged — only 1 card


def test_anothos_while_static_not_fired_on_other_events():
    # WHILE_STATIC must NOT fire on unrelated dispatches (no double-application).
    _load_wtr()
    state = _make_state()
    state.combat = _make_combat(power=5)
    for i in range(2):
        c = _make_card(f"pitched_{i}", 1)
        c.cost = 3
        state.players[1].pitch.add(c)
    card = _make_card("anothos", 1)
    dispatch(state, "ON_ATTACK", "anothos", card=card)
    assert state.combat.attack_power == 5  # unchanged — ON_ATTACK doesn't fire statics


# ── awakening_bellow_red ──────────────────────────────────────────────────────

def test_awakening_bellow_red_queues_next_attack_mod():
    _load_wtr()
    state = _make_state()
    card = _make_card("awakening_bellow_red", 1)
    dispatch(state, "ON_PLAY", "awakening_bellow_red", card=card)
    mods = getattr(state.players[1], 'dsl_queued_attack_mods', [])
    assert len(mods) == 1
    assert mods[0]["amount"] == 3
    assert mods[0]["mod"] == "add"


def test_awakening_bellow_yellow_queues_next_attack_mod():
    _load_wtr()
    state = _make_state()
    card = _make_card("awakening_bellow_yellow", 1)
    dispatch(state, "ON_PLAY", "awakening_bellow_yellow", card=card)
    mods = getattr(state.players[1], 'dsl_queued_attack_mods', [])
    assert len(mods) == 1
    assert mods[0]["amount"] == 2


def test_awakening_bellow_blue_queues_next_attack_mod():
    _load_wtr()
    state = _make_state()
    card = _make_card("awakening_bellow_blue", 1)
    dispatch(state, "ON_PLAY", "awakening_bellow_blue", card=card)
    mods = getattr(state.players[1], 'dsl_queued_attack_mods', [])
    assert len(mods) == 1
    assert mods[0]["amount"] == 1


# ── nimblism_blue ─────────────────────────────────────────────────────────────

def test_nimblism_blue_queues_next_attack_mod():
    _load_wtr()
    state = _make_state()
    card = _make_card("nimblism_blue", 1)
    dispatch(state, "ON_PLAY", "nimblism_blue", card=card)
    mods = getattr(state.players[1], 'dsl_queued_attack_mods', [])
    assert len(mods) == 1
    assert mods[0]["amount"] == 1


# ── scabskin_leathers ─────────────────────────────────────────────────────────

def test_scabskin_leathers_activate_sets_roll_and_gains_ap():
    _load_wtr()
    state = _make_state()
    initial_ap = state.players[1].action_points
    card = _make_card("scabskin_leathers", 1)
    dispatch(state, "ON_ACTIVATE", "scabskin_leathers", card=card)
    roll = getattr(state, '_roll_result', None)
    assert roll is not None and 1 <= roll <= 6
    assert state.players[1].action_points == initial_ap + roll // 2


# ── barkbone_strapping ────────────────────────────────────────────────────────

def test_barkbone_strapping_activate_sets_roll_and_gains_resources():
    _load_wtr()
    state = _make_state()
    initial_res = state.players[1].resources
    card = _make_card("barkbone_strapping", 1)
    dispatch(state, "ON_ACTIVATE", "barkbone_strapping", card=card)
    roll = getattr(state, '_roll_result', None)
    assert roll is not None and 1 <= roll <= 6
    assert state.players[1].resources == initial_res + roll // 2


# ── spinal_crush_red ──────────────────────────────────────────────────────────

def test_spinal_crush_red_on_crush_suppresses_opponent_go_again():
    _load_wtr()
    state = _make_state()
    card = _make_card("spinal_crush_red", 1)
    dispatch(state, "ON_CRUSH", "spinal_crush_red", card=card)
    # Opponent loses go again on their next turn.
    assert "cant_go_again" in state.players[2].next_turn_effects


# ── ancestral_empowerment_red ─────────────────────────────────────────────────

def test_ancestral_empowerment_red_ninja_attack_bonus():
    """Target filter passes for Ninja class attack → +1 power and draw 1."""
    _load_wtr()
    state = _make_state()
    for i in range(2):
        state.players[1].deck.add(_make_deck_card(f"d{i}"))
    ninja_card = _make_card("ninja_strike_red", 1)
    ninja_card.classes = ["Ninja"]
    ninja_card.subtypes = ["Attack"]  # target filter requires an Attack action card
    state.combat = CombatState(
        attacker_id=1, link_id=1,
        attack_power=4, attack_card=ninja_card, keywords=[],
        from_weapon=False,
    )
    card = _make_card("ancestral_empowerment_red", 1)
    dispatch(state, "ON_PLAY", "ancestral_empowerment_red", card=card)
    assert state.combat.attack_power == 5  # 4 + 1
    assert len(state.players[1].hand.cards) == 1  # draw 1


def test_ancestral_empowerment_red_non_ninja_no_effect():
    """Target filter blocks non-Ninja attack — no power bonus or draw."""
    _load_wtr()
    state = _make_state()
    warrior_card = _make_card("warrior_strike_red", 1)
    warrior_card.classes = ["Warrior"]
    state.combat = CombatState(
        attacker_id=1, link_id=1,
        attack_power=4, attack_card=warrior_card, keywords=[],
        from_weapon=False,
    )
    card = _make_card("ancestral_empowerment_red", 1)
    dispatch(state, "ON_PLAY", "ancestral_empowerment_red", card=card)
    assert state.combat.attack_power == 4  # unchanged
    assert len(state.players[1].hand.cards) == 0


# ── alpha_rampage_red ─────────────────────────────────────────────────────────

def test_alpha_rampage_red_on_attack_no_crash():
    """STATIC_TRIGGERED ON_ATTACK fires INTIMIDATE without error."""
    _load_wtr()
    state = _make_state()
    card = _make_card("alpha_rampage_red", 1)
    dispatch(state, "ON_ATTACK", "alpha_rampage_red", card=card)


# ── cranial_crush_blue ────────────────────────────────────────────────────────

def test_cranial_crush_blue_on_crush_blocks_opponent_draw():
    """Crush sets the opponent's 'cant_draw' flag for their next turn."""
    _load_wtr()
    state = _make_state()
    card = _make_card("cranial_crush_blue", 1)
    dispatch(state, "ON_CRUSH", "cranial_crush_blue", card=card)
    assert "cant_draw" in state.players[2].next_turn_effects


# ── debilitate_blue ───────────────────────────────────────────────────────────

def test_debilitate_blue_on_crush_debuffs_opponent_first_attack():
    _load_wtr()
    state = _make_state()
    state.combat = _make_combat(power=5)
    card = _make_card("debilitate_blue", 1)
    dispatch(state, "ON_CRUSH", "debilitate_blue", card=card)
    # Opponent's first attack next turn gets -2 power.
    assert "first_attack_-2p" in state.players[2].next_turn_effects


# ── enlightened_strike_red ────────────────────────────────────────────────────

def test_enlightened_strike_red_loads_and_dispatches_without_crash():
    """MODAL ability loads correctly; dispatching does not raise."""
    _load_wtr()
    state = _make_state()
    card = _make_card("enlightened_strike_red", 1)
    dispatch(state, "ON_PLAY", "enlightened_strike_red", card=card)


# ── sink_below_red ────────────────────────────────────────────────────────────

def test_sink_below_red_no_crash_empty_hand():
    _load_wtr()
    state = _make_state()
    card = _make_card("sink_below_red", 1)
    dispatch(state, "ON_PLAY", "sink_below_red", card=card)


def _attached_on_hit_triggers(state):
    """Every ON_HIT ability granted to the current attack, wherever it lives.

    A grant to an attack ACTION CARD attaches to the card (the attack IS the
    card); a grant to a WEAPON's attack stays on the combat, because the attack
    is a proxy object that dies with the chain link (CR 1.4.3c/e). Tests that
    only knew about combat.injected_triggers were asserting the storage rather
    than the behaviour.
    """
    out = [td for td in (getattr(state.combat, "injected_triggers", None) or [])
           if td.event_type == "ON_HIT"]
    attack = getattr(state.combat, "attack_card", None)
    out += [g for g in (getattr(attack, "granted_abilities", None) or [])
            if str(g.get("trigger", "")).upper() == "ON_HIT"]
    return out

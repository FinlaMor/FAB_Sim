"""Unit tests for condition checkers in loader.py (_make_condition)."""

from __future__ import annotations

from types import SimpleNamespace

from engine.card import Card
from engine.card_effects.db.loader import _make_condition
from engine.state import CombatState, GameState, Player, Step, Zone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hero(pid: int = 1) -> Card:
    c = Card(slug="test_hero", name="Test Hero", types=["Hero"], base_life=40, base_intellect=4)
    c.owner = pid
    c.controller = pid
    return c


def _make_player(pid: int = 1) -> Player:
    return Player(pid, _make_hero(pid))


def _mock_agent(state, options, **kwargs):
    if options:
        return options[0]
    return None


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


def _make_card(slug: str = "test_card", owner: int = 1) -> Card:
    c = Card(slug=slug, name="Test Card", types=["Action"])
    c.owner = owner
    c.controller = owner
    c.zone = "hand"
    return c


def _make_combat(attacker_id: int = 1, attack_power: int = 5) -> CombatState:
    attack_card = _make_card("attack_card", attacker_id)
    return CombatState(
        attacker_id=attacker_id,
        link_id=1,
        attack_power=attack_power,
        attack_card=attack_card,
        keywords=[],
    )


# ---------------------------------------------------------------------------
# none → returns None (always True)
# ---------------------------------------------------------------------------

def test_none_returns_none():
    result = _make_condition("none", {}, None)
    assert result is None


# ---------------------------------------------------------------------------
# custom
# ---------------------------------------------------------------------------

def test_custom_condition():
    def my_cond(c, e, s):
        return True
    result = _make_condition("custom", {}, my_cond)
    assert result is my_cond


# ---------------------------------------------------------------------------
# is_attacking
# ---------------------------------------------------------------------------

def test_is_attacking_true():
    state = _make_state()
    card = _make_card("my_attack", owner=1)
    state.combat = _make_combat()
    state.combat.attack_card = card
    fn = _make_condition("is_attacking", {}, None)
    assert fn(card, None, state) is True


def test_is_attacking_false_no_combat():
    state = _make_state()
    card = _make_card("my_attack", owner=1)
    fn = _make_condition("is_attacking", {}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# is_defending
# ---------------------------------------------------------------------------

def test_is_defending_true():
    state = _make_state()
    card = _make_card("def_card", owner=2)
    state.combat = _make_combat()
    state.combat.defending_cards = [card]
    fn = _make_condition("is_defending", {}, None)
    assert fn(card, None, state) is True


def test_is_defending_false():
    state = _make_state()
    card = _make_card("def_card", owner=2)
    state.combat = _make_combat()
    state.combat.defending_cards = []
    fn = _make_condition("is_defending", {}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# player_is_active
# ---------------------------------------------------------------------------

def test_player_is_active_true():
    state = _make_state()
    card = _make_card(owner=1)
    fn = _make_condition("player_is_active", {}, None)
    assert fn(card, None, state) is True


def test_player_is_active_false():
    state = _make_state()
    card = _make_card(owner=2)
    fn = _make_condition("player_is_active", {}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# player_is_non_active
# ---------------------------------------------------------------------------

def test_player_is_non_active_true():
    state = _make_state()
    card = _make_card(owner=2)  # active_player=1, so player 2 is non-active
    fn = _make_condition("player_is_non_active", {}, None)
    assert fn(card, None, state) is True


def test_player_is_non_active_false():
    state = _make_state()
    card = _make_card(owner=1)
    fn = _make_condition("player_is_non_active", {}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# health_more_than_opp
# ---------------------------------------------------------------------------

def test_health_more_than_opp_true():
    state = _make_state()
    state.players[1].health = 30
    state.players[2].health = 20
    card = _make_card(owner=1)
    fn = _make_condition("health_more_than_opp", {}, None)
    assert fn(card, None, state) is True


def test_health_more_than_opp_false():
    state = _make_state()
    state.players[1].health = 20
    state.players[2].health = 30
    card = _make_card(owner=1)
    fn = _make_condition("health_more_than_opp", {}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# flag_set
# ---------------------------------------------------------------------------

def test_flag_set_true():
    state = _make_state()
    state.players[1].current_turn_effects.append("my_flag")
    card = _make_card(owner=1)
    fn = _make_condition("flag_set", {"flag": "my_flag"}, None)
    assert fn(card, None, state) is True


def test_flag_set_false():
    state = _make_state()
    card = _make_card(owner=1)
    fn = _make_condition("flag_set", {"flag": "my_flag"}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# card_in_zone
# ---------------------------------------------------------------------------

def test_card_in_zone_true():
    card = _make_card()
    card.zone = "hand"
    fn = _make_condition("card_in_zone", {"zone": "hand"}, None)
    assert fn(card, None, None) is True


def test_card_in_zone_false():
    card = _make_card()
    card.zone = "graveyard"
    fn = _make_condition("card_in_zone", {"zone": "hand"}, None)
    assert fn(card, None, None) is False


# ---------------------------------------------------------------------------
# has_counter_gte
# ---------------------------------------------------------------------------

def test_has_counter_gte_true():
    state = _make_state()
    card = _make_card(owner=1)
    card.zone = "permanents"
    key = (card.slug, card.zone, "energy")
    state.players[1].counters[key] = 3
    fn = _make_condition("has_counter_gte", {"counter_type": "energy", "min": 2}, None)
    assert fn(card, None, state) is True


def test_has_counter_gte_false():
    state = _make_state()
    card = _make_card(owner=1)
    card.zone = "permanents"
    fn = _make_condition("has_counter_gte", {"counter_type": "energy", "min": 1}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# has_counter_lt
# ---------------------------------------------------------------------------

def test_has_counter_lt_true():
    state = _make_state()
    card = _make_card(owner=1)
    card.zone = "permanents"
    fn = _make_condition("has_counter_lt", {"type": "energy", "max": 3}, None)
    assert fn(card, None, state) is True  # 0 < 3


def test_has_counter_lt_false():
    state = _make_state()
    card = _make_card(owner=1)
    card.zone = "permanents"
    key = (card.slug, card.zone, "energy")
    state.players[1].counters[key] = 5
    fn = _make_condition("has_counter_lt", {"type": "energy", "max": 3}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# controller_has_card_type
# ---------------------------------------------------------------------------

def test_controller_has_card_type_true():
    state = _make_state()
    card = _make_card(owner=1)
    item = Card(slug="gold", name="Gold", types=["Item"])
    item.card_type = "Item"
    state.players[1].items.add(item)
    fn = _make_condition("controller_has_card_type", {"card_type": "Item", "zone": "permanents"}, None)
    assert fn(card, None, state) is True


def test_controller_has_card_type_false():
    state = _make_state()
    card = _make_card(owner=1)
    fn = _make_condition("controller_has_card_type", {"card_type": "Item", "zone": "permanents"}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# opponent_has_supertype
# ---------------------------------------------------------------------------

def test_opponent_has_supertype_true():
    state = _make_state()
    card = _make_card(owner=1)
    opp_card = Card(slug="opp_card", name="Opp Card", types=["Action"])
    opp_card.supertype = "Shadow"
    state.players[2].permanents.add(opp_card)
    fn = _make_condition("opponent_has_supertype", {"supertype": "Shadow", "zone": "permanents"}, None)
    assert fn(card, None, state) is True


def test_opponent_has_supertype_false():
    state = _make_state()
    card = _make_card(owner=1)
    fn = _make_condition("opponent_has_supertype", {"supertype": "Shadow", "zone": "permanents"}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# attacking_hero_is
# ---------------------------------------------------------------------------

def test_attacking_hero_is_true():
    state = _make_state()
    combat = _make_combat(attacker_id=1)
    # The condition code uses s.combat.attacker (not attacker_id)
    combat.attacker = 1
    state.combat = combat
    state.players[1].hero_slug = "kayo"
    card = _make_card(owner=1)
    fn = _make_condition("attacking_hero_is", {"hero": "kayo"}, None)
    assert fn(card, None, state) is True


def test_attacking_hero_is_false():
    state = _make_state()
    combat = _make_combat(attacker_id=1)
    combat.attacker = 1
    state.combat = combat
    state.players[1].hero_slug = "kayo"
    card = _make_card(owner=1)
    fn = _make_condition("attacking_hero_is", {"hero": "other_hero"}, None)
    assert fn(card, None, state) is False


def test_attacking_hero_is_no_combat():
    state = _make_state()
    card = _make_card(owner=1)
    fn = _make_condition("attacking_hero_is", {"hero": "kayo"}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# defending_hero_is
# ---------------------------------------------------------------------------

def test_defending_hero_is_true():
    state = _make_state()
    combat = _make_combat(attacker_id=1)
    # The condition code uses s.combat.defender (not derived from attacker_id)
    combat.defender = 2
    state.combat = combat
    state.players[2].hero_slug = "bravo"
    card = _make_card(owner=2)
    fn = _make_condition("defending_hero_is", {"hero": "bravo"}, None)
    assert fn(card, None, state) is True


def test_defending_hero_is_false():
    state = _make_state()
    combat = _make_combat(attacker_id=1)
    combat.defender = 2
    state.combat = combat
    state.players[2].hero_slug = "bravo"
    card = _make_card(owner=2)
    fn = _make_condition("defending_hero_is", {"hero": "other"}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# reprise_check
# ---------------------------------------------------------------------------

def test_reprise_check_true():
    state = _make_state()
    state.combat = _make_combat(attacker_id=1)
    # reprise_check uses defender_used_hand_card (set when defend action is applied)
    state.combat.defender_used_hand_card = True
    card = _make_card(owner=1)
    fn = _make_condition("reprise_check", {}, None)
    assert fn(card, None, state) is True


def test_reprise_check_false():
    state = _make_state()
    state.combat = _make_combat(attacker_id=1)
    state.combat.defending_cards = []
    card = _make_card(owner=1)
    fn = _make_condition("reprise_check", {}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# crush_check
# ---------------------------------------------------------------------------

def test_crush_check_true():
    state = _make_state()
    state.combat = _make_combat(attack_power=6)
    # crush_check reads event.data["damage"] — matches the key emitted by engine.py
    event = SimpleNamespace(data={"damage": 5})
    card = _make_card(owner=1)
    fn = _make_condition("crush_check", {}, None)
    assert fn(card, event, state) is True


def test_crush_check_false():
    state = _make_state()
    state.combat = _make_combat(attack_power=3)
    event = SimpleNamespace(data={"damage": 2})
    card = _make_card(owner=1)
    fn = _make_condition("crush_check", {}, None)
    assert fn(card, event, state) is False


# ---------------------------------------------------------------------------
# combo_check
# ---------------------------------------------------------------------------

def test_combo_check_true():
    state = _make_state()
    # combo_check looks at chain_links for matching slugs
    from engine.state import ChainLink
    state.chain_links = [
        ChainLink(chainlink_id=1, attacker_id=1, attack_slug="combo_partner",
                  attack_power=3, net_damage=1, keywords=[], from_weapon=False, hit=True)
    ]
    card = _make_card(owner=1)
    fn = _make_condition("combo_check", {"combo_names": ["combo_partner"]}, None)
    assert fn(card, None, state) is True


def test_combo_check_false():
    state = _make_state()
    state.chain_links = []
    card = _make_card(owner=1)
    fn = _make_condition("combo_check", {"combo_names": ["combo_partner"]}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# surge_check
# ---------------------------------------------------------------------------

def test_surge_check_true():
    state = _make_state()
    # surge_check reads event.data["damage"] — matches the key emitted by engine.py
    event = SimpleNamespace(data={"damage": 3})
    card = _make_card(owner=1)
    fn = _make_condition("surge_check", {"amount": 2}, None)
    assert fn(card, event, state) is True


def test_surge_check_false():
    state = _make_state()
    event = SimpleNamespace(data={"damage": 1})
    card = _make_card(owner=1)
    fn = _make_condition("surge_check", {"amount": 2}, None)
    assert fn(card, event, state) is False


# ---------------------------------------------------------------------------
# rupture_check
# ---------------------------------------------------------------------------

def test_rupture_check_true():
    state = _make_state()
    # rupture_check: len(chain_links) >= 3
    from engine.state import ChainLink
    state.chain_links = [
        ChainLink(chainlink_id=i, attacker_id=1, attack_slug=f"atk{i}",
                  attack_power=3, net_damage=1, keywords=[], from_weapon=False)
        for i in range(3)
    ]
    card = _make_card(owner=1)
    fn = _make_condition("rupture_check", {}, None)
    assert fn(card, None, state) is True


def test_rupture_check_false():
    state = _make_state()
    state.chain_links = []
    card = _make_card(owner=1)
    fn = _make_condition("rupture_check", {}, None)
    assert fn(card, None, state) is False


# ---------------------------------------------------------------------------
# unknown condition → returns None (always True)
# ---------------------------------------------------------------------------

def test_unknown_condition_returns_none():
    result = _make_condition("totally_unknown_xyz", {}, None)
    assert result is None


# ---------------------------------------------------------------------------
# all condition types return callables (or None)
# ---------------------------------------------------------------------------

def test_all_condition_types_return_callable_or_none():
    types = [
        "none", "is_attacking", "is_defending", "player_is_active",
        "player_is_non_active", "health_more_than_opp", "flag_set",
        "card_in_zone", "has_counter_gte", "has_counter_lt",
        "controller_has_card_type", "opponent_has_supertype",
        "attacking_hero_is", "defending_hero_is",
        "reprise_check", "crush_check", "combo_check",
        "surge_check", "rupture_check",
    ]
    for t in types:
        result = _make_condition(t, {}, None)
        assert result is None or callable(result), f"{t} returned {type(result)}"

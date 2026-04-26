"""Unit tests for effect executors in loader.py (_make_effect)."""

from __future__ import annotations

from types import SimpleNamespace

from engine.card import Card
from engine.card_effects.db.loader import _make_effect
from engine.state import CombatState, GameState, Player, Step, Zone


# ---------------------------------------------------------------------------
# Helpers — lightweight mock game state
# ---------------------------------------------------------------------------

def _make_hero(pid: int = 1) -> Card:
    c = Card(slug="test_hero", name="Test Hero", types=["Hero"], base_life=40, base_intellect=4)
    c.owner = pid
    c.controller = pid
    return c


def _make_player(pid: int = 1) -> Player:
    return Player(pid, _make_hero(pid))


def _mock_agent(state, options, **kwargs):
    """Mock agent that always picks the first option."""
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
# gain_life
# ---------------------------------------------------------------------------

def test_gain_life():
    state = _make_state()
    card = _make_card(owner=1)
    fn = _make_effect("gain_life", {"amount": 3}, None)
    initial = state.players[1].health
    fn(card, None, state)
    assert state.players[1].health == initial + 3


# ---------------------------------------------------------------------------
# lose_life
# ---------------------------------------------------------------------------

def test_lose_life():
    state = _make_state()
    card = _make_card(owner=1)
    fn = _make_effect("lose_life", {"amount": 2}, None)
    initial = state.players[1].health
    fn(card, None, state)
    assert state.players[1].health == initial - 2


# ---------------------------------------------------------------------------
# deal_damage (opponent)
# ---------------------------------------------------------------------------

def test_deal_damage_opponent():
    state = _make_state()
    card = _make_card(owner=1)
    fn = _make_effect("deal_damage", {"amount": 4, "target": "opponent"}, None)
    initial = state.players[2].health
    fn(card, None, state)
    assert state.players[2].health == initial - 4


# ---------------------------------------------------------------------------
# deal_arcane
# ---------------------------------------------------------------------------

def test_deal_arcane_opponent():
    state = _make_state()
    card = _make_card(owner=1)
    fn = _make_effect("deal_arcane", {"amount": 2, "target": "opponent"}, None)
    initial = state.players[2].health
    fn(card, None, state)
    assert state.players[2].health == initial - 2


# ---------------------------------------------------------------------------
# draw
# ---------------------------------------------------------------------------

def test_draw():
    state = _make_state()
    card = _make_card(owner=1)
    # Put cards in deck
    for i in range(3):
        state.players[1].deck.add(Card(slug=f"deck_{i}", name=f"Deck {i}"))
    fn = _make_effect("draw", {"amount": 2}, None)
    fn(card, None, state)
    assert len(state.players[1].hand.cards) == 2


# ---------------------------------------------------------------------------
# grant_go_again
# ---------------------------------------------------------------------------

def test_grant_go_again():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card(owner=1)
    fn = _make_effect("grant_go_again", {}, None)
    fn(card, None, state)
    assert "go_again" in state.combat.keywords


def test_grant_go_again_no_duplicate():
    state = _make_state()
    state.combat = _make_combat()
    state.combat.keywords.append("go_again")
    card = _make_card(owner=1)
    fn = _make_effect("grant_go_again", {}, None)
    fn(card, None, state)
    assert state.combat.keywords.count("go_again") == 1


# ---------------------------------------------------------------------------
# power_bonus
# ---------------------------------------------------------------------------

def test_power_bonus():
    state = _make_state()
    state.combat = _make_combat(attack_power=5)
    card = _make_card(owner=1)
    fn = _make_effect("power_bonus", {"amount": 3}, None)
    fn(card, None, state)
    assert state.combat.attack_power == 8


# ---------------------------------------------------------------------------
# discard
# ---------------------------------------------------------------------------

def test_discard():
    state = _make_state()
    card = _make_card(owner=1)
    # Put a card in hand
    hand_card = Card(slug="hand1", name="Hand 1")
    hand_card.owner = 1
    hand_card.controller = 1
    state.players[1].hand.add(hand_card)
    fn = _make_effect("discard", {"amount": 1}, None)
    fn(card, None, state)
    assert len(state.players[1].hand.cards) == 0


# ---------------------------------------------------------------------------
# deal_physical
# ---------------------------------------------------------------------------

def test_deal_physical():
    state = _make_state()
    card = _make_card(owner=1)
    fn = _make_effect("deal_physical", {"amount": 3, "target": "opponent"}, None)
    initial = state.players[2].health
    fn(card, None, state)
    assert state.players[2].health == initial - 3


# ---------------------------------------------------------------------------
# grant_keyword
# ---------------------------------------------------------------------------

def test_grant_keyword():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card(owner=1)
    fn = _make_effect("grant_keyword", {"keyword": "dominate"}, None)
    fn(card, None, state)
    assert "dominate" in state.combat.keywords


def test_grant_keyword_no_combat():
    """grant_keyword should not crash when there's no combat."""
    state = _make_state()
    card = _make_card(owner=1)
    fn = _make_effect("grant_keyword", {"keyword": "dominate"}, None)
    fn(card, None, state)  # should not raise


# ---------------------------------------------------------------------------
# remove_counter
# ---------------------------------------------------------------------------

def test_remove_counter():
    state = _make_state()
    card = _make_card(owner=1)
    card.zone = "permanents"
    key = (card.slug, card.zone, "energy")
    state.players[1].counters[key] = 3
    fn = _make_effect("remove_counter", {"counter_type": "energy", "amount": 1}, None)
    fn(card, None, state)
    assert state.players[1].counters[key] == 2


# ---------------------------------------------------------------------------
# banish_top_deck
# ---------------------------------------------------------------------------

def test_banish_top_deck():
    state = _make_state()
    card = _make_card(owner=1)
    for i in range(3):
        state.players[1].deck.add(Card(slug=f"deck_{i}", name=f"Deck {i}"))
    fn = _make_effect("banish_top_deck", {"amount": 2, "face_up": True}, None)
    fn(card, None, state)
    assert len(state.players[1].banished.cards) == 2
    assert len(state.players[1].deck.cards) == 1


# ---------------------------------------------------------------------------
# reload
# ---------------------------------------------------------------------------

def test_reload():
    state = _make_state()
    card = _make_card(owner=1)
    # Put a card in hand and cards in deck for draw
    hand_card = Card(slug="hand1", name="Hand 1", types=["Action"])
    hand_card.owner = 1
    hand_card.controller = 1
    state.players[1].hand.add(hand_card)
    for i in range(3):
        state.players[1].deck.add(Card(slug=f"deck_{i}", name=f"Deck {i}"))
    fn = _make_effect("reload", {}, None)
    fn(card, None, state)
    # Reload: put hand card on bottom of deck, then draw a card
    # Net result: hand should have 1 card (the drawn one)
    assert len(state.players[1].hand.cards) == 1


# ---------------------------------------------------------------------------
# opt
# ---------------------------------------------------------------------------

def test_opt():
    state = _make_state()
    card = _make_card(owner=1)
    for i in range(3):
        state.players[1].deck.add(Card(slug=f"deck_{i}", name=f"Deck {i}"))
    fn = _make_effect("opt", {"amount": 2}, None)
    # opt uses _ask_player; the default agent returns the first option
    fn(card, None, state)
    # Just verify no crash; opt rearranges top of deck


# ---------------------------------------------------------------------------
# charge
# ---------------------------------------------------------------------------

def test_charge():
    state = _make_state()
    card = _make_card(owner=1)
    hand_card = Card(slug="charge_target", name="Charge Target", types=["Action"])
    hand_card.owner = 1
    hand_card.controller = 1
    state.players[1].hand.add(hand_card)
    fn = _make_effect("charge", {}, None)
    fn(card, None, state)
    # Charge moves a card from hand to soul
    assert len(state.players[1].hand.cards) == 0
    assert len(state.players[1].soul.cards) == 1


# ---------------------------------------------------------------------------
# set_flag
# ---------------------------------------------------------------------------

def test_set_flag_current():
    state = _make_state()
    card = _make_card(owner=1)
    fn = _make_effect("set_flag", {"flag": "test_flag", "scope": "current"}, None)
    fn(card, None, state)
    assert "test_flag" in state.players[1].current_turn_effects


# ---------------------------------------------------------------------------
# put_counter
# ---------------------------------------------------------------------------

def test_put_counter():
    state = _make_state()
    card = _make_card(owner=1)
    card.zone = "permanents"
    fn = _make_effect("put_counter", {"counter_type": "energy"}, None)
    fn(card, None, state)
    key = (card.slug, card.zone, "energy")
    assert state.players[1].counters.get(key, 0) == 1


# ---------------------------------------------------------------------------
# custom effect
# ---------------------------------------------------------------------------

def test_custom_effect():
    called = []
    def my_fn(card, event, state):
        called.append(True)
    fn = _make_effect("custom", {}, my_fn)
    fn(None, None, None)
    assert called == [True]


# ---------------------------------------------------------------------------
# unknown effect type → no-op
# ---------------------------------------------------------------------------

def test_unknown_effect_noop():
    fn = _make_effect("unknown_type_xyz", {}, None)
    assert callable(fn)
    fn(None, None, None)  # should not raise

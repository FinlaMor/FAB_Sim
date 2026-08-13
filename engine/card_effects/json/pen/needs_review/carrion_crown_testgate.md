# carrion_crown — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
_______________ test_carrion_crown_play_discard_ally_draw_card ________________

    def test_carrion_crown_play_discard_ally_draw_card():
        st = _make_state(); st.card_db = DB
        card = _card("carrion_crown")
        st.players[1].permanents.cards.append(card)
        # Add an ally to hand to discard
        ally = _card("vicious_ally")
        st.players[1].hand.cards.append(ally)
        # Capture state before
        before_hand = len(st.players[1].hand.cards)
        before_deck = len(st.players[1].deck.cards)
        before_graveyard = len(st.players[1].graveyard.cards)
        before_permanents = len(st.players[1].permanents.cards)
    
        # Fire the play ability
        activate(st, card)
    
        # Assert effects
>       assert len(st.players[1].hand.cards) == before_hand - 1  # Discard ally
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AssertionError: assert 1 == (1 - 1)
E        +  where 1 = len([Card(slug='vicious_ally', raw_name=None, raw_pitch=None, raw_cost=None, raw_power=None, raw_defense=None, raw_life=No...rget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)])
E        +    where [Card(slug='vicious_ally', raw_name=None, raw_pitch=None, raw_cost=None, raw_power=None, raw_defense=None, raw_life=No...rget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)] = Zone('hand', ['vicious_ally']).cards
E        +      where Zone('hand', ['vicious_ally']) = <engine.state.Player object at 0x0000022A86617230>.hand

tests\_gate_carrion_crown.py:92: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_carrion_crown.py::test_carrion_crown_play_discard_ally_draw_card
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.37s


--- TEST CODE ---
def test_carrion_crown_play_discard_ally_draw_card():
    st = _make_state(); st.card_db = DB
    card = _card("carrion_crown")
    st.players[1].permanents.cards.append(card)
    # Add an ally to hand to discard
    ally = _card("vicious_ally")
    st.players[1].hand.cards.append(ally)
    # Capture state before
    before_hand = len(st.players[1].hand.cards)
    before_deck = len(st.players[1].deck.cards)
    before_graveyard = len(st.players[1].graveyard.cards)
    before_permanents = len(st.players[1].permanents.cards)

    # Fire the play ability
    activate(st, card)

    # Assert effects
    assert len(st.players[1].hand.cards) == before_hand - 1  # Discard ally
    assert len(st.players[1].deck.cards) == before_deck - 1  # Draw a card
    assert len(st.players[1].graveyard.cards) == before_graveyard + 1  # Crown destroyed
    assert len(st.players[1].permanents.cards) == before_permanents - 1  # Crown removed from play


def test_carrion_crown_play_go_again():
    st = _make_state(); st.card_db = DB
    card = _card("carrion_crown")
    st.players[1].permanents.cards.append(card)
    # Add an ally to hand to discard
    ally = _card("vicious_ally")
    st.players[1].hand.cards.append(ally)
    # Capture state before
    before_hand = len(st.players[1].hand.cards)
    before_deck = len(st.players[1].deck.cards)
    before_permanents = len(st.players[1].permanents.cards)

    # Fire the play ability
    activate(st, card)

    # Assert effects
    assert len(st.players[1].hand.cards) == before_hand - 1  # Discard ally
    assert len(st.players[1].deck.cards) == before_deck - 1  # Draw a card
    assert len(st.players[1].permanents.cards) == before_permanents - 1  # Crown destroyed
```

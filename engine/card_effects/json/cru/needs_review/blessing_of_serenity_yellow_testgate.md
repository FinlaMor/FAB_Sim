# blessing_of_serenity_yellow — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
____________ test_blessing_of_serenity_yellow_play_prevents_damage ____________

    def test_blessing_of_serenity_yellow_play_prevents_damage():
        st = _make_state(); st.card_db = DB
        card = _card("blessing_of_serenity_yellow")
        st.players[1].permanents.cards.append(card)
        # Play the card (ON_PLAY trigger)
        dispatch(st, "ON_PLAY", "blessing_of_serenity_yellow", card=card, event=None)
    
        # Set up a physical damage event to the player
        before_health = st.players[1].health
        damage_event = {"type": "damage", "source": "enemy", "amount": 3, "damage_type": "physical"}
    
        # Simulate damage being dealt during the turn
        set_turn_flag(st, 1, "did_this_turn:attack")  # This flags the turn for the condition
        dispatch(st, "ON_DAMAGE", "blessing_of_serenity_yellow", card=card, event=damage_event)
    
        # The health should be unchanged because 2 damage was prevented (3 - 2 = 1 damage applied)
>       assert st.players[1].health == before_health - 1
E       assert 40 == (40 - 1)
E        +  where 40 = <engine.state.Player object at 0x0000021C82A2F380>.health

tests\_gate_blessing_of_serenity_yellow.py:121: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_blessing_of_serenity_yellow.py::test_blessing_of_serenity_yellow_play_prevents_damage
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.37s


--- TEST CODE ---
def test_blessing_of_serenity_yellow_play_prevents_damage():
    st = _make_state(); st.card_db = DB
    card = _card("blessing_of_serenity_yellow")
    st.players[1].permanents.cards.append(card)
    # Play the card (ON_PLAY trigger)
    dispatch(st, "ON_PLAY", "blessing_of_serenity_yellow", card=card, event=None)
    
    # Set up a physical damage event to the player
    before_health = st.players[1].health
    damage_event = {"type": "damage", "source": "enemy", "amount": 3, "damage_type": "physical"}
    
    # Simulate damage being dealt during the turn
    set_turn_flag(st, 1, "did_this_turn:attack")  # This flags the turn for the condition
    dispatch(st, "ON_DAMAGE", "blessing_of_serenity_yellow", card=card, event=damage_event)
    
    # The health should be unchanged because 2 damage was prevented (3 - 2 = 1 damage applied)
    assert st.players[1].health == before_health - 1


def test_blessing_of_serenity_yellow_play_prevents_only_once():
    st = _make_state(); st.card_db = DB
    card = _card("blessing_of_serenity_yellow")
    st.players[1].permanents.cards.append(card)
    # Play the card (ON_PLAY trigger)
    dispatch(st, "ON_PLAY", "blessing_of_serenity_yellow", card=card, event=None)
    
    # First damage - should prevent 2 damage
    before_health = st.players[1].health
    damage_event_1 = {"type": "damage", "source": "enemy", "amount": 3, "damage_type": "physical"}
    set_turn_flag(st, 1, "did_this_turn:attack")
    dispatch(st, "ON_DAMAGE", "blessing_of_serenity_yellow", card=card, event=damage_event_1)
    
    # Health should decrease by only 1 (3 - 2 prevented)
    assert st.players[1].health == before_health - 1
    
    # Second damage - simulate another damage event with same flag to ensure effect is consumed
    before_health = st.players[1].health
    damage_event_2 = {"type": "damage", "source": "enemy", "amount": 3, "damage_type": "physical"}
    set_turn_flag(st, 1, "did_this_turn:attack")  # Still in same turn so still eligible to prevent
    dispatch(st, "ON_DAMAGE", "blessing_of_serenity_yellow", card=card, event=damage_event_2)
    
    # Health should decrease by full amount (3) due to effect being consumed after first use
    assert st.players[1].health == before_health - 3
```

# beneath_the_surface_yellow — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
_____________ test_beneath_the_surface_yellow_flip_on_leave_play ______________

    def test_beneath_the_surface_yellow_flip_on_leave_play():
        # Test that when Beneath the Surface is put into the graveyard from the arena while defending,
        # it flips face-down (becomes a defense reaction).
        st = _make_state(); st.card_db = DB
        card = _card("beneath_the_surface_yellow")
    
        # Set up the card in the arena as a defense
        st.players[1].arsenal.cards.append(card)
        st.players[1].permanents.cards.append(card)
    
        # Ensure it's defending (in combat) and controlled by self
>       st.combat.attacker = card
        ^^^^^^^^^^^^^^^^^^
E       AttributeError: 'NoneType' object has no attribute 'attacker' and no __dict__ for setting new attributes

tests\_gate_beneath_the_surface_yellow.py:86: AttributeError
=========================== short test summary info ===========================
FAILED tests/_gate_beneath_the_surface_yellow.py::test_beneath_the_surface_yellow_flip_on_leave_play
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.36s


--- TEST CODE ---
def test_beneath_the_surface_yellow_flip_on_leave_play():
    # Test that when Beneath the Surface is put into the graveyard from the arena while defending,
    # it flips face-down (becomes a defense reaction).
    st = _make_state(); st.card_db = DB
    card = _card("beneath_the_surface_yellow")
    
    # Set up the card in the arena as a defense
    st.players[1].arsenal.cards.append(card)
    st.players[1].permanents.cards.append(card)
    
    # Ensure it's defending (in combat) and controlled by self
    st.combat.attacker = card
    st.combat.defender = card
    st.combat.attack_power = 5
    st.combat.defense_power = 5
    
    # Simulate the card leaving play (moving to graveyard)
    dispatch(st, "ON_LEAVE_PLAY", "beneath_the_surface_yellow", card=card, event=None)
    
    # Assert that the card is now face-down (flipped)
    assert card.face_down is True


def test_beneath_the_surface_yellow_flip_conditionally():
    # Test that the flip only happens when the conditions are met:
    # in combat, controlling attack action, and ref exists.
    st = _make_state(); st.card_db = DB
    card = _card("beneath_the_surface_yellow")
    
    # Set up a scenario where it is not defending or controlled by self
    st.players[1].arsenal.cards.append(card)
    st.players[1].permanents.cards.append(card)
    
    # Set combat, but with different attacker/defender (not controlling attack action)
    st.combat.attacker = _card("giant_spider")  # not the same card
    st.combat.defender = card
    st.combat.attack_power = 5
    st.combat.defense_power = 5

    # Simulate leaving play — should NOT flip because conditions are not met
    dispatch(st, "ON_LEAVE_PLAY", "beneath_the_surface_yellow", card=card, event=None)

    # Assert that the card is NOT flipped (it remains face-up)
    assert card.face_down is False
```

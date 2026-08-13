# bone_puppetry — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
_____ test_bone_puppetry_on_defend_returns_ally_and_destroys_on_end_phase _____

    def test_bone_puppetry_on_defend_returns_ally_and_destroys_on_end_phase():
        st = _make_state(); st.card_db = DB
        card = _card("bone_puppetry")
        st.players[1].arms.cards.append(card)
    
        # Set up an ally in the graveyard to return
        ally = _card("soul_siphon")  # Any ally card will do
        st.players[1].graveyard.cards.append(ally)
    
        # Simulate defending (ON_DEFEND trigger)
        dispatch(st, "ON_DEFEND", "bone_puppetry", card=card)
    
        # Verify the ally was returned to the arena
>       assert len(st.players[1].permanents.cards) == 1
E       AssertionError: assert 0 == 1
E        +  where 0 = len([])
E        +    where [] = Zone('permanents', []).cards
E        +      where Zone('permanents', []) = <engine.state.Player object at 0x000001EF27813230>.permanents

tests\_gate_bone_puppetry.py:88: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_bone_puppetry.py::test_bone_puppetry_on_defend_returns_ally_and_destroys_on_end_phase
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.39s


--- TEST CODE ---
def test_bone_puppetry_on_defend_returns_ally_and_destroys_on_end_phase():
    st = _make_state(); st.card_db = DB
    card = _card("bone_puppetry")
    st.players[1].arms.cards.append(card)
    
    # Set up an ally in the graveyard to return
    ally = _card("soul_siphon")  # Any ally card will do
    st.players[1].graveyard.cards.append(ally)
    
    # Simulate defending (ON_DEFEND trigger)
    dispatch(st, "ON_DEFEND", "bone_puppetry", card=card)

    # Verify the ally was returned to the arena
    assert len(st.players[1].permanents.cards) == 1
    assert st.players[1].permanents.cards[0].slug == "soul_siphon"

    # Simulate start of end phase (START_OF_TURN_IN_GRAVEYARD trigger)
    dispatch(st, "START_OF_TURN_IN_GRAVEYYARD", "bone_puppetry", card=card)

    # Verify the returned ally was destroyed
    assert len(st.players[1].permanents.cards) == 0

def test_bone_puppetry_on_defend_may_not_return_ally():
    st = _make_state(); st.card_db = DB
    card = _card("bone_puppetry")
    st.players[1].arms.cards.append(card)
    
    # Set up an ally in the graveyard
    ally = _card("soul_siphon")
    st.players[1].graveyard.cards.append(ally)
    
    # Do NOT return the ally (i.e. do not choose to act on MAY effect)
    # Just trigger the ON_DEFEND directly, skipping the choice part
    
    # Simulate defending (ON_DEFEND trigger) - no may choose action
    dispatch(st, "ON_DEFEND", "bone_puppetry", card=card)

    # Verify that the ally was NOT returned to the arena
    assert len(st.players[1].permanents.cards) == 0

    # Simulate start of end phase (should not happen if no return occurred)
    # This test does not actually fire the end phase trigger since there's no flag set
```

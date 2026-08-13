# become_the_cup_blue — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
____________________ test_become_the_cup_blue_choose_color ____________________

    def test_become_the_cup_blue_choose_color():
        # "As you play this, choose a color. This gets the chosen color."
        st = _make_state(); st.card_db = DB
        card = _card("become_the_cup_blue")
        st.players[1].hand.cards.append(card)
    
        # Dispatch the play event
        dispatch(st, "ON_PLAY", "become_the_cup_blue", card=card, event=None)
    
        # Assert that the CHOOSE_COLOR flag is set
>       assert "CHOOSE_COLOR" in st.flags
                                 ^^^^^^^^
E       AttributeError: 'GameState' object has no attribute 'flags'

tests\_gate_become_the_cup_blue.py:85: AttributeError
=========================== short test summary info ===========================
FAILED tests/_gate_become_the_cup_blue.py::test_become_the_cup_blue_choose_color
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.38s


--- TEST CODE ---
def test_become_the_cup_blue_choose_color():
    # "As you play this, choose a color. This gets the chosen color."
    st = _make_state(); st.card_db = DB
    card = _card("become_the_cup_blue")
    st.players[1].hand.cards.append(card)
    
    # Dispatch the play event
    dispatch(st, "ON_PLAY", "become_the_cup_blue", card=card, event=None)
    
    # Assert that the CHOOSE_COLOR flag is set
    assert "CHOOSE_COLOR" in st.flags

def test_become_the_cup_blue_modify_attack_power():
    # "As you play this, choose a color. This gets the chosen color."
    # "Go again" is not directly testable here, so we focus on the attack power modification.
    st = _make_state(); st.card_db = DB
    card = _card("become_the_cup_blue")
    st.players[1].weapon1.add(card)
    
    # Set up the CHOOSE_COLOR flag
    st.flags["CHOOSE_COLOR"] = True
    
    # Set up a real combat
    attack(st, card)
    
    # Assert that the attack power is modified
    assert st.combat.attack_power == 1  # Assuming base attack power is 0
```

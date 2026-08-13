# boltn_boots — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
______________________ test_boltn_boots_attack_reaction _______________________

    def test_boltn_boots_attack_reaction():
        # Test that Bolt'n Boots grants go again on arrow attacks with pitch power >= 1
        st = _make_state(); st.card_db = DB
        boots = _card("boltn_boots")
        st.players[1].permanents.cards.append(boots)
    
        # Equip the boots (required for attack reaction to be active)
        activate(st, boots)
    
        # Set up an arrow attack with pitch power greater than base (1)
        attack_card = _card("bolt")
        st.players[2].arsenal.cards.append(attack_card)
>       st.combat = st.players[1].arsenal.cards[-1]
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       IndexError: list index out of range

tests\_gate_boltn_boots.py:87: IndexError
=========================== short test summary info ===========================
FAILED tests/_gate_boltn_boots.py::test_boltn_boots_attack_reaction - IndexEr...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.39s


--- TEST CODE ---
def test_boltn_boots_attack_reaction():
    # Test that Bolt'n Boots grants go again on arrow attacks with pitch power >= 1
    st = _make_state(); st.card_db = DB
    boots = _card("boltn_boots")
    st.players[1].permanents.cards.append(boots)
    
    # Equip the boots (required for attack reaction to be active)
    activate(st, boots)
    
    # Set up an arrow attack with pitch power greater than base (1)
    attack_card = _card("bolt")
    st.players[2].arsenal.cards.append(attack_card)
    st.combat = st.players[1].arsenal.cards[-1]
    st.combat.attack_power = 2  # Greater than base power
    
    # Trigger the ON_HIT event (this is when attack reaction applies)
    hit(st)
    
    # The key observable is that the boots were destroyed (as per cost)
    assert not any(c.slug == "boltn_boots" for c in st.players[1].permanents.cards)
```

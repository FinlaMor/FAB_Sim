# blast_rig_red — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
_________________ test_blast_rig_red_evo_upgrade_power_boost __________________

    def test_blast_rig_red_evo_upgrade_power_boost():
        st = _make_state(); st.card_db = DB
        card = _card("blast_rig_red")
        st.players[1].arsenal.cards.append(card)
    
        # Add some Evo equipment to player 1
        evo_card1 = _card("evo_shield")
        evo_card2 = _card("evo_glove")
>       st.players[1].equipment.cards.extend([evo_card1, evo_card2])
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: 'list' object has no attribute 'cards'

tests\_gate_blast_rig_red.py:83: AttributeError
=========================== short test summary info ===========================
FAILED tests/_gate_blast_rig_red.py::test_blast_rig_red_evo_upgrade_power_boost
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.38s


--- TEST CODE ---
def test_blast_rig_red_evo_upgrade_power_boost():
    st = _make_state(); st.card_db = DB
    card = _card("blast_rig_red")
    st.players[1].arsenal.cards.append(card)
    
    # Add some Evo equipment to player 1
    evo_card1 = _card("evo_shield")
    evo_card2 = _card("evo_glove")
    st.players[1].equipment.cards.extend([evo_card1, evo_card2])
    
    # Activate the card to trigger the upgrade effect
    activate(st, card)
    
    # Check the attack power was increased by 2 (one for each Evo equipped)
    assert st.combat.attack_power == 2


def test_blast_rig_red_evo_upgrade_with_no_evo_equipped():
    st = _make_state(); st.card_db = DB
    card = _card("blast_rig_red")
    st.players[1].arsenal.cards.append(card)
    
    # No Evo equipment equipped
    st.players[1].equipment.cards.clear()
    
    # Activate the card to trigger the upgrade effect
    activate(st, card)
    
    # Check the attack power was not increased (no Evo cards equipped)
    assert st.combat.attack_power == 0
```

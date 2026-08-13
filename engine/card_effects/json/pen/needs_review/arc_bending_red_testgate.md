# arc_bending_red — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
____________________ test_arc_bending_red_damage_increase _____________________

    def test_arc_bending_red_damage_increase():
        # Set up a state with the card in hand and an opponent hero
        st = _make_state(); st.card_db = DB
        card = _card("arc_bending_red")
        st.players[1].hand.cards.append(card)
        attack(st, card)
    
        # Capture the opponent's health before the hit
        before_hit_health = st.players[2].health
    
        # Land the hit to trigger the ability
        hit(st)
    
        # Assert that the opponent's health is reduced by 1 more than the attack power
        expected_damage = st.combat.attack_power + 1
>       assert st.players[2].health == before_hit_health - expected_damage
E       assert 40 == (40 - 6)
E        +  where 40 = <engine.state.Player object at 0x000002D150E30050>.health

tests\_gate_arc_bending_red.py:90: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_arc_bending_red.py::test_arc_bending_red_damage_increase
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.43s


--- TEST CODE ---
def test_arc_bending_red_damage_increase():
    # Set up a state with the card in hand and an opponent hero
    st = _make_state(); st.card_db = DB
    card = _card("arc_bending_red")
    st.players[1].hand.cards.append(card)
    attack(st, card)
    
    # Capture the opponent's health before the hit
    before_hit_health = st.players[2].health
    
    # Land the hit to trigger the ability
    hit(st)
    
    # Assert that the opponent's health is reduced by 1 more than the attack power
    expected_damage = st.combat.attack_power + 1
    assert st.players[2].health == before_hit_health - expected_damage

def test_arc_bending_red_go_again():
    # Set up a state with the card in hand and pitch a Lightning card
    st = _make_state(); st.card_db = DB
    card = _card("arc_bending_red")
    st.players[1].hand.cards.append(card)
    lightning_card = _card("lightning_strike")  # Assume a Lightning card exists for testing
    st.players[1].deck.cards.append(lightning_card)
    st.players[1].discard(cards=[lightning_card])
    
    # Activate the card
    activate(st, card)
    
    # Assert that the card gets go again
    assert st.players[1].action_points == 1
```

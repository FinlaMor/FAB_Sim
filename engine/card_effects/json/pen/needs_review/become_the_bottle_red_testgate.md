# become_the_bottle_red — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
____________________ test_become_the_bottle_red_on_attack _____________________

    def test_become_the_bottle_red_on_attack():
        st = _make_state(); st.card_db = DB
        card = _card("become_the_bottle_red")
        st.players[1].weapon1.add(card)
        attack(st, card)
>       assert st.combat.combat_chain[0].name == card.name
               ^^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: 'CombatState' object has no attribute 'combat_chain'

tests\_gate_become_the_bottle_red.py:80: AttributeError
=========================== short test summary info ===========================
FAILED tests/_gate_become_the_bottle_red.py::test_become_the_bottle_red_on_attack
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.42s


--- TEST CODE ---
def test_become_the_bottle_red_on_attack():
    st = _make_state(); st.card_db = DB
    card = _card("become_the_bottle_red")
    st.players[1].weapon1.add(card)
    attack(st, card)
    assert st.combat.combat_chain[0].name == card.name

def test_become_the_bottle_red_go_again():
    st = _make_state(); st.card_db = DB
    card = _card("become_the_bottle_red")
    st.players[1].weapon1.add(card)
    attack(st, card)
    assert st.players[1].action_points == 1  # Assuming the card gives go again, it should have 1 action point left
```

# become_the_bottle_yellow — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
___________________ test_become_the_bottle_yellow_on_attack ___________________

    def test_become_the_bottle_yellow_on_attack():
        st = _make_state(); st.card_db = DB
        card = _card("become_the_bottle_yellow")
        st.players[1].weapon1.add(card)
        attack(st, card)
        # Capture the name of the first card on the combat chain before hitting
>       before_name = st.combat.chain[0].name
                      ^^^^^^^^^^^^^^^
E       AttributeError: 'CombatState' object has no attribute 'chain'

tests\_gate_become_the_bottle_yellow.py:81: AttributeError
=========================== short test summary info ===========================
FAILED tests/_gate_become_the_bottle_yellow.py::test_become_the_bottle_yellow_on_attack
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.42s


--- TEST CODE ---
def test_become_the_bottle_yellow_on_attack():
    st = _make_state(); st.card_db = DB
    card = _card("become_the_bottle_yellow")
    st.players[1].weapon1.add(card)
    attack(st, card)
    # Capture the name of the first card on the combat chain before hitting
    before_name = st.combat.chain[0].name
    hit(st)
    # Check if the chosen card's name is set as the card's name
    assert card.name == before_name

def test_become_the_bottle_yellow_go_again():
    st = _make_state(); st.card_db = DB
    card = _card("become_the_bottle_yellow")
    st.players[1].weapon1.add(card)
    attack(st, card)
    hit(st)
    # Check if go_again is granted
    assert st.players[1].action_points == 1  # Assuming go_again grants 1 action point
```

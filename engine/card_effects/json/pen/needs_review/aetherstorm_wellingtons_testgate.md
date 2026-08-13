# aetherstorm_wellingtons — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
_________________ test_aetherstorm_wellingtons_arcane_barrier _________________

    def test_aetherstorm_wellingtons_arcane_barrier():
        # Test the Arcane Barrier 2 effect on equipping the card
        st = _make_state(); st.card_db = DB
        card = _card("aetherstorm_wellingtons")
        st.players[1].head.add(card)
        dispatch(st, "ON_EQUIP", "aetherstorm_wellingtons", card=card, event=None)
>       assert st.players[1].arcane_barrier == 2
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: 'Player' object has no attribute 'arcane_barrier'

tests\_gate_aetherstorm_wellingtons.py:81: AttributeError
=========================== short test summary info ===========================
FAILED tests/_gate_aetherstorm_wellingtons.py::test_aetherstorm_wellingtons_arcane_barrier
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.38s


--- TEST CODE ---
def test_aetherstorm_wellingtons_arcane_barrier():
    # Test the Arcane Barrier 2 effect on equipping the card
    st = _make_state(); st.card_db = DB
    card = _card("aetherstorm_wellingtons")
    st.players[1].head.add(card)
    dispatch(st, "ON_EQUIP", "aetherstorm_wellingtons", card=card, event=None)
    assert st.players[1].arcane_barrier == 2
```

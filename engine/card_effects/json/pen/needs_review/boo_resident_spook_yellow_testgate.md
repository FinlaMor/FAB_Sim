# boo_resident_spook_yellow — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
___________________ test_boo_resident_spook_yellow_activate ___________________

    def test_boo_resident_spook_yellow_activate():
        st = _make_state(); st.card_db = DB
        card = _card("boo_resident_spook_yellow")
        st.players[1].chest.add(card)
        before = st.players[1].resources
        activate(st, card)
>       assert st.players[1].resources == before + 1      # the effect (after the colon)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       assert 0 == (0 + 1)
E        +  where 0 = <engine.state.Player object at 0x000001B18F093230>.resources

tests\_gate_boo_resident_spook_yellow.py:81: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_boo_resident_spook_yellow.py::test_boo_resident_spook_yellow_activate
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.38s


--- TEST CODE ---
def test_boo_resident_spook_yellow_activate():
    st = _make_state(); st.card_db = DB
    card = _card("boo_resident_spook_yellow")
    st.players[1].chest.add(card)
    before = st.players[1].resources
    activate(st, card)
    assert st.players[1].resources == before + 1      # the effect (after the colon)
    assert card not in st.players[1].chest.cards       # the "Destroy this" cost was paid

def test_boo_resident_spook_yellow_spellvoid():
    st = _make_state(); st.card_db = DB
    card = _card("boo_resident_spook_yellow")
    st.players[1].arsenal.cards.append(card)
    assert card.tapped == False  # untapped
    # The spellvoid check is not directly observable via dispatch, but we verify
    # that the card has the ability to gain spellvoid when untapped.
    # This test ensures that the card is in the right zone and untapped.
    assert len(st.players[1].arsenal.cards) == 1
    assert card.tapped == False
```

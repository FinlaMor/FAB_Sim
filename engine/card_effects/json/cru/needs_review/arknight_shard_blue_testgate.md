# arknight_shard_blue — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
______________________ test_arknight_shard_blue_on_pitch ______________________

    def test_arknight_shard_blue_on_pitch():
        st = _make_state(); st.card_db = DB
        card = _card("arknight_shard_blue")
        st.players[1].arsenal.cards.append(card)
        dispatch(st, "ON_PITCH", "arknight_shard_blue", card=card, event=None)
>       assert any(c.slug == "runechant" for c in st.players[1].permanents.cards)
E       assert False
E        +  where False = any(<generator object test_arknight_shard_blue_on_pitch.<locals>.<genexpr> at 0x00000298A92CF780>)

tests\_gate_arknight_shard_blue.py:110: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_arknight_shard_blue.py::test_arknight_shard_blue_on_pitch
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.56s


--- TEST CODE ---
def test_arknight_shard_blue_on_pitch():
    st = _make_state(); st.card_db = DB
    card = _card("arknight_shard_blue")
    st.players[1].arsenal.cards.append(card)
    dispatch(st, "ON_PITCH", "arknight_shard_blue", card=card, event=None)
    assert any(c.slug == "runechant" for c in st.players[1].permanents.cards)

def test_arknight_shard_blue_on_pitch_not_from_arsenal():
    st = _make_state(); st.card_db = DB
    card = _card("arknight_shard_blue")
    st.players[1].hand.cards.append(card)
    dispatch(st, "ON_PITCH", "arknight_shard_blue", card=card, event=None)
    # Should not create a token if not pitched from arsenal
    assert not any(c.slug == "runechant" for c in st.players[1].permanents.cards)
```

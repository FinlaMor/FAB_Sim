# bubba_lubba_run_aground_yellow — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
________ test_bubba_lubba_run_aground_yellow_enters_with_power_counter ________

    def test_bubba_lubba_run_aground_yellow_enters_with_power_counter():
        st = _make_state(); st.card_db = DB
        card = _card("bubba_lubba_run_aground_yellow")
        st.players[1].arsenal.cards.append(card)
        dispatch(st, "ON_ENTER_PLAY", "bubba_lubba_run_aground_yellow", card=card, event=None)
>       assert any(c.has_counter("POWER") and c.counters["POWER"] == 1 for c in st.players[1].permanents.cards if c.slug == "bubba_lubba_run_aground_yellow")
E       assert False
E        +  where False = any(<generator object test_bubba_lubba_run_aground_yellow_enters_with_power_counter.<locals>.<genexpr> at 0x000002DEE925AEA0>)

tests\_gate_bubba_lubba_run_aground_yellow.py:80: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_bubba_lubba_run_aground_yellow.py::test_bubba_lubba_run_aground_yellow_enters_with_power_counter
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.37s


--- TEST CODE ---
def test_bubba_lubba_run_aground_yellow_enters_with_power_counter():
    st = _make_state(); st.card_db = DB
    card = _card("bubba_lubba_run_aground_yellow")
    st.players[1].arsenal.cards.append(card)
    dispatch(st, "ON_ENTER_PLAY", "bubba_lubba_run_aground_yellow", card=card, event=None)
    assert any(c.has_counter("POWER") and c.counters["POWER"] == 1 for c in st.players[1].permanents.cards if c.slug == "bubba_lubba_run_aground_yellow")


def test_bubba_lubba_run_aground_yellow_destroy_aura_token_with_power_counter():
    st = _make_state(); st.card_db = DB
    card = _card("bubba_lubba_run_aground_yellow")
    st.players[1].arsenal.cards.append(card)
    dispatch(st, "ON_ENTER_PLAY", "bubba_lubba_run_aground_yellow", card=card, event=None)
    give_token(st, 1, "aura")
    before = len(st.players[1].permanents.cards)
    activate(st, card)
    assert len(st.players[1].permanents.cards) == before - 1
```

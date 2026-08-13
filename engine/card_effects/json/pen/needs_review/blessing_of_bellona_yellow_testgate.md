# blessing_of_bellona_yellow — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
_______________ test_blessing_of_bellona_yellow_on_gold_created _______________

    def test_blessing_of_bellona_yellow_on_gold_created():
        # Test that when a card is put into soul, a Courage token is created
        st = _make_state(); st.card_db = DB
        card = _card("blessing_of_bellona_yellow")
        st.players[1].permanents.cards.append(card)
    
        # Simulate putting a card into soul (triggers ON_GOLD_CREATED)
        dispatch(st, "ON_GOLD_CREATED", "blessing_of_bellona_yellow", card=card, event=None)
    
        # Verify a Courage token was created
>       assert any(c.slug == "courage" for c in st.players[1].permanents.cards)
E       assert False
E        +  where False = any(<generator object test_blessing_of_bellona_yellow_on_gold_created.<locals>.<genexpr> at 0x000001D1B78920C0>)

tests\_gate_blessing_of_bellona_yellow.py:85: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_blessing_of_bellona_yellow.py::test_blessing_of_bellona_yellow_on_gold_created
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.36s


--- TEST CODE ---
def test_blessing_of_bellona_yellow_on_gold_created():
    # Test that when a card is put into soul, a Courage token is created
    st = _make_state(); st.card_db = DB
    card = _card("blessing_of_bellona_yellow")
    st.players[1].permanents.cards.append(card)
    
    # Simulate putting a card into soul (triggers ON_GOLD_CREATED)
    dispatch(st, "ON_GOLD_CREATED", "blessing_of_bellona_yellow", card=card, event=None)
    
    # Verify a Courage token was created
    assert any(c.slug == "courage" for c in st.players[1].permanents.cards)


def test_blessing_of_bellona_yellow_start_of_turn():
    # Test that at start of turn, the aura is put into soul (bannedh)
    st = _make_state(); st.card_db = DB
    card = _card("blessing_of_bellona_yellow")
    st.players[1].permanents.cards.append(card)
    
    # Capture before state
    before_count = len(st.players[1].permanents.cards)
    
    # Trigger start of turn
    dispatch(st, "START_OF_TURN", "blessing_of_bellona_yellow", card=card, event=None)
    
    # Verify the card was removed from permanents (banned)
    assert len(st.players[1].permanents.cards) == before_count - 1
    assert card not in st.players[1].permanents.cards
```

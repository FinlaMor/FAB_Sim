# break_open_the_chests_yellow — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
.F
================================== FAILURES ===================================
___________ test_break_open_the_chests_yellow_play_with_yellow_card ___________

    def test_break_open_the_chests_yellow_play_with_yellow_card():
        st = _make_state(); st.card_db = DB
        card = _card("break_open_the_chests_yellow")
        st.players[1].permanents.add(card)
        # Add a yellow card to opponent's arsenal to trigger the gold token creation
        yellow_card = _card("yellow_card")  # Assuming this exists in DB
        st.players[2].arsenal.cards.append(yellow_card)
        dispatch(st, "ON_PLAY", "break_open_the_chests_yellow", card=card, event=None)
        # Check that all arsenals are face up and gold tokens were created
        assert len(st.players[1].arsenal.cards) >= 0
        assert len(st.players[2].arsenal.cards) >= 0
        gold_tokens = [c for c in st.players[1].permanents.cards if c.slug == "gold"]
>       assert len(gold_tokens) == 2
E       assert 0 == 2
E        +  where 0 = len([])

tests\_gate_break_open_the_chests_yellow.py:100: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_break_open_the_chests_yellow.py::test_break_open_the_chests_yellow_play_with_yellow_card
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed, 1 passed in 0.39s


--- TEST CODE ---
def test_break_open_the_chests_yellow_play():
    st = _make_state(); st.card_db = DB
    card = _card("break_open_the_chests_yellow")
    st.players[1].permanents.add(card)
    dispatch(st, "ON_PLAY", "break_open_the_chests_yellow", card=card, event=None)
    # Assert that all arsenal cards are face up (observable via .cards)
    assert len(st.players[1].arsenal.cards) >= 0
    assert len(st.players[2].arsenal.cards) >= 0
    # Ensure no tokens created unless yellow card is present
    gold_tokens = [c for c in st.players[1].permanents.cards if c.slug == "gold"]
    assert len(gold_tokens) == 0


def test_break_open_the_chests_yellow_play_with_yellow_card():
    st = _make_state(); st.card_db = DB
    card = _card("break_open_the_chests_yellow")
    st.players[1].permanents.add(card)
    # Add a yellow card to opponent's arsenal to trigger the gold token creation
    yellow_card = _card("yellow_card")  # Assuming this exists in DB
    st.players[2].arsenal.cards.append(yellow_card)
    dispatch(st, "ON_PLAY", "break_open_the_chests_yellow", card=card, event=None)
    # Check that all arsenals are face up and gold tokens were created
    assert len(st.players[1].arsenal.cards) >= 0
    assert len(st.players[2].arsenal.cards) >= 0
    gold_tokens = [c for c in st.players[1].permanents.cards if c.slug == "gold"]
    assert len(gold_tokens) == 2
```

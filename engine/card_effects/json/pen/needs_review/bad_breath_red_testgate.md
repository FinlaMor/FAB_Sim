# bad_breath_red — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
__________________________ test_bad_breath_red_play ___________________________

    def test_bad_breath_red_play():
        # A play ability fires on ON_PLAY; assert the observable result (intimidate target hero)
        st = _make_state(); st.card_db = DB
        card = _card("bad_breath_red")
        st.players[1].arsenal.cards.append(card)
        n0 = len(st.players[2].permanents.cards)  # opponent's hero
        dispatch(st, "ON_PLAY", "bad_breath_red", card=card, event=None)
>       assert len(st.players[2].permanents.cards) == n0 + 1  # intimidated hero should be in the opponent's arsenal
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AssertionError: assert 0 == (0 + 1)
E        +  where 0 = len([])
E        +    where [] = Zone('permanents', []).cards
E        +      where Zone('permanents', []) = <engine.state.Player object at 0x00000167D78A0050>.permanents

tests\_gate_bad_breath_red.py:82: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_bad_breath_red.py::test_bad_breath_red_play - AssertionErr...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.37s


--- TEST CODE ---
def test_bad_breath_red_play():
    # A play ability fires on ON_PLAY; assert the observable result (intimidate target hero)
    st = _make_state(); st.card_db = DB
    card = _card("bad_breath_red")
    st.players[1].arsenal.cards.append(card)
    n0 = len(st.players[2].permanents.cards)  # opponent's hero
    dispatch(st, "ON_PLAY", "bad_breath_red", card=card, event=None)
    assert len(st.players[2].permanents.cards) == n0 + 1  # intimidated hero should be in the opponent's arsenal

def test_bad_breath_red_next_attack():
    # When an attack controlled by the player hits this turn, create 3 Might tokens
    st = _make_state(); st.card_db = DB
    card = _card("bad_breath_red")
    st.players[1].arsenal.cards.append(card)
    dispatch(st, "ON_PLAY", "bad_breath_red", card=card, event=None)

    # Set up an attack and hit
    attack(st, card)
    hit(st)

    # Assert that 3 Might tokens have been created
    assert sum(1 for c in st.players[1].permanents.cards if c.slug == "might") == 3
```

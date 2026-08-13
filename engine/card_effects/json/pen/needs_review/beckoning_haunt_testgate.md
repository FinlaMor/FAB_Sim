# beckoning_haunt — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
________________________ test_beckoning_haunt_activate ________________________

    def test_beckoning_haunt_activate():
        st = _make_state(); st.card_db = DB
        card = _card("beckoning_haunt")
        aura_card = _card("guardwell")
        st.players[1].arms.cards.append(card)
        st.players[1].graveyard.cards.append(aura_card)
    
        # Capture the state before activation
        before_hand_size = len(st.players[1].hand.cards)
        before_graveyard_size = len(st.players[1].graveyard.cards)
    
        # Activate the card
        activate(st, card)
    
        # Assert the observable outcomes
>       assert len(st.players[1].hand.cards) == before_hand_size + 1
E       AssertionError: assert 0 == (0 + 1)
E        +  where 0 = len([])
E        +    where [] = Zone('hand', []).cards
E        +      where Zone('hand', []) = <engine.state.Player object at 0x000001A65348FE00>.hand

tests\_gate_beckoning_haunt.py:90: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_beckoning_haunt.py::test_beckoning_haunt_activate - Assert...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.46s


--- TEST CODE ---
def test_beckoning_haunt_activate():
    st = _make_state(); st.card_db = DB
    card = _card("beckoning_haunt")
    aura_card = _card("guardwell")
    st.players[1].arms.cards.append(card)
    st.players[1].graveyard.cards.append(aura_card)
    
    # Capture the state before activation
    before_hand_size = len(st.players[1].hand.cards)
    before_graveyard_size = len(st.players[1].graveyard.cards)
    
    # Activate the card
    activate(st, card)
    
    # Assert the observable outcomes
    assert len(st.players[1].hand.cards) == before_hand_size + 1
    assert aura_card not in st.players[1].graveyard.cards
    assert card not in st.players[1].arms.cards
```

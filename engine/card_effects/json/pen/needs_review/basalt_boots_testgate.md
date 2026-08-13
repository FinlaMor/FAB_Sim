# basalt_boots — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
_________________ test_basalt_boots_with_seismic_surge_token __________________

    def test_basalt_boots_with_seismic_surge_token():
        st = _make_state()
        st.card_db = DB
        card = _card("basalt_boots")
        st.players[1].legs.add(card)
        give_token(st, 1, "seismic_surge")
    
        # Capture the initial defense value
>       initial_defense = st.players[1].legs.cards[0].defense_value
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: 'Card' object has no attribute 'defense_value'

tests\_gate_basalt_boots.py:83: AttributeError
=========================== short test summary info ===========================
FAILED tests/_gate_basalt_boots.py::test_basalt_boots_with_seismic_surge_token
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.37s


--- TEST CODE ---
def test_basalt_boots_with_seismic_surge_token():
    st = _make_state()
    st.card_db = DB
    card = _card("basalt_boots")
    st.players[1].legs.add(card)
    give_token(st, 1, "seismic_surge")
    
    # Capture the initial defense value
    initial_defense = st.players[1].legs.cards[0].defense_value
    
    # Dispatch the event that triggers the ability
    dispatch(st, "STATIC", "basalt_boots", card=card, event=None)
    
    # Assert the defense value has increased by 1
    assert st.players[1].legs.cards[0].defense_value == initial_defense + 1

def test_basalt_boots_without_seismic_surge_token():
    st = _make_state()
    st.card_db = DB
    card = _card("basalt_boots")
    st.players[1].legs.add(card)
    
    # Capture the initial defense value
    initial_defense = st.players[1].legs.cards[0].defense_value
    
    # Dispatch the event that triggers the ability
    dispatch(st, "STATIC", "basalt_boots", card=card, event=None)
    
    # Assert the defense value has not changed
    assert st.players[1].legs.cards[0].defense_value == initial_defense
```

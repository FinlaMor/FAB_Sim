# aetherize_blue — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
__________________________ test_aetherize_blue_play ___________________________

    def test_aetherize_blue_play():
        # Test that Aetherize negates an instant card with cost 1 or less
        st = _make_state(); st.card_db = DB
        card = _card("aetherize_blue")
        st.players[1].arsenal.cards.append(card)
    
        # Put a target instant card in the opponent's hand
        target_card = _card("lightning_strike", cost=1)
        st.players[2].hand.cards.append(target_card)
    
        # Play Aetherize from arsenal
        dispatch(st, "ON_PLAY", "aetherize_blue", card=card, event=None)
    
        # The target instant should be banished
>       assert target_card not in st.players[2].hand.cards
E       AssertionError: assert Card(slug='lightning_strike', raw_name=None, raw_pitch=None, raw_cost=None, raw_power=None, raw_defense=None, raw_life...arget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None) not in [Card(slug='lightning_strike', raw_name=None, raw_pitch=None, raw_cost=None, raw_power=None, raw_defense=None, raw_lif...rget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)]
E        +  where [Card(slug='lightning_strike', raw_name=None, raw_pitch=None, raw_cost=None, raw_power=None, raw_defense=None, raw_lif...rget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)] = Zone('hand', ['lightning_strike']).cards
E        +    where Zone('hand', ['lightning_strike']) = <engine.state.Player object at 0x0000027CD58E0050>.hand

tests\_gate_aetherize_blue.py:119: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_aetherize_blue.py::test_aetherize_blue_play - AssertionErr...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.60s


--- TEST CODE ---
def test_aetherize_blue_play():
    # Test that Aetherize negates an instant card with cost 1 or less
    st = _make_state(); st.card_db = DB
    card = _card("aetherize_blue")
    st.players[1].arsenal.cards.append(card)
    
    # Put a target instant card in the opponent's hand
    target_card = _card("lightning_strike", cost=1)
    st.players[2].hand.cards.append(target_card)
    
    # Play Aetherize from arsenal
    dispatch(st, "ON_PLAY", "aetherize_blue", card=card, event=None)
    
    # The target instant should be banished
    assert target_card not in st.players[2].hand.cards
    assert target_card in st.banished.cards


def test_aetherize_blue_play_cost_limit():
    # Test that Aetherize does NOT negate an instant card with cost > 1
    st = _make_state(); st.card_db = DB
    card = _card("aetherize_blue")
    st.players[1].arsenal.cards.append(card)
    
    # Put a target instant card in the opponent's hand with cost 2
    target_card = _card("lightning_strike", cost=2)
    st.players[2].hand.cards.append(target_card)
    
    # Play Aetherize from arsenal
    dispatch(st, "ON_PLAY", "aetherize_blue", card=card, event=None)
    
    # The target instant should NOT be banished (cost limit is 1)
    assert target_card in st.players[2].hand.cards
    assert target_card not in st.banished.cards
```

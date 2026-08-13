# blunten_yellow — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
________________ test_blunten_yellow_on_defend_weapon_discards ________________

    def test_blunten_yellow_on_defend_weapon_discards():
        st = _make_state(); st.card_db = DB
        card = _card("blunten_yellow")
        st.players[1].arsenal.cards.append(card)
        # Set up opponent with a weapon to attack
        opp_weapon = _card("lightning_strike")  # A weapon that can be used
        st.players[2].weapon1.cards.append(opp_weapon)
    
        # Setup deck for discard
        stock_deck(st, 2, n=5)
        before = len(st.players[2].deck.cards)
    
        # Simulate a defense of a weapon attack
        attack(st, opp_weapon)
        hit(st)
        dispatch(st, "ON_DEFEND", "blunten_yellow", card=card, event=None)
    
>       assert len(st.players[2].deck.cards) == before - 1
E       AssertionError: assert 25 == (25 - 1)
E        +  where 25 = len([Card(slug='dummy_card', raw_name=None, raw_pitch=None, raw_cost=None, raw_power=None, raw_defense=None, raw_life=None...attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None), ...])
E        +    where [Card(slug='dummy_card', raw_name=None, raw_pitch=None, raw_cost=None, raw_power=None, raw_defense=None, raw_life=None...attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None), ...] = Zone('deck', ['dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy...card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card']).cards
E        +      where Zone('deck', ['dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy...card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card', 'dummy_card']) = <engine.state.Player object at 0x0000025198C28050>.deck

tests\_gate_blunten_yellow.py:92: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_blunten_yellow.py::test_blunten_yellow_on_defend_weapon_discards
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.44s


--- TEST CODE ---
def test_blunten_yellow_on_defend_weapon_discards():
    st = _make_state(); st.card_db = DB
    card = _card("blunten_yellow")
    st.players[1].arsenal.cards.append(card)
    # Set up opponent with a weapon to attack
    opp_weapon = _card("lightning_strike")  # A weapon that can be used
    st.players[2].weapon1.cards.append(opp_weapon)
    
    # Setup deck for discard
    stock_deck(st, 2, n=5)
    before = len(st.players[2].deck.cards)

    # Simulate a defense of a weapon attack
    attack(st, opp_weapon)
    hit(st)
    dispatch(st, "ON_DEFEND", "blunten_yellow", card=card, event=None)

    assert len(st.players[2].deck.cards) == before - 1

def test_blunten_yellow_on_defend_nonweapon_no_discard():
    st = _make_state(); st.card_db = DB
    card = _card("blunten_yellow")
    st.players[1].arsenal.cards.append(card)
    
    # Set up opponent with a non-weapon attack (e.g. direct hit or aura)
    # We simulate this by manually triggering ON_DEFEND without weapon context
    stock_deck(st, 2, n=5)
    before = len(st.players[2].deck.cards)

    # Try to trigger ON_DEFEND even though it's not a weapon
    dispatch(st, "ON_DEFEND", "blunten_yellow", card=card, event=None)

    assert len(st.players[2].deck.cards) == before
```

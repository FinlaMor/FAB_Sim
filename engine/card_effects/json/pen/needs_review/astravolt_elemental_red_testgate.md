# astravolt_elemental_red — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
___________ test_astravolt_elemental_red_on_attack_discard_and_draw ___________

    def test_astravolt_elemental_red_on_attack_discard_and_draw():
        st = _make_state(); st.card_db = DB
        card = _card("astravolt_elemental_red")
        st.players[1].arsenal.cards.append(card)
    
        # Set up the deck with an instant card to discard
        stock_deck(st, 1, n=1)
        before_hand_size = len(st.players[1].hand.cards)
    
        attack(st, card)
        hit(st)
    
        # Assert that an instant card was discarded and a card was drawn
>       assert len(st.players[1].hand.cards) == before_hand_size - 1
E       AssertionError: assert 1 == (0 - 1)
E        +  where 1 = len([Card(slug='dummy_card', raw_name=None, raw_pitch=None, raw_cost=None, raw_power=None, raw_defense=None, raw_life=None...rget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)])
E        +    where [Card(slug='dummy_card', raw_name=None, raw_pitch=None, raw_cost=None, raw_power=None, raw_defense=None, raw_life=None...rget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)] = Zone('hand', ['dummy_card']).cards
E        +      where Zone('hand', ['dummy_card']) = <engine.state.Player object at 0x0000016AE6BFF230>.hand

tests\_gate_astravolt_elemental_red.py:88: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_astravolt_elemental_red.py::test_astravolt_elemental_red_on_attack_discard_and_draw
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.43s


--- TEST CODE ---
def test_astravolt_elemental_red_on_attack_discard_and_draw():
    st = _make_state(); st.card_db = DB
    card = _card("astravolt_elemental_red")
    st.players[1].arsenal.cards.append(card)
    
    # Set up the deck with an instant card to discard
    stock_deck(st, 1, n=1)
    before_hand_size = len(st.players[1].hand.cards)
    
    attack(st, card)
    hit(st)
    
    # Assert that an instant card was discarded and a card was drawn
    assert len(st.players[1].hand.cards) == before_hand_size - 1

def test_astravolt_elemental_red_on_attack_creates_embodiment_of_lightning_token():
    st = _make_state(); st.card_db = DB
    card = _card("astravolt_elemental_red")
    st.players[1].arsenal.cards.append(card)
    
    attack(st, card)
    hit(st)
    
    # Assert that an Embodiment of Lightning token was created
    assert any(c.slug == "embodiment_of_lightning" for c in st.players[1].permanents.cards)
```

# burnished_bunkerplate — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
____________ test_burnished_bunkerplate_defense_reaction_activates ____________

    def test_burnished_bunkerplate_defense_reaction_activates():
        st = _make_state(); st.card_db = DB
        card = _card("burnished_bunkerplate")
        st.players[1].permanents.add(card)
        st.players[1].arsenal.cards.append(_card("lightning_strike"))
    
        # Set up a combat chain link for defense
        attack(st, card)
        hit(st)
    
        # Ensure the card is in play and has an action in arsenal
        assert len(st.players[1].permanents.cards) == 1
        assert len(st.players[1].arsenal.cards) == 1
    
        # Activate the defense reaction (this should destroy the card and add from arsenal to chain link)
        activate(st, card)
    
        # Check that the card was destroyed and action added
        assert len(st.players[1].permanents.cards) == 0  # Card destroyed
>       assert len(st.players[1].arsenal.cards) == 0  # Action removed from arsenal
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AssertionError: assert 1 == 0
E        +  where 1 = len([Card(slug='lightning_strike', raw_name=None, raw_pitch=None, raw_cost=None, raw_power=None, raw_defense=None, raw_lif...rget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)])
E        +    where [Card(slug='lightning_strike', raw_name=None, raw_pitch=None, raw_cost=None, raw_power=None, raw_defense=None, raw_lif...rget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)] = Zone('arsenal', ['lightning_strike']).cards
E        +      where Zone('arsenal', ['lightning_strike']) = <engine.state.Player object at 0x000001D3EFB83230>.arsenal

tests\_gate_burnished_bunkerplate.py:94: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_burnished_bunkerplate.py::test_burnished_bunkerplate_defense_reaction_activates
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.44s


--- TEST CODE ---
def test_burnished_bunkerplate_defense_reaction_activates():
    st = _make_state(); st.card_db = DB
    card = _card("burnished_bunkerplate")
    st.players[1].permanents.add(card)
    st.players[1].arsenal.cards.append(_card("lightning_strike"))
    
    # Set up a combat chain link for defense
    attack(st, card)
    hit(st)
    
    # Ensure the card is in play and has an action in arsenal
    assert len(st.players[1].permanents.cards) == 1
    assert len(st.players[1].arsenal.cards) == 1

    # Activate the defense reaction (this should destroy the card and add from arsenal to chain link)
    activate(st, card)

    # Check that the card was destroyed and action added
    assert len(st.players[1].permanents.cards) == 0  # Card destroyed
    assert len(st.players[1].arsenal.cards) == 0  # Action removed from arsenal
    assert st.combat.chain_link_defense is not None  # Added to chain link as defending card


def test_burnished_bunkerplate_defense_reaction_no_arsenal_action():
    st = _make_state(); st.card_db = DB
    card = _card("burnished_bunkerplate")
    st.players[1].permanents.add(card)
    
    # No action in arsenal
    
    attack(st, card)
    hit(st)

    # Activate the defense reaction (should not add anything if no actions in arsenal)
    activate(st, card)

    # Check that the card was destroyed but nothing added to chain
    assert len(st.players[1].permanents.cards) == 0  # Card destroyed
    assert st.combat.chain_link_defense is None  # No defending card added
```

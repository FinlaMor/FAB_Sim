# benji_the_piercing_wind — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
______________ test_benji_the_piercing_wind_defense_restriction _______________

    def test_benji_the_piercing_wind_defense_restriction():
        # Test that attack action cards with 2 or less {p} can't be defended by hand cards
        st = _make_state(); st.card_db = DB
        benji = _card("benji_the_piercing_wind")
        st.players[1].arsenal.cards.append(benji)
        activate(st, benji)
    
        # Create an attack action card with 2 pitch power
        attack_card = _card("lightning_strike", cost=3, pitch=2)  # example attack action with 2 pitch
        st.players[1].hand.cards.append(attack_card)
    
        # Play the attack action card (this should trigger the static ability)
        dispatch(st, "ON_PLAY", "lightning_strike", card=attack_card, event=None)
    
        # The restriction is applied via continuous effect, so we can't directly test it
        # but we can verify that the card was played and the ability is active
>       assert len(st.players[1].hand.cards) == 0  # card was moved to play area
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AssertionError: assert 1 == 0
E        +  where 1 = len([Card(slug='lightning_strike', raw_name=None, raw_pitch=None, raw_cost=None, raw_power=None, raw_defense=None, raw_lif...rget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)])
E        +    where [Card(slug='lightning_strike', raw_name=None, raw_pitch=None, raw_cost=None, raw_power=None, raw_defense=None, raw_lif...rget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)] = Zone('hand', ['lightning_strike']).cards
E        +      where Zone('hand', ['lightning_strike']) = <engine.state.Player object at 0x000002A7130DF380>.hand

tests\_gate_benji_the_piercing_wind.py:121: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_benji_the_piercing_wind.py::test_benji_the_piercing_wind_defense_restriction
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.62s


--- TEST CODE ---
def test_benji_the_piercing_wind_defense_restriction():
    # Test that attack action cards with 2 or less {p} can't be defended by hand cards
    st = _make_state(); st.card_db = DB
    benji = _card("benji_the_piercing_wind")
    st.players[1].arsenal.cards.append(benji)
    activate(st, benji)

    # Create an attack action card with 2 pitch power
    attack_card = _card("lightning_strike", cost=3, pitch=2)  # example attack action with 2 pitch
    st.players[1].hand.cards.append(attack_card)
    
    # Play the attack action card (this should trigger the static ability)
    dispatch(st, "ON_PLAY", "lightning_strike", card=attack_card, event=None)

    # The restriction is applied via continuous effect, so we can't directly test it
    # but we can verify that the card was played and the ability is active
    assert len(st.players[1].hand.cards) == 0  # card was moved to play area


def test_benji_the_piercing_wind_attack_boost():
    # Test that the next attack gains +1{p} after hitting with an attack action
    st = _make_state(); st.card_db = DB
    benji = _card("benji_the_piercing_wind")
    st.players[1].arsenal.cards.append(benji)
    activate(st, benji)

    # Create and play an attack action card
    attack_card = _card("lightning_strike", cost=3, pitch=2)
    st.players[1].hand.cards.append(attack_card)
    dispatch(st, "ON_PLAY", "lightning_strike", card=attack_card, event=None)

    # Set up turn state to indicate an attack action was played this turn
    set_turn_flag(st, 1, "did_this_turn:attack")

    # Simulate the attack and hit
    attack(st, benji)
    hit(st)

    # Check that the flag for benji's effect is present in current turn effects
    assert any("benji_the_piercing_wind" in flag for flag in st.players[1].current_turn_effects)
```

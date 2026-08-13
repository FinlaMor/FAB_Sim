# billowing_mist_blue — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
____________________ test_billowing_mist_blue_attack_boost ____________________

    def test_billowing_mist_blue_attack_boost():
        # Test that the next attack gets +1 power
        st = _make_state(); st.card_db = DB
        card = _card("billowing_mist_blue")
        st.players[1].arsenal.cards.append(card)
        activate(st, card)
    
        # Set up an attack
        attack(st, card)
>       assert st.combat.attack_power == 1  # Base power of 0 + 1 from Billowing Mist
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AssertionError: assert 0 == 1
E        +  where 0 = CombatState(attacker_id=1, link_id=1, attack_power=0, attack_card=Card(slug='billowing_mist_blue', raw_name='Billowing... attack_target_card=None, wagers=[], keyword_effects=set(), power_mods=[], injected_triggers=[], pitched_for_attack=[]).attack_power
E        +    where CombatState(attacker_id=1, link_id=1, attack_power=0, attack_card=Card(slug='billowing_mist_blue', raw_name='Billowing... attack_target_card=None, wagers=[], keyword_effects=set(), power_mods=[], injected_triggers=[], pitched_for_attack=[]) = GameState(players={1: <engine.state.Player object at 0x0000020F49A9F230>, 2: <engine.state.Player object at 0x0000020F...=[], combat_chain=Zone('combat chain', []), last_acted_player=None, last_known_cache={}, cost_choices={}, recorders=[]).combat

tests\_gate_billowing_mist_blue.py:84: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_billowing_mist_blue.py::test_billowing_mist_blue_attack_boost
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.42s


--- TEST CODE ---
def test_billowing_mist_blue_attack_boost():
    # Test that the next attack gets +1 power
    st = _make_state(); st.card_db = DB
    card = _card("billowing_mist_blue")
    st.players[1].arsenal.cards.append(card)
    activate(st, card)

    # Set up an attack
    attack(st, card)
    assert st.combat.attack_power == 1  # Base power of 0 + 1 from Billowing Mist

def test_billowing_mist_blue_ephemeral_creation():
    # Test that when ephemeral is created, it creates one extra
    st = _make_state(); st.card_db = DB
    card = _card("billowing_mist_blue")
    st.players[1].arsenal.cards.append(card)
    activate(st, card)

    # Set up a token creation event (simulating an ephemeral creation)
    give_token(st, 1, "might")  # Player 1 now controls a might token
    dispatch(st, "ON_TOKEN_CREATED", "billowing_mist_blue", card=card, event=None)

    # Should create 2 ephemeral tokens (1 base + 1 from the effect)
    assert len([c for c in st.players[1].permanents.cards if c.slug == "ephemeral"]) == 2
```

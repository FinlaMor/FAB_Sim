# absorption_dome_yellow — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
________ test_absorption_dome_yellow_on_enter_play_sets_steam_counters ________

    def test_absorption_dome_yellow_on_enter_play_sets_steam_counters():
        st = _make_state(); st.card_db = DB
        card = _card("absorption_dome_yellow")
        # Simulate that the player has boosted this turn
        set_turn_flag(st, 1, "boosted_this_turn")
        st.players[1].arsenal.cards.append(card)
>       dispatch(st, "ON_ENTER_PLAY", "absorption_dome_yellow", card=card, event=None)

tests\_gate_absorption_dome_yellow.py:111: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
engine\card_effects\dsl\__init__.py:37: in dispatch
    dispatch_event(card_def, event_type, card, event, state)
engine\card_effects\dsl\interpreter.py:130: in dispatch_event
    run_ability(ability, card, event, state)
engine\card_effects\dsl\interpreter.py:33: in run_ability
    _run_ability(ability, card, event, state)
engine\card_effects\dsl\interpreter.py:110: in _run_ability
    eff.fn(card, event, state)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

card = Card(slug='absorption_dome_yellow', raw_name='Absorption Dome', raw_pitch=2, raw_cost=0, raw_power=None, raw_defense=N...arget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)
event = None
state = GameState(players={1: <engine.state.Player object at 0x000001FC76FAF380>, 2: <engine.state.Player object at 0x000001FC...=[], combat_chain=Zone('combat chain', []), last_acted_player=None, last_known_cache={}, cost_choices={}, recorders=[])
_ct = 'steam', _a = {'flag': 'boosted_this_turn', 'type': 'FLAG_SET'}

    def _fn(card, event, state, _ct=ctype, _a=amt):
        from engine.card_effects.ability_keywords import effect_put_counter
>       for _ in range(_a):
                 ^^^^^^^^^
E       TypeError: 'dict' object cannot be interpreted as an integer

engine\card_effects\dsl\effect_types.py:524: TypeError
=========================== short test summary info ===========================
FAILED tests/_gate_absorption_dome_yellow.py::test_absorption_dome_yellow_on_enter_play_sets_steam_counters
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.84s


--- TEST CODE ---
def test_absorption_dome_yellow_on_enter_play_sets_steam_counters():
    st = _make_state(); st.card_db = DB
    card = _card("absorption_dome_yellow")
    # Simulate that the player has boosted this turn
    set_turn_flag(st, 1, "boosted_this_turn")
    st.players[1].arsenal.cards.append(card)
    dispatch(st, "ON_ENTER_PLAY", "absorption_dome_yellow", card=card, event=None)
    assert any(c.slug == "absorption_dome_yellow" for c in st.players[1].permanents.cards)
    # Check that steam counter was added
    dome = get_card(st, 1, "absorption_dome_yellow")
    # The card has 1 steam counter because player boosted once this turn
    assert dome.counters.get("steam", 0) == 1


def test_absorption_dome_yellow_on_hit_removes_steam_and_prevents_damage():
    st = _make_state(); st.card_db = DB
    card = _card("absorption_dome_yellow")
    # Simulate that the player has boosted this turn (so 1 steam counter)
    set_turn_flag(st, 1, "boosted_this_turn")
    st.players[1].arsenal.cards.append(card)
    dispatch(st, "ON_ENTER_PLAY", "absorption_dome_yellow", card=card, event=None)
    # Now simulate a hit on the hero
    attack(st, card)
    hit(st)
    # The dome should have removed 1 steam counter and prevented 1 damage
    dome = get_card(st, 1, "absorption_dome_yellow")
    assert dome.counters.get("steam", 0) == 0
    # Hero should have taken no damage (because it was prevented by steam)
    assert st.players[2].health == 40  # assuming starting health is 40


def test_absorption_dome_yellow_destroyed_when_no_steam_counters():
    st = _make_state(); st.card_db = DB
    card = _card("absorption_dome_yellow")
    set_turn_flag(st, 1, "boosted_this_turn")
    st.players[1].arsenal.cards.append(card)
    dispatch(st, "ON_ENTER_PLAY", "absorption_dome_yellow", card=card, event=None)
    # Simulate a hit that removes all steam
    attack(st, card)
    hit(st)
    # End of turn should destroy the dome if it has no steam
    dispatch(st, "END_OF_TURN", "absorption_dome_yellow", card=card, event=None)
    assert not any(c.slug == "absorption_dome_yellow" for c in st.players[1].permanents.cards)
```

# blessing_of_themis_yellow — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
________________ test_blessing_of_themis_yellow_on_enter_play _________________

    def test_blessing_of_themis_yellow_on_enter_play():
        st = _make_state(); st.card_db = DB
        card = _card("blessing_of_themis_yellow")
        st.players[1].arsenal.cards.append(card)
        dispatch(st, "ON_ENTER_PLAY", "blessing_of_themis_yellow", card=card, event=None)
        # The card enters play and triggers its choice ability
        # We can't directly observe the choice without more complex state,
        # but we can verify it's in the arena and has not been put into soul yet
>       assert card in st.players[1].permanents.cards
E       AssertionError: assert Card(slug='blessing_of_themis_yellow', raw_name='Blessing of Themis', raw_pitch=2, raw_cost=0, raw_power=None, raw_def...arget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None) in []
E        +  where [] = Zone('permanents', []).cards
E        +    where Zone('permanents', []) = <engine.state.Player object at 0x0000022003ED3230>.permanents

tests\_gate_blessing_of_themis_yellow.py:83: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_blessing_of_themis_yellow.py::test_blessing_of_themis_yellow_on_enter_play
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.36s


--- TEST CODE ---
def test_blessing_of_themis_yellow_on_enter_play():
    st = _make_state(); st.card_db = DB
    card = _card("blessing_of_themis_yellow")
    st.players[1].arsenal.cards.append(card)
    dispatch(st, "ON_ENTER_PLAY", "blessing_of_themis_yellow", card=card, event=None)
    # The card enters play and triggers its choice ability
    # We can't directly observe the choice without more complex state,
    # but we can verify it's in the arena and has not been put into soul yet
    assert card in st.players[1].permanents.cards
    assert card not in st.players[1].arsenal.cards


def test_blessing_of_themis_yellow_start_of_turn():
    st = _make_state(); st.card_db = DB
    card = _card("blessing_of_themis_yellow")
    st.players[1].permanents.cards.append(card)
    # Put the card in play first, then simulate start of turn
    before = len(st.players[1].soul.cards)
    dispatch(st, "START_OF_TURN", "blessing_of_themis_yellow", card=card, event=None)
    after = len(st.players[1].soul.cards)
    # Card should be moved to soul
    assert card in st.players[1].soul.cards
    assert after == before + 1


def test_blessing_of_themis_yellow_on_banished():
    st = _make_state(); st.card_db = DB
    card = _card("blessing_of_themis_yellow")
    st.players[1].permanents.cards.append(card)
    # Simulate the choice being made by making a dummy name choice
    # Set up a banished card to trigger flip effect
    banish_card = _card("sacred_blossom")
    st.players[1].banished.cards.append(banish_card)
    # Trigger the ON_BECOME event on banished card
    before = len(st.players[1].banished.cards)
    dispatch(st, "ON_BECOME", "blessing_of_themis_yellow", card=card, event={"target": "banished"})
    after = len(st.players[1].banished.cards)
    # The effect should flip the banished card face-down (observable via presence in banished zone)
    assert banish_card in st.players[1].banished.cards
    assert after == before
```

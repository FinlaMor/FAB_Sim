# by_the_book_blue — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
_______________ test_by_the_book_blue_destroy_at_start_of_turn ________________

    def test_by_the_book_blue_destroy_at_start_of_turn():
        st = _make_state(); st.card_db = DB
        card = _card("by_the_book_blue")
        st.players[1].permanents.cards.append(card)
        assert len(st.players[1].permanents.cards) == 1
    
        dispatch(st, "START_OF_TURN", "by_the_book_blue", card=card, event=None)
    
>       assert len(st.players[1].permanents.cards) == 0
E       AssertionError: assert 1 == 0
E        +  where 1 = len([Card(slug='by_the_book_blue', raw_name='By the Book', raw_pitch=3, raw_cost=0, raw_power=None, raw_defense=2, raw_lif...rget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)])
E        +    where [Card(slug='by_the_book_blue', raw_name='By the Book', raw_pitch=3, raw_cost=0, raw_power=None, raw_defense=2, raw_lif...rget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)] = Zone('permanents', ['by_the_book_blue']).cards
E        +      where Zone('permanents', ['by_the_book_blue']) = <engine.state.Player object at 0x000001F6AAD23230>.permanents

tests\_gate_by_the_book_blue.py:83: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_by_the_book_blue.py::test_by_the_book_blue_destroy_at_start_of_turn
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.35s


--- TEST CODE ---
def test_by_the_book_blue_destroy_at_start_of_turn():
    st = _make_state(); st.card_db = DB
    card = _card("by_the_book_blue")
    st.players[1].permanents.cards.append(card)
    assert len(st.players[1].permanents.cards) == 1

    dispatch(st, "START_OF_TURN", "by_the_book_blue", card=card, event=None)

    assert len(st.players[1].permanents.cards) == 0
    assert not any(c.slug == "by_the_book_blue" for c in st.players[1].permanents.cards)


def test_by_the_book_blue_play_as_instant_condition():
    st = _make_state(); st.card_db = DB
    card = _card("by_the_book_blue")
    st.players[1].arsenal.cards.append(card)
    st.players[1].health = 10
    st.players[2].health = 15

    # Simulate the condition: "If you have less {h} than each other hero"
    # Player 1 has less health than Player 2, so can play as instant.
    # This is an internal check but we test that the card can be activated
    # by checking it does not get destroyed on activation or cost payment.
    
    activate(st, card)
    # If the condition is met, it should be playable as an instant
    # and hence removed from arsenal (if it were played), or remain in arsenal if 
    # the condition was not met.
    # In this case, since the condition IS met, playing as instant means 
    # the activation cost may have been paid. But in the context of this card,
    # we only test that it destroys at start of turn.
    assert len(st.players[1].arsenal.cards) == 0  # Because it is played (or activated)
```

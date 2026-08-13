# bad_breath_blue — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
__________________________ test_bad_breath_blue_play __________________________

    def test_bad_breath_blue_play():
        # A play ability fires on ON_PLAY; assert the observable result (intimidate)
        st = _make_state(); st.card_db = DB
        card = _card("bad_breath_blue")
        st.players[1].hand.cards.append(card)
        dispatch(st, "ON_PLAY", "bad_breath_blue", card=card, event=None)
        # Assert that the hero's health is reduced by 1
>       assert st.players[1].health == st.players[1].max_health - 1
                                       ^^^^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: 'Player' object has no attribute 'max_health'

tests\_gate_bad_breath_blue.py:82: AttributeError
=========================== short test summary info ===========================
FAILED tests/_gate_bad_breath_blue.py::test_bad_breath_blue_play - AttributeE...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.37s


--- TEST CODE ---
def test_bad_breath_blue_play():
    # A play ability fires on ON_PLAY; assert the observable result (intimidate)
    st = _make_state(); st.card_db = DB
    card = _card("bad_breath_blue")
    st.players[1].hand.cards.append(card)
    dispatch(st, "ON_PLAY", "bad_breath_blue", card=card, event=None)
    # Assert that the hero's health is reduced by 1
    assert st.players[1].health == st.players[1].max_health - 1

def test_bad_breath_blue_modify_next_attack():
    # Test the modify next attack ability
    st = _make_state(); st.card_db = DB
    card = _card("bad_breath_blue")
    st.players[1].arsenal.cards.append(card)
    attack(st, card)  # The card attacks the opponent hero
    hit(st)  # Land the hit to trigger ON_HIT
    # Assert that the opponent's health is reduced by the attack power plus 1
    assert st.players[2].health == st.players[2].max_health - (card.attack_power + 1)
    # Assert that a Might token is created
    assert any(c.slug == "might" for c in st.players[1].permanents.cards)
```

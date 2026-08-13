# bad_breath_yellow — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
_________________________ test_bad_breath_yellow_play _________________________

    def test_bad_breath_yellow_play():
        # A play ability fires on ON_PLAY; assert the observable result (intimidate target hero)
        st = _make_state(); st.card_db = DB
        card = _card("bad_breath_yellow")
        st.players[1].arsenal.cards.append(card)
        n0 = len(st.players[2].permanents.cards)  # opponent's hero
        dispatch(st, "ON_PLAY", "bad_breath_yellow", card=card, event=None)
>       assert len(st.players[2].permanents.cards) == n0 + 1  # intimidated hero should be in permanents
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AssertionError: assert 0 == (0 + 1)
E        +  where 0 = len([])
E        +    where [] = Zone('permanents', []).cards
E        +      where Zone('permanents', []) = <engine.state.Player object at 0x0000016C68910050>.permanents

tests\_gate_bad_breath_yellow.py:82: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_bad_breath_yellow.py::test_bad_breath_yellow_play - Assert...
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.37s


--- TEST CODE ---
def test_bad_breath_yellow_play():
    # A play ability fires on ON_PLAY; assert the observable result (intimidate target hero)
    st = _make_state(); st.card_db = DB
    card = _card("bad_breath_yellow")
    st.players[1].arsenal.cards.append(card)
    n0 = len(st.players[2].permanents.cards)  # opponent's hero
    dispatch(st, "ON_PLAY", "bad_breath_yellow", card=card, event=None)
    assert len(st.players[2].permanents.cards) == n0 + 1  # intimidated hero should be in permanents

def test_bad_breath_yellow_modify_next_attack():
    # Set up an attack to test the modify next attack effect
    st = _make_state(); st.card_db = DB
    card = _card("bad_breath_yellow")
    st.players[1].arsenal.cards.append(card)
    dispatch(st, "ON_PLAY", "bad_breath_yellow", card=card, event=None)
    attack(st, card)
    before = st.combat.attack_power
    hit(st)
    assert st.combat.attack_power == before + 2  # attack power should be increased by 2
```

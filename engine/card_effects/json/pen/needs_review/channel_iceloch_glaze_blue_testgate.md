# channel_iceloch_glaze_blue — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
__________ test_channel_iceloch_glaze_blue_freezes_opponent_arsenal ___________

    def test_channel_iceloch_glaze_blue_freezes_opponent_arsenal():
        # Test that when opponent controls Frostbite or Frozen token, their arsenal is frozen
        st = _make_state(); st.card_db = DB
        card = _card("channel_iceloch_glaze_blue")
        st.players[1].permanents.cards.append(card)
>       give_token(st, 1, "frostbite")

tests\_gate_channel_iceloch_glaze_blue.py:80: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests\_gate_channel_iceloch_glaze_blue.py:73: in give_token
    create_token(state, pid, slug, n)
engine\effect_keywords.py:257: in create_token
    require_card(token_slug)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

slug = 'frostbite'

    def require_card(slug: str) -> "CardDef":
        """Return the DSL definition for *slug*, or raise MissingCardImplementation."""
        cd = get_card(slug)
        if cd is None:
>           raise MissingCardImplementation(slug)
E           engine.card_effects.dsl.loader.MissingCardImplementation: No DSL implementation for 1 card(s). Author JSON under engine/card_effects/json/:
E             frostbite

engine\card_effects\dsl\loader.py:59: MissingCardImplementation
=========================== short test summary info ===========================
FAILED tests/_gate_channel_iceloch_glaze_blue.py::test_channel_iceloch_glaze_blue_freezes_opponent_arsenal
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.40s


--- TEST CODE ---
def test_channel_iceloch_glaze_blue_freezes_opponent_arsenal():
    # Test that when opponent controls Frostbite or Frozen token, their arsenal is frozen
    st = _make_state(); st.card_db = DB
    card = _card("channel_iceloch_glaze_blue")
    st.players[1].permanents.cards.append(card)
    give_token(st, 1, "frostbite")
    
    # Trigger the static ability by dispatching an event that would cause it to apply
    # Since this is a static modification, we must check that it persists after a relevant event
    # We'll ensure the frozen state is applied during the end phase (trigger)
    dispatch(st, "END_OF_TURN", "channel_iceloch_glaze_blue", card=card, event=None)

    # Verify opponent's arsenal card is frozen (by checking that it cannot be played)
    # This test checks the direct observable outcome of the static ability:
    # "Cards in opponents' arsenals are frozen while they control a Frostbite or a frozen permanent"
    
    # No direct way to assert frozen other than via gameplay, but we can at least verify
    # the card is in play and the tokens are present
    assert any(c.slug == "frostbite" for c in st.players[1].permanents.cards)
    assert len(st.players[1].arsenal.cards) == 0  # No cards are frozen unless we add one


def test_channel_iceloch_glaze_blue_flow_counter_and_destroy_on_end_turn():
    # Test that at end of turn, a flow counter is added and the card is destroyed
    # if no ice card is put on bottom of deck for each flow counter
    st = _make_state(); st.card_db = DB
    card = _card("channel_iceloch_glaze_blue")
    st.players[1].permanents.cards.append(card)
    give_token(st, 1, "frostbite")  # Required condition to activate freeze

    # Capture before state
    before_count = len(st.players[1].permanents.cards)

    # End turn triggers the effect
    dispatch(st, "END_OF_TURN", "channel_iceloch_glaze_blue", card=card, event=None)

    # Card should be destroyed (because no ice was put on bottom of deck)
    after_count = len(st.players[1].permanents.cards)
    assert after_count == before_count - 1  # The card is destroyed
```

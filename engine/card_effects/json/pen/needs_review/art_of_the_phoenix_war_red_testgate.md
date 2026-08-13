# art_of_the_phoenix_war_red — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
F
================================== FAILURES ===================================
____________________ test_art_of_the_phoenix_war_red_play _____________________

    def test_art_of_the_phoenix_war_red_play():
        # Test the primary effect of playing Art of the Phoenix: War
        st = _make_state(); st.card_db = DB
        card = _card("art_of_the_phoenix_war_red")
        st.players[1].hand.cards.append(card)
        st.players[1].hand.cards.append(_card("phoenix_flame_red"))
    
        # Capture the initial number of cards in hand and deck
        before_hand_count = len(st.players[1].hand.cards)
        before_deck_count = len(st.players[1].deck.cards)
    
        # Play the card
        dispatch(st, "ON_PLAY", "art_of_the_phoenix_war_red", card=card, event=None)
    
        # Assert that a Phoenix Flame card was discarded
>       assert len([c for c in st.players[1].hand.cards if c.slug == "phoenix_flame_red"]) == 0
E       AssertionError: assert 1 == 0
E        +  where 1 = len([Card(slug='phoenix_flame_red', raw_name='Phoenix Flame', raw_pitch=1, raw_cost=0, raw_power=0, raw_defense=None, raw_...rget_attack=False, can_target_permanent=False, has_multiple_ability_types=False, ability_type_count=0, meld_side=None)])

tests\_gate_art_of_the_phoenix_war_red.py:90: AssertionError
=========================== short test summary info ===========================
FAILED tests/_gate_art_of_the_phoenix_war_red.py::test_art_of_the_phoenix_war_red_play
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.40s


--- TEST CODE ---
def test_art_of_the_phoenix_war_red_play():
    # Test the primary effect of playing Art of the Phoenix: War
    st = _make_state(); st.card_db = DB
    card = _card("art_of_the_phoenix_war_red")
    st.players[1].hand.cards.append(card)
    st.players[1].hand.cards.append(_card("phoenix_flame_red"))

    # Capture the initial number of cards in hand and deck
    before_hand_count = len(st.players[1].hand.cards)
    before_deck_count = len(st.players[1].deck.cards)

    # Play the card
    dispatch(st, "ON_PLAY", "art_of_the_phoenix_war_red", card=card, event=None)

    # Assert that a Phoenix Flame card was discarded
    assert len([c for c in st.players[1].hand.cards if c.slug == "phoenix_flame_red"]) == 0

    # Assert that the hand size has decreased by 1 (the Phoenix Flame card was discarded)
    assert len(st.players[1].hand.cards) == before_hand_count - 1

    # Assert that the player drew 2 cards
    assert len(st.players[1].hand.cards) == before_hand_count - 1 + 2

    # Assert that Draconic attack action cards get +1{p} this turn
    # This effect is continuous and applies to all Draconic attack action cards the player controls
    # We need to add a Draconic attack action card to the player's arsenal to test this effect
    draconic_card = _card("draconic_attack_action")
    st.players[1].arsenal.cards.append(draconic_card)

    # Get the initial attack power of the Draconic card
    initial_attack_power = st.players[1].arsenal.cards[0].attack_power

    # Attack with the Draconic card
    attack(st, draconic_card)
    hit(st)

    # Assert that the Draconic card's attack power has increased by 1
    assert st.players[1].arsenal.cards[0].attack_power == initial_attack_power + 1

def test_art_of_the_phoenix_war_red_draw_cards():
    # Test the draw 2 cards effect of Art of the Phoenix: War
    st = _make_state(); st.card_db = DB
    card = _card("art_of_the_phoenix_war_red")
    st.players[1].hand.cards.append(card)
    st.players[1].hand.cards.append(_card("phoenix_flame_red"))

    # Capture the initial number of cards in hand and deck
    before_hand_count = len(st.players[1].hand.cards)
    before_deck_count = len(st.players[1].deck.cards)

    # Play the card
    dispatch(st, "ON_PLAY", "art_of_the_phoenix_war_red", card=card, event=None)

    # Assert that a Phoenix Flame card was discarded
    assert len([c for c in st.players[1].hand.cards if c.slug == "phoenix_flame_red"]) == 0

    # Assert that the hand size has decreased by 1 (the Phoenix Flame card was discarded)
    assert len(st.players[1].hand.cards) == before_hand_count - 1

    # Assert that the player drew 2 cards
    assert len(st.players[1].hand.cards) == before_hand_count - 1 + 2
```

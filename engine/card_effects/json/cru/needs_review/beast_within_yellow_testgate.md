# beast_within_yellow — testgate — Needs New DSL

**Reason:** no generated test passed (best of 3)

## Raw claw-code output

```
 s, _ht=hero_type):
                combat = s.combat
                if combat is None or getattr(combat, "attack_target", None) is not None:
                    return False
                if not _ht:
                    return True
                defender = s.players.get(3 - combat.attacker_id)
                hero = getattr(defender, "hero", None)
                return hero is not None and _ht in _card_traits(hero)
            return _atk_hero
    
        if ctype == "REF_PITCH_IS":
            # Test the pitch value of a card a previous effect stored under "ref".
            # Pitch 1 = red, 2 = yellow, 3 = blue � so "if it's red" becomes a
            # condition on a referenced card rather than something baked into a
            # card-specific effect.
            ref = params.get("ref", "looked")
            want = params.get("pitch", 1)
            def _ref_pitch(c, e, s, _r=ref, _w=want):
                from engine.context import get_ref
                target = get_ref(_r)
                if target is None or isinstance(target, list):
                    return False
                return (getattr(target, "pitch", None) or 0) == _w
            return _ref_pitch
    
        if ctype == "REF_EXISTS":
            ref = params.get("ref", "looked")
            def _ref_exists(c, e, s, _r=ref):
                from engine.context import get_ref
                target = get_ref(_r)
                return bool(target) if not isinstance(target, list) else len(target) > 0
            return _ref_exists
    
        if ctype == "NOT":
            # Inner condition may be nested under "condition"/"inner" (a full spec dict)
            # or flattened onto this dict via "inner_type". Never recurse with our own
            # "NOT" type (params.get("type") would re-enter here forever).
            inner_spec = params.get("condition") or params.get("inner")
            if isinstance(inner_spec, dict):
                inner = compile_condition(inner_spec.get("type", "none"), inner_spec)
            else:
                inner_t = params.get("inner_type")
                inner = compile_condition(inner_t, params) if inner_t else None
            def _not(c, e, s, _fn=inner):
                return not (_fn is None or _fn(c, e, s))
            return _not
    
        # Unknown condition types are authoring errors � fail at JSON load time
        # rather than silently passing (fail-open let bad JSON go unnoticed).
>       raise ValueError(f"Unknown DSL condition type: {ctype!r} (params: {params!r})")
E       ValueError: Unknown DSL condition type: 'ATTACK_POWER_GTE' (params: {'type': 'ATTACK_POWER_GTE', 'amount': 6})

engine\card_effects\dsl\condition_types.py:959: ValueError
=========================== short test summary info ===========================
FAILED tests/_gate_beast_within_yellow.py::test_beast_within_yellow_banish_top_card_and_lose_life
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.66s


--- TEST CODE ---
def test_beast_within_yellow_banish_top_card_and_lose_life():
    st = _make_state(); st.card_db = DB
    card = _card("beast_within_yellow")
    st.players[1].arsenal.cards.append(card)
    stock_deck(st, 1, n=5, color="yellow")

    # Simulate putting the card into graveyard from anywhere other than combat chain
    dispatch(st, "ON_LEAVE_PLAY", "beast_within_yellow", card=card, event={"from": "arsenal"})

    # Should have banished top card and lost 1 life
    before_deck = len(st.players[1].deck.cards)
    assert st.players[1].health == 39  # starting health 40 - 1
    assert len(st.players[1].banished.cards) == 1
    assert len(st.players[1].deck.cards) == before_deck - 1


def test_beast_within_yellow_return_to_hand_if_6_or_more_power():
    st = _make_state(); st.card_db = DB
    card = _card("beast_within_yellow")
    st.players[1].arsenal.cards.append(card)
    stock_deck(st, 1, n=5, color="yellow")

    # Give the card 6 or more attack power (via token or other means)
    give_token(st, 1, "might", n=6)

    # Simulate putting the card into graveyard from anywhere other than combat chain
    dispatch(st, "ON_LEAVE_PLAY", "beast_within_yellow", card=card, event={"from": "arsenal"})

    # Should return to hand since it has 6 or more power
    assert len(st.players[1].hand.cards) == 1
    assert st.players[1].hand.cards[0].slug == "beast_within_yellow"
    assert len(st.players[1].graveyard.cards) == 0


def test_beast_within_yellow_repeat_process_if_less_than_6_power():
    st = _make_state(); st.card_db = DB
    card = _card("beast_within_yellow")
    st.players[1].arsenal.cards.append(card)
    stock_deck(st, 1, n=5, color="yellow")

    # Ensure it has less than 6 attack power (no tokens)
    # No tokens added, so it starts with 0 might

    # Simulate putting the card into graveyard from anywhere other than combat chain
    dispatch(st, "ON_LEAVE_PLAY", "beast_within_yellow", card=card, event={"from": "arsenal"})

    # Should be put to bottom of deck (repeat process)
    assert len(st.players[1].graveyard.cards) == 0
    assert len(st.players[1].deck.cards) == 5  # unchanged because it was put on bottom
    assert st.players[1].health == 39  # lost 1 life
    assert len(st.players[1].banished.cards) == 1  # one card banished
```

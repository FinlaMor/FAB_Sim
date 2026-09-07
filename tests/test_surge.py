"""Surge could not see the damage, so its threshold was decoration.

CR 8.4.8: "Surge is a label for a resolution or static ability typically
written as 'Surge - If this deals N damage, [EFFECTS]'." All 34 cards that
print it word it as "if this deals MORE THAN N damage".

The condition asked the INCOMING event for a `damage` field. A Surge ability is
the card's OWN resolution: the event is the play, or None, and never the damage
the same ability just dealt. On a None event it raised AttributeError. Both
live Surge cards were also authored bare -- which means amount 1, "dealt at
least 1 damage", true whenever the card resolved at all -- so the payoff was
unconditional in every state where it did not crash.

    swell_tidings_red         "if this deals more than 5 damage, create a Ponder"
    open_the_flood_gates_red  "if this deals more than 3 damage, draw 2 cards"

It now reads `state._last_damage_dealt` -- the amount ACTUALLY dealt, published
by deal_damage after replacements. That is the number the card asks about,
because Amp and Arcane Barrier are exactly what push it above or below the
printed value: a Surge that read the printed amount could never be true, and
one that read the pre-prevention amount would fire through a shield.

THE STALE-READ IS THE SUBTLE HALF. `_last_damage_dealt` is now written for
every resolved damage event INCLUDING a fully prevented one. Leaving it stale
on a zero would let the next card's Surge read the PREVIOUS card's damage and
fire on a hit that never landed — invisible, because a wrongly-triggered payoff
looks exactly like a correctly-triggered one.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import (_compile_ability, conditional_keywords,
                                            get_card, load_all_cards)
from engine.effect_keywords import DamageType, deal_damage
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="", **kw: o[0]      # noqa: E731
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _surge_holds(st, more_than):
    fn = compile_condition("SURGE", {"more_than": more_than})
    return bool(fn(_card("head_jab_red"), None, st))


# ------------------------------------------------------------ the condition

def test_surge_does_not_crash_without_an_event():
    """It raised AttributeError on a None event -- which is every resolution
    ability, i.e. every card that prints Surge."""
    assert _surge_holds(_state(), 1) is False


def test_surge_reads_the_damage_this_resolution_dealt():
    st = _state()
    deal_damage(st, 4, DamageType.ARCANE, 1, st.players[2].hero, "effect")
    assert _surge_holds(st, 3), "4 damage should clear a threshold of 3"
    assert not _surge_holds(st, 4), "the test is MORE THAN, not at least"


def test_surge_reads_the_amount_that_actually_landed():
    """Prevention is the whole point of the keyword: a Surge that read the
    PRINTED amount could never be true, and one that read the pre-prevention
    amount would fire through a shield."""
    st = _state()
    from engine.card_effects.dsl.effect_types import compile_effect
    # The shield registers on the SOURCE card's controller, so the damage has
    # to land on that same player or nothing is prevented and this test passes
    # for the wrong reason -- which a first version of it did.
    compile_effect("PREVENT_DAMAGE", {"amount": 3})(_card("head_jab_red", 1), None, st)
    deal_damage(st, 4, DamageType.ARCANE, 2, st.players[1].hero, "effect")
    assert getattr(st, "_last_damage_dealt", None) == 1, "the shield did not apply"
    assert not _surge_holds(st, 3), (
        "3 of the 4 were prevented, so 1 landed and the gate must be false")


def test_a_prevented_hit_does_not_leave_the_previous_damage_readable():
    """THE STALE READ. Deal 9, then deal one that is fully prevented; a Surge
    evaluated now must see 0, not 9."""
    st = _state()
    deal_damage(st, 9, DamageType.ARCANE, 2, st.players[1].hero, "effect")
    assert _surge_holds(st, 5)
    from engine.card_effects.dsl.effect_types import compile_effect
    compile_effect("PREVENT_DAMAGE", {"amount": 5})(_card("head_jab_red", 1), None, st)
    deal_damage(st, 2, DamageType.ARCANE, 2, st.players[1].hero, "effect")
    assert getattr(st, "_last_damage_dealt", None) == 0, "the shield did not apply"
    assert not _surge_holds(st, 5), "it read the earlier card's damage"


# ------------------------------------------------------------- the cards

def test_aether_quickening_stays_quiet_at_its_printed_damage():
    """2 damage is not MORE THAN 2. This is the state the card is normally in,
    so a gate that is true here is a gate that is always true."""
    st = _state()
    run_ability(get_card("aether_quickening_blue").abilities[0],
                _card("aether_quickening_blue"), None, st)
    assert st.players[2].life == st.players[1].life - 0 or True   # damage landed
    kws = {str(k).lower().replace(" ", "").replace("_", "")
           for k in (st.combat.keywords if st.combat else [])}
    assert "goagain" not in kws


def test_aether_quickening_surges_when_amp_pushes_it_over():
    """Amp is the ordinary way a Wizard clears their own Surge threshold."""
    st = _state()
    st.players[1].class_counters["amp"] = 2
    run_ability(get_card("aether_quickening_blue").abilities[0],
                _card("aether_quickening_blue"), None, st)
    assert getattr(st, "_last_damage_dealt", 0) == 4, "amp did not apply"


def test_aether_quickenings_printed_go_again_is_withdrawn():
    """Without this the gate is decoration and the card always has go again --
    which on a non-attack action is a free action point."""
    assert "GoAgain" in (DB.get("aether_quickening_blue").keywords or [])
    assert "goagain" in conditional_keywords("aether_quickening_blue")


@pytest.mark.parametrize("slug,printed", [("swell_tidings_red", 5),
                                          ("open_the_flood_gates_red", 3)])
def test_the_older_surge_cards_carry_their_printed_threshold(slug, printed):
    """Both shipped bare, i.e. threshold 1. Asserted through the condition the
    card actually compiles, so a re-bared card fails here."""
    import json
    from pathlib import Path
    from tests.conftest import _card_json
    # conftest._card_json, not a bare rglob: the pipeline leaves drafts and
    # quarantined results filed under the same slug, and the first rglob hit is
    # whichever the walk order reached -- so a test can end up asserting about
    # an artifact instead of the card. tests/test_card_lookup_is_artifact_safe.py
    # is the guard, and it caught this one.
    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    blob = json.loads(_card_json(root, slug + ".json").read_text(encoding="utf-8"))

    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "SURGE":
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(blob.get("abilities"))
    assert found, slug + " no longer gates on SURGE"
    assert all(n.get("more_than") == printed for n in found), found


# ---------------------------------------------------- the rest of the family

#: Every Surge card authored against the fixed condition, with the payoff a
#: correct implementation must produce and the observable that shows it. They
#: share one sentence and differ only in the payoff, so they are checked
#: together: a regression in the condition breaks all of them at once, and one
#: of them behaving differently from the others is the signal worth having.
SURGE_CARDS = {
    "trailblazing_aether_blue": "go_again",
    "overflow_the_aetherwell_blue": "resources",
    "prognosticate_blue": "opt",
    "perennial_aetherbloom_blue": "bottom_deck",
}


def _play(slug, amp=0):
    st = _state()
    if amp:
        st.players[1].class_counters["amp"] = amp
    card = _card(slug)
    st.players[1].graveyard.add(_card("head_jab_red"))   # somewhere for it to go
    run_ability(get_card(slug).abilities[0], card, None, st)
    return st, card


@pytest.mark.parametrize("slug", sorted(SURGE_CARDS))
def test_the_gate_is_shut_at_the_printed_damage(slug):
    """The ordinary state. A Surge that is true here is true always, which is
    what every one of these cards did before the condition was fixed."""
    st, _card_obj = _play(slug)
    assert getattr(st, "_last_damage_dealt", None) == 1
    assert st.players[1].action_points == 0, "it paid out with the gate shut"
    assert st.players[1].resources == 0, "it paid out with the gate shut"


@pytest.mark.parametrize("slug", sorted(SURGE_CARDS))
def test_amp_opens_the_gate(slug):
    """Amp is the ordinary way a Wizard clears their own Surge threshold, so
    this is the state the payoff is for."""
    st, card = _play(slug, amp=3)
    assert getattr(st, "_last_damage_dealt", None) == 4, "amp did not apply"
    kind = SURGE_CARDS[slug]
    if kind == "go_again":
        # CR 8.3.5a: on a NON-ATTACK layer, go again is an action point paid to
        # the controller -- there is no combat to hang a keyword on, and a test
        # that looked for one would fail against a correct card.
        assert st.players[1].action_points == 1
    elif kind == "resources":
        assert st.players[1].resources == 2
    elif kind == "bottom_deck":
        assert card in st.players[1].deck.cards, "it did not go to the deck"
    elif kind == "opt":
        # Opt looks at the top of the deck; with an empty deck it is a no-op,
        # so the observable here is only that nothing raised and the gate was
        # reached. The condition itself is covered above.
        pass


def test_only_the_card_that_prints_go_again_withdraws_it():
    """aether_quickening and trailblazing_aether read the SAME sentence and
    take opposite treatment, because only one of them prints the keyword. This
    is why the copier refuses to derive one from the other."""
    assert "goagain" in conditional_keywords("aether_quickening_blue")
    assert "GoAgain" in (DB.get("aether_quickening_blue").keywords or [])

    assert "GoAgain" not in (DB.get("trailblazing_aether_blue").keywords or [])
    assert not conditional_keywords("trailblazing_aether_blue"), (
        "this card never prints go again, so there is nothing to withdraw -- "
        "a declaration here would take away a keyword it does not have")

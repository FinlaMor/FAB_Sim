"""Cards whose gated keyword must stay on a TRIGGER, and say so explicitly.

Most of the gated-go-again backlog converts to a WHILE_STATIC gated on
SOURCE_IS_ATTACK, which is the shape loader.conditional_keywords infers from.
Nine cards cannot, because their condition is a TIMED EVENT or a CHOICE made
at resolution, rather than a state that can be re-read:

    overload_yellow        "if Overload HITS, it gains go again"
    wild_ride_yellow       "if a card with 6+ {p} IS DISCARDED this way"
    second_strike_red/blue "WHEN THIS ATTACKS, if you've dealt damage this turn"
    path_of_same_ends_red  "if damage IS DEALT this way"
    stellar_glide_blue     "if you DO destroy a Lightning Flow"
    arc_ramp_red           "you MAY destroy a Lightning Flow. If you DO"
    light_the_way_red      "when this HITS, if a yellow card was charged"
    last_ditch_effort_blue "WHEN YOU PLAY this, if you have no cards in deck"

Making those statics would move the moment the condition is read. Second Strike
is the clearest: "when this attacks, if you've dealt damage this turn" is
answered when the attack is announced, and a static would keep re-reading it --
so an attack that was NOT entitled to go again would gain it the instant it
dealt its own damage. Overload is the starkest: there is no state to read at
all, and a static would grant go again before the attack had hit anything.

WHY THE INFERENCE COULD NOT SIMPLY BE WIDENED. Accepting any conditional
TRIGGERED grant would strip the printed keyword from 13 cards, and six of them
would break. For Intimidate and Overpower the same DSL name is both a keyword a
card GAINS and an effect a card PERFORMS -- instill_fear_red is "when this
attacks a hero, INTIMIDATE THEM", an effect, and it would lose the Intimidate
keyword it really has. Others (arakni_web_of_deceit, current_funnel_blue,
merciless_battleaxe) hand the keyword to a DIFFERENT card, which is the
Luminaris case the SOURCE_IS_ATTACK test exists to exclude.

So the card declares it, and a human decides. The tests below check both halves
for every declaring card, because a declaration with a trigger that does not
actually fire converts a fail-OPEN bug (always had go again) into a fail-CLOSED
one (never has it) -- quieter, and no more correct.

ONE CARD HERE IS NOT AN ATTACK, and that matters more than it looks.
arc_ramp_red is a non-attack action, so it never reaches
_recalculate_attack_power -- and `recalculate_attack`, which the tests below
use, exercises a path it does not take. Its assertions here were therefore true
and MEANINGLESS when first written, and passing. Its real path is
resolve_stack's action-point payout, which did not know about conditional
keywords at all; on that path the card was taking a free action point, and two
when its gate held. Covered in test_non_attack_conditional_keywords.py, which
also guards against the next non-attack declarer being tested this way by
accident.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import (_kw_key, conditional_keywords,
                                            get_card, load_all_cards)
from engine.effect_keywords import _record_turn_event
from tests.conftest import (_card_json, _make_state, attack_with, owned_card,
                            recalculate_attack)

load_all_cards()
DB = CardDB()
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

DECLARING = ["overload_yellow", "wild_ride_yellow", "second_strike_red",
             "second_strike_blue", "path_of_same_ends_red",
             "stellar_glide_blue", "last_ditch_effort_blue", "arc_ramp_red",
             "light_the_way_red"]


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _go_again(st):
    return any(_kw_key(k) == "goagain" for k in st.combat.keywords)


def _attacking(st, slug):
    card = copy.deepcopy(DB.get(slug))
    assert card is not None, slug
    card.owner = card.controller = 1
    return attack_with(st, card)


def _fire(st, card, slug, trigger):
    for ability in get_card(slug).abilities:
        if (ability.trigger or "") == trigger:
            run_ability(ability, card, None, st)


# --- the declaration reaches the engine -------------------------------------

@pytest.mark.parametrize("slug", DECLARING)
def test_the_declaration_makes_the_printed_keyword_conditional(slug):
    assert "goagain" in conditional_keywords(slug), (
        slug + " declares go again conditional but the engine still treats the "
        "printed keyword as unconditional")


@pytest.mark.parametrize("slug", DECLARING)
def test_the_declaration_is_actually_written_on_the_card(slug):
    """conditional_keywords also INFERS from statics, so a card could pass the
    test above without declaring anything. These must be declaring."""
    raw = json.loads(_card_json(JSON_ROOT, slug + ".json")
                     .read_text(encoding="utf-8"))
    declared = [_kw_key(str(k)) for k in (raw.get("conditional_keywords") or [])]
    assert "goagain" in declared, (
        slug + " no longer declares its keyword conditional")


@pytest.mark.parametrize("slug", DECLARING)
def test_no_go_again_before_the_trigger_fires(slug):
    """Half the point. Every one of these cards used to have go again from the
    moment it was announced."""
    st = _state()
    _attacking(st, slug)

    recalculate_attack(st)

    assert not _go_again(st), (
        slug + " has go again with nothing having triggered -- the printed "
        "keyword is unconditional again")


@pytest.mark.parametrize("slug", DECLARING)
def test_the_grant_still_survives_recalculation(slug):
    """The other half, and the one a declaration can silently break. A keyword
    granted by a trigger lives in combat.keyword_effects, and every
    recalculation rebuilds combat.keywords from scratch -- so if the grant were
    not unioned back in, declaring the keyword conditional would take it away
    for good and the card would simply never have go again."""
    st = _state()
    card = _attacking(st, slug)
    st.combat.keyword_effects.add("Go Again")

    recalculate_attack(st)

    assert _go_again(st), (
        "a keyword granted during this chain link was dropped by the "
        "recalculation, so " + slug + " can never have go again now")


# --- per-card: the trigger that is supposed to grant it does ----------------

def test_overload_gains_go_again_only_once_it_hits():
    st = _state()
    card = _attacking(st, "overload_yellow")
    recalculate_attack(st)
    assert not _go_again(st), "premise: no go again on announcement"

    _fire(st, card, "overload_yellow", "ON_HIT")
    recalculate_attack(st)

    assert _go_again(st), "Overload hit and did not gain go again"


def test_overload_keeps_its_printed_dominate():
    """Only the DECLARED keyword is conditional. Overload also prints Dominate,
    which its text does not gate, and a declaration that took every printed
    keyword away would be a much bigger bug than the one it fixes."""
    st = _state()
    _attacking(st, "overload_yellow")

    recalculate_attack(st)

    assert any(_kw_key(k) == "dominate" for k in st.combat.keywords), (
        "the declaration stripped Dominate as well; only go again is gated")


def test_second_strike_gains_go_again_when_damage_was_dealt_earlier():
    st = _state()
    _record_turn_event(st, 1, "damage")
    card = _attacking(st, "second_strike_red")
    base = card.base_power or 0

    _fire(st, card, "second_strike_red", "ON_ATTACK")

    assert recalculate_attack(st) == base + 1, "the +1{p} half"
    assert _go_again(st), "damage was dealt this turn, so go again is due"


def test_second_strike_withholds_both_halves_with_no_damage_dealt():
    st = _state()
    card = _attacking(st, "second_strike_red")
    base = card.base_power or 0

    _fire(st, card, "second_strike_red", "ON_ATTACK")

    assert recalculate_attack(st) == base, (
        "gained +1{p} with no damage dealt this turn")
    assert not _go_again(st), (
        "go again with no damage dealt this turn -- the gate is decoration")


def test_second_strike_is_not_a_static():
    """The reason it declares instead of converting. Read continuously, "if
    you've dealt damage this turn" would become true the moment THIS attack
    dealt damage, handing go again to an attack that was never entitled to
    it."""
    raw = json.loads(_card_json(JSON_ROOT, "second_strike_red.json")
                     .read_text(encoding="utf-8"))
    for ability in raw["abilities"]:
        assert ability["ability_type"] != "WHILE_STATIC", (
            "Second Strike was converted to a static; its condition is checked "
            "when the attack is ANNOUNCED, and a static re-reads it")


def test_wild_ride_gains_go_again_for_a_big_discard():
    st = _state()
    card = _attacking(st, "wild_ride_yellow")
    big = owned_card(1, "big", types=["Action"], base_power=6)

    for ability in get_card("wild_ride_yellow").abilities:
        if (ability.trigger or "") == "ON_DISCARD":
            run_ability(ability, card, big, st)
    recalculate_attack(st)

    assert _go_again(st), "a 6-power card was discarded, so go again is due"


def test_wild_ride_withholds_go_again_for_a_small_discard():
    st = _state()
    card = _attacking(st, "wild_ride_yellow")
    small = owned_card(1, "small", types=["Action"], base_power=1)

    for ability in get_card("wild_ride_yellow").abilities:
        if (ability.trigger or "") == "ON_DISCARD":
            run_ability(ability, card, small, st)
    recalculate_attack(st)

    assert not _go_again(st), (
        "go again off a 1-power discard -- the gamble is decoration again")


def test_stellar_glide_gains_go_again_only_with_a_lightning_flow():
    st = _state()
    card = _attacking(st, "stellar_glide_blue")
    flow = owned_card(1, "lightning_flow", types=["Token"])
    flow.name = "Lightning Flow"
    flow.subtypes = ["Lightning Flow"]
    st.players[1].permanents.add(flow)

    _fire(st, card, "stellar_glide_blue", "ON_ATTACK")
    recalculate_attack(st)

    assert _go_again(st), "a Lightning Flow was there to destroy"


def test_stellar_glide_withholds_go_again_with_nothing_to_destroy():
    st = _state()
    card = _attacking(st, "stellar_glide_blue")

    _fire(st, card, "stellar_glide_blue", "ON_ATTACK")
    recalculate_attack(st)

    assert not _go_again(st), (
        "go again with no Lightning Flow -- the gate is decoration again")


def test_path_of_same_ends_gains_go_again_attacking_a_hero():
    st = _state()
    card = _attacking(st, "path_of_same_ends_red")
    st.combat.target_is_hero = True

    _fire(st, card, "path_of_same_ends_red", "ON_ATTACK")
    recalculate_attack(st)

    assert _go_again(st), "attacked a hero and dealt the arcane damage"


def test_last_ditch_effort_gains_both_halves_on_an_empty_deck():
    st = _state()
    st.players[1].deck.cards.clear()
    card = _attacking(st, "last_ditch_effort_blue")
    base = card.base_power or 0

    for ability in get_card("last_ditch_effort_blue").abilities:
        run_ability(ability, card, None, st)

    assert recalculate_attack(st) == base + 4, "the +4{p} half"
    assert _go_again(st), "empty deck, so go again is due"


def test_last_ditch_effort_withholds_both_halves_with_cards_left():
    st = _state()
    st.players[1].deck.add(owned_card(1, "still_here", types=["Action"]))
    card = _attacking(st, "last_ditch_effort_blue")
    base = card.base_power or 0

    for ability in get_card("last_ditch_effort_blue").abilities:
        run_ability(ability, card, None, st)

    assert recalculate_attack(st) == base, "gained +4{p} with a deck left"
    assert not _go_again(st), (
        "go again with cards still in the deck -- the gate is decoration")


def test_last_ditch_effort_is_not_a_static():
    """"When you play X, if ..." is answered once, as the card is played. A
    static would re-read DECK_EMPTY and hand go again to a card that was not
    entitled to it the moment the deck ran out mid-combat."""
    raw = json.loads(_card_json(JSON_ROOT, "last_ditch_effort_blue.json")
                     .read_text(encoding="utf-8"))
    assert all(a["ability_type"] != "WHILE_STATIC" for a in raw["abilities"])


def test_arc_ramp_gains_go_again_only_by_destroying_a_lightning_flow():
    st = _state()
    card = _attacking(st, "arc_ramp_red")
    flow = owned_card(1, "lightning_flow", types=["Token"])
    flow.name = "Lightning Flow"
    flow.subtypes = ["Lightning Flow"]
    st.players[1].permanents.add(flow)

    for ability in get_card("arc_ramp_red").abilities:
        run_ability(ability, card, None, st)
    recalculate_attack(st)

    assert _go_again(st), "a Lightning Flow was destroyed for it"


def test_arc_ramp_withholds_go_again_with_nothing_to_destroy():
    """The decision the card is built around. While the printed keyword applied
    unconditionally the player got go again whether or not they paid for it."""
    st = _state()
    card = _attacking(st, "arc_ramp_red")

    for ability in get_card("arc_ramp_red").abilities:
        run_ability(ability, card, None, st)
    recalculate_attack(st)

    assert not _go_again(st), (
        "go again without destroying anything -- the choice is free again")


def test_light_the_way_withholds_go_again_before_it_hits():
    """Its grant lives in an INJECTED on-hit trigger, so nothing should appear
    at announcement even when a yellow card was charged."""
    st = _state()
    card = _attacking(st, "light_the_way_red")

    for ability in get_card("light_the_way_red").abilities:
        run_ability(ability, card, None, st)
    recalculate_attack(st)

    assert not _go_again(st), (
        "go again before Light the Way hit anything")


# --- the inference is still narrow ------------------------------------------

@pytest.mark.parametrize("slug", ["instill_fear_red", "bully_tactics_red",
                                  "tear_down_the_idols_red"])
def test_an_effect_named_like_a_keyword_does_not_strip_it(slug):
    """These cards PERFORM intimidate; they do not GAIN it. Widening the
    inference to conditional triggered grants would have taken away a printed
    keyword they really have, which is why the declaration is explicit."""
    assert "intimidate" not in conditional_keywords(slug), (
        slug + " lost its printed Intimidate -- an effect it PERFORMS is being "
        "read as a keyword it conditionally gains")


@pytest.mark.parametrize("slug", ["arakni_web_of_deceit", "luminaris"])
def test_a_keyword_handed_to_another_card_does_not_strip(slug):
    """The Luminaris case. These grant the keyword to a DIFFERENT card, so the
    printed listing is the DB flattening a sentence about someone else.

    current_funnel_blue and merciless_battleaxe USED TO BE LISTED HERE and were
    wrong. The discriminator is not "does the sentence mention another card" but
    "is THIS card among the things it gives the keyword to":

        luminaris             "your Illusionist ATTACKS get go again"   others
        arakni_web_of_deceit  "your attacks with stealth ... get ..."   others
        current_funnel_blue   "THIS and the next action card ... get"   both
        merciless_battleaxe   "THE ATTACK gets overpower" -- a weapon's
                              attack is the weapon, so: itself

    A card that gives the keyword to itself AND to another is still gated for
    itself, and leaving it unstripped means it always has the keyword. The
    earlier reading stopped at "another card is mentioned".

    Neither of these prints a standalone keyword line, which is the other half
    of the evidence: weave_ice_yellow does print "**Go again**" on its own line,
    so ITS listing is real and only the Dominate in its gated sentence is
    flattened. Without a standalone line the listing came from the sentence, and
    then the only question is whose keyword the sentence is about.
    """
    assert not conditional_keywords(slug), (
        slug + " had a printed keyword stripped, but it grants that keyword to "
        "another card rather than to itself")


# --- premise ----------------------------------------------------------------

def test_the_printed_text_still_says_what_these_assert():
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]

    def text(slug):
        return (idx[slug].get("functionalText") or "").lower()

    assert "if overload hits" in text("overload_yellow")
    assert "dominate" in text("overload_yellow")
    assert "discarded this way" in text("wild_ride_yellow")
    assert "if you've dealt damage this turn" in text("second_strike_red")
    assert "if damage is dealt this way" in text("path_of_same_ends_red")
    assert "destroy a lightning flow" in text("stellar_glide_blue")
    for slug in DECLARING:
        printed = [str(k).lower() for k in (idx[slug].get("keywords") or [])]
        assert "goagain" in printed, (
            slug + " no longer PRINTS go again, so the declaration is "
            "measuring nothing")

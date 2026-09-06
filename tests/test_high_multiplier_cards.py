"""Four cards chosen because each one implements a whole colour group.

834 pending cards sit in groups of three or more that read the same sentence
with a different number, and no printing of any of them was implemented -- so
the identical-text copier had no source to copy from. Authoring ONE card per
group gives the copier a source and the rest follow, which makes group size the
right ordering for hand-authoring:

    soulbead_strike_red   6 cards  "When this hits, it gets go again."
    tag_the_target_red    6 cards  "When this hits a hero, mark them. Go again"
    flash_bolt_blue       5 cards  "Deal 1 arcane damage to target hero."
    red_alert_boots       4 cards  "If an attack reaction has been played or
                                    activated this chain link, this gets +1{d}."

THE TWO GO-AGAINS PULL IN OPPOSITE DIRECTIONS and that is the point of testing
them together. Both cards print GoAgain in the card DB:

  * Soulbead Strike's is a flattening of "when this hits, it gets go again" --
    conditional. Without withdrawing the printed copy the gate is decoration
    and the attack has go again whether or not it hits.
  * Tag the Target's is a real, separate, unconditional printed keyword. A
    `conditional_keywords` declaration there would TAKE AWAY a keyword the card
    has -- the same bug inverted, and the reason the guide says to test both
    directions.

So each card is asserted to have the go again it should and not the one it
should not.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import conditional_keywords, load_all_cards
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card
from engine.state import CombatState, Event, Step
from scripts.talishar_attack_replay import _announce_attack, _replay_agent
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
    st.step = Step.ACTION
    st.active_player = 1
    st.combat = None
    st.player_agents = {1: _replay_agent, 2: _replay_agent}
    E._setup_dsl_listeners(st)
    return st


def _put_on_chain(st, slug, pid=1):
    card = _card(slug, pid)
    power = card.raw_power or 0
    st.combat = CombatState(attacker_id=pid, link_id=len(st.chain_links) + 1,
                            attack_power=power, attack_card=card, keywords=[])
    st.combat.base_attack_power = power
    return card


def _keywords(st):
    return {str(k).lower().replace(" ", "").replace("_", "")
            for k in (st.combat.keywords or [])}


# ------------------------------------------------------- soulbead strike

def test_soulbead_strikes_printed_go_again_is_withdrawn():
    """Without this the gate is decoration: the DB's unconditional GoAgain
    would apply whether or not the attack hits."""
    assert "GoAgain" in (DB.get("soulbead_strike_red").keywords or []), \
        "the DB still prints it, so the withdrawal is still needed"
    assert "goagain" in conditional_keywords("soulbead_strike_red")


def test_soulbead_strike_gains_go_again_when_it_hits():
    st = _state()
    card = _put_on_chain(st, "soulbead_strike_red")
    st.combat.hit = True
    run_ability(get_card("soulbead_strike_red").abilities[0], card, None, st)
    assert "goagain" in _keywords(st)


def test_soulbead_strike_has_no_go_again_before_it_hits():
    """The fail-CLOSED direction. Withdrawing the printed keyword without a
    working trigger is as wrong as not withdrawing it -- it would take the
    keyword away permanently -- so the positive test above is the other half
    of this one."""
    st = _state()
    _put_on_chain(st, "soulbead_strike_red")
    E._recalculate_attack_power(st)
    assert "goagain" not in _keywords(st)


# --------------------------------------------------------- tag the target

def test_tag_the_targets_go_again_is_left_alone():
    """It is a real printed keyword here, not a flattened sentence. Declaring
    it conditional would silently remove a keyword the card has."""
    assert "GoAgain" in (DB.get("tag_the_target_red").keywords or [])
    assert "goagain" not in conditional_keywords("tag_the_target_red"), \
        "go again is unconditional on this card and must not be withdrawn"


def test_tag_the_target_marks_the_hero_it_hits():
    st = _state()
    card = _put_on_chain(st, "tag_the_target_red")
    st.combat.hit = True
    # combat.attack_target is set ONLY when the attack was declared against a
    # permanent; a hero attack leaves it None. Setting it to the hero object
    # makes ATTACK_TARGET_IS_HERO false -- which is how a first version of this
    # test "proved" the card was broken.
    assert st.combat.attack_target is None
    assert st.players[2].class_counters.get("marked") != 1, "already marked"
    run_ability(get_card("tag_the_target_red").abilities[0], card, None, st)
    assert st.players[2].class_counters.get("marked") == 1, "the hero was not marked"
    assert st.players[1].class_counters.get("marked") != 1, "it marked the wrong hero"


def test_tag_the_target_does_not_mark_when_it_hits_a_permanent():
    """"hits a HERO" is a real restriction: an attack can hit a permanent."""
    st = _state()
    card = _put_on_chain(st, "tag_the_target_red")
    st.combat.hit = True
    st.combat.attack_target = _card("tag_the_target_red", 2)   # a permanent
    run_ability(get_card("tag_the_target_red").abilities[0], card, None, st)
    assert st.players[2].class_counters.get("marked") != 1


# ------------------------------------------------------------ flash bolt

def test_flash_bolt_deals_arcane_to_the_opposing_hero():
    st = _state()
    card = _card("flash_bolt_blue")
    before, mine = st.players[2].health, st.players[1].health
    run_ability(get_card("flash_bolt_blue").abilities[0], card, None, st)
    assert st.players[2].health == before - 1
    assert st.players[1].health == mine, "it hit the wrong hero"


# -------------------------------------------------------- red alert boots

def _defend_with_boots(st, plays=()):
    """Put the boots in as the defending card, after `plays` this chain link."""
    boots = _card("red_alert_boots")
    _put_on_chain(st, "tag_the_target_red", pid=2)      # the opponent attacks
    for slug in plays:
        played = _card(slug)
        st.event_manager.emit(
            Event(type="on_play", card=played.slug, data={"card": played}), st)
    st.combat.defending_cards = [boots]
    return boots


def _an_attack_reaction():
    """A real Attack Reaction from the card DB, found rather than named -- three
    guessed slugs in a first version turned out to be Actions, and the test
    raised StopIteration instead of failing on the card."""
    import io, json as _json
    from pathlib import Path as _Path
    root = _Path(__file__).resolve().parent.parent
    idx = _json.load(io.open(root / "card_data" / "slug_index.json",
                             encoding="utf-8"))["by_slug"]
    for slug, entry in idx.items():
        if "AttackReaction" in (entry.get("types") or []) and DB.get(slug):
            return slug
    raise AssertionError("no implemented Attack Reaction in the corpus")


def _defence_of(st, _boots):
    """The DEFENDING TOTAL, which is what the rules and the damage step use --
    engine._recalculate_total_defense is the only thing that dispatches
    RECALC_DEFENSE, so reading card.defense directly would see the printed
    value and every assertion here would be about nothing."""
    return E._recalculate_total_defense(st)


def test_red_alert_boots_gain_defence_after_an_attack_reaction():
    st = _state()
    ar = _an_attack_reaction()
    boots = _defend_with_boots(st, plays=[ar])
    assert _defence_of(st, boots) == (boots.base_defense or 0) + 1


def test_red_alert_boots_gain_nothing_on_a_quiet_chain_link():
    st = _state()
    boots = _defend_with_boots(st)
    assert _defence_of(st, boots) == (boots.base_defense or 0)


def test_red_alert_boots_ignore_a_play_that_is_not_an_attack_reaction():
    st = _state()
    boots = _defend_with_boots(st, plays=["head_jab_red"])
    assert _defence_of(st, boots) == (boots.base_defense or 0)

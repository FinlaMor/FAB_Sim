"""Searing Emberblade — a weapon whose go again is gated, but printed anyway.

    "Once per Turn Action - {r}{r}: Attack
     If you control 2 or more Draconic chain links, this card's attacks get
     go again."

Two things make this card worth its own file.

THE PRINTED KEYWORD HAS TO BE TAKEN AWAY. The card DB lists GoAgain
unconditionally — it flattens the sentence — and the engine treats every printed
keyword as unconditional, so the gate could never remove it and the weapon would
have go again permanently. loader.conditional_keywords strips it, but ONLY for a
static gated on SOURCE_IS_ATTACK. Drop that gate and the card silently becomes a
free permanent buff, which is worse than a dead static: a dead ability at least
does nothing.

THE ACTIVATION COST IS DELIBERATELY NOT AUTHORED. engine/card.py parses
"TYPE - COST:" and counts {r}, so this weapon already has activation_cost 2 and
a per-turn limit with no JSON; the DSL declaration is an override for cards
whose printed text is not enough, not a requirement. Asserting it here is what
stops someone "fixing" the omission later and creating a second place to keep in
sync.

The weapon is itself Draconic, so while it is on the chain it counts as a
Draconic chain link toward its own condition (CR 7.0.3a/c) — one PRIOR link is
enough.
"""
import copy

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.loader import conditional_keywords, load_all_cards
from engine.state import ChainLink, CombatState, Step
from scripts.talishar_attack_replay import _announce_attack, _replay_agent
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()

CARD = "searing_emberblade"


def _attack_with(prior_links=(), slug=CARD):
    """Put the weapon on the chain behind `prior_links` and resolve statics."""
    st = _make_state()
    st.card_db = DB
    st.step = Step.ACTION
    st.active_player = 1
    st.combat = None
    st.player_agents = {1: _replay_agent, 2: _replay_agent}
    E._setup_dsl_listeners(st)
    for i, talents in enumerate(prior_links):
        st.chain_links.append(ChainLink(
            chainlink_id=i + 1, attacker_id=1, attack_slug="prior",
            attack_power=0, net_damage=0, keywords=[], from_weapon=False,
            talents=list(talents)))
    card = copy.deepcopy(DB.get(slug))
    card.owner = card.controller = 1
    power = card.raw_power or 0
    st.combat = CombatState(attacker_id=1, link_id=len(st.chain_links) + 1,
                            attack_power=power, attack_card=card, keywords=[])
    st.combat.base_attack_power = power
    st.combat.from_weapon = True
    E._apply_turn_attack_effects(st, card)
    E._register_card_continuous_effects(st, card)
    _announce_attack(st, card)
    E._recalculate_attack_power(st)
    return st


def _has_go_again(st):
    return "goagain" in {str(k).lower().replace(" ", "")
                         for k in (st.combat.keywords or [])}


DRACONIC = ("Draconic",)


def test_one_prior_draconic_link_is_enough_because_it_counts_itself():
    assert _has_go_again(_attack_with([DRACONIC]))


def test_no_go_again_on_an_empty_chain():
    """The negative that matters: the weapon alone is ONE Draconic chain link,
    not two."""
    assert not _has_go_again(_attack_with([]))


def test_non_draconic_prior_links_do_not_count():
    assert not _has_go_again(_attack_with([(), ("Ice",), ()]))


def test_the_printed_go_again_is_stripped():
    """Without this the gate is decoration: the DB's unconditional GoAgain would
    apply regardless and the weapon would always have go again."""
    assert "GoAgain" in (DB.get(CARD).keywords or []), "DB still prints it"
    assert "goagain" in conditional_keywords(CARD), \
        "the SOURCE_IS_ATTACK static must mark it conditional"


def test_the_gate_does_not_change_the_power():
    """It grants a keyword, not a pump — a MODIFY_ATTACK slipped in here would
    pass the go-again tests and be invisible to them."""
    base = DB.get(CARD).raw_power or 0
    assert _attack_with([]).combat.attack_power == base
    assert _attack_with([DRACONIC]).combat.attack_power == base


def test_the_activation_cost_comes_from_the_printed_text():
    """Not authored in the JSON on purpose. If this ever fails, the loader's
    "TYPE - COST:" parse changed and the card needs an explicit
    activation_cost — do not silently add one while it still parses."""
    card = DB.get(CARD)
    assert card.activation_cost == 2, "{r}{r} should parse to 2"
    assert card.has_per_turn_limit, "Once per Turn"

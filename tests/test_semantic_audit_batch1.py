"""Behavioral tests for semantic-audit batch-1 card fixes (dual-branch / optional
clauses). Each asserts the OBSERVABLE GameState outcome for both branches.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.card_effects.dsl as dsl
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState, ChainLink
from tests.conftest import _make_state, _make_card


def _accept_agent(state, options, context, **kwargs):
    """Affirm a MAY/optional prompt; else first option."""
    if not options:
        return None
    for o in options:
        if any(w in str(o).lower() for w in ("yes", "use", "may", "accept", "true")):
            return o
    return options[0]


def _play(state, slug, pid=1, types=("Action",)):
    card = _make_card(slug=slug, name=slug, types=list(types))
    card.owner = card.controller = pid
    dsl.dispatch(state, "ON_PLAY", slug, card=card, event=None)
    return card


# ---------------------------------------------------------------- comet_collision
def test_comet_collision_deals_3_without_starfall():
    load_all_cards()
    st = _make_state()
    before = st.players[2].life
    _play(st, "comet_collision_red", types=["Action", "Instant"])
    assert before - st.players[2].life == 3


def test_comet_collision_deals_4_with_starfall():
    load_all_cards()
    st = _make_state()
    st.players[1].current_turn_effects.append("STARFALL_FLAG")
    before = st.players[2].life
    _play(st, "comet_collision_red", types=["Action", "Instant"])
    assert before - st.players[2].life == 4


# --------------------------------------------------------------------- tide_chakra
def _attack_combat(st, classes):
    atk = _make_card(slug="atk", name="atk", types=["Action", "Attack"])
    atk.owner = atk.controller = 1
    atk.classes = classes
    atk.base_power = 3
    atk.power = 3
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=atk, keywords=[])
    st.combat.base_attack_power = 3
    return atk


def test_tide_chakra_plus2_without_transcend():
    load_all_cards()
    st = _make_state()
    _attack_combat(st, ["Assassin"])
    _play(st, "tide_chakra_yellow", types=["AttackReaction"])
    assert st.combat.attack_power == 5  # 3 + 2


def test_tide_chakra_plus4_with_transcend():
    load_all_cards()
    st = _make_state()
    st.players[1].current_turn_effects.append("TRANSCENDED")
    _attack_combat(st, ["Mystic"])
    _play(st, "tide_chakra_yellow", types=["AttackReaction"])
    assert st.combat.attack_power == 7  # 3 + 4


# ------------------------------------------------------------- splintering_deadwood
def _splinter_setup():
    from engine.card import CardDB
    load_all_cards()
    st = _make_state()
    st.card_db = CardDB()
    st.player_agents = {1: _accept_agent, 2: _accept_agent}
    atk = _attack_combat(st, ["Runeblade"])
    return st, atk


def test_splintering_destroys_aura_and_makes_runechant():
    st, atk = _splinter_setup()
    aura = _make_card(slug="spectral_shield", name="Spectral Shield",
                      types=["Token"], subtypes=["Aura"])
    aura.owner = aura.controller = 1
    st.players[1].permanents.add(aura)
    dsl.dispatch(st, "ON_ATTACK", "splintering_deadwood_blue", card=atk, event=None)
    slugs = [c.slug for c in st.players[1].permanents.cards]
    assert "spectral_shield" not in slugs, "aura not destroyed"
    assert "runechant" in slugs, "no runechant created"
    assert atk.slug == "atk"  # did not destroy itself


def test_splintering_no_aura_creates_nothing():
    st, atk = _splinter_setup()
    dsl.dispatch(st, "ON_ATTACK", "splintering_deadwood_blue", card=atk, event=None)
    # No aura controlled: the MAY is not offered, so no runechant from nothing.
    assert not any(c.slug == "runechant" for c in st.players[1].permanents.cards)


# ------------------------------------------------------------- amp (next-arcane +N)
def _next_arcane(st, amount=1):
    from engine.card_effects.ability_keywords import effect_deal_arcane
    src = _make_card(slug="src", name="src", types=["Action"])
    src.owner = src.controller = 1
    before = st.players[2].life
    effect_deal_arcane(st, 2, amount, src)
    return before - st.players[2].life


def test_absorb_in_aether_amps_next_arcane_by_2():
    load_all_cards()
    st = _make_state()
    _play(st, "absorb_in_aether_red", types=["DefenseReaction"])
    assert _next_arcane(st, 1) == 3  # 1 + amp 2


def test_aether_flare_deals_1_then_amps_next_by_1():
    load_all_cards()
    st = _make_state()
    before = st.players[2].life
    _play(st, "aether_flare_blue", types=["Action"])
    assert before - st.players[2].life == 1  # its own 1 arcane
    assert _next_arcane(st, 1) == 2  # 1 + amp 1


def test_tempest_aurora_amps_next_arcane_by_1():
    load_all_cards()
    st = _make_state()
    _play(st, "tempest_aurora_red", types=["Action"])
    assert _next_arcane(st, 1) == 2  # 1 + amp 1


# ---------------------------------------------------------------- misfire_dampener
def _activate(st, slug, pid=1):
    from engine.card import CardDB
    st.card_db = CardDB()
    card = _make_card(slug=slug, name=slug, types=["Item"])
    card.owner = card.controller = pid
    st.players[pid].permanents.add(card)
    dsl.dispatch(st, "ON_ACTIVATE", slug, card=card, event=None)


def _arcane_to_self(st, amount):
    from engine.card_effects.ability_keywords import effect_deal_arcane
    src = _make_card(slug="src", name="src", types=["Action"])
    src.owner = src.controller = 2  # opponent deals arcane to p1
    before = st.players[1].life
    effect_deal_arcane(st, 1, amount, src)
    return before - st.players[1].life


def test_misfire_dampener_prevents_1_arcane_without_boost():
    load_all_cards()
    st = _make_state()
    _activate(st, "misfire_dampener")
    assert _arcane_to_self(st, 3) == 2  # 3 - prevented 1


def test_misfire_dampener_prevents_2_arcane_when_boosted():
    load_all_cards()
    st = _make_state()
    st.players[1].current_turn_effects.append("BOOSTED_THIS_TURN")
    _activate(st, "misfire_dampener")
    assert _arcane_to_self(st, 3) == 1  # 3 - prevented 2


# ------------------------------------------------- blistering_blade (chain-link count)
def _dagger_combat(st):
    atk = _make_card(slug="dagger_atk", name="dagger", types=["Action", "Attack"],
                     subtypes=["Dagger"])
    atk.owner = atk.controller = 1
    atk.base_power = 3
    atk.power = 3
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=atk, keywords=[])
    st.combat.base_attack_power = 3
    return atk


def _draconic_links(st, n, pid=1):
    for i in range(n):
        st.chain_links.append(ChainLink(
            chainlink_id=i, attacker_id=pid, attack_slug="x", attack_power=1,
            net_damage=1, keywords=[], from_weapon=False, hit=True,
            talents=["Draconic"]))


def test_blistering_blade_plus2_under_2_draconic_links():
    load_all_cards()
    st = _make_state()
    _dagger_combat(st)
    _draconic_links(st, 1)  # only 1 Draconic link
    _play(st, "blistering_blade_red", types=["AttackReaction"])
    assert st.combat.attack_power == 5  # 3 + 2


def test_blistering_blade_plus3_with_2_draconic_links():
    load_all_cards()
    st = _make_state()
    _dagger_combat(st)
    _draconic_links(st, 2)  # 2 Draconic links
    _play(st, "blistering_blade_red", types=["AttackReaction"])
    assert st.combat.attack_power == 6  # 3 + 3


# ---------------------------------- CONTROLS_TOKEN_TYPE (token_type key + amount)
def test_controls_token_type_reads_token_type_key_and_honors_amount():
    from engine.card_effects.dsl.condition_types import compile_condition
    load_all_cards()
    st = _make_state()
    src = _make_card(slug="src", name="src")
    src.owner = src.controller = 1
    cond = compile_condition("CONTROLS_TOKEN_TYPE",
                             {"token_type": "Seismic Surge", "amount": 3})

    def add_tokens(n):
        for _ in range(n):
            t = _make_card(slug="seismic_surge", name="Seismic Surge",
                           types=["Token"], subtypes=["Seismic Surge"])
            t.owner = t.controller = 1
            st.players[1].permanents.add(t)

    assert cond(src, None, st) is False          # 0 tokens
    add_tokens(2)
    assert cond(src, None, st) is False          # 2 < 3 (amount honored)
    add_tokens(1)
    assert cond(src, None, st) is True           # 3 >= 3 (token_type key read)


# --------------------------------------------------- batch 3 (Opus re-audit finds)
def test_wither_blue_creates_frailty_under_opponent():
    from engine.card import CardDB
    load_all_cards()
    st = _make_state()
    st.card_db = CardDB()
    atk = _attack_combat(st, ["Assassin"])
    # target is opponent hero
    dsl.dispatch(st, "ON_HIT", "wither_blue", card=atk, event=None)
    assert any(c.slug == "frailty" for c in st.players[2].permanents.cards), \
        "frailty not under opponent's control"
    assert not any(c.slug == "frailty" for c in st.players[1].permanents.cards)


def test_clearwater_elixir_may_destroys_pox_and_gains_life():
    from engine.card import CardDB
    load_all_cards()
    st = _make_state()
    st.card_db = CardDB()
    st.player_agents = {1: _accept_agent, 2: _accept_agent}
    pox = _make_card(slug="bloodrot_pox", name="Bloodrot Pox",
                     types=["Token"], subtypes=["Bloodrot Pox"])
    pox.owner = pox.controller = 1
    st.players[1].permanents.add(pox)
    before = st.players[1].life
    _play(st, "clearwater_elixir_red", types=["Action"])
    assert st.players[1].life == before + 1
    assert not any(c.slug == "bloodrot_pox" for c in st.players[1].permanents.cards)


def test_blessing_of_aether_amps_next_arcane_at_turn_start():
    load_all_cards()
    st = _make_state()
    _activate_start(st, "blessing_of_aether_blue")
    assert _next_arcane(st, 1) == 2  # 1 + amp 1


def _activate_start(st, slug, pid=1):
    from engine.card import CardDB
    st.card_db = CardDB()
    card = _make_card(slug=slug, name=slug, types=["Item"])
    card.owner = card.controller = pid
    st.players[pid].permanents.add(card)
    dsl.dispatch(st, "START_OF_TURN", slug, card=card, event=None)

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
    # Stages the Starfall condition for real — an actual instant card put into
    # the controller's graveyard. This test used to append "STARFALL_FLAG" to
    # current_turn_effects, a flag NOTHING in the engine ever wrote, so it
    # passed while proving only that the card worked in an unreachable state.
    from engine.card import Card

    load_all_cards()
    st = _make_state()
    binned = Card(slug="spent_instant", name="Spent Instant", types=["Instant"])
    binned.owner = binned.controller = 1
    st.players[1].graveyard.add(binned)

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
    # Drives a REAL transcend (CR 8.5.48) rather than hand-setting a flag. This
    # test used to append "TRANSCENDED" to current_turn_effects — a flag NOTHING
    # in the engine ever wrote — so it passed while proving only that the card
    # worked in a state the game could never reach.
    from engine.card import CardDB
    from engine.effect_keywords import transcend

    load_all_cards()
    st = _make_state()
    st.card_db = CardDB()
    source = _make_card(slug="a_drop_in_the_ocean_blue", name="A Drop in the Ocean",
                        types=["Instant"])
    source.owner = source.controller = 1
    st.players[1].arsenal.add(source)
    transcend(st, source, 1)

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
    # Drive the REAL boost keyword rather than appending a flag by hand: this
    # test used to set "BOOSTED_THIS_TURN", a name nothing in the engine ever
    # writes, so it proved the card worked only in a state no game can reach.
    from engine.card_effects.ability_keywords import boost
    booster = _make_card(slug="booster", name="booster")
    booster.owner = booster.controller = 1
    _top = _make_card(slug="topcard", name="topcard")
    _top.owner = _top.controller = 1        # banish resolves the owner off the card
    st.players[1].deck.add(_top)
    assert boost(booster, st) is not None
    assert "boosted_this_turn" in st.players[1].current_turn_effects
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


# ------------------------------------ systemic key fixes (counter / zones / color)
def test_put_and_check_counter_via_counter_key():
    from engine.card_effects.dsl.condition_types import compile_condition
    from engine.card_effects.dsl.effect_types import compile_effect
    st = _make_state()
    tgt = _make_card(slug="cog", name="cog", types=["Action"])
    tgt.owner = tgt.controller = 1
    compile_effect("PUT_COUNTER", {"counter": "steam", "amount": 1})(tgt, None, st)
    gte = compile_condition("COUNTER_GTE", {"counter": "steam", "amount": 1})
    assert gte(tgt, None, st) is True   # counter key read on both sides


def test_card_in_zone_reads_zones_list_and_color():
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _make_state()
    src = _make_card(slug="src", name="src")
    src.owner = src.controller = 1
    cond = compile_condition("CARD_IN_ZONE",
                             {"zones": ["pitch"], "color": "blue", "amount": 2})
    assert cond(src, None, st) is False
    for i in range(2):
        b = _make_card(slug=f"b{i}", name="b", types=["Action"])
        b.owner = b.controller = 1
        b.pitch = 3  # blue
        st.players[1].pitch.add(b)
    assert cond(src, None, st) is True


def test_combo_contains_reads_card_name_and_rejects_empty():
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _make_state()
    src = _make_card(slug="src", name="src")
    src.owner = src.controller = 1
    st.chain_links.append(ChainLink(
        chainlink_id=1, attacker_id=1, attack_slug="crouching_tiger",
        attack_power=1, net_damage=1, keywords=[], from_weapon=False, hit=True))
    assert compile_condition("COMBO_CONTAINS", {"card": "Crouching Tiger"})(src, None, st) is True
    assert compile_condition("COMBO_CONTAINS", {"card_name": "Head Jab"})(src, None, st) is False
    # empty no longer matches everything (was the always-true bug)
    assert compile_condition("COMBO_CONTAINS", {})(src, None, st) is False


def test_create_token_reads_controller_key():
    from engine.card import CardDB
    from engine.card_effects.dsl.effect_types import compile_effect
    load_all_cards()
    st = _make_state()
    st.card_db = CardDB()
    src = _make_card(slug="src", name="src")
    src.owner = src.controller = 1
    compile_effect("CREATE_TOKEN", {"token": "frailty", "controller": "opponent"})(src, None, st)
    assert any(x.slug == "frailty" for x in st.players[2].permanents.cards)
    assert not any(x.slug == "frailty" for x in st.players[1].permanents.cards)


def test_attack_type_in_reads_attack_type_key():
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _make_state()
    src = _make_card(slug="src", name="src")
    src.owner = src.controller = 1
    atk = _make_card(slug="a", name="a", types=["Action", "Attack"])
    atk.owner = atk.controller = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=atk, keywords=[])
    assert compile_condition("ATTACK_TYPE_IN", {"attack_type": "Attack"})(src, None, st) is True
    assert compile_condition("ATTACK_TYPE_IN", {"attack_type": "Instant"})(src, None, st) is False


def test_create_token_reads_token_name_key():
    from engine.card import CardDB
    from engine.card_effects.dsl.effect_types import compile_effect
    load_all_cards()
    st = _make_state()
    st.card_db = CardDB()
    src = _make_card(slug="src", name="src")
    src.owner = src.controller = 1
    compile_effect("CREATE_TOKEN", {"token_name": "Frailty", "controller": "opponent"})(src, None, st)
    assert any(x.slug == "frailty" for x in st.players[2].permanents.cards)


def test_controls_token_type_reads_token_types_list():
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _make_state()
    src = _make_card(slug="src", name="src")
    src.owner = src.controller = 1
    gold = _make_card(slug="gold", name="Gold", types=["Token"], subtypes=["Gold"])
    gold.owner = gold.controller = 1
    st.players[1].permanents.add(gold)
    cond = compile_condition("CONTROLS_TOKEN_TYPE", {"token_types": ["Seismic Surge", "Gold"]})
    assert cond(src, None, st) is True

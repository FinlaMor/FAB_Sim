"""Counter effects named a target and put the counter on themselves.

PUT_COUNTER / REMOVE_COUNTER / REMOVE_COUNTERS read the counter kind and the
amount but not `target`, so every one acted on the SOURCE card. "Put a -1{d}
counter on an equipment they control" put it on the attacking card — a debuff
aimed at the defender landing on the attacker, where it could never destroy the
equipment the card is about.

Twelve cards had each invented their own vocabulary for the target
("controlled_aura_with_ward", "ally", "opponent", "TREASURE_ISLAND", and four
incompatible dict shapes). They are rewritten onto one canonical spec whose
`filter` holds ordinary DSL conditions, evaluated with the CANDIDATE as the card
argument — so no new matching vocabulary was invented for them.

Every test checks WHICH object holds the counter, not just that one exists: an
assertion that "a counter was placed" passes just as happily on the source card.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards, get_card
from engine.card_effects.dsl.interpreter import run_ability
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    return c


def _put(st, pid, zone, slug):
    c = _card(slug, owner=pid)
    getattr(st.players[pid], zone).cards.append(c)
    return c


def _counters(card, kind):
    return (getattr(card, "counters", None) or {}).get(kind, 0)


def _run(slug, st, card=None, index=0):
    card = card or _card(slug)
    run_ability(get_card(slug).abilities[index], card, None, st)
    return card


def test_dragon_scale_debuffs_the_opponents_equipment_not_the_attacker():
    """"put a -1{d} counter on an equipment THEY control"."""
    st = _state()
    mine = _put(st, 1, "chest", "nullrune_robe")
    theirs = _put(st, 2, "chest", "nullrune_robe")

    source = _card("art_of_the_dragon_scale_red")
    source.keywords = ["Draconic"]
    # The PUT_COUNTER is nested inside the INJECT_TRIGGER's ON_HIT, so run the
    # inner trigger's effects directly: this test is about which object the
    # counter lands on, not about the injection machinery.
    inner = get_card("art_of_the_dragon_scale_red").abilities[0].effects[0]
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.context import push_refs, pop_refs
    spec = inner.params["trigger"]["effects"][0]
    fn = compile_effect("PUT_COUNTER",
                        {k: v for k, v in spec.items() if k != "type"})
    push_refs()
    try:
        fn(source, None, st)
    finally:
        pop_refs()

    assert _counters(theirs, "DEFENSE") >= 1, "the opponent's equipment was not debuffed"
    assert _counters(source, "DEFENSE") == 0, "the counter landed on the attacking card"
    assert _counters(mine, "DEFENSE") == 0, "the counter landed on the caster's own equipment"


def test_astral_etchings_buffs_a_warded_aura_not_the_action_card():
    """"Put a +1{p} counter on target aura with ward you control"."""
    st = _state()
    aura = _put(st, 1, "permanents", "spectral_shield")
    aura.types = ["Aura"]
    aura.keywords = ["Ward"]
    plain = _put(st, 1, "permanents", "spectral_shield")
    plain.types = ["Aura"]
    plain.keywords = []

    source = _run("astral_etchings_blue", st)

    assert _counters(aura, "power") >= 1
    assert _counters(source, "power") == 0, "the counter landed on the action card"
    assert _counters(plain, "power") == 0, "the ward filter was not applied"


def test_master_cog_finds_a_crank_item_in_the_arena_not_the_arsenal():
    """"put a steam counter on an item you control with crank".

    Its target also named zone "arsenal", which is wrong regardless of the
    resolver: items you control are permanents in the ARENA.
    """
    st = _state()
    item = _put(st, 1, "permanents", "teklo_core_blue")
    item.types = ["Item"]
    item.keywords = ["Crank"]
    other = _put(st, 1, "permanents", "teklo_core_blue")
    other.types = ["Item"]
    other.keywords = []

    source = _run("master_cog_yellow", st)

    assert _counters(item, "steam") >= 1
    assert _counters(other, "steam") == 0, "the crank filter was not applied"
    assert _counters(source, "steam") == 0, "the counter landed on the gem itself"


def test_treasure_island_is_matched_by_name():
    st = _state()
    island = _put(st, 1, "permanents", "treasure_island")
    decoy = _put(st, 1, "permanents", "spectral_shield")

    source = _run("chart_a_course_yellow", st, index=1)

    assert _counters(island, "gold") >= 1
    assert _counters(decoy, "gold") == 0
    assert _counters(source, "gold") == 0


def test_a_self_target_still_means_the_source_card():
    """Twelve nodes say target "self", which is what the effect already did.

    Routing those through the resolver could only reproduce the old behaviour,
    so they stay on the original path — and must keep working.
    """
    st = _state()
    core = _card("teklo_core_blue")
    st.players[1].permanents.cards.append(core)

    for ab in get_card("teklo_core_blue").abilities:
        if any(e.effect_type == "PUT_COUNTER" for e in ab.effects):
            run_ability(ab, core, None, st)
            break

    assert _counters(core, "steam") >= 1


def test_an_unresolvable_target_falls_back_to_the_source():
    """A target shape the resolver does not recognise must not silently pick
    some other object — it keeps the old behaviour and stays reported by
    scripts/audit_params.py."""
    from engine.card_effects.dsl.effect_types import _object_target_spec

    for target in ("controlled_aura_with_ward", "ally", "opponent", "self",
                   {"type": "CARD"}, None, 7):
        assert _object_target_spec(target) is None, target


def test_the_canonical_shape_is_recognised():
    from engine.card_effects.dsl.effect_types import _object_target_spec

    for target in ({"controller": "OPPONENT", "zone": "EQUIPMENT"},
                   {"zones": ["EQUIPMENT", "WEAPON"]},
                   {"name": "Treasure Island"},
                   {"filter": [{"type": "CARD_IS_TYPE", "card_type": "Aura"}]}):
        assert _object_target_spec(target) == target


def test_base_defense_condition_reads_the_printed_value():
    """BASE_DEFENSE_LTE was the corpus's only invented condition type, hidden
    because it sat inside a target dict where conditions are never compiled."""
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _state()
    fn = compile_condition("BASE_DEFENSE_LTE", {"amount": 2})

    low = _card("nullrune_robe")
    low.base_defense = 2
    high = _card("nullrune_robe")
    high.base_defense = 3

    assert fn(low, None, st) is True
    assert fn(high, None, st) is False

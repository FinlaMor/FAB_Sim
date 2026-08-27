""""Instant cards you play this turn get go again" — set a flag, read by nothing.

Two cards grant a keyword to every matching card PLAYED for the rest of the
turn. Both were written as an activated SET_FLAG plus a STATIC gated on that
flag, and nothing dispatches a plain STATIC — so the flag was set and read by
nothing at all.

This is neither of the shapes that already existed. GRANT_NEXT_ATTACK is a
one-shot consumed by the NEXT attack; a continuous effect on a card cannot see
cards that are not in play yet. The grant is turn-scoped state on the player,
matched by the same filter mechanism as the cost reductions, and consulted where
a resolving card's effective keywords decide whether it returns an action point.

perch_grapplers was worse than dead: its ACTIVATE was gated on FLAG_SET of the
flag IT SETS, so the ability could only be used after it had already been used.
It could never be activated at all.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.loader import load_all_cards, get_card
from tests.conftest import _make_state
from tests.conftest import _card_json

load_all_cards()
DB = CardDB()

#: A real Instant with no printed go again, so the grant is the only source of
#: it, and a real non-attack action to check the filter excludes.
INSTANT = "a_drop_in_the_ocean_blue"
NON_INSTANT = "10000_year_reunion_red"   # Action, not Instant


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


def _grant(st, source, keyword, filt):
    compile_effect("GRANT_KEYWORD_TO_PLAYED",
                   {"keyword": keyword, "filter": filt})(source, None, st)


def _resolve_played(st, card, player_id=1):
    """Resolve `card` as a played non-attack layer and report the action point.

    This is the path the grant has to reach: engine._resolve_layer computes a
    resolving card's effective keywords and returns an action point when it has
    go again.
    """
    from engine.state import StackEntry

    # is_attack is a read-only property derived from the card and the layer
    # type, and the go-again branch only runs for NON-attack card layers -- so
    # the card under test has to genuinely be one, not be forced.
    entry = StackEntry(player_id=player_id, card=card, layer_type='card',
                       layer_position=1)
    assert not entry.is_attack, f"{card.slug} is an attack layer"
    entry.pitched_for_attack = []
    st.active_player = player_id
    st.stack_entries = [entry]
    before = st.players[player_id].action_points
    E.resolve_stack(st)
    return st.players[player_id].action_points - before


def test_a_granted_keyword_reaches_a_card_played_later():
    st = _state()
    source = _card("lightning_greaves")
    instant = _card(INSTANT)

    assert _resolve_played(st, instant) == 0, "it had go again before the grant"

    _grant(st, source, "go again", [{"type": "CARD_IS_TYPE",
                                     "card_type": "Instant"}])
    again = _card(INSTANT)
    assert _resolve_played(st, again) == 1, "the granted go again did not apply"


def test_the_grant_respects_its_filter():
    st = _state()
    _grant(st, _card("lightning_greaves"), "go again",
           [{"type": "CARD_IS_TYPE", "card_type": "Instant"}])

    action = _card(NON_INSTANT)
    assert _resolve_played(st, action) == 0, (
        "a non-instant took the instant-only grant")


def test_the_grant_covers_every_matching_card_not_just_the_next():
    """The difference from GRANT_NEXT_ATTACK: it is not consumed on use."""
    st = _state()
    _grant(st, _card("lightning_greaves"), "go again",
           [{"type": "CARD_IS_TYPE", "card_type": "Instant"}])

    for i in range(3):
        card = _card(INSTANT)
        assert _resolve_played(st, card) == 1, f"grant expired after {i} uses"


def test_the_grant_ends_with_the_turn():
    """Nothing consumes it, so the turn boundary is the ONLY thing that ends it.

    Driven through the real end phase — clearing the list in the test and then
    asserting it is empty would pass whether the engine clears it or not, which
    is exactly the vacuous shape this codebase keeps finding.
    """
    st = _state()
    st.active_player = 1
    _grant(st, _card("lightning_greaves"), "go again",
           [{"type": "CARD_IS_TYPE", "card_type": "Instant"}])
    assert st.players[1].dsl_play_keyword_grants, "the grant was not recorded"

    E._end_phase_iter(st)

    assert not getattr(st.players[1], "dsl_play_keyword_grants", []), (
        "the grant outlived the turn, so it is permanent")


def test_a_card_played_after_the_turn_ends_has_no_go_again():
    """The observable consequence of the cleanup above."""
    st = _state()
    st.active_player = 1
    _grant(st, _card("lightning_greaves"), "go again",
           [{"type": "CARD_IS_TYPE", "card_type": "Instant"}])
    E._end_phase_iter(st)

    later = _card(INSTANT)
    assert _resolve_played(st, later) == 0, "the grant still applied next turn"


def test_lightning_greaves_grants_on_activation():
    st = _state()
    source = _card("lightning_greaves")
    st.players[1].permanents.cards.append(source)

    ability = get_card("lightning_greaves").abilities[0]
    for eff in ability.effects:
        eff.fn(source, None, st)

    grants = getattr(st.players[1], "dsl_play_keyword_grants", [])
    assert grants, "activating Lightning Greaves granted nothing"
    assert str(grants[0]["keyword"]).lower().replace("_", " ") == "go again"


def test_perch_grapplers_is_not_gated_on_the_flag_it_sets():
    """Its ACTIVATE required the flag it itself set, so it could never run."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(_card_json(root, "perch_grapplers.json").read_text(encoding="utf-8"))
    for ability in raw.get("abilities") or []:
        set_flags = {e.get("flag") for e in ability.get("effects") or []
                     if e.get("type") == "SET_FLAG"}
        read_flags = {c.get("flag") for c in ability.get("conditions") or []
                      if c.get("type") == "FLAG_SET"}
        assert not (set_flags & read_flags), (
            f"ability gated on a flag it sets: {set_flags & read_flags}")


@pytest.mark.parametrize("slug", ["lightning_greaves", "perch_grapplers"])
def test_neither_card_still_uses_a_dead_static(slug):
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(_card_json(root, f"{slug}.json").read_text(encoding="utf-8"))
    types = [(a.get("ability_type") or "").upper() for a in raw.get("abilities") or []]
    assert "STATIC" not in types, types


# ── a hero's permanent static, re-established each turn ────────────────────
def test_teklovossen_grants_go_again_to_mechanologist_attacks():
    """"Your Mechanologist attack action cards get go again."

    A hero's PERMANENT static, expressed with the turn-scoped grant list: it is
    cleared in the end phase, so the hero re-establishes it at the start of each
    of its controller's turns. Attack action cards are only playable on your own
    turn, so that covers the whole window.
    """
    from engine.card_effects.dsl.interpreter import run_ability
    from engine.card_effects.dsl.loader import get_card

    st = _state()
    st.active_player = 1
    hero = _card("teklovossen_the_mechropotent")
    run_ability(get_card("teklovossen_the_mechropotent").abilities[2],
                hero, None, st)

    grants = getattr(st.players[1], "dsl_play_keyword_grants", [])
    assert grants, "the hero granted nothing"
    assert str(grants[0]["keyword"]).lower().replace("_", " ") == "go again"

    # ATTACK go again is decided from combat.keywords in the resolution step,
    # not from the non-attack layer path -- so the grant has to reach the attack
    # recalculation too, or it misses every card this text is about.
    from engine.state import CombatState
    mech = _card("wounded_bull_red")
    mech.classes = ["Mechanologist"]
    mech.keywords = []
    power = mech.base_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=mech, keywords=[])
    st.combat.base_attack_power = power
    E._apply_turn_attack_effects(st, mech)
    E._register_card_continuous_effects(st, mech)
    E._recalculate_attack_power(st)
    assert any(str(k).lower().replace("_", " ") == "go again"
               for k in st.combat.keywords), (
        f"the grant did not reach the attack's keywords: {st.combat.keywords}")


def test_teklovossen_does_not_grant_to_other_classes():
    from engine.card_effects.dsl.interpreter import run_ability
    from engine.card_effects.dsl.loader import get_card
    from engine.play import _cost_mod_matches

    st = _state()
    st.active_player = 1
    run_ability(get_card("teklovossen_the_mechropotent").abilities[2],
                _card("teklovossen_the_mechropotent"), None, st)
    grant = st.players[1].dsl_play_keyword_grants[0]

    mech = _card(INSTANT)
    mech.classes = ["Mechanologist"]
    mech.types = ["Action"]
    mech.subtypes = ["Attack"]
    other = _card(INSTANT)
    other.classes = ["Guardian"]
    other.types = ["Action"]
    other.subtypes = ["Attack"]

    assert _cost_mod_matches(st, grant, mech) is True
    assert _cost_mod_matches(st, grant, other) is False, (
        "it granted go again to a non-Mechanologist card")


def test_teklovossen_no_longer_grants_a_fabricated_defence_bonus():
    """"This counts as having 4 Evos equipped" was MODIFY_DEFENSE_VALUE +4."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(_card_json(root, "teklovossen_the_mechropotent.json")
                     .read_text(encoding="utf-8"))

    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "MODIFY_DEFENSE_VALUE":
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(raw.get("abilities", []))
    assert not found, f"the fabricated +4{{d}} is back: {found}"

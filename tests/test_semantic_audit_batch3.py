"""Duplicate-slug guard, crowd-cheer unification, and the one-shot
"next attack gains <keyword>" primitive.

All three came out of resolving two duplicate card slugs: the guard so a
duplicate can never again be settled by filesystem walk order, and the other
two because the cards involved needed primitives that did not exist.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.card_effects.dsl as dsl
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.loader import (
    DUPLICATE_SLUGS, LOAD_ERRORS, get_card, load_all_cards,
)
from tests.conftest import _make_card, _make_state


def _src(pid=1):
    card = _make_card(slug="src", name="src")
    card.owner = card.controller = pid
    return card


# ------------------------------------------------------------- duplicate slugs
def test_real_corpus_has_no_duplicate_slugs():
    load_all_cards()
    assert DUPLICATE_SLUGS == {}, (
        f"a slug is defined by more than one JSON file: {DUPLICATE_SLUGS}"
    )


def test_duplicate_slug_is_rejected_not_silently_resolved():
    """Two files claiming one slug used to mean the last one WALKED won, so the
    live definition depended on filesystem order and the loser could be the
    correct one. An ambiguous definition must count as no definition."""
    d = Path(tempfile.mkdtemp())
    try:
        (d / "a").mkdir()
        (d / "b").mkdir()
        (d / "a" / "dupe.json").write_text(
            json.dumps({"slug": "dupe", "abilities": []}), encoding="utf-8")
        (d / "b" / "dupe.json").write_text(
            json.dumps({"slug": "dupe", "abilities": []}), encoding="utf-8")
        (d / "a" / "fine.json").write_text(
            json.dumps({"slug": "fine", "abilities": []}), encoding="utf-8")

        assert load_all_cards(d) == 1                 # only "fine" counts
        assert get_card("fine") is not None
        assert get_card("dupe") is None              # ambiguous => unimplemented
        assert "dupe" in DUPLICATE_SLUGS
        assert len(DUPLICATE_SLUGS["dupe"]) == 2     # both paths named
        assert "dupe" in LOAD_ERRORS
    finally:
        shutil.rmtree(d)
        load_all_cards()                             # restore the real corpus


# ------------------------------------------------------------- crowd cheer
def test_crowd_cheer_is_visible_to_other_cards():
    """Cards used to hand-roll SET_FLAG with four different private spellings
    (CROWD_CHEERS, CROWD_CHEERS_ACTIVE, THE_CROWD_CHEERS, CHEERED_THIS_TURN),
    so a cheer was invisible to every card but the one that caused it."""
    st = _make_state()
    src = _src()
    is_cheered = compile_condition("IS_CHEERED", {})
    assert is_cheered(src, None, st) is False
    compile_effect("CROWD_CHEER", {})(src, None, st)
    assert is_cheered(src, None, st) is True
    # the opponent was not cheered
    assert is_cheered(_src(2), None, st) is False


def test_crowd_cheer_sets_the_cr_keyword_state():
    """CROWD_CHEER routes through effect_keywords.cheer (CR 8.5.57), which was
    dead code called by nothing but its own unit test."""
    st = _make_state()
    compile_effect("CROWD_CHEER", {})(_src(), None, st)
    assert st.players[1].class_counters.get("cheered_this_turn") == 1


def test_is_cheered_accepts_the_legacy_flag_spellings():
    """A cheer recorded by an older path must still be visible."""
    st = _make_state()
    is_cheered = compile_condition("IS_CHEERED", {})
    st.players[1].current_turn_effects.append("crowd_cheers")
    assert is_cheered(_src(), None, st) is True


def test_crowd_boo_still_works_and_now_sets_cr_state():
    """effect_crowd_boos gained the same routing; the existing IS_BOOED path
    must be unchanged."""
    st = _make_state()
    src = _src()
    is_booed = compile_condition("IS_BOOED", {})
    assert is_booed(src, None, st) is False
    compile_effect("CROWD_BOO", {})(src, None, st)
    assert is_booed(src, None, st) is True
    assert st.players[1].class_counters.get("booed_this_turn") == 1


def test_comeback_kid_red_and_blue_share_one_cheer_state():
    """The two halves of the cycle used DIFFERENT private flags, so neither
    could see the other's cheer."""
    load_all_cards()
    for slug in ("comeback_kid_red", "comeback_kid_blue"):
        cd = get_card(slug)
        blob = json.dumps([
            {"conditions": [c.condition_type for c in a.conditions],
             "effects": [e.effect_type for e in a.effects]}
            for a in cd.abilities
        ])
        assert "CROWD_CHEER" in blob and "IS_CHEERED" in blob
        assert "FLAG_SET" not in blob


# ------------------------------------- one-shot "next attack gains <keyword>"
def test_grant_next_attack_queues_a_one_shot_entry():
    st = _make_state()
    compile_effect("GRANT_NEXT_ATTACK", {"keyword": "GO_AGAIN"})(_src(), None, st)
    queued = st.players[1].dsl_queued_attack_mods
    assert queued == [{"mod": "grant_keyword", "keyword": "Go Again", "filter": []}]


def test_grant_next_attack_applies_once_then_is_consumed():
    """"Your NEXT attack this turn" — the whole point is that the second attack
    does not get it. Authored as a turn-long flag it buffed every attack."""
    from engine.engine import _apply_turn_attack_effects
    from engine.state import CombatState

    st = _make_state()
    compile_effect("GRANT_NEXT_ATTACK", {"keyword": "GO_AGAIN"})(_src(), None, st)

    def _attack():
        card = _make_card(slug="atk", name="atk", types=["Action", "Attack"])
        card.owner = card.controller = 1
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                                keywords=[], attack_card=card)
        _apply_turn_attack_effects(st, card)
        return list(st.combat.keywords or [])

    assert "Go Again" in _attack()          # first attack gets it
    assert "Go Again" not in _attack()      # second does not — it was consumed
    assert st.players[1].dsl_queued_attack_mods == []


def test_grant_next_attack_honours_its_filter():
    """Driving Blade grants only to a WEAPON attack, so a non-weapon attack
    must neither receive the keyword nor consume the entry."""
    from engine.engine import _apply_turn_attack_effects
    from engine.state import CombatState

    st = _make_state()
    compile_effect("GRANT_NEXT_ATTACK",
                   {"keyword": "GO_AGAIN",
                    "filter": [{"type": "ATTACK_IS_WEAPON"}]})(_src(), None, st)

    def _attack(from_weapon):
        card = _make_card(slug="atk", name="atk", types=["Action", "Attack"])
        card.owner = card.controller = 1
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                                keywords=[], attack_card=card)
        st.combat.from_weapon = from_weapon
        _apply_turn_attack_effects(st, card)
        return list(st.combat.keywords or [])

    assert "Go Again" not in _attack(False)                 # non-weapon: no grant
    assert st.players[1].dsl_queued_attack_mods != []       # and not consumed
    assert "Go Again" in _attack(True)                      # weapon attack gets it
    assert st.players[1].dsl_queued_attack_mods == []


def test_agility_token_grants_go_again_to_one_attack():
    """The Agility token's go-again clause was a TODO in one implementation and
    a turn-long flag in the duplicate that shadowed it."""
    load_all_cards()
    st = _make_state()
    token = _make_card(slug="agility", name="Agility", types=["Token"], subtypes=["Aura"])
    token.owner = token.controller = 1
    st.players[1].permanents.add(token)
    dsl.dispatch(st, "START_OF_TURN", "agility", card=token, event=None)
    assert st.players[1].dsl_queued_attack_mods == [
        {"mod": "grant_keyword", "keyword": "Go Again", "filter": []}]

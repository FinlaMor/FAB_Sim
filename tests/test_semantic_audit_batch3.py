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


# ------------------------------------------------ pitch-zone power filter
def test_card_in_zone_power_filter():
    """"a card with 6 or more {p} in your pitch zone". Cards authored this as
    pitch_power_gte on REF_PITCH_IS, which tests a REFERENCED card's PITCH VALUE
    and defaults to pitch 1 — so it really asked "is it red?"."""
    st = _make_state()
    src = _src()
    cond = compile_condition("CARD_IN_ZONE", {"zone": "pitch", "power_gte": 6})
    assert cond(src, None, st) is False
    st.players[1].pitch.add(_make_card(slug="weak", name="weak", base_power=3))
    assert cond(src, None, st) is False
    st.players[1].pitch.add(_make_card(slug="big", name="big", base_power=6))
    assert cond(src, None, st) is True
    # legacy key name resolves to the same filter
    assert compile_condition(
        "CARD_IN_ZONE", {"zone": "pitch", "pitch_power_gte": 6})(src, None, st) is True


def test_card_in_zone_power_filter_skips_cards_with_no_power():
    st = _make_state()
    src = _src()
    st.players[1].pitch.add(_make_card(slug="equip", name="equip", types=["Equipment"]))
    assert compile_condition(
        "CARD_IN_ZONE", {"zone": "pitch", "power_gte": 1})(src, None, st) is False


# ------------------------------------------------ PAY_OR_ELSE with a counter cost
def _counter_state(steam):
    """Prismatic Lens is an Item — a plain Action would be redirected out of the
    permanents zone by the CR 3.13.2 entry rule and never land there."""
    st = _make_state()
    card = _make_card(slug="lens", name="lens", types=["Item"])
    card.owner = card.controller = 1
    st.players[1].permanents.add(card)
    assert card in st.players[1].permanents.cards      # fixture sanity
    # Capture the counter key NOW: destroying the card moves it to the
    # graveyard, so a key rebuilt from card.zone afterwards would silently look
    # up a different entry and make these assertions meaningless.
    key = (card.slug, card.zone, "steam")
    if steam:
        st.players[1].counters[key] = steam
    return st, card, key


def test_pay_or_else_counter_cost_removes_the_counter_when_paid():
    """"destroy this UNLESS you remove a steam counter from it" — the two
    branches are mutually exclusive; the card used to do BOTH every turn."""
    st, card, key = _counter_state(1)

    def _pay(state, options, context, **kwargs):
        return "pay"

    st.player_agents = {1: _pay, 2: _pay}
    compile_effect("PAY_OR_ELSE", {
        "counter_type": "steam", "amount": 1,
        "on_failure": [{"type": "DESTROY_PERMANENT", "target": "self"}],
    })(card, None, st)
    assert st.players[1].counters.get(key, 0) == 0
    assert card in st.players[1].permanents.cards      # survived


def test_pay_or_else_counter_cost_runs_on_failure_when_declined():
    st, card, key = _counter_state(1)

    def _decline(state, options, context, **kwargs):
        return "decline"

    st.player_agents = {1: _decline, 2: _decline}
    compile_effect("PAY_OR_ELSE", {
        "counter_type": "steam", "amount": 1,
        "on_failure": [{"type": "DESTROY_PERMANENT", "target": "self"}],
    })(card, None, st)
    assert st.players[1].counters.get(key, 0) == 1
    assert card not in st.players[1].permanents.cards  # destroyed


def test_pay_or_else_counter_cost_with_no_counter_cannot_pay():
    """No counter to remove: the else-branch is forced, not skipped."""
    st, card, key = _counter_state(0)

    def _pay(state, options, context, **kwargs):
        return "pay"

    st.player_agents = {1: _pay, 2: _pay}
    compile_effect("PAY_OR_ELSE", {
        "counter_type": "steam", "amount": 1,
        "on_failure": [{"type": "DESTROY_PERMANENT", "target": "self"}],
    })(card, None, st)
    assert card not in st.players[1].permanents.cards


# ------------------------------------------------------------- dangling flags
def test_lightning_flow_flag_is_actually_written_when_a_lightning_card_is_played():
    """Every Lightning Flow card read "played_lightning" out of
    current_turn_effects and NOTHING wrote it, so the mechanic was inert —
    ability_keywords.check_lightning_flow could never return True."""
    from engine.actions import Action, ActionType
    from engine.play import _apply_play_card

    st = _make_state()
    lightning = _make_card(slug="arc_lightning_yellow", name="Arc Lightning",
                           talents=["Lightning"])
    lightning.owner = lightning.controller = 1
    st.players[1].hand.add(lightning)
    assert "played_lightning" not in st.players[1].current_turn_effects
    _apply_play_card(st, Action(type=ActionType.PLAY_CARD, player_id=1, card=lightning))
    assert "played_lightning" in st.players[1].current_turn_effects

    from engine.card_effects.ability_keywords import check_lightning_flow
    assert check_lightning_flow(st, 1) is True


def test_non_lightning_card_does_not_set_lightning_flow():
    from engine.actions import Action, ActionType
    from engine.play import _apply_play_card

    st = _make_state()
    other = _make_card(slug="plain", name="Plain", talents=["Elemental"])
    other.owner = other.controller = 1
    st.players[1].hand.add(other)
    _apply_play_card(st, Action(type=ActionType.PLAY_CARD, player_id=1, card=other))
    assert "played_lightning" not in st.players[1].current_turn_effects


def test_renamed_flags_now_match_what_the_engine_writes():
    """These families read flags nothing set. The engine records fusion as
    "fused_<slug>", boost as "boosted_this_turn" and a played Lightning card as
    "played_lightning" — all lowercase; the cards used bare uppercase names."""
    import glob
    load_all_cards()
    dead = {"FUSED", "FUSED_FLAG", "FUSION", "BOOSTED", "BOOSTED_THIS_TURN",
            "BOOSTED_ATTACK_THIS_TURN", "LIGHTNING_PLAYED_THIS_TURN", "LIGHTNING_FUSED"}
    offenders = []

    def walk(o, slug):
        if isinstance(o, dict):
            if (o.get("type") or "").upper() == "FLAG_SET" and o.get("flag") in dead:
                offenders.append((slug, o["flag"]))
            for v in o.values():
                walk(v, slug)
        elif isinstance(o, list):
            for v in o:
                walk(v, slug)

    for f in glob.glob("engine/card_effects/json/**/*.json", recursive=True):
        if "needs_review" in f or "_work_queue" in f:
            continue
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict):
            walk(d.get("abilities", []), Path(f).stem)
    assert offenders == [], f"cards still reading a never-set flag: {offenders}"


# ------------------------------------ generic "destroyed a <thing> this turn"
def test_destroyed_this_turn_records_slug_and_types():
    """One generic condition replaces the per-card flags cards invented
    (MIGHT_TOKEN_DESTROYED_THIS_TURN, ITEM_DESTROYED_THIS_TURN, ...), none of
    which anything ever set."""
    from engine.effect_keywords import destroy

    st = _make_state()
    token = _make_card(slug="might", name="Might", types=["Token"], subtypes=["Might"])
    token.owner = token.controller = 1
    st.players[1].permanents.add(token)
    src = _src()

    by_slug = compile_condition("DESTROYED_THIS_TURN", {"name": "Might"})
    by_type = compile_condition("DESTROYED_THIS_TURN", {"name": "Token"})
    other = compile_condition("DESTROYED_THIS_TURN", {"name": "Item"})

    assert by_slug(src, None, st) is False
    destroy(st, token)
    assert by_slug(src, None, st) is True     # matches the slug
    assert by_type(src, None, st) is True     # and the type
    assert other(src, None, st) is False      # but not an unrelated name


def test_destroyed_this_turn_player_opponent():
    """"if the ATTACK'S CONTROLLER has destroyed a Might token" reads the other
    player's record, not your own."""
    from engine.effect_keywords import destroy

    st = _make_state()
    token = _make_card(slug="might", name="Might", types=["Token"], subtypes=["Might"])
    token.owner = token.controller = 1
    st.players[1].permanents.add(token)
    destroy(st, token)

    mine, theirs = _src(1), _src(2)
    own = compile_condition("DESTROYED_THIS_TURN", {"name": "might"})
    opp = compile_condition("DESTROYED_THIS_TURN", {"name": "might", "player": "OPPONENT"})
    assert own(mine, None, st) is True        # p1 destroyed it
    assert opp(mine, None, st) is False       # p2 did not
    assert opp(theirs, None, st) is True      # from p2's view, p1 did


# ------------------------------------------------------ DEFEND_RESTRICTION
def _defend_setup(destroyed_a_might):
    """p2 defends p1's attack with Embrace Adversity."""
    from engine.state import CombatState
    load_all_cards()
    st = _make_state()
    st.active_player = 1
    atk = _make_card(slug="atk", name="atk", types=["Action", "Attack"])
    atk.owner = atk.controller = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            keywords=[], attack_card=atk)
    st.combat.attack_target = None

    shield = _make_card(slug="embrace_adversity", name="Embrace Adversity",
                        types=["Equipment"], subtypes=["Chest"], base_defense=2)
    shield.owner = shield.controller = 2
    st.players[2].chest.add(shield)

    if destroyed_a_might:
        from engine.effect_keywords import destroy
        token = _make_card(slug="might", name="Might", types=["Token"], subtypes=["Might"])
        token.owner = token.controller = 1          # the ATTACKER destroyed it
        st.players[1].permanents.add(token)
        destroy(st, token)
    return st, shield


def test_embrace_adversity_cannot_defend_without_the_destroyed_might():
    """"This may only defend an attack if the attack's controller has destroyed
    a Might token this turn." Previously the card carried a fabricated
    ON_DEFEND -> INTIMIDATE gated on a flag nothing set: dead twice over."""
    from engine.actions import get_defendable_cards

    st, shield = _defend_setup(destroyed_a_might=False)
    assert shield not in get_defendable_cards(st)


def test_embrace_adversity_may_defend_once_the_attacker_destroyed_a_might():
    from engine.actions import get_defendable_cards

    st, shield = _defend_setup(destroyed_a_might=True)
    assert shield in get_defendable_cards(st)


def test_defend_restriction_does_not_affect_ordinary_equipment():
    from engine.actions import get_defendable_cards
    from engine.state import CombatState

    load_all_cards()
    st = _make_state()
    st.active_player = 1
    atk = _make_card(slug="atk", name="atk", types=["Action", "Attack"])
    atk.owner = atk.controller = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            keywords=[], attack_card=atk)
    st.combat.attack_target = None
    plain = _make_card(slug="teklo_base_chest", name="Teklo Base Chest",
                       types=["Equipment"], subtypes=["Chest"], base_defense=2)
    plain.owner = plain.controller = 2
    st.players[2].chest.add(plain)
    assert plain in get_defendable_cards(st)


# ------------------------------------------------ OR / AND sub-condition key
def test_or_and_read_sub_conditions_authored_as_conditions():
    """Cards write sub-conditions under "conditions"; OR/AND read only
    "any"/"all". The mismatch produced an EMPTY combinator, which does not fail
    loudly — it collapses: any([]) is False so the OR could never fire and its
    ability was dead, all([]) is True so the AND removed its own gate. 54
    usages across ~50 cards."""
    st = _make_state()
    src = _src()
    true_c = {"type": "IS_ACTIVE_PLAYER", "value": True}
    false_c = {"type": "IS_ACTIVE_PLAYER", "value": False}

    # canonical keys still work
    assert compile_condition("OR", {"any": [false_c, true_c]})(src, None, st) is True
    assert compile_condition("AND", {"all": [true_c, false_c]})(src, None, st) is False
    # and so does the spelling cards actually use
    assert compile_condition("OR", {"conditions": [false_c, true_c]})(src, None, st) is True
    assert compile_condition("OR", {"conditions": [false_c]})(src, None, st) is False
    assert compile_condition("AND", {"conditions": [true_c, false_c]})(src, None, st) is False
    assert compile_condition("AND", {"conditions": [true_c]})(src, None, st) is True


def test_empty_combinator_is_not_a_truth_value():
    """An empty OR/AND is an authoring error. Neither silently killing the
    ability nor silently passing the gate is acceptable, so both read as "no
    restriction" and the real fault surfaces as an unknown inner type."""
    st = _make_state()
    src = _src()
    assert compile_condition("OR", {})(src, None, st) is True
    assert compile_condition("AND", {})(src, None, st) is True


def test_invalid_nested_condition_now_fails_at_load():
    """The empty-combinator bug meant inner conditions were never compiled, so
    invalid types inside OR/AND escaped the load gate entirely — a PHP
    identifier (TalentContainsAny) reached a shipped card that way."""
    import pytest
    with pytest.raises(ValueError):
        compile_condition("OR", {"conditions": [{"type": "TalentContainsAny"}]})

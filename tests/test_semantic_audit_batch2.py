"""Behavioral tests for param-key sweep pass 2.

Each of these keys was authored by card JSON but never read by the compiler, so
the clause was silently dropped — invisible to any per-card audit because the
card still loaded and still passed its own test. Each test pins the observable
behaviour the key is supposed to produce, plus the unrestricted form staying
unchanged where the key is optional.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.effect_types import compile_effect, _resolve_amount
from engine.state import CombatState, Step
from tests.conftest import _make_state, _make_card


def _accept_agent(state, options, context, **kwargs):
    """Affirm an optional prompt; else take the first option."""
    if not options:
        return None
    for o in options:
        if any(w in str(o).lower() for w in ("yes", "pay", "use", "may", "accept", "true")):
            return o
    return options[0]


def _src(pid=1):
    card = _make_card(slug="src", name="src")
    card.owner = card.controller = pid
    return card


# ------------------------------------------------------------- PAY_OR_DAMAGE
def test_pay_or_damage_accepts_named_resource_without_crashing():
    """`resource` sometimes names a resource type ("RESOURCE_POINTS") rather than
    a quantity, putting a str where the cost comparison expects an int. That
    raised TypeError mid-trigger; the quantity comes from `amount` in that style.
    """
    st = _make_state()
    st.player_agents = {1: _accept_agent, 2: _accept_agent}
    st.players[1].resources = 5
    life_before = st.players[1].life
    fn = compile_effect("PAY_OR_DAMAGE",
                        {"resource": "RESOURCE_POINTS", "amount": 1, "damage": 2})
    fn(_src(), None, st)  # must not raise
    # Either it paid 1 resource or it took the 2 damage — never both, never neither.
    paid = st.players[1].resources == 4
    took = st.players[1].life == life_before - 2
    assert paid != took


def test_pay_or_damage_runs_on_success_when_paid():
    """"You may pay {r}. If you do, X" — X lives under on_success and was dropped
    entirely, which made cards like Flex do nothing at all."""
    st = _make_state()
    st.player_agents = {1: _accept_agent, 2: _accept_agent}
    st.players[1].resources = 3
    before = st.players[1].life
    compile_effect("PAY_OR_DAMAGE",
                   {"resource_cost": 2,
                    "on_success": [{"type": "GAIN", "asset": "LIFE_POINTS", "amount": 3}]})(_src(), None, st)
    assert st.players[1].resources == 1
    assert st.players[1].life == before + 3


def test_pay_or_damage_skips_prompt_when_paying_buys_nothing():
    """No damage to avoid and no payoff: paying could only waste resources."""
    st = _make_state()
    st.player_agents = {1: _accept_agent, 2: _accept_agent}
    st.players[1].resources = 3
    compile_effect("PAY_OR_DAMAGE", {"resource_cost": 2})(_src(), None, st)
    assert st.players[1].resources == 3


# ----------------------------------------------------------------------- ROLL
def test_roll_reads_sides_alias_and_runs_on_success():
    """Die size is authored as `sides` or `faces`; effects that consume the
    result live under on_success and read it via ROLL_RESULT/HALF."""
    st = _make_state()
    before = st.players[1].life
    compile_effect("ROLL", {"sides": 6, "on_success": [
        {"type": "GAIN", "asset": "LIFE_POINTS",
         "amount": {"type": "HALF", "value": {"type": "ROLL_RESULT"}}}]})(_src(), None, st)
    assert 1 <= st._roll_result <= 6
    assert st.players[1].life - before == st._roll_result // 2


def test_resolve_amount_handles_nested_expression_dicts():
    st = _make_state()
    st._roll_result = 5
    assert _resolve_amount({"type": "ROLL_RESULT"}, st) == 5
    assert _resolve_amount({"type": "HALF", "value": {"type": "ROLL_RESULT"}}, st) == 2
    assert _resolve_amount("ROLL_NUMBER", st) == 5
    assert _resolve_amount(3, st) == 3


# ------------------------------------------------- singular "effect" authoring
def test_may_accepts_singular_effect_key():
    """A lone sub-effect authored as "effect": {...}; the list-only read made
    accepting the prompt do nothing."""
    st = _make_state()
    st.player_agents = {1: _accept_agent, 2: _accept_agent}
    before = st.players[1].life
    compile_effect("MAY", {"effect": {"type": "GAIN", "asset": "LIFE_POINTS", "amount": 2}})(_src(), None, st)
    assert st.players[1].life == before + 2


def test_apply_continuous_accepts_singular_effect_key():
    st = _make_state()
    compile_effect("APPLY_CONTINUOUS",
                   {"target": "PLAYER_ATTACKS",
                    "effect": {"type": "MODIFY_ATTACK", "mod": "add",
                               "amount": 1}})(_src(), None, st)
    assert st.players[1].dsl_continuous_effects[0]["modifications"] == [
        {"type": "MODIFY_ATTACK", "mod": "add", "amount": 1}]


# ----------------------------------------------------------------- conditions
def test_has_keyword_reads_keywords_list_and_normalises():
    """The list form fell back to an empty keyword and was always False, killing
    the whole ability. Matching folds "blood_debt" onto the stored "BloodDebt"."""
    cond = compile_condition("HAS_KEYWORD", {"keywords": ["blood_debt"]})
    have = _make_card(slug="a", name="a", keywords=["BloodDebt", "GoAgain"])
    lack = _make_card(slug="b", name="b", keywords=["Battleworn"])
    assert cond(have, None, None) is True
    assert cond(lack, None, None) is False
    assert compile_condition("HAS_KEYWORD", {"keyword": "Battleworn"})(lack, None, None) is True


def test_in_combat_combat_role_separates_attacker_and_defender():
    """Without combat_role, both role-gated branches fired in every combat."""
    st = _make_state()
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3, keywords=[],
                            attack_card=_make_card(slug="atk", name="atk",
                                                   types=["Action", "Attack"]))
    mine, theirs = _src(1), _src(2)
    atk = compile_condition("IN_COMBAT", {"combat_role": "ATTACKER"})
    dfd = compile_condition("IN_COMBAT", {"combat_role": "DEFENDER"})
    assert (atk(mine, None, st), dfd(mine, None, st)) == (True, False)
    assert (atk(theirs, None, st), dfd(theirs, None, st)) == (False, True)
    assert compile_condition("IN_COMBAT", {})(mine, None, st) is True


def test_card_in_zone_card_class_filter():
    """card_class matches class, talent or color; ignoring it let the condition
    fire on any card in the zone."""
    st = _make_state()
    src = _src()
    earth = _make_card(slug="e", name="e", classes=["NotClassed"], talents=["Earth"])
    st.players[1].pitch.add(earth)
    assert compile_condition(
        "CARD_IN_ZONE", {"zone": "pitch", "card_class": "Earth"})(src, None, st) is True
    assert compile_condition(
        "CARD_IN_ZONE", {"zone": "pitch", "card_class": "Guardian"})(src, None, st) is False
    st.players[1].pitch.add(_make_card(slug="g", name="g", classes=["Guardian"], talents=[]))
    assert compile_condition(
        "CARD_IN_ZONE", {"zone": "pitch", "card_class": "Guardian"})(src, None, st) is True


def test_card_in_zone_keywords_filter():
    st = _make_state()
    src = _src()
    st.players[1].pitch.add(_make_card(slug="p", name="p", keywords=["GoAgain"]))
    cond = compile_condition("CARD_IN_ZONE", {"zone": "pitch", "keywords": ["blood_debt"]})
    assert cond(src, None, st) is False
    st.players[1].pitch.add(_make_card(slug="d", name="d", keywords=["BloodDebt"]))
    assert cond(src, None, st) is True


def test_during_turn_phase_filter():
    """DURING_TURN ignored `phase`, so an end-phase-only clause ran all turn."""
    st = _make_state()
    st.individual_turns = 1
    src = _src()
    action = compile_condition("DURING_TURN", {"phase": "ACTION_PHASE"})
    end = compile_condition("DURING_TURN", {"phase": "END_PHASE"})
    st.step = Step.ACTION
    assert (action(src, None, st), end(src, None, st)) == (True, False)
    st.step = Step.END_PHASE_BEGINNING
    assert (action(src, None, st), end(src, None, st)) == (False, True)
    # combat happens inside the action phase (CR 4.3)
    st.step = Step.COMBAT_DAMAGE
    assert action(src, None, st) is True
    assert compile_condition("DURING_TURN", {})(src, None, st) is True


def test_attack_target_is_hero_hero_type_filter():
    """hero_type narrows "attacks a Revered hero" to that talent/class."""
    st = _make_state()
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3, keywords=[],
                            attack_card=_make_card(slug="atk", name="atk",
                                                   types=["Action", "Attack"]))
    st.combat.attack_target = None
    src = _src()
    st.players[2].hero = _make_card(slug="h", name="h",
                                    classes=["NotClassed"], talents=["Revered"])
    assert compile_condition(
        "ATTACK_TARGET_IS_HERO", {"hero_type": "Revered"})(src, None, st) is True
    assert compile_condition(
        "ATTACK_TARGET_IS_HERO", {"hero_type": "Wizard"})(src, None, st) is False
    assert compile_condition("ATTACK_TARGET_IS_HERO", {})(src, None, st) is True


# ============================================= per-card fixes exposed by the sweep
import engine.card_effects.dsl as dsl
from engine.card_effects.dsl.loader import load_all_cards


def _play(state, slug, pid=1, types=("Action",)):
    card = _make_card(slug=slug, name=slug, types=list(types))
    card.owner = card.controller = pid
    dsl.dispatch(state, "ON_PLAY", slug, card=card, event=None)
    return card


def test_reckless_charge_blue_gains_action_points_from_the_roll():
    """on_success was dropped and the AP was authored as a combat `keyword`
    rather than the ACTION_POINTS asset, so the card gained nothing."""
    load_all_cards()
    st = _make_state()
    before = st.players[1].action_points
    _play(st, "reckless_charge_blue")
    assert st.players[1].action_points - before == st._roll_result // 2


def test_reckless_charge_blue_draws_only_after_a_six():
    """The DIE_ROLLED_SIX flag used to be set unconditionally, so the draw
    happened on every roll."""
    load_all_cards()
    st = _make_state()
    hand_before = len(st.players[1].hand.cards)
    _play(st, "reckless_charge_blue")
    drew = len(st.players[1].hand.cards) - hand_before
    assert drew == (1 if st._roll_result == 6 else 0)
    assert ("DIE_ROLLED_SIX" in st.players[1].current_turn_effects) == (st._roll_result == 6)


def test_controls_token_type_comparison_against_opponent():
    """"if you control less Gold than an opponent" — `comparison` and `opponent`
    were both ignored, so the card fired whenever it controlled ANY Gold, which
    is roughly the opposite of the printed condition."""
    st = _make_state()
    src = _src()

    def _gold(pid):
        g = _make_card(slug="gold", name="Gold", types=["Token"], subtypes=["Gold"])
        g.owner = g.controller = pid
        return g

    less = compile_condition("CONTROLS_TOKEN_TYPE",
                             {"token_type": "Gold", "comparison": "lt", "opponent": True})
    st.players[2].permanents.add(_gold(2))
    st.players[2].permanents.add(_gold(2))
    assert less(src, None, st) is True          # 0 vs 2
    for _ in range(3):
        st.players[1].permanents.add(_gold(1))
    assert less(src, None, st) is False         # 3 vs 2
    # threshold form is unchanged
    assert compile_condition("CONTROLS_TOKEN_TYPE", {"token_type": "Gold"})(src, None, st) is True


def _decline_agent(state, options, context, **kwargs):
    """Refuse an optional payment; else take the last option."""
    for o in options or []:
        if "decline" in str(o).lower():
            return o
    return options[-1] if options else None


def test_aether_icevein_blue_opponent_discards_only_when_fused():
    """Text: "they discard a card unless they pay {r}{r}" — the OPPONENT pays.
    The card had invented pay_cost/damage_effect keys and did nothing."""
    load_all_cards()

    def _setup():
        st = _make_state()
        st.player_agents = {1: _decline_agent, 2: _decline_agent}
        st.players[2].resources = 0          # cannot pay
        for i in range(3):
            c = _make_card(slug=f"h{i}", name=f"h{i}")
            c.owner = c.controller = 2
            st.players[2].hand.add(c)
        return st

    st = _setup()
    st.players[1].current_turn_effects.append("FUSED")
    before = len(st.players[2].hand.cards)
    _play(st, "aether_icevein_blue")
    assert len(st.players[2].hand.cards) == before - 1

    st2 = _setup()                            # not fused: clause does not apply
    before2 = len(st2.players[2].hand.cards)
    _play(st2, "aether_icevein_blue")
    assert len(st2.players[2].hand.cards) == before2

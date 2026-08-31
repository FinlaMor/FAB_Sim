"""The gated-keyword defect is not about go again.

`loader.conditional_keywords` strips a printed keyword for any of the eleven
entries in `_GRANTABLE_KEYWORDS`, and the go-again backlog was only ever the
slice of the problem that happened to be swept for. Widening the same sweep to
the other ten keywords found 14 more cards, 9 of them Overpower.

Four are fixed here, and three of those are the safest kind of conversion
available: their printed text is a sentence already fixed under go again, with
one word changed.

    torque_tuned_red/blue  "If an item you control has been destroyed this
                           turn, this gets OVERPOWER."   <- soup_up_red
    vantage_point_red      "If you've played or created an aura this turn,
                           this gets OVERPOWER."         <- runerager_swarm_blue
    glaring_impact_blue    "you may CHARGE your hero's soul. If a yellow card
                           is charged this way, this gets OVERPOWER."
                                                         <- light_the_way_red

They carried the same defects as their go-again twins, not merely the same
text. torque_tuned's clause hung off ON_DEFEND -- the card's OTHER half --
exactly as soup_up_red's did. vantage_point asked only about CREATED auras,
missing the played half, exactly as runerager_swarm_blue did. Two independently
authored cards do not acquire identical defects by chance: the sentence was
being read the same wrong way each time it appeared.

GLARING IMPACT'S COST HAD TO MOVE. Its grant is now a WHILE_STATIC, and
interpreter._run_ability checks and pays an ability's additional_costs on EVERY
dispatch -- so leaving the CHARGE there would charge the hero's soul once per
attack-power recalculation. The card-level `cost` is checked for legality and
paid once. Same trap as Breakneck Battery, third card to hit it.

ONE CARD THE SWEEP MATCHED IS CORRECT AS AUTHORED and must not be touched.
weave_ice_yellow reads "The next Ice or Elemental attack action card you play
this turn gains +2{p}. If it's fused, IT GAINS DOMINATE" -- the dominate
belongs to that NEXT card, and Weave Ice prints the keyword only because the
card DB flattens the sentence. That is the Luminaris case wearing a different
keyword, and the pronoun rule had to learn a second referent shape to see it.
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
from engine.card_effects.dsl.loader import (_kw_key, conditional_keywords,
                                            get_card, load_all_cards)
from engine.effect_keywords import _record_turn_event
from tests.conftest import (_card_json, _make_state, attack_with, owned_card,
                            recalculate_attack)

load_all_cards()
DB = CardDB()
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

CONVERTED = ["torque_tuned_red", "torque_tuned_blue", "vantage_point_red",
             "glaring_impact_blue"]


def _state(accept=True):
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": (o[0] if accept else o[-1])
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _overpower(st):
    return any(_kw_key(k) == "overpower" for k in st.combat.keywords)


def _attacking(st, slug):
    card = copy.deepcopy(DB.get(slug))
    assert card is not None, slug
    card.owner = card.controller = 1
    return attack_with(st, card)


def _raw(slug):
    return json.loads(_card_json(JSON_ROOT, slug + ".json")
                      .read_text(encoding="utf-8"))


# --- the printed keyword is conditional, in the one shape that strips --------

@pytest.mark.parametrize("slug", CONVERTED)
def test_the_printed_overpower_is_conditional_now(slug):
    assert "overpower" in conditional_keywords(slug), (
        slug + " still has an unconditional printed Overpower, so its gate is "
        "decoration")


@pytest.mark.parametrize("slug", CONVERTED)
def test_the_grant_uses_the_only_shape_that_strips(slug):
    granting = []
    for ability in _raw(slug)["abilities"]:
        for eff in ability.get("effects", []):
            name = eff.get("keyword") if eff.get("type") == "GAIN" else eff.get("type")
            if _kw_key(str(name or "")) == "overpower":
                granting.append(ability)
                break
    assert granting, slug + " no longer grants overpower at all"
    for ability in granting:
        assert ability["ability_type"] == "WHILE_STATIC", ability["ability_type"]
        types = [c.get("type") for c in ability.get("conditions", [])]
        assert "SOURCE_IS_ATTACK" in types, types


def test_the_stripping_is_not_go_again_specific():
    """The premise for this whole file. conditional_keywords covers every
    entry in _GRANTABLE_KEYWORDS; the go-again backlog was one slice of the
    problem, not the problem."""
    from engine.card_effects.dsl.loader import _GRANTABLE_KEYWORDS
    keys = {_kw_key(k) for k in _GRANTABLE_KEYWORDS}
    for keyword in ("goagain", "overpower", "dominate", "intimidate",
                    "piercing", "stealth", "phantasm"):
        assert keyword in keys, (
            keyword + " is no longer strippable, so cards gating it print it "
            "unconditionally again")


# --- "if an item you control has been destroyed this turn" ------------------

@pytest.mark.parametrize("slug", ["torque_tuned_red", "torque_tuned_blue"])
def test_torque_tuned_gains_overpower_after_an_item_is_destroyed(slug):
    st = _state()
    st.players[1].current_turn_effects.append("destroyed_this_turn:item")
    _attacking(st, slug)

    recalculate_attack(st)

    assert _overpower(st), "an item was destroyed, so overpower is due"


@pytest.mark.parametrize("slug", ["torque_tuned_red", "torque_tuned_blue"])
def test_torque_tuned_withholds_overpower_with_no_destruction(slug):
    st = _state()
    _attacking(st, slug)

    recalculate_attack(st)

    assert not _overpower(st), (
        "overpower with no item destroyed -- the gate is decoration again")


@pytest.mark.parametrize("slug", ["torque_tuned_red", "torque_tuned_blue"])
def test_torque_tuned_keeps_its_galvanize(slug):
    """The overpower clause was wrongly hung off ON_DEFEND next to Galvanize.
    Moving it must not have taken Galvanize with it -- the mistake soup_up_red
    was one edit away from."""
    defends = [a for a in _raw(slug)["abilities"] if a.get("trigger") == "ON_DEFEND"]
    assert len(defends) == 1, (
        "expected exactly the Galvanize defend trigger, got %d" % len(defends))
    assert any(e.get("type") == "MAY" for e in defends[0]["effects"])


# --- "played or created an aura" -------------------------------------------

def _vantage(st):
    _attacking(st, "vantage_point_red")
    recalculate_attack(st)
    return _overpower(st)


def test_vantage_point_counts_a_created_aura():
    st = _state()
    _record_turn_event(st, 1, "create", "aura")
    assert _vantage(st)


def test_vantage_point_counts_a_played_aura():
    """The half it was missing, and the same half runerager_swarm_blue was
    missing. The sentence was read the same wrong way both times."""
    st = _state()
    _record_turn_event(st, 1, "play", "aura")
    assert _vantage(st), (
        "played an aura and got no overpower; the condition still only asks "
        "about CREATED auras")


def test_vantage_point_withholds_overpower_with_no_aura():
    assert not _vantage(_state())


# --- "if a yellow card is charged this way" ---------------------------------

def _glaring(colour, accept=True):
    st = _state(accept)
    card = copy.deepcopy(DB.get("glaring_impact_blue"))
    card.owner = card.controller = 1
    if colour:
        fodder = owned_card(1, "fodder", types=["Action"])
        fodder.base_color = colour
        st.players[1].hand.add(fodder)
    cost = get_card("glaring_impact_blue").play_cost
    payable = cost.check_fn(card, None, st)
    cost.pay_fn(card, None, st)
    attack_with(st, card)
    recalculate_attack(st)
    return st, card, payable


def test_glaring_impact_gains_overpower_for_a_yellow_charge():
    st, card, _ = _glaring("yellow")

    assert [c.slug for c in st.players[1].soul.cards] == ["fodder"], (
        "the card was not actually charged to the soul")
    assert _overpower(st), "a yellow card was charged, so overpower is due"


def test_glaring_impact_withholds_overpower_for_another_colour():
    st, _, _ = _glaring("red")

    assert not _overpower(st), (
        "overpower off a RED charge -- the colour gate is decoration")


def test_glaring_impact_withholds_overpower_when_declined():
    st, _, _ = _glaring("yellow", accept=False)

    assert not st.players[1].soul.cards, "charged despite declining"
    assert not _overpower(st), "declined the charge and still got overpower"


def test_glaring_impact_is_playable_with_an_empty_hand():
    """"You MAY charge" is an optional additional cost, and an optional cost
    must never block the play (CR 5.1.6)."""
    _, _, payable = _glaring(None)
    assert payable


def test_glaring_impacts_charge_cost_is_not_on_the_static():
    """_run_ability re-pays an ability's additional_costs on every dispatch,
    and this grant is a WHILE_STATIC -- one dispatch per attack-power
    recalculation. The cost belongs at card level, paid once."""
    raw = _raw("glaring_impact_blue")
    assert raw.get("cost", {}).get("type") == "CHARGE"
    assert not any(a.get("additional_cost") for a in raw["abilities"]), (
        "the charge cost moved back onto an ability; on a WHILE_STATIC that "
        "charges the hero's soul once per recalculation")


# --- the card the sweep matched that must NOT be converted ------------------

def test_weave_ice_keeps_its_unconditional_printed_dominate():
    """Its dominate is granted to "the next Ice or Elemental attack action card
    you play", not to itself. Stripping the printed keyword would take it from
    a card that is not the one the sentence is about."""
    assert "dominate" not in conditional_keywords("weave_ice_yellow"), (
        "weave_ice_yellow had its printed Dominate stripped, but the keyword "
        "belongs to another card -- this is the Luminaris mistake")


def test_weave_ice_does_not_grant_dominate_to_itself():
    raw = _raw("weave_ice_yellow")
    assert not any(_kw_key(str(e.get("keyword") or e.get("type") or "")) == "dominate"
                   for a in raw["abilities"] for e in a.get("effects", [])), (
        "a dominate grant was added to Weave Ice itself; the card hands it to "
        "the next card you play, and that clause is documented as unmodelled "
        "because fusion state is not tracked on the queued attack")


# --- premise ----------------------------------------------------------------

def test_the_printed_text_still_says_what_these_assert():
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]

    def text(slug):
        return (idx[slug].get("functionalText") or "").lower()

    assert "has been destroyed this turn" in text("torque_tuned_red")
    assert "played or created an aura this turn" in text("vantage_point_red")
    assert "yellow card is **charged** this way" in text("glaring_impact_blue")
    assert "the next ice or elemental attack action card you play" in text(
        "weave_ice_yellow")
    for slug in CONVERTED + ["weave_ice_yellow"]:
        printed = [str(k).lower() for k in (idx[slug].get("keywords") or [])]
        assert "overpower" in printed or "dominate" in printed, slug
    assert text("torque_tuned_red") == text("torque_tuned_blue"), (
        "the two printings have diverged, so sharing an implementation is no "
        "longer justified")

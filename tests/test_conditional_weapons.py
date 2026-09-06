"""Three weapons whose printed clause is a gated static.

Picked off the corpus frequency list — 46 unimplemented weapons account for
60,655 observed attack-states, and a weapon attacks on most of its controller's
turns, so one implementation covers a lot of real game.

  harmonized_kodachi  cost-0 card in your pitch zone -> its attacks get go again
  titans_fist         cost-3-or-more in your pitch zone -> +1{p}
  raydn_duskbane      charged this turn -> +3{p}

SOURCE_IS_ATTACK is on all three and does two different jobs. On the two that
grant a KEYWORD it is what makes loader.conditional_keywords strip the printed
copy — the card DB lists GoAgain unconditionally because it flattens the
sentence, and without the strip the gate cannot take the keyword away, leaving a
free permanent buff. On the pump it does something else entirely: a weapon sits
equipped all game, so an ungated MODIFY_ATTACK would pump every attack its
controller makes rather than this weapon's own.

RAYDN'S ACTIVATION COST IS THE LOAD-BEARING PART of that card and is asserted
below. engine/card.py derives a weapon's activation cost by counting {r} symbols
and only accepts a count > 0, so a printed cost of "0" left activation_cost None
— and play._add_weapon_attacks refuses to offer a weapon whose activation_cost
is None. Raydn could not attack at all. The DSL declaration must be TOP-LEVEL:
loader.compile_card reads raw["activation_cost"], so one nested inside an
ability is silently unread (high_riser has one there, which happens to be
harmless only because its printed text parses to the same number).
"""
import copy
import io
import json

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.loader import conditional_keywords, load_all_cards
from engine.state import CombatState, Step
from scripts.talishar_attack_replay import _announce_attack, _replay_agent
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()


@pytest.fixture(scope="module")
def fodder():
    """A real cost-0 card and a real cost-3+ card to put in the pitch zone."""
    root = __import__("pathlib").Path(__file__).resolve().parent.parent
    si = json.load(io.open(root / "card_data" / "slug_index.json",
                           encoding="utf-8"))["by_slug"]
    zero = next(s for s, e in si.items()
                if e.get("cost") == 0 and "Attack" in (e.get("subtypes") or []))
    three = next(s for s, e in si.items()
                 if isinstance(e.get("cost"), int) and e["cost"] >= 3)
    return zero, three


def _attack(slug, pitch=(), charged=False):
    st = _make_state()
    st.card_db = DB
    st.step = Step.ACTION
    st.active_player = 1
    st.combat = None
    st.player_agents = {1: _replay_agent, 2: _replay_agent}
    E._setup_dsl_listeners(st)
    for s in pitch:
        c = copy.deepcopy(DB.get(s))
        c.owner = c.controller = 1
        st.players[1].pitch.add(c)
    if charged:
        from engine.effect_keywords import _record_turn_event
        _record_turn_event(st, 1, "charge", "some_card", [], [], [])
    card = copy.deepcopy(DB.get(slug))
    card.owner = card.controller = 1
    power = card.raw_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = power
    st.combat.from_weapon = True
    E._apply_turn_attack_effects(st, card)
    E._register_card_continuous_effects(st, card)
    _announce_attack(st, card)
    E._recalculate_attack_power(st)
    return st


def _go_again(st):
    return "goagain" in {str(k).lower().replace(" ", "")
                         for k in (st.combat.keywords or [])}


def _base(slug):
    return DB.get(slug).raw_power or 0


# ------------------------------------------------------------ kodachi

def test_kodachi_gets_go_again_from_a_cost_zero_pitch(fodder):
    zero, _ = fodder
    assert _go_again(_attack("harmonized_kodachi", pitch=[zero]))


def test_kodachi_gets_nothing_from_an_empty_pitch():
    assert not _go_again(_attack("harmonized_kodachi"))


def test_kodachi_reads_cost_zero_exactly_not_as_absent(fodder):
    """`cost: 0` is an EXACT match. Zero is falsy, so a reader that treated a
    missing cost and a cost of 0 alike would fire on any pitched card."""
    _, three = fodder
    assert not _go_again(_attack("harmonized_kodachi", pitch=[three]))


def test_kodachis_printed_go_again_is_stripped():
    assert "GoAgain" in (DB.get("harmonized_kodachi").keywords or [])
    assert "goagain" in conditional_keywords("harmonized_kodachi")


# ------------------------------------------------------------ titan's fist

def test_titans_fist_pumps_off_an_expensive_pitch(fodder):
    _, three = fodder
    st = _attack("titans_fist", pitch=[three])
    assert st.combat.attack_power == _base("titans_fist") + 1


def test_titans_fist_ignores_a_cheap_pitch(fodder):
    zero, _ = fodder
    st = _attack("titans_fist", pitch=[zero])
    assert st.combat.attack_power == _base("titans_fist")


def test_titans_fist_grants_no_keyword(fodder):
    """It is a pump, not a keyword -- a GAIN slipped in here would be invisible
    to the power assertions above."""
    _, three = fodder
    assert not _go_again(_attack("titans_fist", pitch=[three]))


# ------------------------------------------------------------ raydn

def test_raydn_pumps_when_charged():
    st = _attack("raydn_duskbane", charged=True)
    assert st.combat.attack_power == _base("raydn_duskbane") + 3


def test_raydn_does_not_pump_without_a_charge():
    st = _attack("raydn_duskbane")
    assert st.combat.attack_power == _base("raydn_duskbane")


def test_raydn_has_a_zero_activation_cost_not_a_missing_one():
    """Without this the weapon cannot attack AT ALL: the printed-text parser
    counts {r} symbols and rejects a count of 0, and play._add_weapon_attacks
    requires activation_cost to be non-None before offering the attack."""
    card = DB.get("raydn_duskbane")
    assert card.activation_cost == 0, "0 is a real cost, not a missing one"
    assert card.has_per_turn_limit


def test_raydn_would_be_unplayable_on_the_printed_parse_alone():
    """Pins WHY the declaration exists, so removing it fails loudly here rather
    than silently making the weapon unusable."""
    import re
    text = json.load(io.open(
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "card_data" / "slug_index.json", encoding="utf-8")
    )["by_slug"]["raydn_duskbane"].get("functionalText") or ""
    cost_part = text.split(":", 1)[0]
    m = re.search(r"[-–—]\s*(.*)$", cost_part)
    counted = (m.group(1).count("{r}") + m.group(1).count("{R}")) if m else 0
    assert counted == 0, "printed text carries no {r}, so the parser yields none"

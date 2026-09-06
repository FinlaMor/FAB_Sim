""""...with Herald in its name" is a substring, and the DSL only had a name.

ATTACK_NAME_IN compares whole names (stripping the colour suffix, so one entry
covers all three printings). 40 cards in the corpus say "with X in its name",
and for every one of them the exact comparison is FALSE IN EVERY STATE -- no
card is called "Herald". Silently, too: a targeting filter that matches nothing
is indistinguishable from a board with no legal target.

`name_contains` is kept as a SEPARATE key rather than making `name` fuzzy. A
card that names one specific attack -- "the next Crouching Tiger you play this
turn" -- must not start matching a family whose names happen to share a word.
Both directions are asserted below.

Angelic Wrath is the card it was added for: "Target attack action card with
Herald in its name gets +2{p}."
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state, attack_with, recalculate_attack

load_all_cards()
DB = CardDB()


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="", **kw: o[0]      # noqa: E731
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


@pytest.fixture(scope="module")
def herald():
    """A real implemented attack action card with Herald in its name."""
    import io, json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    idx = json.load(io.open(root / "card_data" / "slug_index.json",
                            encoding="utf-8"))["by_slug"]
    for slug, entry in idx.items():
        if ("herald" in (entry.get("name") or "").lower()
                and "Attack" in (entry.get("subtypes") or [])
                and DB.get(slug)):
            return slug
    pytest.skip("no implemented attack action card with Herald in its name")


def _holds(st, spec):
    spec = dict(spec)
    fn = compile_condition(spec.pop("type"), spec)
    return bool(fn(st.combat.attack_card, None, st))


def test_the_probe_really_is_a_herald(herald):
    """Guards every test below: if the fixture stopped finding a Herald card
    the matches would be about nothing."""
    assert "herald" in (DB.get(herald).name or "").lower()


def test_name_contains_matches_a_substring(herald):
    st = _state()
    attack_with(st, _card(herald))
    assert _holds(st, {"type": "ATTACK_NAME_IN", "name_contains": "Herald"})


def test_name_contains_does_not_match_an_unrelated_attack():
    st = _state()
    attack_with(st, _card("head_jab_red"))
    assert not _holds(st, {"type": "ATTACK_NAME_IN", "name_contains": "Herald"})


def test_an_exact_name_still_needs_the_whole_name(herald):
    """The separation that matters. If `name` had been made fuzzy, "the next
    Crouching Tiger you play" would start matching every card whose name
    contains those letters."""
    st = _state()
    attack_with(st, _card(herald))
    assert not _holds(st, {"type": "ATTACK_NAME_IN", "name": "Herald"}), \
        "an exact-name filter matched a card merely containing the word"


def test_an_exact_name_matches_the_whole_name(herald):
    """The other half -- over-tightening would break every card that names one
    specific attack."""
    st = _state()
    attack_with(st, _card(herald))
    assert _holds(st, {"type": "ATTACK_NAME_IN", "name": DB.get(herald).name})


# ------------------------------------------------------------ the card

def test_angelic_wrath_pumps_a_herald(herald):
    st = _state()
    attacker = attack_with(st, _card(herald))
    base = attacker.base_power or 0
    run_ability(get_card("angelic_wrath_blue").abilities[0],
                _card("angelic_wrath_blue"), None, st)
    assert recalculate_attack(st) == base + 2


def test_angelic_wrath_leaves_an_unrelated_attack_alone():
    st = _state()
    attacker = attack_with(st, _card("head_jab_red"))
    base = attacker.base_power or 0
    run_ability(get_card("angelic_wrath_blue").abilities[0],
                _card("angelic_wrath_blue"), None, st)
    assert recalculate_attack(st) == base

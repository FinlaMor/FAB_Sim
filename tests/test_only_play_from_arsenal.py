"""Three of a Kind: "Until end of turn, you may only play cards from arsenal."

The restriction had been authored twice and been wrong both times. First as
RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT -- a DEFENDER restriction, a different rule
about different cards at a different time. Then, after that was noticed, as a
SET_FLAG ONLY_PLAY_FROM_ARSENAL with a `_comment` recording that there was no
hook to enforce it. The card drew three and let you play anything.

WHAT MAKES THIS ONE DELICATE. play._legality_check is the single gate that both
PLAYING a card and ACTIVATING a permanent pass through -- that is exactly why
the freeze rule lives there -- so a restriction written into it without asking
which of the two is happening would also switch off every weapon, item and
equipment the player controls for a turn. The card says "play cards". A weapon
activation is not playing a card, and the test below pins that.

Also removed: a GAIN GO_AGAIN alongside the draw. Go again is PRINTED on this
card and granted by the card DB (verified: has_go_again is already True, and
conditional_keywords strips nothing here), so the JSON was granting a second
copy of a keyword CR 8.3.5b says an object cannot have twice.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.play import available_actions
from tests.conftest import _make_state, owned_card

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.active_player = 1
    st.players[1].resources = 9
    st.players[1].action_points = 1
    return st


def _card_in(st, zone_name, slug, pid=1, **kw):
    c = owned_card(pid, slug=slug, name=slug, types=["Action"], raw_cost=0, **kw)
    c.cost = 0
    getattr(st.players[pid], zone_name).add(c)
    return c


def _play_three_of_a_kind(st, pid=1):
    card = owned_card(pid, "three_of_a_kind_red")
    run_ability(get_card("three_of_a_kind_red").abilities[0], card, None, st)


def _playable_slugs(st, pid=1):
    return {getattr(a.card, "slug", None) for a in available_actions(st, pid)}


def test_hand_cards_become_unplayable_and_arsenal_cards_do_not():
    st = _state()
    _card_in(st, "hand", "from_hand")
    _card_in(st, "arsenal", "from_arsenal")

    before = _playable_slugs(st)
    assert {"from_hand", "from_arsenal"} <= before, "fixture: both were playable"

    _play_three_of_a_kind(st)
    after = _playable_slugs(st)
    assert "from_hand" not in after, "a card in HAND was still playable"
    assert "from_arsenal" in after, "the arsenal card was blocked too"


def test_it_does_not_switch_off_the_players_permanents():
    """_legality_check gates activating as well as playing. "Play cards" is not
    "activate permanents", and conflating them would disable the whole board."""
    st = _state()
    weapon = owned_card(1, slug="test_weapon", name="Test Weapon",
                        types=["Weapon"], raw_cost=0)
    weapon.activatable = True
    st.players[1].weapon1.add(weapon)

    from engine.play import _legality_check
    _play_three_of_a_kind(st)
    assert _legality_check(st, weapon, 1), (
        "an arena permanent was caught by a restriction on PLAYING cards")


def test_the_restriction_only_binds_its_own_controller():
    st = _state()
    _card_in(st, "hand", "theirs", pid=2)
    st.players[2].resources = 9
    st.players[2].action_points = 1

    _play_three_of_a_kind(st, pid=1)
    st.active_player = 2
    assert "theirs" in _playable_slugs(st, 2), (
        "Three of a Kind restricted the opponent as well")


def test_it_ends_with_the_turn():
    st = _state()
    _card_in(st, "hand", "from_hand")
    _play_three_of_a_kind(st)
    assert "from_hand" not in _playable_slugs(st)

    st.players[1].current_turn_effects = []      # 4.4.4 end of turn
    assert "from_hand" in _playable_slugs(st), (
        "the restriction outlived the turn it was played on")


def test_go_again_is_not_granted_twice():
    """CR 8.3.5b: an object cannot have two instances of go again. The keyword
    is printed and the card DB grants it, so a GAIN in the JSON was a duplicate."""
    assert DB.get("three_of_a_kind_red").has_go_again
    effects = [e.effect_type for e in
               get_card("three_of_a_kind_red").abilities[0].effects]
    assert "GAIN" not in effects, (
        "the JSON grants a keyword the card already prints")

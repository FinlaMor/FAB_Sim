"""Cards that ask what was played THIS CHAIN LINK, not this turn.

    obsidian_fire_vein     "If you've played a Draconic card this chain link,
                            this attack gets +1{p} and go again."
    flittering_charge_red  "If you've played an instant card this chain link,
                            this gets go again."

The engine tracked plays per TURN only, and a turn holds several chain links, so
neither clause had anything correct to read. combat.link_plays is the new record.

THE WINDOW IS CR 7.0.3d, and it is narrower than "until the next attack becomes
the attacking card":

    a chain link starts when it becomes the ACTIVE chain link and ends when it
    is no longer the active chain link ... if there is no active chain link
    (during the Layer or Resolution Step, or when the combat chain is closed)
    the effect fails to be generated.

So the link begins at the Attack Step (7.0.3b) and ends at the Resolution Step
(7.6.2), and a card played during the Resolution Step or the following Layer
Step belongs to NO chain link. That falls out of where the record lives rather
than needing a rule: a CombatState is created per attack and replaced by the
next one, and there is no CombatState during the Layer Step.

7.0.3e is what makes announce the right moment to record: "any layer that is
played/activated/triggered is considered to be played/activated/triggered on the
active chain link".

The leak test is the load-bearing one — a per-TURN record passes every other
assertion here.
"""
import copy
import io
import json
from pathlib import Path

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.loader import conditional_keywords, load_all_cards
from engine.state import CombatState, Event, Step
from scripts.talishar_attack_replay import _announce_attack, _replay_agent
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()

ROOT = Path(__file__).resolve().parent.parent
NON_MATCHING = "head_jab_red"          # neither Draconic nor an Instant


@pytest.fixture(scope="module")
def fodder():
    si = json.load(io.open(ROOT / "card_data" / "slug_index.json",
                           encoding="utf-8"))["by_slug"]
    draconic = next(s for s, e in si.items()
                    if "Draconic" in (e.get("talents") or []) and DB.get(s))
    instant = next(s for s, e in si.items()
                   if "Instant" in (e.get("types") or []) and DB.get(s))
    return draconic, instant


def _board():
    st = _make_state()
    st.card_db = DB
    st.step = Step.ACTION
    st.active_player = 1
    st.combat = None
    st.player_agents = {1: _replay_agent, 2: _replay_agent}
    E._setup_dsl_listeners(st)
    return st


def _open_link(st, slug):
    """Put `slug` on the chain as a new active chain link."""
    card = copy.deepcopy(DB.get(slug))
    card.owner = card.controller = 1
    power = card.raw_power or 0
    st.combat = CombatState(attacker_id=1, link_id=len(st.chain_links) + 1,
                            attack_power=power, attack_card=card, keywords=[])
    st.combat.base_attack_power = power
    st.combat.from_weapon = "Weapon" in (card.types or [])
    return card


def _play(st, slug):
    """Play a card through the real on_play event, not by hand."""
    c = copy.deepcopy(DB.get(slug))
    c.owner = c.controller = 1
    st.event_manager.emit(Event(type="on_play", card=c.slug, data={"card": c}), st)
    return c


def _resolve(st, card):
    E._apply_turn_attack_effects(st, card)
    E._register_card_continuous_effects(st, card)
    _announce_attack(st, card)
    E._recalculate_attack_power(st)
    kws = {str(k).lower().replace(" ", "") for k in (st.combat.keywords or [])}
    return st.combat.attack_power, "goagain" in kws


def _attack_after(slug, plays=()):
    st = _board()
    card = _open_link(st, slug)
    for s in plays:
        _play(st, s)
    return _resolve(st, card)


def _base(slug):
    return DB.get(slug).raw_power or 0


# ------------------------------------------------------ obsidian fire vein

def test_obsidian_gets_both_effects_from_a_draconic_play(fodder):
    draconic, _ = fodder
    power, go_again = _attack_after("obsidian_fire_vein", [draconic])
    assert power == _base("obsidian_fire_vein") + 1
    assert go_again, "the clause grants +1{p} AND go again"


def test_obsidian_gets_nothing_on_a_quiet_link():
    power, go_again = _attack_after("obsidian_fire_vein")
    assert power == _base("obsidian_fire_vein")
    assert not go_again


def test_obsidian_ignores_a_non_draconic_play():
    power, go_again = _attack_after("obsidian_fire_vein", [NON_MATCHING])
    assert power == _base("obsidian_fire_vein")
    assert not go_again


# ------------------------------------------------------ flittering charge

def test_flittering_charge_gets_go_again_from_an_instant(fodder):
    _, instant = fodder
    power, go_again = _attack_after("flittering_charge_red", [instant])
    assert go_again
    assert power == _base("flittering_charge_red"), "keyword only, not a pump"


def test_flittering_charge_gets_nothing_on_a_quiet_link():
    assert not _attack_after("flittering_charge_red")[1]


def test_flittering_charge_ignores_a_non_instant():
    assert not _attack_after("flittering_charge_red", [NON_MATCHING])[1]


# ------------------------------------------------------ the record itself

def test_a_play_is_not_recorded_when_no_chain_link_is_active(fodder):
    """CR 7.0.3d: there is no active chain link during the Layer Step, so a card
    played then belongs to no link. Nothing to record it against."""
    draconic, _ = fodder
    st = _board()
    assert st.combat is None
    _play(st, draconic)          # must not raise, must not record anywhere
    assert st.combat is None


def test_a_play_does_not_leak_into_the_next_chain_link(fodder):
    """THE ONE THAT MATTERS. A per-TURN record satisfies every other test here
    and fails this: the Draconic card was played during link 1, so link 2 must
    not see it."""
    draconic, _ = fodder
    st = _board()
    _open_link(st, "obsidian_fire_vein")
    _play(st, draconic)
    assert len(st.combat.link_plays) == 1

    # Link 1 resolves; link 2 opens with a fresh CombatState.
    from engine.state import ChainLink
    st.chain_links.append(ChainLink(
        chainlink_id=1, attacker_id=1, attack_slug="obsidian_fire_vein",
        attack_power=0, net_damage=0, keywords=[], from_weapon=True))
    card = _open_link(st, "obsidian_fire_vein")
    assert st.combat.link_plays == [], "the new link starts empty"
    power, go_again = _resolve(st, card)
    assert power == _base("obsidian_fire_vein")
    assert not go_again


def test_the_filter_rejects_rather_than_the_recorder_failing():
    """A non-matching play must still be RECORDED -- otherwise the negative
    tests above would pass even if the recorder were broken entirely."""
    st = _board()
    _open_link(st, "obsidian_fire_vein")
    _play(st, NON_MATCHING)
    assert len(st.combat.link_plays) == 1, "recorded, then filtered out"


# ------------------------------------------------------ printed keywords

@pytest.mark.parametrize("slug", ["obsidian_fire_vein", "flittering_charge_red"])
def test_the_printed_go_again_is_stripped(slug):
    """Both cards ship with GoAgain in the DB because it flattens the sentence.
    Without the strip the gate is decoration and the card always has it."""
    assert "GoAgain" in (DB.get(slug).keywords or [])
    assert "goagain" in conditional_keywords(slug)

"""A ref name nothing ever writes: an effect aimed at a register that is empty.

Reference names ("refs") are a private register: an effect stores objects under
a name via `into`/`record_as`, and a LATER EFFECT IN THE SAME ABILITY reads them
back via `ref`. `get_ref` returns None for a name nothing wrote, and every
consumer treats None as "nothing to act on" -- so the effect silently does
nothing and the gate is silently false.

Fourteen abilities read names nothing anywhere writes (swift_pickup_red has
since been fixed: it needed SELECT_FROM_ZONE, which did not exist -- the *_REF
family could not reach a graveyard, so there was no way to author the card
correctly and the ref was aimed at an empty register instead). They read like zone or
filter names, which is what they were meant as:

  deathly_duet_yellow    REF_PITCH_IS ref "ATTACK_ACTION" / "NON_ATTACK_ACTION"
                         -- and REF_PITCH_IS tests a PITCH VALUE, not a type, so
                         even a populated ref would have answered the wrong
                         question. "Pitched to play it" is PITCHED_FOR_THIS.
  frosthaven_sheath_red  REF_PITCH_IS ref "ICE" for Ice Bond.
  high_pitched_howl_y.   REF_PITCH_IS ref "pitch_zone" -- the pitch zone is a
                         ZONE, and CARD_IN_ZONE already reads it.
  tome_of_the_arknight   RETURN_TO_HAND ref "revealed", with REVEAL_TOP_DECK
                         storing the revealed cards nowhere.
  new_horizon            DESTROY_REF ref "arsenal".
  goon_tactics_blue      DESTROY_REF ref "OPPONENT_DECK_TOP".

None of it is visible to scripts/audit_params.py: `ref` IS read by every one of
these handlers. What is wrong is the value.

The guard at the bottom is the durable half -- it derives the legal names from
the engine rather than listing the cards.
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
from engine.card import Card, CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state
from tests.conftest import card_json_files

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
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def _plain(slug, pid, **kw):
    c = Card(slug=slug, name=slug, **kw)
    c.owner = c.controller = pid
    return c


# --- new_horizon: "destroy all cards in your arsenal" ------------------------

def test_new_horizon_destroys_its_own_controllers_arsenal():
    st = _state()
    src = _card("new_horizon", 1)
    doomed = [_plain(f"a{i}", 1, types=["Action"]) for i in range(2)]
    for c in doomed:
        st.players[1].arsenal.add(c)
    theirs = _plain("safe", 2, types=["Action"])
    st.players[2].arsenal.add(theirs)

    run_ability(get_card("new_horizon").abilities[0], src, None, st)

    assert st.players[1].arsenal.cards == [], "the arsenal survived"
    assert theirs in st.players[2].arsenal.cards, "it emptied the wrong arsenal"


# --- goon_tactics_blue: "destroy the top card of their deck" -----------------

def test_goon_tactics_destroys_only_the_top_card_of_their_deck():
    st = _state()
    src = _card("goon_tactics_blue", 1)
    top = _plain("victim", 2, types=["Action"])
    under = _plain("survivor", 2, types=["Action"])
    st.players[2].deck.add(top)
    st.players[2].deck.add(under)
    mine = _plain("mine", 1, types=["Action"])
    st.players[1].deck.add(mine)

    hit = [a for a in get_card("goon_tactics_blue").abilities
           if a.trigger == "ON_HIT"][0]
    for eff in hit.effects:
        eff.fn(src, None, st)

    left = [c.slug for c in st.players[2].deck.cards]
    assert "victim" not in left, "the top card survived"
    assert "survivor" in left, "it took more than the top card"
    assert mine in st.players[1].deck.cards, "it milled the wrong player"


# --- deathly_duet_yellow: pitched to play it, not a pitch value --------------

def _duet(st, pitched):
    src = _card("deathly_duet_yellow", 1)
    src.pitched_for_this = pitched
    return src


def _run_duet(st, index, pitched):
    from engine.state import CombatState
    src = _duet(st, pitched)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=src, keywords=[], from_weapon=False)
    run_ability(get_card("deathly_duet_yellow").abilities[index], src, None, st)
    return src


def _runechants(st):
    return [c for c in st.players[1].permanents.cards
            if "runechant" in (c.slug or "").lower()]


def test_duet_pumps_only_when_an_attack_action_paid_for_it():
    attack = _plain("some_attack", 1, types=["Action"], subtypes=["Attack"])
    non_attack = _plain("some_action", 1, types=["Action"])

    st = _state()
    _run_duet(st, 0, [attack])
    assert st.combat.attack_power == 5, "the +2 never applied"

    st = _state()
    _run_duet(st, 0, [non_attack])
    assert st.combat.attack_power == 3, "it pumped off a non-attack pitch"

    st = _state()
    _run_duet(st, 0, [])
    assert st.combat.attack_power == 3, "it pumped with nothing pitched"


def test_duet_makes_runechants_only_for_a_non_attack_action():
    attack = _plain("some_attack", 1, types=["Action"], subtypes=["Attack"])
    non_attack = _plain("some_action", 1, types=["Action"])

    st = _state()
    _run_duet(st, 1, [non_attack])
    assert len(_runechants(st)) == 2, "the Runechants were never created"

    st = _state()
    _run_duet(st, 1, [attack])
    assert _runechants(st) == [], "an attack pitch made Runechants"


def test_both_duet_clauses_fire_when_both_kinds_were_pitched():
    """Why "non-attack" cannot be NOT(an attack was pitched): pitch two cards,
    one of each, and both printed clauses apply. A negation around the whole
    condition would silence the second."""
    both = [_plain("some_attack", 1, types=["Action"], subtypes=["Attack"]),
            _plain("some_action", 1, types=["Action"])]

    st = _state()
    _run_duet(st, 0, both)
    assert st.combat.attack_power == 5

    st = _state()
    _run_duet(st, 1, both)
    assert len(_runechants(st)) == 2


# --- tome_of_the_arknight_blue ----------------------------------------------

def _tome(st, top):
    src = _card("tome_of_the_arknight_blue", 1)
    for c in top:
        st.players[1].deck.add(c)
    run_ability(get_card("tome_of_the_arknight_blue").abilities[0], src, None, st)
    return src


def test_tome_takes_both_cards_when_it_reveals_one_of_each():
    st = _state()
    a = _plain("an_attack", 1, types=["Action"], subtypes=["Attack"])
    b = _plain("an_action", 1, types=["Action"])
    _tome(st, [a, b])

    assert a in st.players[1].hand.cards and b in st.players[1].hand.cards


def test_tome_takes_nothing_when_both_are_attacks():
    """The clause needs one of EACH. REF_IS_TYPE could not have asked this: it
    collapses a list ref to its last entry, so a two-card reveal is judged by
    one card twice."""
    st = _state()
    a = _plain("attack_one", 1, types=["Action"], subtypes=["Attack"])
    b = _plain("attack_two", 1, types=["Action"], subtypes=["Attack"])
    _tome(st, [a, b])

    assert a not in st.players[1].hand.cards
    assert b not in st.players[1].hand.cards


# --- the guard --------------------------------------------------------------

#: Names the ENGINE writes implicitly (grep: set_ref call sites) plus the
#: defaults handlers fall back to when a card names no ref.
ENGINE_REFS = {
    "arsenaled", "banished", "banished_cards", "bottomed",
    "bottomed_from_hand", "clash_revealed_opponent", "clash_revealed_self",
    "countered", "dagger", "destroyed", "destroyed_count", "discarded",
    "sharpened", "looked", "chosen", "named_card", "rest",
}
#: Names a card writes for itself.
WRITE_KEYS = ("into", "rest_into", "record_as", "store_as")

#: Cards still reading an invented ref, each needing a mechanic that does not
#: exist yet -- NOT a licence to add more. The count may fall; a name added to
#: this set must come with the reason it cannot be fixed instead.
KNOWN_UNFIXED = {
    # REVEAL_HAND_MARK_IF_TYPE reveals the whole hand and MARKS; it stores
    # nothing and ignores `amount`, so "reveal 2 cards ... choose one" has no
    # implementation to point a ref at.
    "pulsewave_harpoon_red",
}


def _offenders():
    root = ROOT / "engine" / "card_effects" / "json"
    bad = {}
    for path in card_json_files(root):
        rel = path.relative_to(root)
        if (path.stem.endswith("_work_queue")
                or any(p.startswith(".") or p == "needs_review"
                       for p in rel.parts)):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for ab in raw.get("abilities") or []:
            reads, writes = set(), set()

            def walk(node):
                if isinstance(node, dict):
                    for k in ("ref", "from_ref", "target_ref"):
                        if isinstance(node.get(k), str):
                            reads.add(node[k])
                    for k in WRITE_KEYS:
                        if isinstance(node.get(k), str):
                            writes.add(node[k])
                    for v in node.values():
                        walk(v)
                elif isinstance(node, list):
                    for v in node:
                        walk(v)

            walk(ab)
            missing = reads - writes - ENGINE_REFS - {w + "_owner" for w in writes}
            if missing:
                bad.setdefault(raw.get("slug"), set()).update(missing)
    return bad


def test_no_new_card_reads_a_ref_nothing_writes():
    bad = _offenders()
    new = {k: sorted(v) for k, v in bad.items() if k not in KNOWN_UNFIXED}
    assert new == {}, (
        "abilities reading a ref name nothing ever writes -- the effect is a "
        f"silent no-op and the gate is silently false: {new}")


def test_the_unfixed_list_does_not_go_stale():
    """A card fixed elsewhere must leave the list, or it stops meaning
    anything."""
    still = set(_offenders())
    assert KNOWN_UNFIXED <= still, (
        "already fixed, remove from KNOWN_UNFIXED: "
        f"{sorted(KNOWN_UNFIXED - still)}")

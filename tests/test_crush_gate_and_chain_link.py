"""Four Crush abilities gated on the one condition that contradicts Crush.

ON_CRUSH fires only when `crush_check` passes -- the attack HIT for 4 or more.
Four cards then gated that trigger on DID_NOT_HIT, which is true only when the
attack did NOT hit. The two are mutually exclusive, so the abilities could
never resolve in any state the game can reach: the whole printed effect was
dead, and nothing about the JSON looks wrong.

  flatten_the_field_blue   destroy a Seismic Surge token they control
  grind_them_down_blue     destroy the top card of their deck
  cartilage_crush_blue     their first action next turn costs an extra {r}
  chokeslam_yellow         their attack action cards can't gain {p}

The `amount: 4` those gates carried is the tell: DID_NOT_HIT reads no amount
(condition_types.py), so the 4 was decoration that made the node read like the
"4 or more damage" clause it was standing in for. ON_CRUSH already IS that
clause, which is why the gate is deleted rather than corrected.

send_packing_yellow is the opposite case and is why the whole group looked
plausible: its text really does say "if this didn't hit", so DID_NOT_HIT is
right -- but the TRIGGER was ON_CRUSH, a card with no Crush at all. Its timing
is "when the chain link resolves" (CR 7.6.2), a per-link event the engine
emitted with no DSL trigger attached to it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card
from engine.card_effects.dsl import dispatch, load_all_cards
from engine.card_effects.dsl.loader import get_card
from engine.state import CombatState, Event, GameState, Player, Step
from tests.conftest import card_json_files

load_all_cards()

DEGATED = ["flatten_the_field_blue", "grind_them_down_blue",
           "cartilage_crush_blue", "chokeslam_yellow"]


def _hero(pid: int) -> Card:
    c = Card(slug="test_hero", name="H", types=["Hero"], base_life=40,
             base_intellect=4)
    c.owner = c.controller = pid
    return c


def _state() -> GameState:
    return GameState(
        players={1: Player(1, _hero(1)), 2: Player(2, _hero(2))},
        active_player=1,
        player_agents={1: lambda *a, **k: None, 2: lambda *a, **k: None},
        step=Step.ACTION, turn_number=1, combat=None, done=False, winner=None,
    )


def _attack(state: GameState, slug: str, hit: bool = True) -> None:
    ac = Card(slug=slug, name=slug, types=["Action"], subtypes=["Attack"])
    ac.owner = ac.controller = 1
    ac.zone = "combat_chain"
    state.combat = CombatState(attacker_id=1, link_id=1, attack_power=9,
                               attack_card=ac, keywords=[], from_weapon=False)
    state.combat.hit = hit


def _crush(state: GameState, slug: str) -> None:
    dispatch(state, "ON_CRUSH", slug, card=state.combat.attack_card,
             event=Event(type="ON_CRUSH", data={"damage": 5}))


# --- the effects actually happen now ----------------------------------------

def test_grind_them_down_destroys_the_top_card_of_their_deck():
    s = _state()
    top = Card(slug="victim", name="V", types=["Action"])
    top.owner = top.controller = 2
    rest = Card(slug="survivor", name="S", types=["Action"])
    rest.owner = rest.controller = 2
    s.players[2].deck.add(top)
    s.players[2].deck.add(rest)
    _attack(s, "grind_them_down_blue")

    _crush(s, "grind_them_down_blue")

    remaining = [c.slug for c in s.players[2].deck.cards]
    assert "victim" not in remaining, "the crush effect never resolved"
    assert "survivor" in remaining, "it took more than the top card"


def test_flatten_the_field_destroys_their_seismic_surge_token():
    from engine.card import CardDB
    from engine.card_effects.ability_keywords import create_token
    s = _state()
    s.card_db = CardDB()
    _attack(s, "flatten_the_field_blue")
    create_token(s, 2, "seismic_surge")
    assert s.players[2].permanents.cards, "fixture built no token"

    _crush(s, "flatten_the_field_blue")

    assert not [c for c in s.players[2].permanents.cards
                if "seismic" in c.slug], "the token survived the crush"


# --- send_packing: the trigger its text names -------------------------------

def test_send_packing_no_longer_claims_crush():
    """It has no Crush; ON_CRUSH would fire only on a 4+ damage hit, which is
    the one case where its "if this didn't hit" clause must NOT fire."""
    trigs = [a.trigger for a in get_card("send_packing_yellow").abilities]
    assert "ON_CRUSH" not in trigs, trigs
    assert "ON_CHAIN_LINK_RESOLVE" in trigs, trigs


def test_the_chain_link_resolve_event_reaches_the_dsl():
    """The engine emitted 'chain_link_resolves' with nothing listening, so the
    timing was unreachable from a card. Fire the real event, not a dispatch."""
    import engine.engine as E
    import engine.card_effects.dsl as D
    s = _state()
    _attack(s, "send_packing_yellow", hit=False)

    seen = []
    real = D.dispatch

    def _spy(state, trigger, slug, **kw):
        seen.append(trigger)
        return real(state, trigger, slug, **kw)

    # The listeners close over `dispatch` at setup time, so the substitution
    # has to be in place before they are registered.
    D.dispatch = _spy
    try:
        E._setup_dsl_listeners(s)
        s.event_manager.emit("chain_link_resolves", s)
    finally:
        D.dispatch = real

    assert "ON_CHAIN_LINK_RESOLVE" in seen, seen


# --- the guard --------------------------------------------------------------

def test_no_crush_ability_is_gated_on_did_not_hit():
    """Derived, so it keeps probing as cards are added: ON_CRUSH means the
    attack hit for 4+, and DID_NOT_HIT means it did not hit. An ability
    carrying both resolves in no reachable state."""
    root = ROOT / "engine" / "card_effects" / "json"
    bad = []
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
            if ab.get("trigger") != "ON_CRUSH":
                continue
            if "DID_NOT_HIT" in json.dumps(ab):
                bad.append(raw.get("slug"))
    assert bad == [], f"ON_CRUSH abilities that can never resolve: {bad}"


@pytest.mark.parametrize("slug", DEGATED)
def test_the_card_really_has_crush(slug):
    """The premise of deleting the gate: ON_CRUSH already carries the "4 or
    more damage" clause, so the condition was redundant as well as inverted."""
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    text = (idx[slug].get("functionalText") or "").lower()
    assert "crush" in text and "4 or more damage" in text, text

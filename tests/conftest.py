"""Shared test fixtures and helpers for FAB_Sim test suite."""

import json
import os
import sys

import pytest

from engine.card import Card
from engine.state import CombatState, GameState, Player, Step, Zone


# ---------------------------------------------------------------------------
# Opt-in DSL execution-coverage capture during the test run
# ---------------------------------------------------------------------------
# scripts/dsl_coverage.py plays random games and flags any authored effect that
# never fired. On its own that is a *weak* signal: an effect a unit test drives
# but no random game happens to reach reads as "never executed". Set
# FAB_DSL_COVERAGE_OUT=<path> to record every (slug, effect_type) the *test
# suite* executes into that JSON file; `dsl_coverage.py --merge-tests <path>`
# then folds it in, so only genuinely-dead effects remain flagged.
#
# Disabled unless the env var is set — no overhead on a normal run.

def pytest_sessionstart(session):
    out = os.environ.get("FAB_DSL_COVERAGE_OUT")
    if not out:
        return
    from engine.card_effects.dsl import coverage
    coverage.start()


def pytest_sessionfinish(session, exitstatus):
    out = os.environ.get("FAB_DSL_COVERAGE_OUT")
    if not out:
        return
    from engine.card_effects.dsl import coverage
    tracker = coverage.stop()
    effects = sorted(tracker.effects) if tracker else []
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"effects": effects}, f, indent=2)


@pytest.fixture(autouse=True, scope="module")
def _restore_dsl_registry():
    """Keep the full DSL card registry loaded around each test module.

    Some tests (and some modules at import time) call load_all_cards() on a temp
    dir or a single set folder, which replaces the module-global registry.
    Reload the full tree both before and after each module so no module runs
    against a subset polluted during collection or by a prior module.
    """
    from engine.card_effects.dsl import loader
    if loader._LOADED:
        loader.load_all_cards()
    yield
    if loader._LOADED:
        loader.load_all_cards()


# ---------------------------------------------------------------------------
# Test helper factories (extracted from tests/test_loader_conditions.py)
# ---------------------------------------------------------------------------

def _make_hero(pid: int = 1) -> Card:
    c = Card(slug="test_hero", raw_name="Test Hero", raw_types=["Hero"], raw_life=40,
            raw_intellect=4)
    c.owner = pid
    c.controller = pid
    return c


def _make_player(pid: int = 1) -> Player:
    return Player(pid, _make_hero(pid))


def _mock_agent(state, options, context, **kwargs):
    if options:
        return options[0]
    return None


def _make_state() -> GameState:
    p1 = _make_player(1)
    p2 = _make_player(2)
    return GameState(
        players={1: p1, 2: p2},
        active_player=1,
        player_agents={1: _mock_agent, 2: _mock_agent},
        step=Step.ACTION,
        turn_number=1,
        combat=None,
        done=False,
        winner=None,
    )


def _make_card(slug: str = "test_card", name: str = "Test Card",
               types: list[str] | None = None, **kwargs) -> Card:
    """Create a Card with sensible defaults, overridable via kwargs.
    Defaults to type 'Action' so cards can legally enter hand/deck zones.
    Extra kwargs (e.g. base_defense, base_power) are set as attributes on the card.
    """
    raw_types = types if types is not None else ["Action"]
    card = Card(slug=slug, raw_name=name, raw_types=raw_types)
    for attr, val in kwargs.items():
        setattr(card, attr, val)
        # Propagate base_X → X so the current field reflects the new base value
        if attr.startswith('base_'):
            current = attr[5:]
            if hasattr(card, current) and getattr(card, current) is None:
                setattr(card, current, val)
    return card


def _make_combat(attacker_id: int = 1, attack_card: Card | None = None) -> CombatState:
    """Create a minimal CombatState for testing combat-related cards."""
    if attack_card is None:
        attack_card = _make_card(
            slug="test_attack",
            name="Test Attack",
            types=["Action", "Attack"])

        attack_card.base_power=3
        attack_card.owner = attacker_id
        attack_card.controller = attacker_id

    opp_hero = _make_hero(3 - attacker_id)

    return CombatState(
        attacker_id=attacker_id,
        attack_target=opp_hero,
        link_id=1,
        attack_power=attack_card.base_power or 0,
        attack_card=attack_card,
        keywords=[],
    )


# ---------------------------------------------------------------------------
# Dynamic parametrization hook for card_slug fixture
# ---------------------------------------------------------------------------

def pytest_generate_tests(metafunc):
    """Parametrize tests that request a 'card_slug' fixture with all slugs
    from slug_index.json.  Only fires when 'card_slug' is explicitly listed
    in fixture names — will NOT interfere with other tests."""
    if "card_slug" in metafunc.fixturenames:
        from config import SLUG_INDEX_PATH

        with open(SLUG_INDEX_PATH, "r", encoding="utf-8") as f:
            slug_index = json.load(f)
        slugs = sorted(slug_index["by_slug"].keys())
        metafunc.parametrize("card_slug", slugs)


def card_json_files(root):
    """Every IMPLEMENTED card file under `root`.

    rglob walks everything, and the card tree is not only cards. This repo
    keeps `.quarantine/` there, and the pipeline worktree additionally keeps
    `.drafts/`, `.review/`, `.triage/` and `.draft-review/` results filed under
    the same slugs. A dot-directory under the card tree is never an implemented
    card, which is the rule the loader already applies.
    """
    return [p for p in root.rglob("*.json")
            if not any(part.startswith(".") for part in p.parts)]


def _card_json(root, name):
    """The implemented card file called `name`.

    `next(root.rglob(name))` returns whatever the walk reaches first, and
    ".review" sorts before every set directory -- so in the pipeline worktree
    that first hit was a REVIEW VERDICT, an object with no "abilities". 77
    tests failed there for a reason that had nothing to do with the card they
    were testing, and each looked like a product bug.
    """
    hits = [p for p in root.rglob(name)
            if not any(part.startswith(".") for part in p.parts)]
    assert hits, f"no implemented card file for {name}"
    return hits[0]


# --- card-behaviour helpers --------------------------------------------------
#
# Three separate false alarms in this suite came from tests rolling their own
# versions of these and getting them subtly wrong. Each accused a CORRECT card:
#
#   1. `SOURCE_IS_ATTACK` compares IDENTITY -- `combat.attack_card is c`. A test
#      that builds the attack from one deepcopy and passes the ability a second
#      deepcopy has a card that is equal but not identical, so the condition is
#      false and the static silently does nothing. That looks exactly like a
#      missing buff.
#   2. `auras` is a VIEW over the same objects `permanents` holds, so summing
#      the zones counts every aura token twice. Three tokens looked like six.
#   3. `discard()` decides whose hand a card left by reading the DISCARDED
#      CARD's owner, so a filler card created without one resolves to player 0
#      and raises KeyError deep in the engine.
#
# Use these rather than reimplementing them.

def attack_with(state, card, power=None, wire=True):
    """Make `card` the active attack and return THE OBJECT now in combat.

    Always use the returned card as the ability's source. Passing a different
    copy is the identity trap above.

    `wire` runs the two engine steps a real attack goes through, and both
    matter:

      _apply_turn_attack_effects       applies buffs QUEUED earlier in the turn,
                                       which is how MODIFY_NEXT_ATTACK lands.
                                       Without it, "your next attack gets +4"
                                       silently does nothing and the card that
                                       queued it looks broken.
      _register_card_continuous_effects registers this card's own statics.

    Pass wire=False only when testing the helper itself or a card with no
    interest in either path.
    """
    if power is None:
        power = getattr(card, "base_power", None) or 0
    state.combat = CombatState(attacker_id=getattr(card, "controller", 1) or 1,
                               link_id=1, attack_power=power,
                               attack_card=card, keywords=[])
    state.combat.base_attack_power = power
    if wire:
        import engine.engine as _E
        _E._apply_turn_attack_effects(state, card)
        _E._register_card_continuous_effects(state, card)
    return card


def recalculate_attack(state):
    """Run the real attack-power path and return the resulting power."""
    import engine.engine as _E
    _E._recalculate_attack_power(state)
    return state.combat.attack_power


def assert_source_is_the_attack(ability, card, state):
    """Fail LOUDLY when an ability gated on SOURCE_IS_ATTACK is handed a card
    that is not the one in combat.

    Without this the condition is merely false and the test reports a working
    card as broken -- which has now happened more than once.
    """
    conds = [str(getattr(c, "condition_type", "") or "").upper()
             for c in (getattr(ability, "conditions", None) or [])]
    if "SOURCE_IS_ATTACK" not in conds:
        return
    actual = getattr(getattr(state, "combat", None), "attack_card", None)
    assert actual is card, (
        "this ability is gated on SOURCE_IS_ATTACK, which compares IDENTITY: "
        "the source card must BE state.combat.attack_card, not an equal copy. "
        "Use `card = attack_with(state, card)` and pass that same object.")


def tokens_controlled(state, pid, name=None):
    """Tokens the player controls, counted ONCE.

    `auras` overlaps `permanents`, so summing zones double-counts.
    """
    seen, out = set(), []
    player = state.players[pid]
    for attr in ("permanents", "tokens", "arena", "auras"):
        zone = getattr(player, attr, None)
        if zone is None:
            continue
        for c in list(getattr(zone, "cards", zone) or []):
            if id(c) in seen:
                continue
            seen.add(id(c))
            out.append(c)
    if name is None:
        return out
    return [c for c in out if name in str(getattr(c, "slug", "")).lower()]


def owned_card(pid, slug="filler", name=None, types=None, **kwargs):
    """A card that KNOWS WHO OWNS IT.

    Several engine paths resolve a player from the card rather than from an
    argument -- discard() reads the discarded card's owner -- so an ownerless
    card resolves to player 0.

    MIND THE TYPE. It defaults to "Action" because zone entry rules reject
    types that cannot legally be there: put_object moving a ["Item"] or
    ["Token"] card to hand comes back CANCELED and nothing moves. A fixture
    typed unrealistically makes a working card look like it silently drops a
    clause -- a real FAB aura is an Action with subtype Aura, not type Token.
    """
    card = _make_card(slug=slug, name=name or slug,
                      types=types if types is not None else ["Action"],
                      **kwargs)
    card.owner = card.controller = pid
    return card


def give_permanent(state, pid, card, subtype=None):
    """Put `card` in the arena, in the SUB-ZONE the engine will look in.

    `player.auras` is a SubZoneView matching `card.permanent_subtype`, and that
    attribute is set by `auras.add()` -- NOT by the card having subtype "Aura".
    So `permanents.add(token)` leaves `auras` empty, and a card counting auras
    sees none. That looked like a broken card until the zone was inspected.

        give_permanent(st, 1, owned_card(1, "vigor"), subtype="Aura")
    """
    if subtype is None:
        state.players[pid].permanents.add(card)
        return card
    # TWO different notions of "aura" have to agree, and they are set in
    # different places:
    #   permanent_subtype  what SubZoneView matches, set by `auras.add()`
    #   subtypes           what CARD_IS_TYPE / filters match
    # A token with only the first is in the auras zone but invisible to any
    # card that filters for an Aura by type -- which made a correct card look
    # like it silently dropped its second clause.
    existing = list(getattr(card, "subtypes", None) or [])
    if subtype not in existing:
        card.subtypes = existing + [subtype]
    getattr(state.players[pid], subtype.lower() + "s").add(card)
    return card

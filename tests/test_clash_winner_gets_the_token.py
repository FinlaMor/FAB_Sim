"""Seven clash cards said "the WINNER creates a token" and always created it.

Found by following CLASH's unread `target` rather than by the unread param
itself — the target turned out to be genuinely inert (every one of these clashes
with the attacking hero, which is the default), but the effect NEXT TO it was
not.

The token was a plain CREATE_TOKEN sitting after the CLASH, so it ran whatever
the clash returned. The controller got the token whether they won or lost, which
means the clash decided nothing at all. CLASH already takes `on_winner` outcome
specs; the token now rides one.

clash_of_might_blue failed differently and worse: it used `on_win` (CLASH reads
`on_winner`) holding a nested `{"type": "CREATE_TOKEN"}` where CLASH expects
`{"action": "create_token", "who": ...}`. Two mismatches on the same node, so
its token was never created at all — the one card in the cycle that did nothing
rather than too much.
"""
import json
from pathlib import Path

import pytest

JSON_ROOT = Path(__file__).resolve().parent.parent / "engine/card_effects/json"

CLASH_CARDS = [
    "clash_of_agility_blue",
    "clash_of_might_blue",
    "clash_of_might_yellow",
    "clash_of_vigor_yellow",
    "clash_of_mountains_red",
    "test_of_agility_red",
    "test_of_vigor_red",
]


def _raw(slug):
    return json.loads(next(JSON_ROOT.rglob(f"{slug}.json")).read_text(encoding="utf-8"))


def _nodes(raw, want):
    out = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == want:
                out.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(raw.get("abilities", []))
    return out


@pytest.mark.parametrize("slug", CLASH_CARDS)
def test_the_token_is_an_outcome_of_the_clash(slug):
    """The token must hang off the clash's winner, not run beside it."""
    raw = _raw(slug)
    clashes = _nodes(raw, "CLASH")
    assert len(clashes) == 1, slug

    winners = clashes[0].get("on_winner")
    assert winners, f"{slug}: CLASH has no on_winner, so nothing depends on winning"
    assert all(spec.get("action") == "create_token" for spec in winners), winners
    assert all(spec.get("who") == "WINNER" for spec in winners), winners
    assert all(spec.get("token") for spec in winners), (
        f"{slug}: outcome names no token slug, so it would create nothing")


@pytest.mark.parametrize("slug", CLASH_CARDS)
def test_no_unconditional_create_token_beside_the_clash(slug):
    """The shape that made the clash pointless."""
    raw = _raw(slug)
    assert not _nodes(raw, "CREATE_TOKEN"), (
        f"{slug} still creates a token outside the clash outcome, so it is "
        "created whether the clash is won or lost")


@pytest.mark.parametrize("slug", CLASH_CARDS)
def test_no_clash_uses_the_unread_on_win_key(slug):
    """CLASH reads `on_winner`. `on_win` is read by nothing."""
    raw = _raw(slug)
    for clash in _nodes(raw, "CLASH"):
        assert "on_win" not in clash, slug


def test_the_outcome_spec_shape_is_the_one_clash_reads():
    """Guards against re-introducing the nested-effect form.

    CLASH's _run_outcome dispatches on spec["action"]; a spec carrying "type"
    instead is silently skipped, which is how clash_of_might_blue's token was
    never created.
    """
    import inspect
    from engine.card_effects.dsl import effect_types

    src = inspect.getsource(effect_types.compile_effect)
    assert 'spec.get("action"' in src, (
        "CLASH outcomes no longer dispatch on 'action' — the card JSON shape "
        "these tests pin may no longer be the right one")

    for slug in CLASH_CARDS:
        for clash in _nodes(_raw(slug), "CLASH"):
            for spec in clash.get("on_winner") or []:
                assert "type" not in spec, (slug, spec)


def _behavioural_state():
    import copy

    import engine.engine as E
    from engine.card import CardDB
    from engine.card_effects.dsl.loader import load_all_cards
    from tests.conftest import _make_state

    load_all_cards()
    db = CardDB()
    st = _make_state()
    st.card_db = db
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    return st, db, copy


@pytest.mark.parametrize("winner,loser", [(1, 2), (2, 1)])
def test_only_the_clash_winner_gets_the_token(winner, loser):
    """The observable outcome, not the JSON shape.

    CR 8.5.45: both reveal their top deck card, highest power wins. Stacking the
    decks decides the winner, so the same card is run twice — once winning, once
    losing. A test that only ever wins would pass on the old unconditional
    CREATE_TOKEN too, which is exactly how this survived.
    """
    from engine.card_effects.dsl.interpreter import run_ability
    from engine.card_effects.dsl.loader import get_card

    st, db, copy = _behavioural_state()

    def _stack(pid, slug):
        # Two real cards with different PRINTED power: Card.power is fixed at
        # construction, so assigning raw_power/base_power afterwards does not
        # move it, and both decks would tie (CR 8.5.45c: a tie has no winner,
        # so on_winner never runs and the test would pass for the wrong reason).
        card = copy.deepcopy(db.get(slug))
        card.owner = card.controller = pid
        st.players[pid].deck.cards = [card]

    _stack(winner, "a_good_clean_fight_red")   # power 7
    _stack(loser, "aether_ashwing")            # power 1

    source = copy.deepcopy(db.get("clash_of_agility_blue"))
    source.owner = source.controller = 1
    st.combat = None            # no combat: CLASH falls back to the plain opponent

    # Count PERMANENTS, not the `tokens` view: Agility is an Aura token, and the
    # per-subtype views route it to `auras`. Asserting on `tokens` reads zero
    # whether the token was created or not.
    before = {pid: len(st.players[pid].permanents.cards) for pid in (1, 2)}
    run_ability(get_card("clash_of_agility_blue").abilities[0], source, None, st)

    gained = {pid: len(st.players[pid].permanents.cards) - before[pid]
              for pid in (1, 2)}
    assert gained[winner] == 1, f"the clash winner (P{winner}) got no token: {gained}"
    assert gained[loser] == 0, (
        f"the clash LOSER (P{loser}) got a token — the token does not depend on "
        f"winning: {gained}")


def test_donkey_wagers_rather_than_clashing():
    """"wagers with the defending hero" is not a clash.

    A clash resolves immediately by revealing cards; a wager rides the attack
    and is settled at chain-link resolution by whether it hit. Donkey was a
    CLASH, which settles at the wrong time and against the wrong player.
    """
    raw = _raw("donkey_blue")
    assert not _nodes(raw, "CLASH"), "donkey_blue still clashes"
    assert _nodes(raw, "WAGER"), "donkey_blue no longer wagers"

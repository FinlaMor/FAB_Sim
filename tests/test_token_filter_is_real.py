"""`"token": true` matched nothing and `"token": false` matched everything.

Three filters -- `_permanent_filter`, the DESTROY_PERMANENT selection, and the
DESTROY_PERMANENTS_OPTIONAL cost's `exclude_tokens` -- all asked
`getattr(c, "is_token", False)`. Nothing anywhere sets `is_token`. The corpus
marks a token by putting "Token" in its types, which is what `state._is_token`
reads and what `Zone.add` uses to make a token cease to exist on entry to the
graveyard (CR 3.0.12a).

So the test was a constant:

    "token": true    -> False is not True  -> filtered EVERYTHING out... except
                        the comparison was `bool(False) is not bool(True)`, so
                        every card was rejected only if it was a token, which
                        none were: the restriction simply did not apply.
    "token": false   -> matched every card, tokens included.

Both directions are wrong and both are silent. Smack of Reality's "destroy an
aura TOKEN they control" would take a non-token aura; Vaporize/Shock's two
halves ("auras with cost X or less" then "aura tokens") were indistinguishable;
Cash Out's `exclude_tokens` excluded nothing.

The fix routes all three through `state._is_token`, so there is ONE definition
of what a token is. These tests are written against the filter's observable
outcome -- which permanents get destroyed -- rather than the predicate.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import _compile_ability, load_all_cards
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

TOKEN_AURA = "runechant"          # types: ["Token"], subtypes: ["Aura"]
CARD_AURA = "arcanite_skullcap"   # a real card, not a token


def _obj(slug, pid=1):
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


def _aura_pair(st, pid=2):
    """One token aura and one non-token aura, both under `pid`'s control."""
    token = _obj(TOKEN_AURA, pid)
    card = copy.deepcopy(DB.get(CARD_AURA))
    card.owner = card.controller = pid
    # Force the non-token onto the same subtype so the ONLY thing separating
    # the two is tokenness -- otherwise a subtype filter could be doing the
    # work and these tests would pass without the fix.
    card.subtypes = ["Aura"]
    card.raw_subtypes = ["Aura"]
    st.players[pid].auras.add(token)
    st.players[pid].auras.add(card)
    return token, card


def _destroy(st, **params):
    src = _obj("runechant", 1)
    run_ability(_compile_ability({
        "ability_type": "ON_PLAY",
        "effects": [dict({"type": "DESTROY_PERMANENT", "subtype": "Aura",
                          "player": "OPPONENT", "amount": 99}, **params)],
    }), src, None, st)


def test_the_two_probes_differ_only_in_tokenness():
    """Guards every test below. If the non-token aura stopped being a
    non-token, or the token stopped carrying "Token" in its types, the
    assertions would be about nothing."""
    from engine.state import _is_token
    st = _state()
    token, card = _aura_pair(st)
    assert _is_token(token) and not _is_token(card)
    assert "Aura" in token.subtypes and "Aura" in card.subtypes


def test_token_true_destroys_only_the_token():
    """'Destroy an aura TOKEN they control' -- Smack of Reality, Bubba Lubba."""
    st = _state()
    token, card = _aura_pair(st)
    _destroy(st, token=True)
    remaining = list(st.players[2].auras.cards)
    assert token not in remaining, "the aura token survived"
    assert card in remaining, "a non-token aura was destroyed by a token-only clause"


def test_token_false_spares_the_token():
    """The other half of Vaporize/Shock: the non-token clause must not take
    the token, or the two clauses are the same clause."""
    st = _state()
    token, card = _aura_pair(st)
    _destroy(st, token=False)
    remaining = list(st.players[2].auras.cards)
    assert card not in remaining
    assert token in remaining, "a token was destroyed by a non-token clause"


def test_no_token_key_still_destroys_both():
    """The filter must stay OPTIONAL: an unqualified 'destroy an aura' has no
    opinion about tokens, and a fix that made tokenness always matter would
    quietly narrow every such card."""
    st = _state()
    token, card = _aura_pair(st)
    _destroy(st)
    remaining = list(st.players[2].auras.cards)
    assert token not in remaining and card not in remaining

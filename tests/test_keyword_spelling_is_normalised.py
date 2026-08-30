"""Keyword spellings vary across the corpus, and 88 cards depend on that being
harmless.

`GAIN` accepts a keyword under any spelling -- "GO_AGAIN", "Go Again" and
"go again" all reach the same place -- because `loader._kw_key` strips
non-alphanumerics and lowercases before comparing. That is deliberate and it
works. The corpus relies on it heavily:

    'Go Again'   17 cards        'Phantasm'   9
    'go again'   13              'Dominate'   7
    'stealth'    10              88 in total

NOTHING PINNED IT UNTIL NOW, and the cards that rely on it do not announce
themselves. If the normalisation regressed, thirty cards would quietly stop
granting go again -- no error, no failed load, just an attack that does not
give back its action point. That is the exact shape of defect this whole effort
keeps finding.

THE SPELLING IS ALSO A TRAP FOR TOOLING, which is how it came up.
insult_to_injury_blue wrote `"keyword": "go again"`, a conversion script
matched `keyword == "GO_AGAIN"` exactly, and the card was silently skipped --
leaving it with an unconditional printed keyword AND a missing hero gate. The
sloppy spelling was concealing the real defect. Any sweep over keywords must
normalise the way the engine does.
"""
from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import _kw_key, load_all_cards
from tests.conftest import _make_state, attack_with, owned_card

load_all_cards()
DB = CardDB()
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

SPELLINGS = ["GO_AGAIN", "Go Again", "go again", "goagain"]


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_every_spelling_normalises_the_same(spelling):
    assert _kw_key(spelling) == "goagain", (
        f"{spelling!r} no longer normalises to 'goagain'; cards written with "
        "it lose their keyword silently")


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_every_spelling_actually_grants_go_again(spelling):
    """Behavioural, not just the normaliser: the GAIN handler has to route all
    of them to the same place."""
    from engine.card_effects.dsl.loader import _compile_effect

    st = _state()
    card = attack_with(st, owned_card(1, "x", types=["Action"], base_power=4))
    _compile_effect({"type": "GAIN", "keyword": spelling}).fn(card, None, st)

    got = [_kw_key(k) for k in st.combat.keywords]
    assert "goagain" in got, (
        f"GAIN with keyword {spelling!r} did not put go again on the combat; "
        f"got {st.combat.keywords}")


def test_the_corpus_really_does_rely_on_this():
    """The premise. If every card were canonical, the tests above would be
    guarding nothing and could be deleted -- so the count is asserted rather
    than assumed."""
    noncanon = Counter()
    for path in JSON_ROOT.rglob("*.json"):
        rel = path.relative_to(JSON_ROOT)
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") for p in rel.parts):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue

        def walk(node):
            if isinstance(node, dict):
                kw = node.get("keyword")
                if isinstance(kw, str) and kw.strip() and (
                        kw != kw.upper() or " " in kw):
                    noncanon[kw] += 1
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(raw.get("abilities"))

    assert sum(noncanon.values()) > 50, (
        f"only {sum(noncanon.values())} non-canonical keyword spellings remain; "
        "if the corpus has been normalised these guards may be redundant")
    assert any(_kw_key(k) == "goagain" for k in noncanon), (
        "no spaced/lowercase go again spellings left in the corpus")

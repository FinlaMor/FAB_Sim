"""Creating a token with no JSON definition ABORTS THE GAME.

`effect_keywords.create_token` calls `require_card(token_slug)`, which raises
MissingCardImplementation. Not a wrong card -- a crash, mid-game, whenever the
effect resolves. Sixteen live cards referenced ten tokens that did not exist:

  Frostbite x5, Copper x2, Hyper Driver x2, and one each for Spellbane Aegis,
  Sigil of Fate, Zen State, Gate to iArathael, Blasmophet the Insatiable
  Hunger, and "FRAGMENT".

FRAGMENT was the odd one: Erode Authority prints exactly "**Dominate**
**Fragment**", two keywords and nothing else, and the implementation authored
BOTH as effects -- a DOMINATE effect duplicating a printed keyword, and a
CREATE_TOKEN for a token that was never a token. The release notes discuss
"attacks with fragment", an ability. So that card is now `abilities: []`, which
is what a card whose whole text is printed keywords should be.

The precedent was already here: tokens/aether_ashwing.json exists solely
because creating it raised MissingCardImplementation and aborted the game. That
fix was made for one token and the other ten were left.

Found by the draft-review pass, which flagged it on three drafts before anyone
looked at the live corpus.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.ability_keywords import create_token
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

#: The ten that were missing, so a regression names itself rather than showing
#: up as a generic sweep failure.
WERE_MISSING = ["frostbite", "copper", "hyper_driver", "spellbane_aegis",
                "sigil_of_fate", "zen_state", "gate_to_iarathael",
                "blasmophet_the_insatiable_hunger"]


def _slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def _every_created_token():
    """(card slug, token name) for every CREATE_TOKEN in the corpus."""
    out = []
    for path in JSON_ROOT.rglob("*.json"):
        rel = path.relative_to(JSON_ROOT)
        if (path.stem.endswith("_work_queue")
                or any(p.startswith(".") or p == "needs_review"
                       for p in rel.parts)):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "CREATE_TOKEN":
                    name = (node.get("token") or node.get("token_slug")
                            or node.get("token_name") or node.get("token_type"))
                    if name:
                        out.append((raw.get("slug"), str(name)))
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(raw.get("abilities"))
    return out


# --- the guard --------------------------------------------------------------

def test_every_created_token_has_a_definition():
    """Derived from the corpus, so it keeps probing as cards are added. A token
    without a definition is not a weak card, it is a crash."""
    missing = sorted({f"{card} -> {token}"
                      for card, token in _every_created_token()
                      if get_card(_slugify(token)) is None})
    assert missing == [], (
        "CREATE_TOKEN naming a token with no JSON definition; create_token's "
        f"require_card raises and the game aborts: {missing}")


def test_the_sweep_actually_finds_create_token_nodes():
    """A premise: if CREATE_TOKEN were renamed, the guard above would pass by
    looking at nothing."""
    found = _every_created_token()
    assert len(found) > 50, len(found)


# --- they really create, not merely parse -----------------------------------

@pytest.mark.parametrize("slug", WERE_MISSING)
def test_the_token_can_actually_be_created(slug):
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)

    create_token(st, 1, slug)          # raised MissingCardImplementation before

    made = [c for c in st.players[1].permanents.cards
            + st.players[1].tokens.cards if slug in (c.slug or "")]
    assert made, f"{slug} was created but landed in no zone"


# --- erode_authority: a keyword is not a token ------------------------------

def test_erode_authority_authors_nothing():
    """Its whole printed text is two keywords, both carried by the card DB.
    Authoring them again gave it a duplicate Dominate and a CREATE_TOKEN for a
    token that does not exist."""
    card = get_card("erode_authority_blue")
    assert card.abilities == [], [a.ability_type for a in card.abilities]


def test_erode_authority_really_only_prints_keywords():
    """The premise for the above."""
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    text = idx["erode_authority_blue"].get("functionalText") or ""
    stripped = re.sub(r"\*\*[^*]+\*\*", "", text).strip()
    assert stripped == "", f"it prints more than keywords now: {text!r}"

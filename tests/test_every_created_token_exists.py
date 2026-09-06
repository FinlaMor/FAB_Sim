"""A token with no JSON is a crash, not a missing feature.

`effect_keywords.create_token` calls `require_card(token_slug)`, which raises
`MissingCardImplementation`. So a card whose CREATE_TOKEN names a token nothing
defines does not quietly do less -- it ABORTS THE GAME, mid-resolution, every
time that effect resolves. One card takes down every game it appears in.

Chane shipped exactly this: the hero's once-per-turn signature ability creates a
Soul Shackle, and `tokens/soul_shackle.json` did not exist. Nothing caught it,
because every other gate the corpus has asks whether a card LOADS -- and this
one does. The failure is at resolution time, which only a played game reaches.

This test is the cheap version of playing every game: walk every CREATE_TOKEN
node in the corpus, resolve the slug the way create_token itself resolves it,
and require a definition. It is not a claim that the token is CORRECT, only
that asking for it cannot crash.

THE RESOLUTION HAS TO MATCH THE ENGINE'S, not a reimplementation of it. Two
details make a hand-rolled version wrong in opposite directions:

  * the token is authored under any of five keys (`token`, `token_name`,
    `token_type`, `token_slug`, `subtype`) -- CREATE_TOKEN reads all five, so a
    scan that reads one under-reports;
  * create_token accepts a DISPLAY name ("Seismic Surge") and falls back to its
    slugified form, so a scan that demands an exact slug over-reports.

A first pass here made both mistakes at once and reported two missing tokens
that were fine while missing the one that was real.
"""
import json
import pathlib
import re

import pytest

from engine.card_effects.dsl.loader import get_card, load_all_cards

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

#: Directories that are not part of the live corpus: drafts awaiting adoption,
#: their reviews, the pipeline's scratch queues, and quarantine.
NOT_LIVE = {".drafts", ".draft-review", ".quarantine", "batch", "needs_review"}

#: The keys CREATE_TOKEN reads, in the order effect_types.py reads them.
TOKEN_KEYS = ("token", "token_name", "token_type", "token_slug", "subtype")

load_all_cards()


def _live_card_files():
    for path in sorted(JSON_ROOT.rglob("*.json")):
        if path.name.endswith("_work_queue.json"):
            continue
        if set(path.relative_to(JSON_ROOT).parts) & NOT_LIVE:
            continue
        yield path


def _token_requests():
    """(token value as authored, slug of the card asking for it)."""
    out = []

    def walk(node, slug):
        if isinstance(node, dict):
            if str(node.get("type", "")).upper().startswith("CREATE_TOKEN"):
                for key in TOKEN_KEYS:
                    value = node.get(key)
                    if isinstance(value, str) and value:
                        out.append((value, slug))
                        break
            for value in node.values():
                walk(value, slug)
        elif isinstance(node, list):
            for value in node:
                walk(value, slug)

    for path in _live_card_files():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict):
            walk(raw.get("abilities"), raw.get("slug") or path.stem)
    return out


def _resolves(value: str) -> bool:
    """Exactly what create_token does: try the value, then its slugified form."""
    if get_card(value) is not None:
        return True
    alt = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return bool(alt) and get_card(alt) is not None


def test_the_scan_sees_the_corpus():
    """Guards the guard. If the walk or the key list broke, the test below
    would pass while checking nothing -- the same shape of silence it exists
    to catch."""
    requests = _token_requests()
    assert len(requests) >= 30, f"only {len(requests)} CREATE_TOKEN nodes found"
    assert len(list(_live_card_files())) > 500


def test_every_token_a_card_creates_has_a_definition():
    missing = {}
    for value, slug in _token_requests():
        if not _resolves(value):
            missing.setdefault(value, set()).add(slug)
    assert not missing, (
        "CREATE_TOKEN names a token with no JSON definition -- create_token "
        "raises MissingCardImplementation and the game ABORTS when the effect "
        "resolves:\n  "
        + "\n  ".join(f"{tok}  <- {', '.join(sorted(cards))}"
                      for tok, cards in sorted(missing.items()))
        + "\n\nAdd engine/card_effects/json/tokens/<slug>.json. A token whose "
          "own text cannot be expressed is still a file: an empty `abilities` "
          "with a _comment saying so keeps the game running.")

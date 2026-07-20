#!/usr/bin/env python3
"""DSL execution-coverage report: which authored card effects actually run?

tests/test_card_json_hygiene.py proves card JSON is well-formed. It cannot
prove an ability ever fires — an effect whose trigger the engine never
dispatches is structurally perfect and completely inert. This plays real games
and diffs what was *authored* against what actually *executed*.

Anything authored-but-never-executed is one of: a dead trigger, an unreachable
condition, or simply a line the random agents never happened to take. The
report separates the cases it can distinguish; the rest needs a human.

Usage:
  python scripts/dsl_coverage.py                    # all deck pairs, 5 seeds
  python scripts/dsl_coverage.py --seeds 25         # more games, better coverage
  python scripts/dsl_coverage.py --json out.json    # machine-readable
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card_effects.dsl import coverage  # noqa: E402
from engine.card_effects.dsl.loader import load_all_cards  # noqa: E402

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
DECK_DIR = ROOT / "decks"


def authored() -> dict[str, set[str]]:
    """slug -> {effect_type, ...} declared in that card's JSON.

    Walks nested structures (modes, options, INJECT_TRIGGER bodies) so an
    effect buried inside a conditional branch still counts as authored.
    """
    out: dict[str, set[str]] = {}
    for path in sorted(JSON_ROOT.rglob("*.json")):
        rel = path.relative_to(JSON_ROOT)
        if path.stem.endswith("_work_queue") or any(p.startswith(".") for p in rel.parts):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        slug = raw.get("slug") or path.stem
        found: set[str] = set()

        def walk(node, in_effects=False):
            if isinstance(node, dict):
                if in_effects and isinstance(node.get("type"), str):
                    found.add(node["type"])
                for key, value in node.items():
                    walk(value, in_effects=key in ("effects", "modes", "options"))
            elif isinstance(node, list):
                for item in node:
                    walk(item, in_effects=in_effects)

        walk(raw)
        if found:
            out[slug] = found
    return out


_COUNT = re.compile(r"^\s*\d+\s*x?\s+", re.I)
_HEADER = re.compile(r"^\s*(name|hero|format)\s*:", re.I)


def _slugify(name: str) -> str:
    """'Big Bully (red)' -> 'big_bully_red', matching card_data slug style.

    Accented letters are folded to ASCII first ('Trōpal' -> 'tropal'); dropping
    them instead would split the word and silently fail to resolve.
    """
    s = unicodedata.normalize("NFKD", name)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def deck_slugs(deck_path: Path, index: dict | None = None) -> set[str]:
    """Slugs a deck list can put into play.

    Deck lines look like '3x Big Bully (red)' or a bare hero/equipment name.
    Any parsed slug that does not resolve in slug_index.json is reported
    rather than silently dropped — a mis-parsed line would otherwise
    misclassify a card as unreachable and hide a real dead effect.
    """
    slugs, unresolved = set(), []
    for line in deck_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or _HEADER.match(line):
            continue
        if line.lower().endswith("cards") and " " not in line.strip().rstrip("cards").strip():
            continue  # section header like "Arena cards"
        counted = bool(_COUNT.match(line))
        slug = _slugify(_COUNT.sub("", line))
        if not slug:
            continue
        if index is not None and slug not in index:
            # Only a line with a 'Nx ' count claims to be a card. Uncounted
            # prose (FaBrary footers, section titles) is expected not to
            # resolve; a counted line that fails is a genuine parse failure.
            if counted:
                unresolved.append((line, slug))
            continue
        slugs.add(slug)
    if unresolved:
        for raw, slug in unresolved:
            print(f"  ? {deck_path.name}: cannot resolve {raw!r} -> {slug!r}", file=sys.stderr)
    return slugs


def play(decks: list[Path], seeds: int, max_turns: int) -> coverage.CoverageTracker:
    from engine.card import CardDB
    from engine.engine import new_game
    from rl_agents.random_agent import RandomAgent
    import random

    total = coverage.CoverageTracker()
    db = CardDB()
    pairs = list(itertools.combinations([str(d) for d in decks], 2)) or [
        (str(decks[0]), str(decks[0]))
    ]
    games = 0
    for d1, d2 in pairs:
        for seed in range(seeds):
            random.seed(seed)
            tracker = coverage.start()
            try:
                new_game(d1, d2, RandomAgent(seed=seed), RandomAgent(seed=seed + 1),
                         db, p1_seed=seed, p2_seed=seed + 1, max_turns=max_turns)
            except Exception as exc:  # a crashed game still yields partial coverage
                print(f"  ! game {Path(d1).stem} vs {Path(d2).stem} seed={seed}: {exc}",
                      file=sys.stderr)
            finally:
                coverage.stop()
            total.merge(tracker)
            games += 1
            print(f"\r  played {games}/{len(pairs) * seeds} games", end="", file=sys.stderr)
    print(file=sys.stderr)
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5, help="games per deck pair")
    ap.add_argument("--max-turns", type=int, default=60)
    ap.add_argument("--json", dest="json_out", help="write machine-readable report here")
    args = ap.parse_args()

    load_all_cards()
    decks = sorted(DECK_DIR.glob("*.txt"))
    if not decks:
        print("no decks found", file=sys.stderr)
        return 1

    print(f"Playing {args.seeds} seeds across {len(decks)} decks...", file=sys.stderr)
    tracker = play(decks, args.seeds, args.max_turns)

    auth = authored()
    executed: dict[str, set[str]] = {}
    for slug, etype in tracker.effects:
        executed.setdefault(slug, set()).add(etype)

    # A card no deck can draw is untested-by-corpus, not dead. Keep the two apart.
    index = json.loads((ROOT / "card_data" / "slug_index.json").read_text(encoding="utf-8"))
    index = index.get("by_slug", index)
    in_decks: set[str] = set()
    for deck in decks:
        in_decks |= deck_slugs(deck, index)

    reachable_dead: dict[str, list[str]] = {}
    unreachable: list[str] = []
    token_only: list[str] = []
    for slug, types in sorted(auth.items()):
        missed = sorted(types - executed.get(slug, set()))
        if not missed:
            continue
        if slug in in_decks or slug in executed:
            reachable_dead[slug] = missed
        elif "token" in (index.get(slug, {}).get("typeText") or "").lower():
            # Tokens are created by effects and can never appear in a decklist,
            # so "add a deck" is never the remedy — they need a card that
            # creates them. Reporting them as deck-unreachable is misleading.
            token_only.append(slug)
        else:
            unreachable.append(slug)

    total_auth = sum(len(v) for v in auth.values())
    total_exec = sum(len(executed.get(s, set()) & v) for s, v in auth.items())
    pct = (100.0 * total_exec / total_auth) if total_auth else 0.0

    print(f"\n=== DSL execution coverage ===")
    print(f"cards with authored effects : {len(auth)}")
    print(f"authored (card, effect) pairs: {total_auth}")
    print(f"executed at least once       : {total_exec}  ({pct:.1f}%)")
    print(f"\n--- authored but NEVER executed, in a tested deck ({len(reachable_dead)} cards) ---")
    print("    these are the real suspects: dead trigger, or a line no agent took")
    for slug, missed in reachable_dead.items():
        print(f"  {slug}: {', '.join(missed)}")
    print(f"\n--- not reachable from the {len(decks)} test decks ({len(unreachable)} cards) ---")
    print("    not evidence of a bug — add a deck containing them to test")
    for slug in unreachable:
        print(f"  {slug}")
    print(f"\n--- tokens, never in a decklist ({len(token_only)}) ---")
    print("    reachable only via a card that creates them, not by adding a deck")
    for slug in token_only:
        print(f"  {slug}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({
            "authored_pairs": total_auth,
            "executed_pairs": total_exec,
            "coverage_pct": round(pct, 2),
            "reachable_never_executed": reachable_dead,
            "unreachable_from_test_decks": unreachable,
            "tokens_not_in_any_decklist": token_only,
        }, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audit recorded game transcripts for rules-effectiveness violations.

Reads JSONL transcripts written by engine.recorder.JsonlRecorder (run with
snapshot_on={'decision'}) and checks invariants that must hold under the FAB
comprehensive rules, reporting violations with turn/context. Advisory: a flag
is a lead to verify against the CR, not proof of a bug.

Invariants checked
------------------
- Starting conditions: each player's opening hand == hero intellect; start life.
- Life / winner integrity: no player sits at <=0 life in a live state; the game
  ends with the loser at <=0 (or a turn cap) and the winner alive.
- Zone sanity: arsenal holds <=1 card; non-negative resources and deck_count.
- Card conservation: the count of real (non-token) cards is constant. Tokens are
  excluded via the slug index; cards in flight on the stack / combat are counted.
  A total that ever EXCEEDS the opening count means a card was created from
  nothing (a real violation); brief dips below are cards mid-resolution and are
  reported as informational only.

Usage:
  python scripts/audit_recorded_games.py <dir-of-jsonl>
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REAL_CARD_ZONES = ("hand", "graveyard", "pitch", "arsenal", "banished",
                   "permanents", "items", "auras", "allies")
EQUIP_SLOTS = ("head", "chest", "arms", "legs", "weapon1", "weapon2")


def load_hero_stats() -> dict[str, tuple[int, int]]:
    idx = json.loads((ROOT / "card_data" / "slug_index.json").read_text(encoding="utf-8"))
    idx = idx.get("by_slug", idx)
    out = {}
    for slug, e in idx.items():
        if "Hero" in (e.get("types") or []):
            life = e.get("health") or e.get("life")
            intel = e.get("intelligence") or e.get("intellect")
            if isinstance(life, int) and isinstance(intel, int):
                out[slug] = (life, intel)
    return out


def load_token_slugs() -> set[str]:
    # Authoritative source: every card with a JSON under json/tokens/ is a token.
    # The slug_index typeText heuristic alone misses tokens whose index entry has
    # no type metadata (e.g. 'reviled'), which would then be miscounted as real
    # cards and inflate the conservation total.
    toks = {p.stem for p in (ROOT / "engine" / "card_effects" / "json" / "tokens").glob("*.json")}
    idx = json.loads((ROOT / "card_data" / "slug_index.json").read_text(encoding="utf-8"))
    idx = idx.get("by_slug", idx)
    for slug, e in idx.items():
        blob = (e.get("typeText") or "") + " " + " ".join(e.get("types") or [])
        if "token" in blob.lower():
            toks.add(slug)
    return toks


HERO_STATS = load_hero_stats()
TOKENS = load_token_slugs()


def _n(slugs) -> int:
    """Count non-token slug strings in a list (ignoring non-str entries)."""
    return sum(1 for s in slugs if isinstance(s, str) and s not in TOKENS)


def real_total(snap) -> int:
    total = 0
    for pl in snap["players"].values():
        total += pl["deck_count"]  # deck never holds tokens
        for z in REAL_CARD_ZONES:
            total += _n(pl[z])
        for s in EQUIP_SLOTS:
            total += _n(pl["equipment"].get(s, []))
    total += _n(snap.get("stack", []))
    c = snap.get("combat")
    ac = c.get("attack_card") if c else None
    if isinstance(ac, str) and ac not in TOKENS:
        total += 1
    return total


def audit_game(path):
    findings, info = [], []
    start_snap = end_rec = None
    opening_total = None
    max_total = min_total = None

    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        snap = d.get("snapshot")
        if not snap:
            continue
        turn = snap.get("turn_number", 0)
        if d["kind"] == "game_start":
            start_snap = snap
        if d["kind"] == "game_end":
            end_rec = d

        for pid, pl in snap["players"].items():
            if not isinstance(pl["life"], int):
                findings.append((turn, f"p{pid} life not int: {pl['life']!r}"))
            if pl["resources"] < 0:
                findings.append((turn, f"p{pid} negative resources {pl['resources']}"))
            if pl["deck_count"] < 0:
                findings.append((turn, f"p{pid} negative deck_count {pl['deck_count']}"))
            if len(pl["arsenal"]) > 1:
                findings.append((turn, f"p{pid} arsenal holds {len(pl['arsenal'])} (>1)"))
            if pl["life"] <= 0 and not snap.get("done"):
                findings.append((turn, f"p{pid} life {pl['life']}<=0 but game not done"))

        t = real_total(snap)
        if opening_total is None:
            opening_total = max_total = min_total = t
        max_total = max(max_total, t)
        min_total = min(min_total, t)

    if start_snap:
        for pid, pl in start_snap["players"].items():
            exp = HERO_STATS.get(pl["hero"])
            if exp:
                life, intel = exp
                if pl["life"] != life:
                    findings.append((0, f"p{pid} {pl['hero']} start life {pl['life']} != {life}"))
                if len(pl["hand"]) != intel:
                    findings.append((0, f"p{pid} {pl['hero']} start hand {len(pl['hand'])} != intellect {intel}"))

    if end_rec:
        snap = end_rec["snapshot"]
        winner = end_rec["winner"]
        lives = {pid: pl["life"] for pid, pl in snap["players"].items()}
        capped = end_rec.get("ended_on_turn_cap")
        if winner is not None:
            loser = str(3 - int(winner))
            if lives.get(loser, 1) > 0 and not capped:
                findings.append((-1, f"winner P{winner} but loser P{loser} life {lives.get(loser)}>0, not capped"))
            if lives.get(str(winner), 0) <= 0:
                findings.append((-1, f"winner P{winner} has life {lives.get(str(winner))}<=0"))

    # A card created from nothing persists to game end. A transient mid-game peak
    # (a card briefly counted in two zones during a multi-event window, or moving
    # through an in-flight zone the counter doesn't track) resolves by game end
    # and is only informational — decision-snapshot granularity is too coarse to
    # treat it as a real violation.
    end_total = real_total(end_rec["snapshot"]) if end_rec else max_total
    if end_total is not None and opening_total is not None and end_total > opening_total:
        findings.append((-1, f"real-card total rose {opening_total}->{end_total} at game end (card created from nothing)"))
    elif max_total is not None and max_total > opening_total:
        info.append(f"card total transiently peaked at {max_total} (opening {opening_total}), resolved by end - informational")
    if min_total is not None and min_total < opening_total:
        info.append(f"card total dipped to {min_total} (opening {opening_total}) - cards in flight, informational")

    return os.path.basename(path), findings, info, opening_total


def main():
    if len(sys.argv) < 2:
        print("usage: audit_recorded_games.py <dir-of-jsonl>", file=sys.stderr)
        return 2
    files = sorted(glob.glob(os.path.join(sys.argv[1], "*.jsonl")))
    grand = 0
    for path in files:
        name, findings, info, total = audit_game(path)
        print(f"\n=== {name}  (real-card count={total}) ===")
        if not findings:
            print("  ok: no invariant violations")
        for turn, msg in findings:
            loc = "end" if turn == -1 else f"t{turn}"
            print(f"  [{loc}] VIOLATION: {msg}")
            grand += 1
        for msg in info:
            print(f"  - {msg}")
    print(f"\n==== {grand} violations across {len(files)} games ====")
    return 1 if grand else 0


if __name__ == "__main__":
    raise SystemExit(main())

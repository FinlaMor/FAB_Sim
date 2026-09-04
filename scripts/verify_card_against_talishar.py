#!/usr/bin/env python3
"""Verify ONE card against the real games that actually played it.

A pipeline step, not a sweep. After authoring a card and writing its
behavioural test, this asks a different question than the test does: not "does
it do what I think the text says" but "does it do what an independent
implementation of the rules did, in games real people played".

    python scripts/verify_card_against_talishar.py --card felling_of_the_crown_red

WHAT IT CHECKS

  power      For every real attack made with the card, rebuild the board from
             the spectator feed, put the attack on the chain, and compare our
             computed attack power with Talishar's own `total_power`.
             (scripts/talishar_attack_replay.py holds the machinery.)
  keywords   Every keyword flag Talishar reported for the card across those
             attacks, against the keywords our engine gives it.
  presence   How often the card shows up at all, which is the honest prior on
             everything above: a card with two observations tells you nothing.

WHY AN INDEX. Both a full JSON parse and a SQL LIKE prefilter cost 20-40s per
card on a 10.6GB event store, because SQLite scans the blob column either way.
That is fine once and hopeless per card in a batch, so the first run builds a
slug -> rowid index and later runs are instant. `--refresh-index` picks up
games collected since, incrementally from the last rowid seen.

WHAT A DISAGREEMENT MEANS. Read it as a lead, never a verdict. The replay
harness fails in the direction that manufactures findings — a gap in the
reconstruction is indistinguishable from a defect in the card — and three
classes are known to be unreconstructible from spectator data:

  * "you've been booed this turn" and the rest of the crowd state, which exists
    only as English in the chat log
  * whether an attack action was played FROM ARSENAL, since 94% of the arsenal
    a spectator sees is CardBack
  * anything gated on a player CHOICE ("you MAY banish ... if you do, +1")

Those are reported under KNOWN LIMITS rather than as failures. Everything else
is worth reading the board for; --explain prints it.
"""
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.talishar_attack_replay import (  # noqa: E402
    DB, DB_PATH, FLAGS_TO_KEYWORDS, _ids, build_state, canonical, hero_name,
    our_power,
)

INDEX_PATH = ROOT / "card_data" / "talishar_card_index.json"

#: Text that marks a card as depending on state the spectator feed does not
#: carry. Matched against the card's own functionalText, so the verdict can
#: separate "we disagree" from "this could never have been checked".
UNRECONSTRUCTABLE = (
    ("booed", "crowd state appears only in the chat log"),
    ("cheered", "crowd state appears only in the chat log"),
    ("from arsenal", "arsenal is face-down to spectators (94% CardBack)"),
    ("you may", "depends on a player choice that is not in the state"),
)


def build_index(db_path, previous=None, verbose=True):
    """slug -> rowids where that slug is the ATTACKING card."""
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    index = collections.defaultdict(list)
    played = collections.Counter()
    since = 0
    if previous:
        for slug, rows in (previous.get("attacks") or {}).items():
            index[slug] = list(rows)
        played.update(previous.get("played") or {})
        since = int(previous.get("max_rowid") or 0)

    started = time.time()
    max_rowid = since
    scanned = 0
    for rowid, data in con.execute(
            "SELECT rowid, data FROM events WHERE rowid > ? AND data IS NOT NULL",
            (since,)):
        max_rowid = max(max_rowid, rowid)
        scanned += 1
        try:
            gs = json.loads(data)["gameState"]
        except Exception:
            continue
        lp = gs.get("last_played_card")
        if isinstance(lp, dict):
            lp = lp.get("cardNumber")
        if isinstance(lp, str) and lp:
            played[canonical(lp)] += 1
        cc = gs.get("combat_chain") or {}
        slug = cc.get("attacking_card")
        if isinstance(slug, str) and slug and slug != "CardBack":
            index[canonical(slug)].append(rowid)
    if verbose:
        print("indexed %d new event(s) in %.0fs" % (scanned, time.time() - started))
    return {"max_rowid": max_rowid,
            "attacks": {k: v for k, v in index.items()},
            "played": dict(played)}


def load_index(db_path, refresh=False, verbose=True):
    previous = None
    if INDEX_PATH.exists():
        try:
            previous = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except Exception:
            previous = None
    if previous is not None and not refresh:
        return previous
    index = build_index(db_path, previous, verbose)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index), encoding="utf-8")
    return index


_SLUG_INDEX = None


def _slug_index():
    global _SLUG_INDEX
    if _SLUG_INDEX is None:
        _SLUG_INDEX = json.loads((ROOT / "card_data" / "slug_index.json")
                                 .read_text(encoding="utf-8"))["by_slug"]
    return _SLUG_INDEX


def known_limits(slug):
    text = ((_slug_index().get(slug) or {}).get("functionalText") or "").lower()
    return [why for phrase, why in UNRECONSTRUCTABLE if phrase in text]


def attacks_for(db_path, rowids):
    """Yield the FIRST state of each distinct attack among these rows."""
    if not rowids:
        return
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    prev = {}
    chunk = 900
    for start in range(0, len(rowids), chunk):
        batch = rowids[start:start + chunk]
        placeholders = ",".join("?" * len(batch))
        for gid, data in con.execute(
                "SELECT game_id, data FROM events WHERE rowid IN (%s) "
                "ORDER BY rowid" % placeholders, batch):
            try:
                gs = json.loads(data)["gameState"]
            except Exception:
                continue
            cc = gs.get("combat_chain") or {}
            slug = cc.get("attacking_card")
            if prev.get(gid) == slug:
                continue
            prev[gid] = slug
            yield gid, gs, cc


def verify(slug, db_path, explain=False, refresh=False):
    index = load_index(db_path, refresh)
    rowids = (index.get("attacks") or {}).get(slug) or []
    plays = (index.get("played") or {}).get(slug, 0)

    print("CARD: %s" % slug)
    card = DB.get(slug)
    if card is None:
        print("  not in card_data")
        return 2
    print("  observed being played   : %d state(s)" % plays)
    print("  observed attacking      : %d state(s)" % len(rowids))

    checked = agree = 0
    mismatches = []
    flags_seen = collections.Counter()
    attacks = 0

    for gid, gs, cc in attacks_for(db_path, rowids):
        attacks += 1
        for flag, keyword in FLAGS_TO_KEYWORDS.items():
            if cc.get(flag):
                flags_seen[keyword] += 1
        theirs = cc.get("total_power")
        if not isinstance(theirs, int):
            continue
        if cc.get("total_defense") or cc.get("reactions") or cc.get("chain_links"):
            continue
        p, o = gs.get("player") or {}, gs.get("opponent") or {}
        target = str(cc.get("attack_target") or "").strip().lower()
        pn, on = hero_name(p), hero_name(o)
        norm = lambda s: "".join(ch for ch in s if ch.isalnum())
        p_hit, o_hit = norm(target) == norm(pn), norm(target) == norm(on)
        if o_hit and not p_hit:
            side, other = p, o
        elif p_hit and not o_hit:
            side, other = o, p
        else:
            continue
        if _ids(side.get("effects")) or _ids(other.get("effects")):
            continue
        try:
            st = build_state(side, other)
            ours = our_power(st, slug)
        except Exception:
            continue
        checked += 1
        if ours == theirs:
            agree += 1
        else:
            mismatches.append((gid, gs.get("turn_no"), ours, theirs, side, other))

    print("  distinct attacks        : %d" % attacks)
    if checked:
        print("  power replayed          : %d/%d agree (%.0f%%)"
              % (agree, checked, 100 * agree / checked))
    else:
        print("  power replayed          : 0 comparable attacks")

    ours_kw = set(card.keywords or [])
    surprising = {k: n for k, n in flags_seen.items()
                  if k not in ours_kw and attacks and n / attacks >= 0.98}
    if surprising:
        print("  keywords Talishar always reported that we lack: %s"
              % ", ".join(sorted(surprising)))

    limits = known_limits(slug)
    if limits:
        print("\n  KNOWN LIMITS (a disagreement here may not be a defect):")
        for why in dict.fromkeys(limits):
            print("     - %s" % why)

    if mismatches:
        print("\n  DISAGREEMENTS (%d):" % len(mismatches))
        for gid, turn, ours, theirs, side, other in mismatches[:10]:
            print("     game %-9s turn %-4s ours=%-4s theirs=%-4s" % (gid, turn, ours, theirs))
            if explain:
                print("        attacker %s" % hero_name(side))
                for z in ("equipment", "auras", "items", "allies", "permanents"):
                    v = _ids(side.get(z))
                    if v:
                        print("          %-10s %s" % (z, v))
                print("          banish(%d) discard(%d)"
                      % (len(_ids(side.get("banish"))), len(_ids(side.get("discard")))))

    if not attacks:
        print("\nVERDICT: NO EVIDENCE - this card never attacks in the corpus.")
        return 0
    if not checked:
        print("\nVERDICT: NO COMPARABLE ATTACK - every appearance was excluded.")
        return 0
    if not mismatches:
        print("\nVERDICT: AGREES with Talishar on %d attack(s)." % checked)
        return 0
    if limits:
        print("\nVERDICT: DISAGREES on %d of %d, but this card depends on state the "
              "feed does not carry. Read the board before believing it." % (len(mismatches), checked))
        return 0
    print("\nVERDICT: DISAGREES on %d of %d attacks. Re-run with --explain."
          % (len(mismatches), checked))
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", required=True)
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--explain", action="store_true",
                    help="Print the attacker's board for each disagreement.")
    ap.add_argument("--refresh-index", action="store_true",
                    help="Index games collected since the last run.")
    args = ap.parse_args()
    return verify(args.card, args.db, args.explain, args.refresh_index)


if __name__ == "__main__":
    raise SystemExit(main())

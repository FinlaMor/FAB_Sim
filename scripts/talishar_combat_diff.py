#!/usr/bin/env python3
"""Differential-test ATTACK KEYWORDS against real Talishar games.

The sibling scripts compare a card PLAY (talishar_outcome_diff.py) or the
playable set (talishar_legality_diff.py). Neither can say anything about attack
action cards: an attack goes to the combat chain, its effects are on-attack and
on-hit, and a neutral play-and-resolve never touches them. Attacks are the
largest and most important card class in the game, and they were the blind spot.

This closes it, using a property of the spectator feed that needs no state
reconstruction at all. FAB_Coach's fab_games.db stores every `gameState` a
spectator saw across 1,981 real games, and each one carries the resolved combat
chain:

    {"attacking_card": "savage_claw", "total_power": 3, "go_again": true,
     "dominate": false, "overpower": false, "piercing": false, ...}

That is Talishar's own computed answer for the live attack. Aggregated over
318,870 attack observations it says what a card's keywords ACTUALLY are, from
an independent implementation of the same rules.

WHAT IS TRUSTWORTHY HERE, and what is not. A printed keyword should be true in
every appearance of the card; a granted or conditional one varies. Measured
per-card over cards with >=30 observations:

    piercing    508 cards always-off,   8 always-on,   3 in between   <- printed
    phantasm    506                     5              8
    fusion      514                     0              5
    overpower   495                     2             22
    dominate    455                     6             58
    go_again    150                    92            277              <- granted
    combo       494                     2             23              <- condition
    confidence  504                     0             15              <- condition
    wager       490                     0             29              <- condition

So only the ALWAYS-ON direction is used: a flag true in >=98% of >=30
observations is a keyword the card really has. The always-off direction is
reported separately and is weaker — a conditional keyword whose condition never
came up looks identical to an absent one.

AN "OBSERVATION" IS AN EVENT, NOT AN ATTACK. The combat chain sits in every
gameState for as long as the attack is live, so one real attack contributes as
many observations as the spectator saw events during it — roughly 10-20. Treat
the counts as relative weight, not as a sample size: 985 observations is a lot
of attacks, 30 might be two. This is why MIN_OBS is a floor and not a
confidence level, and why the low-count rows deserve a manual look before they
are believed.

POWER IS DELIBERATELY NOT CHECKED. Two heuristics were tried and both fail:

* "is our printed power ever observed?" — 23 cards failed, all 23 false. They
  are cards whose own text pumps them nearly always: reckless_arithmetic_blue
  rolls a d6 and gets +X, so its printed 1 is unobservable by construction;
  speed_demon_red gets +1 while you control a Hyper Driver, which in a real
  Mechanologist deck is always.
* "does the MINIMUM observed power equal the printed power, for cards with no
  self-pump?" — 116 of 337 failed, and the minimums include -1 and -3. Attack
  power is pushed DOWN by opposing effects at least as often as up, and the
  minimum is an outlier a handful of times out of thousands.

In real competitive play almost every attack is modified in one direction or
the other, so `total_power` cannot validate printed power. Left out rather than
left in as noise. The keyword flags survive precisely because they are boolean
and a printed keyword cannot be removed by an opponent.

    python scripts/talishar_combat_diff.py
"""
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = "C:/Users/Joseph/Desktop/FAB_Coach/fab_games.db"

#: Talishar combat-chain flag -> our keyword spelling in card_data.
FLAGS = {
    "go_again": "GoAgain",
    "dominate": "Dominate",
    "overpower": "Overpower",
    "piercing": "Piercing",
    "phantasm": "Phantasm",
    "fusion": "Fusion",
    "wager": "Wager",
    "combo": "Combo",
}

#: Flags whose absence is meaningful. The rest are conditions rather than
#: keywords — `combo` is "the combo condition is met", not "this has combo" —
#: so "never observed" says nothing about the printed card.
ABSENCE_IS_MEANINGFUL = ("dominate", "overpower", "piercing", "phantasm")

MIN_OBS = 30
ALWAYS = 0.98


def merge_dual_wield(slug, index):
    """Talishar tags the SECOND copy of a dual-wielded one-handed weapon with a
    `_r` suffix (hunters_klaive / hunters_klaive_r). There is no `_l` because
    the first copy is unsuffixed, and both carry identical power distributions.
    Not a distinct card, so fold it back onto the stem."""
    if slug.endswith("_r") and slug[:-2] in index:
        return slug[:-2]
    return slug


def scan(db_path, game_id=None):
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    seen = collections.Counter()
    played = collections.Counter()
    flag_true = collections.defaultdict(collections.Counter)
    if game_id:
        rows = con.execute(
            "SELECT data FROM events WHERE game_id = ? AND data IS NOT NULL",
            (game_id,))
    else:
        rows = con.execute("SELECT data FROM events WHERE data IS NOT NULL")
    for (data,) in rows:
        try:
            gs = json.loads(data)["gameState"]
        except Exception:
            continue
        lp = gs.get("last_played_card")
        if isinstance(lp, dict):
            lp = lp.get("cardNumber")
        if isinstance(lp, str) and lp and lp != "CardBack":
            played[lp] += 1
        cc = gs.get("combat_chain") or {}
        a = cc.get("attacking_card")
        if not (isinstance(a, str) and a and a != "CardBack"):
            continue
        seen[a] += 1
        for f in FLAGS:
            if cc.get(f):
                flag_true[a][f] += 1
    return seen, flag_true, played


def audit_one_game(db_path, game_id, index):
    """Everything one real game says about our corpus.

    Deliberately reports raw agreement rather than applying the >=30
    observation floor: a single game cannot clear it, and the point here is to
    see what a freshly collected game contains, not to draw corpus-wide
    conclusions from it.
    """
    from engine.card_effects.dsl.loader import get_card, load_all_cards
    load_all_cards()

    seen, flag_true, played = scan(db_path, game_id)
    print("GAME %s" % game_id)
    print("  attack observations: %d over %d distinct attacking cards"
          % (sum(seen.values()), len(seen)))
    print("  distinct cards played: %d" % len(played))

    cards = [c for c in played if c in index or c.islower()]
    impl = [c for c in cards if get_card(c) is not None]
    print("  of those, implemented: %d of %d (%.0f%%)"
          % (len(impl), len(cards), 100 * len(impl) / max(1, len(cards))))

    # Talishar mixes internal identifiers into last_played_card ("CBFABChaos").
    # Real slugs are lowercase; anything with capitals that card data has never
    # heard of is machinery, not a card we are missing.
    def is_card(slug):
        return slug in index or slug.islower()

    noise = sorted(c for c in played if not is_card(c))
    unimpl = sorted((c for c in played if is_card(c) and get_card(c) is None),
                    key=lambda c: -played[c])
    if unimpl:
        print("\n  PLAYED BUT NOT IMPLEMENTED")
        for slug in unimpl[:20]:
            print("     %-38s %d obs%s"
                  % (slug, played[slug],
                     "" if slug in index else "   (not in card data either)"))
    if noise:
        print("\n  ignored non-card identifiers: %s" % ", ".join(noise))

    print("\n  ATTACK KEYWORDS vs OUR CARD DATA")
    disagreements = 0
    for slug, n in seen.most_common():
        stem = merge_dual_wield(slug, index)
        entry = index.get(stem)
        if entry is None:
            print("     %-34s %4d obs  NOT IN CARD DATA" % (slug, n))
            disagreements += 1
            continue
        ours = set(entry.get("keywords") or [])
        for tal, name in FLAGS.items():
            ratio = flag_true[slug][tal] / n
            if ratio >= ALWAYS and name not in ours:
                print("     %-34s %4d obs  %s reported %.0f%%, we lack it"
                      % (stem, n, name, 100 * ratio))
                disagreements += 1
    if not disagreements:
        print("     (no disagreements)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--min-obs", type=int, default=MIN_OBS)
    ap.add_argument("--game", help="Audit a single game id instead of the corpus.")
    args = ap.parse_args()

    index = json.loads((ROOT / "card_data" / "slug_index.json")
                       .read_text(encoding="utf-8"))["by_slug"]

    if args.game:
        return audit_one_game(args.db, args.game, index)

    seen, flag_true, _played = scan(args.db)

    merged_seen = collections.Counter()
    merged_flags = collections.defaultdict(collections.Counter)
    unknown = collections.Counter()
    for slug, n in seen.items():
        stem = merge_dual_wield(slug, index)
        if stem not in index:
            unknown[stem] += n
            continue
        merged_seen[stem] += n
        for f, c in flag_true[slug].items():
            merged_flags[stem][f] += c

    print("attack observations: %d over %d distinct cards"
          % (sum(seen.values()), len(seen)))
    print("cards with >=%d observations: %d"
          % (args.min_obs, sum(1 for n in merged_seen.values() if n >= args.min_obs)))

    missing, extra = [], []
    for slug, n in merged_seen.items():
        if n < args.min_obs:
            continue
        ours = set(index[slug].get("keywords") or [])
        for tal, name in FLAGS.items():
            ratio = merged_flags[slug][tal] / n
            if ratio >= ALWAYS and name not in ours:
                missing.append((slug, name, n, ratio))
            elif ratio == 0.0 and name in ours and tal in ABSENCE_IS_MEANINGFUL:
                extra.append((slug, name, n))

    print("\nTALISHAR REPORTS THE KEYWORD ON EVERY APPEARANCE; OUR DATA LACKS IT")
    for slug, name, n, r in sorted(missing, key=lambda x: -x[2]):
        print("   %-34s %-10s %5d obs  %.0f%%" % (slug, name, n, 100 * r))
    if not missing:
        print("   (none)")

    print("\nWE DECLARE THE KEYWORD; TALISHAR NEVER ONCE REPORTED IT")
    for slug, name, n in sorted(extra, key=lambda x: -x[2]):
        print("   %-34s %-10s %5d obs" % (slug, name, n))
    if not extra:
        print("   (none)")

    print("\nATTACK CARDS SEEN IN REAL PLAY THAT ARE NOT IN OUR CARD DATA")
    for slug, n in unknown.most_common(20):
        print("   %-34s %5d obs" % (slug, n))
    if not unknown:
        print("   (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

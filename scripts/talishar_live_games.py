#!/usr/bin/env python3
"""What real competitive Talishar games say about this corpus.

FAB_Coach spectates talishar.net (spectator_bot.py, playerID=3) and stores every
SSE `game_state_update` in fab_games.db. That is 1,981 real games across 59
heroes -- human competitive play, not bot self-play, and not our own engine.

WHAT A SPECTATOR CAN AND CANNOT SEE. Both players' discard, banish, pitch,
arsenal, equipment, allies, auras, items, permanents and effects are fully
visible, as is health and every count. HANDS ARE NOT: they arrive as "CardBack",
with only `hand_size` for the opponent. So a state cannot be rebuilt well enough
to replay a play from hand -- which is what scripts/talishar_outcome_diff.py
does with the headless corpus, where hands are open.

Two things this data answers that the headless corpus cannot:

  coverage    which cards competitive players ACTUALLY play, and how many of
              them we implement. A prioritised implementation queue drawn from
              real play rather than from set order.
  inertness   a card that visibly changes the board in real games and changes
              NOTHING in ours is inert. That is the defect class this corpus is
              best at finding, because it needs no state reconstruction: it
              compares "something happened" against "nothing happened".

    python scripts/talishar_live_games.py --events 60000
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = "C:/Users/Joseph/Desktop/FAB_Coach/fab_games.db"

import engine.engine as E
from engine.actions import ActionType
from engine.card import CardDB
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.play import apply_action, available_actions
from engine.state import Step
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _played_card(gs):
    lp = gs.get("last_played_card")
    if isinstance(lp, dict):
        c = lp.get("cardNumber")
    else:
        c = lp
    if isinstance(c, str) and c and c != "CardBack":
        return c
    return None


def _visible(gs):
    """The counts a spectator can see, for both players."""
    out = {}
    for side in ("player", "opponent"):
        d = gs.get(side) or {}
        pre = side[0]
        for k in ("health", "action_pts", "pitch_count", "deck_count", "soul_count"):
            try:
                out["%s.%s" % (pre, k)] = int(d.get(k) or 0)
            except (TypeError, ValueError):
                out["%s.%s" % (pre, k)] = 0
        for k in ("discard", "banish", "pitch", "arsenal", "allies", "auras",
                  "items", "permanents", "effects"):
            out["%s.%s" % (pre, k)] = len(d.get(k) or [])
    return out


def our_delta(slug):
    """What playing this card changes in a neutral state, or None if unplayable."""
    st = _make_state()
    st.card_db = DB
    st.active_player = 1
    st.step = Step.ACTION
    st.players[1].resources = 9
    st.players[1].action_points = 1
    card = copy.deepcopy(DB.get(slug))
    if card is None:
        return None
    card.owner = card.controller = 1
    st.players[1].hand.add(card)

    def snap():
        p, o = st.players[1], st.players[2]
        return (p.life, o.life, len(p.graveyard.cards), len(p.banished.cards),
                len(p.auras.cards), len(p.items.cards), len(p.allies.cards),
                len(p.arsenal.cards), len(p.deck.cards), p.resources)

    offers = [a for a in available_actions(st, 1)
              if getattr(a.card, "slug", None) == slug
              and a.type == ActionType.PLAY_CARD]
    if not offers:
        return None
    before = snap()
    try:
        apply_action(st, offers[0])
        E.resolve_stack(st)
    except Exception:
        return "CRASH"
    after = snap()
    # The card leaving hand for the graveyard is not an EFFECT.
    return tuple(a - b for a, b in zip(after, before))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=60000)
    ap.add_argument("--db", default=DB_PATH)
    args = ap.parse_args()

    con = sqlite3.connect("file:%s?mode=ro" % args.db, uri=True)
    games = con.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    heroes = con.execute("SELECT COUNT(DISTINCT hero) FROM games").fetchone()[0]

    played = collections.Counter()
    visible_change = collections.Counter()
    seen_after = {}
    scanned = 0

    prev_by_game = {}
    for gid, data in con.execute(
            "SELECT game_id, data FROM events WHERE data IS NOT NULL LIMIT ?",
            (args.events,)):
        try:
            gs = json.loads(data)["gameState"]
        except Exception:
            continue
        scanned += 1
        vis = _visible(gs)
        slug = _played_card(gs)
        prev = prev_by_game.get(gid)
        prev_by_game[gid] = (vis, slug)
        if slug:
            played[slug] += 1
            # A new card became "last played" and something visible moved.
            if prev and prev[1] != slug and any(
                    vis.get(k) != prev[0].get(k) for k in vis):
                visible_change[slug] += 1

    impl = {c for c in played if get_card(c) is not None}
    total = sum(played.values())
    covered = sum(v for k, v in played.items() if k in impl)

    print("real spectated games: %d across %d heroes" % (games, heroes))
    print("events scanned: %d" % scanned)
    print("distinct cards played: %d | implemented: %d (%.0f%%)"
          % (len(played), len(impl), 100 * len(impl) / max(1, len(played))))
    print("plays on implemented cards: %d / %d (%.0f%%)"
          % (covered, total, 100 * covered / max(1, total)))

    print("\nMOST-PLAYED CARDS WE DO NOT IMPLEMENT")
    print("(a prioritised queue drawn from real competitive play)")
    for slug, n in collections.Counter(
            {k: v for k, v in played.items() if k not in impl}).most_common(25):
        print("   %-38s %d" % (slug, n))

    print("\nIMPLEMENTED NON-ATTACK CARDS THAT DO NOTHING IN OUR ENGINE")
    print("(visibly changed the board in real games; no state change in ours)")
    # ATTACK ACTION CARDS ARE EXCLUDED, and the check was worthless without
    # that. An attack goes to the COMBAT CHAIN and its effects are on-attack /
    # on-hit, none of which a neutral play-and-resolve touches. Every one of the
    # 18 cards the unfiltered version flagged was an attack: a blind spot in the
    # probe, not an inert card.
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    suspects = []
    for slug, n in played.most_common():
        if slug not in impl or visible_change.get(slug, 0) < 5:
            continue
        if "Attack" in ((idx.get(slug) or {}).get("subtypes") or []):
            continue
        d = our_delta(slug)
        if d is None:
            continue
        if d == "CRASH":
            suspects.append((slug, n, "CRASHES"))
        elif not any(d):
            suspects.append((slug, n, "no change"))
    for slug, n, why in suspects[:25]:
        print("   %-38s played %-6d %s" % (slug, n, why))
    if not suspects:
        print("   (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

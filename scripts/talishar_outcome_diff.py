#!/usr/bin/env python3
"""Differential-test CARD OUTCOMES against Talishar.

Talishar is an independent implementation of the same rules, and
FAB_Sim_Headless drives the real PHP engine. Its parquet records hold, per
transition, the full state before, the action taken, and the state after.

WHICH TRANSITIONS ARE USABLE, and why it is not all of them. `next_state_json`
is the state immediately after Talishar's ProcessInput, which for a card play is
usually BEFORE the card resolves -- it goes on the stack and resolution happens
over later steps as priority passes. Measured over ~2,000 plays:

    55%   the stack is EMPTY in next_state -- the card resolved as part of the
          same input, so next_state IS the post-effect state
    16%   a clean span: the stack empties a few steps later with nothing else
          played in between
    29%   another card was played before the stack emptied, so a delta cannot
          be attributed to one card

Only the first group is used here. It is the largest, needs no attribution
argument, and there are roughly 76,000 of them across the corpus.

WHAT IS COMPARED. Life and resources exactly, and the SIZE of every zone. Not
zone contents: Talishar publishes `deck_count` rather than deck order, so a card
that draws produces a card whose identity we cannot know. Sizes still catch a
wrong life swing, a wrong resource spend, the wrong number of cards moved, and a
missing or extra draw -- which is most of what a card does.

Plays needing a pitch are skipped (`resources >= cost` only), because which card
a player pitches is a choice, and ours would differ from theirs for reasons that
are not defects.

    python scripts/talishar_outcome_diff.py --files 40 --limit 400
"""
from __future__ import annotations

import argparse
import copy
import glob
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CORPUS = "C:/Users/Joseph/Desktop/FAB_Sim_Headless/datasets/*/parquet/games/*.parquet"

import engine.engine as E
from engine.actions import ActionType
from engine.card import CardDB
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.play import apply_action, available_actions
from engine.state import Step
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

#: Deck filler. Talishar publishes deck_count, not deck order, so a draw has to
#: come from somewhere; a real implemented card keeps sizes honest and the drawn
#: object valid. Its identity is never compared.
FILLER = "head_jab_red"

ZONES = ("hand", "arsenal", "graveyard", "banished", "pitch",
         "items", "auras", "allies", "permanents", "soul")

#: `permanents` is NOT compared. In our engine it is the union of the arena --
#: an aura appears in BOTH `auras` and `permanents`, as the same object -- while
#: Talishar keeps them disjoint. Counting it turned every token creation into a
#: false disagreement, and it was the single largest bucket before this was
#: checked. `auras`, `items` and `allies` are disjoint on both sides and carry
#: the same information.
NOT_COMPARED = ("permanents",)


def _mk(slug, pid):
    proto = DB.get(slug)
    if proto is None:
        return None
    c = copy.deepcopy(proto)
    c.owner = c.controller = pid
    return c


def build_state(st_json):
    """Rebuild a Talishar state in our engine, as fully as the JSON allows."""
    st = _make_state()
    st.card_db = DB
    st.step = Step.ACTION
    st.combat = None
    st.active_player = int(st_json.get("active_player") or 1)

    for p in st_json["players"]:
        pid = int(p["player_id"])
        player = st.players[pid]
        hero = _mk(p["hero"], pid)
        if hero is not None:
            player.hero = hero
        player.life = int(p.get("health") or 0)
        player.resources = int(p.get("resources") or 0)
        player.intellect = int(p.get("intellect") or 4)

        for zone_name in ZONES:
            zone = getattr(player, zone_name, None)
            if zone is None:
                continue
            # No clearing: _make_state hands back empty zones, and `soul` is a
            # SubZoneView whose .cards is read-only.
            for slug in (p.get(zone_name) or []):
                c = _mk(slug, pid)
                if c is not None:
                    zone.add(c)

        # Equipment goes to its printed slot; the JSON lists them flat.
        for slug in (p.get("equipment") or []):
            c = _mk(slug, pid)
            if c is None:
                continue
            subs = {str(s).lower() for s in (c.subtypes or [])}
            for slot in ("head", "chest", "arms", "legs"):
                if slot in subs:
                    getattr(player, slot).add(c)
                    break
            else:
                if c.is_weapon:
                    (player.weapon1 if not player.weapon1.cards
                     else player.weapon2).add(c)

        player.deck.cards = []
        for _ in range(int(p.get("deck_count") or 0)):
            c = _mk(FILLER, pid)
            if c is not None:
                player.deck.cards.append(c)

    st.players[st.active_player].action_points = int(st_json.get("action_points") or 0)
    return st


def observe_ours(st):
    out = {}
    for pid in (1, 2):
        p = st.players[pid]
        out["p%d.life" % pid] = p.life
        out["p%d.resources" % pid] = p.resources
        for zone_name in ZONES + ("deck",):
            zone = getattr(p, zone_name, None)
            if zone is not None:
                out["p%d.%s" % (pid, zone_name)] = len(zone.cards)
    return out


def observe_talishar(st_json):
    out = {}
    for p in st_json["players"]:
        pid = int(p["player_id"])
        out["p%d.life" % pid] = int(p.get("health") or 0)
        out["p%d.resources" % pid] = int(p.get("resources") or 0)
        for zone_name in ZONES:
            out["p%d.%s" % (pid, zone_name)] = len(p.get(zone_name) or [])
        out["p%d.deck" % pid] = int(p.get("deck_count") or 0)
    return out


def usable(row):
    """(state, action, next_state) when this is an immediately-resolving play we
    can replicate, else None with a reason."""
    try:
        stj = json.loads(row["state_json"])
        nxt = json.loads(row["next_state_json"])
        act = json.loads(row["chosen_action_json"] or "{}")
    except Exception:
        return None, "unparseable"
    if act.get("type") != "PLAY_FROM_HAND":
        return None, "not a play from hand"
    if nxt.get("stack"):
        return None, "did not resolve in this input"
    c = stj.get("combat") or {}
    if int(c.get("active") or 0) or stj.get("combat_chain") or stj.get("stack"):
        return None, "mid combat or non-empty stack"
    slug = act.get("card_id")
    if not slug or get_card(slug) is None:
        return None, "played card not implemented"
    pid = int(act.get("player_id") or stj.get("active_player") or 1)
    me = next((p for p in stj["players"] if int(p["player_id"]) == pid), None)
    if me is None or slug not in (me.get("hand") or []):
        return None, "played card not in the acting hand"
    proto = DB.get(slug)
    if proto is None or (proto.cost or 0) > int(me.get("resources") or 0):
        return None, "would need a pitch"
    return (stj, act, nxt, pid, slug), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=40)
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    import pyarrow.parquet as pq
    files = sorted(glob.glob(CORPUS))
    if not files:
        print("no corpus at %s" % CORPUS)
        return 1
    random.seed(args.seed)
    picked = random.sample(files, min(args.files, len(files)))

    checked = agree = 0
    skipped = Counter()
    field_mismatch = Counter()
    card_mismatch = Counter()
    errored = Counter()

    for f in picked:
        table = pq.read_table(f, columns=["state_json", "next_state_json",
                                          "chosen_action_json"])
        for row in table.to_pylist():
            if checked >= args.limit:
                break
            got, why = usable(row)
            if got is None:
                skipped[why] += 1
                continue
            stj, act, nxt, pid, slug = got

            try:
                st = build_state(stj)
                offer = [a for a in available_actions(st, pid)
                         if getattr(a.card, "slug", None) == slug
                         and a.type == ActionType.PLAY_CARD]
                if not offer:
                    skipped["we do not offer that play"] += 1
                    continue
                before = observe_ours(st)
                apply_action(st, offer[0])
                E.resolve_stack(st)
                ours = observe_ours(st)
            except Exception as exc:
                errored[type(exc).__name__] += 1
                continue

            theirs = observe_talishar(nxt)
            base = observe_talishar(stj)
            checked += 1

            bad = []
            for k in sorted(theirs):
                if k not in ours or k.split(".", 1)[1] in NOT_COMPARED:
                    continue
                # Compare the DELTA, so a field our reconstruction cannot seed
                # exactly still tests what the card did to it.
                if (ours[k] - before.get(k, 0)) != (theirs[k] - base.get(k, 0)):
                    bad.append(k)
            if not bad:
                agree += 1
            else:
                card_mismatch[slug] += 1
                for k in bad:
                    field_mismatch[k] += 1

    print("plays compared: %d" % checked)
    if checked:
        print("identical outcome deltas: %d (%.0f%%)" % (agree, 100 * agree / checked))
    print("\nskipped: %s" % dict(skipped.most_common(8)))
    if errored:
        print("errors while replaying: %s" % dict(errored.most_common(6)))
    print("\nfields that disagreed most:")
    for k, n in field_mismatch.most_common(12):
        print("   %-22s %d" % (k, n))
    print("\ncards that disagreed most:")
    for k, n in card_mismatch.most_common(15):
        print("   %-34s %d" % (k, n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

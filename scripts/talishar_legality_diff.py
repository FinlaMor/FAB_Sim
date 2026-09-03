"""Feasibility probe: can a Talishar state be rebuilt well enough to compare
PLAY legality against ours?

Talishar is an independent implementation of the same rules, so its
`legal_actions_json` is an oracle for "what may be played from hand here" --
the exact question several defects this session lived in (a fabricated cost
blocking a legal play, a missing restriction allowing an illegal one).

Deliberately narrow. Only transitions where:
  * it is the acting player's action phase, no combat, empty stack
  * every card in their hand is implemented by us
so a disagreement is about legality and not about a card we have not written.
"""
import glob
import json
import random
import sys
from collections import Counter

sys.path.insert(0, "C:/Users/Joseph/Desktop/FAB_Sim")

import pyarrow.parquet as pq

from engine.card import Card, CardDB
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.play import available_actions
from engine.state import Step
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _mk(slug, pid):
    proto = DB.get(slug)
    if proto is None:
        return None
    import copy
    c = copy.deepcopy(proto)
    c.owner = c.controller = pid
    return c


def build_state(st_json):
    """Our GameState from a Talishar state. Only what play legality reads."""
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
        player.hand.cards = []
        for slug in p.get("hand") or []:
            c = _mk(slug, pid)
            if c is not None:
                player.hand.add(c)
        player.arsenal.cards = []
        for slug in p.get("arsenal") or []:
            c = _mk(slug, pid)
            if c is not None:
                player.arsenal.add(c)
    st.players[st.active_player].action_points = int(st_json.get("action_points") or 0)
    return st


def main(n_files=25, want=250):
    files = sorted(glob.glob(
        "C:/Users/Joseph/Desktop/FAB_Sim_Headless/datasets/cc/parquet/games/*.parquet"))
    random.seed(7)
    checked = agree = 0
    only_talishar = Counter()
    only_ours = Counter()
    skipped = Counter()

    for f in random.sample(files, n_files):
        t = pq.read_table(f, columns=["state_json", "legal_actions_json"])
        for sj, lj in zip(t.column("state_json").to_pylist(),
                          t.column("legal_actions_json").to_pylist()):
            if checked >= want:
                break
            try:
                stj = json.loads(sj)
                legal = json.loads(lj)
            except Exception:
                skipped["unparseable"] += 1
                continue
            # `combat` is ALWAYS a dict; it is idle when combat["active"] is 0.
            # Truth-testing the dict skipped every state in the corpus.
            _c = stj.get("combat") or {}
            if (stj.get("phase") != "M" or int(_c.get("active") or 0)
                    or stj.get("stack") or stj.get("combat_chain")):
                skipped["not a clean main phase"] += 1
                continue
            pid = int(stj.get("active_player") or 1)
            me = next((p for p in stj["players"] if int(p["player_id"]) == pid), None)
            if me is None:
                continue
            hand = me.get("hand") or []
            if not hand:
                skipped["empty hand"] += 1
                continue
            if any(get_card(s) is None for s in hand):
                skipped["hand has an unimplemented card"] += 1
                continue

            their = {a.get("card_id") for a in legal
                     if a.get("type") == "PLAY_FROM_HAND" and a.get("player_id") == pid}
            st = build_state(stj)
            ours = {getattr(a.card, "slug", None) for a in available_actions(st, pid)
                    if str(getattr(a.type, "value", a.type)) in ("play_card",)}
            ours = {s for s in ours if s in set(hand)}

            checked += 1
            if their == ours:
                agree += 1
            else:
                for s in their - ours:
                    only_talishar[s] += 1
                for s in ours - their:
                    only_ours[s] += 1
        if checked >= want:
            break

    print("comparable states checked: %d" % checked)
    if checked:
        print("exact agreement on the playable-from-hand set: %d (%.0f%%)"
              % (agree, 100 * agree / checked))
    print("\nskipped:", dict(skipped))
    print("\nTalishar says playable, we do not (top 12):")
    for s, n in only_talishar.most_common(12):
        print("   %-34s %d" % (s, n))
    print("\nWe say playable, Talishar does not (top 12):")
    for s, n in only_ours.most_common(12):
        print("   %-34s %d" % (s, n))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Replay real attacks through our engine and compare the computed power.

THIS IS THE BEHAVIOURAL CHECK THAT talishar_combat_diff.py IS NOT. That script
compares Talishar's published keyword flags against our CARD DATA and never
instantiates a GameState — it can say our `keywords` list is wrong, but nothing
about whether the engine computes an attack the same way Talishar does. This
one reconstructs the board, puts the attack on the chain, asks our engine for
the attack's power, and compares it to Talishar's own `total_power`.

WHY THIS WORKS ON SPECTATOR DATA WHEN talishar_outcome_diff.py CANNOT. A
spectator sees hands as "CardBack", which is fatal for replaying a card played
FROM HAND. But once an attack is on the chain, nothing about anyone's hand
determines its power: the attacking card, the attacker's equipment, auras,
items and allies, and the prior chain links are all fully visible, and Talishar
publishes its own computed `total_power` as the oracle. Attacks are the one
class where the hidden-hand problem does not bite.

WHAT IS COMPARED, AND ON WHICH ATTACKS. Only the FIRST state of each attack, so
defenders and reactions have not yet piled on. The comparison is
`combat.attack_power` against `total_power`.

The slice is deliberately narrow, because a reconstruction gap produces a false
positive that looks exactly like an engine bug. Excluded by default:

  * attacks with a non-empty `chain_links` — later links carry bonuses from
    earlier ones that the visible state does not fully explain
  * an attacker holding Talishar `effects` entries (agility, toughness and
    friends) — these are token-shaped modifiers we do not map
  * anything already defended (`total_defense` or `reactions` non-empty)
  * cards we have no DSL implementation for, since an unimplemented card has no
    behaviour to disagree about

`--wide` drops the effects/chain-link exclusions to show how much of the
disagreement they account for. Expect it to be worse; that is the point.

WHERE IT STANDS: 94% of 800 attacks agree exactly.

EVERY BUG THIS TOOL HAS FOUND SO FAR HAS BEEN IN ITSELF, and that is worth
stating plainly, because a replay harness fails in the direction that
manufactures findings — a gap in the reconstruction is indistinguishable from a
defect in the engine, and it always looks like the engine is wrong.

The first run reported 89% with a 53-attack cluster at exactly -4, which read
like a systematic engine bug. It was `_setup_dsl_listeners` never being called:
WHILE_STATIC abilities fire off the RECALC_ATTACK_POWER dispatch, which does
not exist until the listeners are registered, so every conditional pump was
silently absent. I guessed at three other causes first (missing public zones,
positional hero detection, face-up flags) and only found the real one by
instrumenting a single case end to end. Two of those guesses were worth keeping
anyway; none of them was the bug.

THE RESIDUAL IS MOSTLY NOT REPRODUCIBLE. The largest remaining cluster is
felling_of_the_crown_red, whose +4 needs "4 or more Earth cards in your
banished zone". In the disagreeing cases Talishar applies the bonus while the
banish zone the spectator can see holds only 2-3 Earth cards, and our talent
data is not at fault — no card in the corpus has Earth in its typeText and not
in its talents. Talishar is counting cards the feed does not show us. That is a
limit of spectator data, not a defect, and it caps what this method can prove.

Treat a disagreement as a lead, never as a finding: confirm it by reading the
card and the engine before believing it.

    python scripts/talishar_attack_replay.py --limit 3000
    python scripts/talishar_attack_replay.py --limit 3000 --wide
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
from engine.card import CardDB
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState, Step
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

EQUIP_SLOTS = ("head", "chest", "arms", "legs")


def _ids(entries):
    """Talishar zones hold either bare slugs or full card objects."""
    out = []
    for c in entries or []:
        slug = c.get("cardNumber") if isinstance(c, dict) else c
        if isinstance(slug, str) and slug and slug != "CardBack":
            out.append(slug)
    return out


def hero_name(side):
    """The side's hero name, lowercased, or "" — located by card type rather
    than by its position in the equipment list."""
    for slug in _ids(side.get("equipment")):
        card = DB.get(slug)
        if card is None:
            continue
        types = {str(t).lower() for t in (card.types or [])}
        if types & {"hero", "demihero"}:
            return (card.name or "").strip().lower()
    return ""


def _mk(slug, pid):
    proto = DB.get(slug)
    if proto is None:
        return None
    card = copy.deepcopy(proto)
    card.owner = card.controller = pid
    return card


def build_state(side, opp, attacker_id=1):
    """Reconstruct as much of the attacker's board as the feed exposes.

    THE LISTENERS ARE NOT OPTIONAL. A card's WHILE_STATIC abilities fire off
    the RECALC_ATTACK_POWER dispatch, which only exists once
    `_setup_dsl_listeners` has run. Without it every conditional pump is
    silently absent: felling_of_the_crown_red computed 4 instead of 8 and 53
    attacks looked like engine bugs. This is the whole hazard of a replay
    harness — a gap in the reconstruction is indistinguishable from a defect in
    the thing being tested, and it fails in the direction that manufactures
    findings.
    """
    st = _make_state()
    st.card_db = DB
    st.step = Step.COMBAT if hasattr(Step, "COMBAT") else Step.ACTION
    st.active_player = attacker_id
    st.combat = None
    st.player_agents = {1: lambda s, options, context="": options[0],
                        2: lambda s, options, context="": options[0]}

    for pid, data in ((attacker_id, side), (3 - attacker_id, opp)):
        player = st.players[pid]
        try:
            player.life = int(data.get("health") or 0)
        except (TypeError, ValueError):
            pass
        for slug in _ids(data.get("equipment")):
            card = _mk(slug, pid)
            if card is None:
                continue
            subs = {str(s).lower() for s in (card.subtypes or [])}
            types = {str(t).lower() for t in (card.types or [])}
            if "hero" in types or "demihero" in types:
                player.hero = card
                continue
            for slot in EQUIP_SLOTS:
                if slot in subs:
                    getattr(player, slot).add(card)
                    break
            else:
                if card.is_weapon:
                    (player.weapon1 if not player.weapon1.cards
                     else player.weapon2).add(card)
        # Arena zones, then the PUBLIC card zones. Leaving the latter out was
        # the single largest source of false positives on the first run:
        # felling_of_the_crown_red gets +4 for "4 or more Earth cards in your
        # banished zone", and with an empty banish zone our engine was right to
        # say 4 while Talishar said 8. A spectator can see all of these, so
        # there is no reason not to rebuild them.
        for zone_name, source in (("auras", "auras"), ("items", "items"),
                                  ("allies", "allies"), ("graveyard", "discard"),
                                  ("banished", "banish"), ("pitch", "pitch"),
                                  ("arsenal", "arsenal")):
            zone = getattr(player, zone_name, None)
            if zone is None:
                continue
            for slug in _ids(data.get(source)):
                card = _mk(slug, pid)
                if card is not None:
                    zone.add(card)
    E._setup_dsl_listeners(st)
    return st


def our_power(st, slug, attacker_id=1):
    """What our engine says this attack's power is, on this board."""
    card = _mk(slug, attacker_id)
    if card is None:
        return None
    # An attack from a weapon is the equipped object itself, so prefer the copy
    # already on the board — its continuous effects are registered there.
    for zone in ("weapon1", "weapon2"):
        for equipped in getattr(st.players[attacker_id], zone).cards:
            if equipped.slug == slug:
                card = equipped
    power = card.base_power or 0
    st.combat = CombatState(attacker_id=attacker_id, link_id=1,
                            attack_power=power, attack_card=card, keywords=[])
    st.combat.base_attack_power = power
    E._apply_turn_attack_effects(st, card)
    E._register_card_continuous_effects(st, card)
    E._recalculate_attack_power(st)
    return st.combat.attack_power


def attack_states(db_path, limit, wide=False):
    """Yield (slug, talishar_power, attacker_side, other_side) for the first
    state of each attack that meets the comparison criteria."""
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    prev: dict = {}
    skipped = collections.Counter()
    yielded = 0
    for gid, data in con.execute(
            "SELECT game_id, data FROM events WHERE data IS NOT NULL"):
        if yielded >= limit:
            return
        try:
            gs = json.loads(data)["gameState"]
        except Exception:
            continue
        cc = gs.get("combat_chain") or {}
        slug = cc.get("attacking_card")
        if not (isinstance(slug, str) and slug and slug != "CardBack"):
            prev[gid] = None
            continue
        if prev.get(gid) == slug:
            continue
        prev[gid] = slug

        power = cc.get("total_power")
        if not isinstance(power, int):
            skipped["no total_power"] += 1
            continue
        if cc.get("total_defense") or cc.get("reactions"):
            skipped["already defended"] += 1
            continue
        if not wide and cc.get("chain_links"):
            skipped["later chain link"] += 1
            continue
        if DB.get(slug) is None:
            skipped["not in card data"] += 1
            continue
        if get_card(slug) is None:
            skipped["not implemented"] += 1
            continue

        # Which side is attacking? attack_target names the DEFENDING hero, so
        # the attacker is whichever side is NOT being pointed at.
        #
        # The hero is found by TYPE, not by position. Taking equipment[0] as
        # the hero looked right on the samples I checked and silently picked a
        # weapon on others, which flipped the side assignment and rebuilt the
        # wrong player's board — the attacker then got an empty banish zone and
        # every felling_of_the_crown_red read as a 4-point engine bug.
        p, o = gs.get("player") or {}, gs.get("opponent") or {}
        p_name, o_name = hero_name(p), hero_name(o)
        target = str(cc.get("attack_target") or "").strip().lower()
        if target and o_name and target.startswith(o_name[:8]):
            side, other = p, o
        elif target and p_name and target.startswith(p_name[:8]):
            side, other = o, p
        else:
            skipped["attacker side unknown"] += 1
            continue

        if not wide and _ids(side.get("effects")):
            skipped["attacker has effect tokens"] += 1
            continue

        yielded += 1
        yield slug, power, side, other, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--wide", action="store_true",
                    help="Drop the effect-token and chain-link exclusions.")
    args = ap.parse_args()

    checked = agree = 0
    diffs = collections.Counter()
    by_card = collections.defaultdict(collections.Counter)
    errors = collections.Counter()
    skipped = collections.Counter()

    for slug, theirs, side, other, skip in attack_states(
            args.db, args.limit, args.wide):
        skipped = skip
        try:
            st = build_state(side, other)
            ours = our_power(st, slug)
        except Exception as exc:
            errors[type(exc).__name__] += 1
            continue
        if ours is None:
            continue
        checked += 1
        if ours == theirs:
            agree += 1
        else:
            diffs[ours - theirs] += 1
            by_card[slug][ours - theirs] += 1

    print("attacks compared: %d" % checked)
    if checked:
        print("power identical  : %d (%.0f%%)" % (agree, 100 * agree / checked))
    print("\nskipped: %s" % dict(skipped.most_common(8)))
    if errors:
        print("errors: %s" % dict(errors.most_common(6)))
    if diffs:
        print("\ndelta (ours - theirs):")
        for d, n in sorted(diffs.items(), key=lambda x: -x[1])[:10]:
            print("   %+d  %d" % (d, n))
        print("\ncards disagreeing most:")
        for slug, c in sorted(by_card.items(),
                              key=lambda x: -sum(x[1].values()))[:15]:
            print("   %-32s %s" % (slug, dict(c)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

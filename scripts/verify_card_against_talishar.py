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
             This is the part that decides the verdict.
  on-hit     ADVISORY. Talishar usually resolves combat damage and the on-hit
             into separate states while the attack is still on the chain:

                 o.hp=21   before damage
                 o.hp=15   combat damage (6)
                 o.hp=14   the on-hit, "they lose 1 life"

             so the on-hit's effect on life, deck, banish, discard, arsenal
             count, soul, items, auras and allies can be read off and compared
             with dispatching ON_HIT in our engine.

             It is advisory rather than a gate because ATTRIBUTION IS THE WEAK
             PART. The window from damage to the chain clearing also holds
             defenders going to the graveyard and any other trigger, and the
             agreement rate is strongly card-dependent for reasons that are
             mostly OUR blind spots, not defects: 100% on pain_in_the_backside,
             ~60% on kiss_of_death, 32% on mark_of_the_black_widow, whose text
             is "they banish a card from THEIR HAND" — a hand we cannot see and
             therefore replay as empty, so our side correctly does nothing and
             the comparison is meaningless. Read the disagreements; do not
             treat the percentage as a score.
  effects    Talishar publishes, per side, the cards whose effects are
             currently live. That list IS the set of reasons an attack's power
             differs from the printed number, so attacks carrying one are
             excluded from the gate and the sources are REPORTED instead of
             silently dropped, tagged by whether we could model them.

             `--with-effects` replays them rather than excluding, by
             dispatching each listed ACTION card's play ability to re-register
             what it left pending (Up Sticks and Run's MODIFY_NEXT_ATTACK +4).
             On a single traced case that reproduces Talishar exactly, 1 -> 5.
             At scale it barely moves: 43% -> 45% over 400 attacks, because
             only 14% of listed effects are replayable today —

                 58%  a card we have not implemented
                 27%  a token, hero or equipment, where "replay the play
                      ability" is meaningless
                 14%  an implemented Action card
                  0%  not in card_data

             so the ceiling is our own coverage, and it rises on its own as
             cards get implemented. The ARRAYS ARE INVERTED relative to who
             controls the effect: Talishar's chat has Player 1 playing Up
             Sticks and Run and attacking with Hunter's Klaive, while the
             effect sits in the defender's array.
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
    DB, DB_PATH, FLAGS_TO_KEYWORDS, _ids, build_state, canonical, get_card,
    hero_name, our_power,
)

INDEX_PATH = ROOT / "card_data" / "talishar_card_index.json"

#: How large a rowid gap can be and still be the same attack. Bridges the empty
#: heartbeat states, which carry no attacking card and so are never indexed.
RUN_GAP = 4

#: Text that marks a card as depending on state the spectator feed does not
#: carry. Matched against the card's own functionalText, so the verdict can
#: separate "we disagree" from "this could never have been checked".
UNRECONSTRUCTABLE = (
    ("booed", "crowd state appears only in the chat log"),
    ("cheered", "crowd state appears only in the chat log"),
    ("from arsenal", "arsenal is face-down to spectators (94% CardBack)"),
    ("you may", "depends on a player choice that is not in the state"),
    ("from their hand", "hands are CardBack; we replay with an empty hand"),
    ("from your hand", "hands are CardBack; we replay with an empty hand"),
    ("reveal their hand", "hand contents are never visible to a spectator"),
    ("discard a card", "hands are CardBack; we replay with an empty hand"),
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


def sides_of(gs, cc):
    """(attacker, defender) dicts, or (None, None) if it cannot be told apart."""
    p, o = gs.get("player") or {}, gs.get("opponent") or {}
    target = str(cc.get("attack_target") or "").strip().lower()
    norm = lambda s: "".join(ch for ch in s if ch.isalnum())
    p_hit = norm(target) == norm(hero_name(p))
    o_hit = norm(target) == norm(hero_name(o))
    if o_hit and not p_hit:
        return p, o
    if p_hit and not o_hit:
        return o, p
    return None, None


def talishar_on_hit_delta(run):
    """What the on-hit did, per Talishar, or None if this attack did not hit.

    HIT IS DECIDED ON THE LAST ON-CHAIN STATE, not the first. Defense
    accumulates as blockers are declared: art_of_desire_body_red opens a chain
    at def=0 and closes it at def=4 against power 3, so reading the opening
    state scores a hit that never happened and blames the card for an on-hit
    that was never supposed to fire.

    The delta is measured from the state where combat damage lands to the end
    of the run, so the damage itself is excluded and what remains is the
    on-hit.
    """
    last = run[-1].get("combat_chain") or {}
    power, defense = last.get("total_power"), last.get("total_defense") or 0
    if not isinstance(power, int) or defense >= power:
        return None
    attacker, defender = sides_of(run[-1], last)
    if defender is None:
        return None

    expected_damage = power - defense
    life = [_int((sides_of(gs, gs.get("combat_chain") or {})[1] or {}).get("health"))
            for gs in run]
    damage_at = None
    for i in range(1, len(run)):
        if life[i] is None or life[i - 1] is None:
            continue
        if life[i - 1] - life[i] >= expected_damage:
            damage_at = i
            break
    if damage_at is None:
        return None                      # damage never observed; nothing to attribute

    def snapshot(index):
        a, d = sides_of(run[index], run[index].get("combat_chain") or {})
        if a is None:
            return None
        return {"attacker": observable(a), "defender": observable(d)}

    # Measure from BEFORE the damage and subtract the damage back out, rather
    # than from after it. Talishar usually resolves combat damage and the
    # on-hit into separate states, but not always — when they land together,
    # measuring "everything after the damage state" reads the on-hit as zero
    # and blames us for applying it.
    before, after = snapshot(damage_at), snapshot(len(run) - 1)
    if before is None or after is None:
        return None
    delta = {}
    for who in ("attacker", "defender"):
        for field, value in after[who].items():
            prior = before[who].get(field)
            if prior is None or value is None or prior == value:
                continue
            delta["%s.%s" % (who, field)] = value - prior
    return delta


def our_on_hit_delta(slug, run):
    """The same measurement, from our engine: reconstruct, fire ON_HIT, diff."""
    from engine.card_effects.dsl import dispatch

    last = run[-1]
    cc = last.get("combat_chain") or {}
    attacker, defender = sides_of(last, cc)
    if attacker is None:
        return None
    st = build_state(attacker, defender)

    card = None
    for zone in ("weapon1", "weapon2"):
        for equipped in getattr(st.players[1], zone).cards:
            if equipped.slug == slug:
                card = equipped
    if card is None:
        proto = DB.get(slug)
        if proto is None:
            return None
        import copy
        card = copy.deepcopy(proto)
        card.owner = card.controller = 1

    from engine.state import CombatState
    power = last.get("combat_chain", {}).get("total_power") or card.base_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = card.base_power or 0
    # combat.attack_target is set ONLY when the attack was declared against a
    # permanent or ally; a hero attack leaves it None (see
    # ATTACK_TARGET_IS_HERO in dsl/condition_types.py). Setting it to the
    # defending hero — the intuitive reading — makes every "when this hits a
    # hero" ability false, which read as the engine ignoring its own on-hits.
    # We only get here for hero attacks, so it stays None.
    st.combat.from_weapon = bool(
        {str(t).lower() for t in (card.types or [])} & {"weapon"})

    def snap():
        return {"attacker": {
                    "life": st.players[1].life,
                    "deck": len(st.players[1].deck.cards),
                    "soul": len(st.players[1].soul.cards),
                    "discard": len(st.players[1].graveyard.cards),
                    "banish": len(st.players[1].banished.cards),
                    "arsenal": len(st.players[1].arsenal.cards),
                    "items": len(st.players[1].items.cards),
                    "auras": len(st.players[1].auras.cards),
                    "allies": len(st.players[1].allies.cards)},
                "defender": {
                    "life": st.players[2].life,
                    "deck": len(st.players[2].deck.cards),
                    "soul": len(st.players[2].soul.cards),
                    "discard": len(st.players[2].graveyard.cards),
                    "banish": len(st.players[2].banished.cards),
                    "arsenal": len(st.players[2].arsenal.cards),
                    "items": len(st.players[2].items.cards),
                    "auras": len(st.players[2].auras.cards),
                    "allies": len(st.players[2].allies.cards)}}

    before = snap()
    try:
        dispatch(st, "ON_HIT", slug, card=card, event=None)
    except Exception:
        return None
    after = snap()
    delta = {}
    for who in ("attacker", "defender"):
        for field, value in after[who].items():
            if before[who][field] != value:
                delta["%s.%s" % (who, field)] = value - before[who][field]
    return delta


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


def _int(value):
    """Talishar sends health as a STRING. Reading it as an int and silently
    getting None is how the first on-hit measurement came back empty."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


#: The visible fields an on-hit can move. Anything an on-hit does that is not
#: one of these — "reveal their hand", "look at the top card" — is invisible to
#: a spectator and cannot be checked.
def observable(side):
    return {
        "life": _int(side.get("health")),
        "deck": _int(side.get("deck_count")),
        "soul": _int(side.get("soul_count")),
        "discard": len(_ids(side.get("discard"))),
        "banish": len(_ids(side.get("banish"))),
        "arsenal": len(side.get("arsenal") or []),
        "items": len(_ids(side.get("items"))),
        "auras": len(_ids(side.get("auras"))),
        "allies": len(_ids(side.get("allies"))),
    }


def attack_runs(db_path, rowids):
    """Yield one entry per distinct attack: every state it was on the chain for.

    The whole run, not just the first state, because that is where the on-hit
    lives. Talishar resolves combat damage and the on-hit into SEPARATE states
    while the attack is still on the chain:

        o.hp=21   before damage
        o.hp=15   combat damage
        o.hp=14   the on-hit ("they lose 1 life")

    Looking only at the first state, or differencing past the end of the run,
    sees none of it.
    """
    if not rowids:
        return
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    runs = collections.defaultdict(list)
    chunk = 900
    ordered = sorted(rowids)
    for start in range(0, len(ordered), chunk):
        batch = ordered[start:start + chunk]
        placeholders = ",".join("?" * len(batch))
        for gid, rowid, data in con.execute(
                "SELECT game_id, rowid, data FROM events WHERE rowid IN (%s) "
                "ORDER BY rowid" % placeholders, batch):
            try:
                gs = json.loads(data)["gameState"]
            except Exception:
                continue
            runs[gid].append((rowid, gs))

    for gid, states in runs.items():
        run = []
        last_rowid = None
        for rowid, gs in states:
            # A gap in rowids means states where this card was NOT the attacker
            # — but SMALL gaps are not run boundaries. Talishar sends empty
            # `data: {}` heartbeats to an authenticated spectator, and those
            # decode to an all-null state with no attacking card, so they are
            # never indexed. Splitting on a one-state gap cut runs off right
            # before the damage resolved, which is precisely where the on-hit
            # lives: a traced case ended at phase D with life untouched.
            if last_rowid is not None and rowid - last_rowid > RUN_GAP and run:
                yield gid, run
                run = []
            run.append(gs)
            last_rowid = rowid
        if run:
            yield gid, run


def attacks_for(db_path, rowids):
    """Yield (game_id, first_state, combat_chain) per distinct attack."""
    for gid, run in attack_runs(db_path, rowids):
        yield gid, run[0], (run[0].get("combat_chain") or {})


def verify(slug, db_path, explain=False, refresh=False, with_effects=False):
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
    hits = hits_agree = 0
    hit_mismatches = []
    excluded_by_effects = 0
    effect_sources = collections.Counter()

    for gid, run in attack_runs(db_path, rowids):
        theirs_hit = talishar_on_hit_delta(run)
        if theirs_hit is None:
            continue
        hits += 1
        ours_hit = our_on_hit_delta(slug, run)
        if ours_hit is None:
            continue
        # Only fields ONE of us moved are interesting; agreeing on zero is the
        # common case and says the on-hit did nothing visible either way.
        keys = set(theirs_hit) | set(ours_hit)
        differing = {k: (ours_hit.get(k, 0), theirs_hit.get(k, 0)) for k in keys
                     if ours_hit.get(k, 0) != theirs_hit.get(k, 0)}
        if differing:
            hit_mismatches.append((gid, differing))
        else:
            hits_agree += 1

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
        active = _ids(side.get("effects")) + _ids(other.get("effects"))
        if active and not with_effects:
            # Excluded from the gate, but NOT silently: Talishar's active-effects
            # list is its own account of why a power differs, so the names are
            # collected and reported. --with-effects replays them instead.
            excluded_by_effects += 1
            for slug_ in active:
                effect_sources[canonical(slug_)] += 1
            continue
        try:
            st = build_state(side, other, with_effects=with_effects)
            ours = our_power(st, slug)
        except Exception:
            continue
        checked += 1
        if ours == theirs:
            agree += 1
        else:
            active = _ids(side.get("effects")) + _ids(other.get("effects"))
            mismatches.append((gid, gs.get("turn_no"), ours, theirs, side, other,
                               active))

    print("  distinct attacks        : %d" % attacks)
    if checked:
        print("  power replayed          : %d/%d agree (%.0f%%)"
              % (agree, checked, 100 * agree / checked))
    else:
        print("  power replayed          : 0 comparable attacks")

    if hits:
        print("  on-hit replayed         : %d/%d agree (%.0f%%) over %d hit(s)  [ADVISORY]"
              % (hits_agree, hits, 100 * hits_agree / hits, hits))
    else:
        print("  on-hit replayed         : never observed hitting a hero")

    if excluded_by_effects:
        print("  excluded (active effects): %d attack(s)" % excluded_by_effects)
        top = []
        for slug_, count in effect_sources.most_common(6):
            proto = DB.get(slug_)
            if proto is None:
                tag = "?"
            elif get_card(slug_) is None:
                tag = "unimplemented"
            elif "Action" not in (proto.types or []):
                tag = "not-an-action"
            else:
                tag = "implemented"
            top.append("%s[%s]" % (slug_, tag))
        print("     what was modifying them: %s" % ", ".join(top))

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

    if hit_mismatches:
        print("\n  ON-HIT DISAGREEMENTS (%d)   ours vs theirs:" % len(hit_mismatches))
        for gid, differing in hit_mismatches[:10]:
            parts = ", ".join("%s ours%+d theirs%+d" % (k, a, b)
                              for k, (a, b) in sorted(differing.items()))
            print("     game %-9s %s" % (gid, parts))

    if mismatches:
        print("\n  POWER DISAGREEMENTS (%d):" % len(mismatches))
        for gid, turn, ours, theirs, side, other, active in mismatches[:10]:
            print("     game %-9s turn %-4s ours=%-4s theirs=%-4s" % (gid, turn, ours, theirs))
            # Talishar's own list of what is currently modifying things. This is
            # the shortlist of reasons the power differs, and reading it beats
            # guessing from the board -- it is how the dagger clusters were
            # finally explained (up_sticks_and_run_red, "your next dagger attack
            # gets +4"). Marked so you can see which we could even model.
            if active:
                labelled = []
                for slug_ in dict.fromkeys(active):
                    proto = DB.get(canonical(slug_))
                    if proto is None:
                        tag = "?"
                    elif get_card(canonical(slug_)) is None:
                        tag = "unimplemented"
                    elif "Action" not in (proto.types or []):
                        tag = "not-an-action"
                    else:
                        tag = "implemented"
                    labelled.append("%s[%s]" % (slug_, tag))
                print("        active effects: %s" % ", ".join(labelled))
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
    ap.add_argument("--with-effects", action="store_true",
                    help="Replay Talishar's active-effects list instead of "
                         "excluding those attacks. Only ~14%% of listed effects "
                         "are replayable today, so expect worse agreement.")
    ap.add_argument("--refresh-index", action="store_true",
                    help="Index games collected since the last run.")
    args = ap.parse_args()
    return verify(args.card, args.db, args.explain, args.refresh_index,
                  args.with_effects)


if __name__ == "__main__":
    raise SystemExit(main())

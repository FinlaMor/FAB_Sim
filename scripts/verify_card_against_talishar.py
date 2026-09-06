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

TWO CORPORA, and they are complementary. The spectator DB gives VOLUME —
thousands of attacks per popular card — but shows hands as CardBack. The
headless parquet corpus (`--parquet`) drives the same Talishar engine and
records the FULL state: hands, current_turn_effects, next_turn_effects, marked.
It is smaller, but it covers precisely what the spectator feed cannot judge.
mark_of_the_black_widow_red reads 32% on the spectator on-hit check — its text
banishes "a card from their hand" and we replay with an empty one — and 10/10
against the open-hand corpus.

I spent a long time asserting those classes were unverifiable. They were
unverifiable IN ONE CORPUS, which is not the same thing, and the second corpus
was sitting unused the whole time because I had filed it under "that is for
card plays".

WHAT A DISAGREEMENT MEANS. Read it as a lead, never a verdict. The replay
harness fails in the direction that manufactures findings — a gap in the
reconstruction is indistinguishable from a defect in the card. Classes the
SPECTATOR check cannot see (all reported under KNOWN LIMITS, and all covered by
--parquet):

  * "you've been booed this turn" and the rest of the crowd state, which exists
    only as English in the chat log
  * whether an attack action was played FROM ARSENAL, since 94% of the arsenal
    a spectator sees is CardBack
  * anything reading a HAND
  * anything gated on a player CHOICE ("you MAY banish ... if you do, +1"). The
    choice is in neither corpus, so these are no longer SCORED: when declining
    disagrees but accepting would have matched, the attack is reported as "not
    judgeable" instead. Both directions really occur — 171 corpus attacks paid
    Cadaverous Tilling's Decompose cost and 102 did not — so answering the
    prompt either way manufactures about a hundred findings. Build the board
    with scripts/talishar_scenario.py to test the taken branch on purpose.

A MEASURED NON-FIX, recorded so it is not tried again: `layer` names what is
currently resolving (a step, or the slug of a card), and attributing on-hit
deltas by it looked like the obvious cure for the window contaminating one
card's on-hit with another's. It changes nothing. 100 of 201 hit windows do
contain a foreign card's layer, but they resolve BEFORE damage — only 4 fall in
the post-damage window that is actually attributed. The guard is kept because
it is correct, not because it helped.
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
    DB, DB_PATH, FLAGS_TO_KEYWORDS, _announce_attack as announce_attack, _ids,
    _accepting_agent as accepting_agent, _replay_agent as replay_agent,
    build_state, canonical, explains_as_choice, get_card, hero_name,
    our_power,
)

INDEX_PATH = ROOT / "card_data" / "talishar_card_index.json"

#: How large a rowid gap can be and still be the same attack. Bridges the empty
#: heartbeat states, which carry no attacking card and so are never indexed.
RUN_GAP = 4

#: `layer` holds either one of these STEP names or the slug of the card
#: currently resolving. A step means "the game itself is doing something", so
#: the delta belongs to the attack; a slug that is not our card means someone
#: else's effect and its delta is not ours to claim.
STEP_LAYERS = {
    "TRIGGER", "PRETRIGGER", "FINALIZECHAINLINK", "RESOLUTIONSTEP",
    "ATTACKSTEP", "DEFENDSTEP", "ENDTURN", "STARTTURN", "DAMAGESTEP",
    "LINKRESOLUTION", "CHAINCLOSE",
}


def slug_of(run):
    """The card this run is an attack with."""
    cc = run[0].get("combat_chain") or {}
    return canonical(cc.get("attacking_card") or "")

#: Text that marks a card as depending on state the spectator feed does not
#: carry. Matched against the card's own functionalText, so the verdict can
#: separate "we disagree" from "this could never have been checked".
UNRECONSTRUCTABLE = (
    ("booed", "crowd state appears only in the chat log"),
    ("cheered", "crowd state appears only in the chat log"),
    ("from arsenal", "arsenal is face-down to spectators (94% CardBack)"),
    # Attacks the choice explains are reported as "not judgeable" rather than
    # scored. The residue is the cases where accepting could not reproduce
    # Talishar's number EITHER, because the option's own gate fails on our
    # rebuilt board -- Decompose needs 2 Earth cards and an action in the
    # graveyard, and a spectator graveyard is not fully reconstructible. Those
    # stay in the disagreement list on purpose: explaining them away would need
    # the harness to ignore the gate, and a harness that can bypass conditions
    # can explain almost anything.
    ("you may", "depends on a player choice that is not in the state; the "
                "attacks it explains are reported as not judgeable"),
    ("from their hand", "hands are CardBack; we replay with an empty hand"),
    ("from your hand", "hands are CardBack; we replay with an empty hand"),
    ("reveal their hand", "hand contents are never visible to a spectator"),
    ("discard a card", "hands are CardBack; we replay with an empty hand"),
    # chain_links carries ONLY {"result", "isDraconic"} across all 53,050
    # entries in the corpus -- it never names the previous card. So "if X was
    # the last attack this combat chain" cannot be evaluated, and every combo
    # card reads one pump low. (isDraconic IS there, so "Draconic chain links
    # you control" is reconstructible; the named-card form is not.)
    ("was the last attack",
     "spectator chain_links never names the previous card - use --parquet or "
     "generated states, whose `links` does"),
    ("**combo**",
     "spectator chain_links never names the previous card - use --parquet or "
     "generated states, whose `links` does"),
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

    # ATTRIBUTED BY `layer`, not by window. Talishar publishes what is
    # currently resolving: a step name (TRIGGER, FINALIZECHAINLINK,
    # RESOLUTIONSTEP, ATTACKSTEP...) or the SLUG of the card resolving. A naive
    # "everything between damage and the chain clearing" window silently
    # credits us with other cards' work -- a traced Kiss of Death attack has
    # `layer=tarantula_toxin_red` resolving mid-combat, and its effects were
    # being scored as Kiss of Death's on-hit.
    #
    # So each state's delta is attributed to whatever `layer` names at that
    # state, and states naming a DIFFERENT card are skipped.
    delta = collections.Counter()
    for i in range(damage_at + 1, len(run)):
        here, prior = snapshot(i), snapshot(i - 1)
        if here is None or prior is None:
            continue
        layer = run[i].get("layer")
        if isinstance(layer, str) and layer and layer not in STEP_LAYERS:
            if canonical(layer) != slug_of(run):
                continue                 # another card's effect, not ours
        for who in ("attacker", "defender"):
            for field, value in here[who].items():
                was = prior[who].get(field)
                if was is None or value is None or was == value:
                    continue
                delta["%s.%s" % (who, field)] += value - was
    return {k: v for k, v in delta.items() if v}


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


GENERATED_DIR = ROOT / "card_data" / "generated_states"


def compare_rows(rows, slug, limit=200):
    """Run one card's transitions through the outcome comparison.

    Shared by the parquet corpus and by states we generated ourselves — both
    carry the identical shape, so this is written once.
    """
    from scripts.talishar_outcome_diff import (
        NOT_COMPARED, build_state as pq_build, observe_ours, observe_talishar,
        usable,
    )
    import engine.engine as E
    from engine.actions import ActionType
    from engine.play import apply_action, available_actions

    checked = agree = 0
    diffs = collections.Counter()
    for row in rows:
        if checked >= limit:
            break
        if slug not in (row.get("chosen_action_json") or ""):
            continue
        got, _why = usable(row)
        if got is None:
            continue
        stj, act, nxt, pid, played = got
        if played != slug:
            continue
        try:
            st = pq_build(stj)
            offers = [a for a in available_actions(st, pid)
                      if getattr(a.card, "slug", None) == slug
                      and a.type == ActionType.PLAY_CARD]
            if not offers:
                continue
            before = observe_ours(st)
            apply_action(st, offers[0])
            E.resolve_stack(st)
            ours = observe_ours(st)
        except Exception:
            continue
        theirs, base = observe_talishar(nxt), observe_talishar(stj)
        checked += 1
        bad = [k for k in sorted(theirs)
               if k in ours and k.split(".", 1)[1] not in NOT_COMPARED
               and (ours[k] - before.get(k, 0)) != (theirs[k] - base.get(k, 0))]
        if bad:
            for k in bad:
                diffs[k] += 1
        else:
            agree += 1
    return checked, agree, diffs


def rebuild_chain_links(st, st_json, attacker):
    """Rebuild the resolved combat chain from the local engine's `links`.

    This is what makes COMBO cards verifiable. The spectator feed's
    chain_links holds only {"result", "isDraconic"} and never names the
    previous card, so "if Surging Strike was the last attack this combat chain"
    can never be evaluated there — whelming_gustwave_red disagrees on 215 of
    269 spectator attacks for exactly that reason, every one of them a false
    positive.

    The local engine records the real thing. Each `links` entry is a flat run
    of 10-field card records (Talishar's ChainLinksPieces()=10), the first of
    which is that link's attacking card:

        [["persuasive_prognosis_blue", "1", "1", "HAND", ...], ...]

    Only attack_slug is filled in, because that is what LAST_CHAIN_ATTACK's
    `name` form reads. The hit/talent/class forms would need fields this array
    does not obviously carry, and inventing values for them would make the
    condition answer confidently from made-up data.
    """
    from engine.state import ChainLink

    links = st_json.get("links") or []
    rebuilt = []
    for i, entry in enumerate(links):
        if not isinstance(entry, (list, tuple)) or not entry:
            continue
        card_slug = canonical(str(entry[0] or ""))
        if not card_slug:
            continue
        rebuilt.append(ChainLink(
            chainlink_id=i + 1, attacker_id=attacker, attack_slug=card_slug,
            attack_power=0, net_damage=0, keywords=[], from_weapon=False))
    if rebuilt:
        st.chain_links = rebuilt
    return len(rebuilt)


def generated_attack_check(slug):
    """Compare attack power on states we made Talishar produce.

    This is the path that works for ATTACK cards. The play/outcome comparison
    cannot judge them — talishar_outcome_diff.usable() wants a quiet board and
    same-input resolution, and a chained attack gives neither — but an active
    combat state carries Talishar's own `combat.attack_power`, which is the
    same oracle the spectator replay uses, on a state that ALSO has hands.
    """
    path = GENERATED_DIR / ("%s.attacks.jsonl" % slug)
    if not path.exists():
        return None
    from scripts.talishar_outcome_diff import build_state as pq_build
    import engine.engine as E
    from engine.state import CombatState

    checked = agree = 0
    deltas = collections.Counter()
    buffs = collections.Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            st_json = json.loads(line)
        except Exception:
            continue
        combat = st_json.get("combat") or {}
        chain = st_json.get("combat_chain") or []
        # `_fab_oracle_power` is set only on a generated row that PAID an
        # optional cost. The board on that row is the one from BEFORE the
        # payment -- paying spends the cost, and a state whose graveyard has
        # already been banished away cannot reproduce the pump it bought -- so
        # the board and the oracle number deliberately come from either side of
        # the choice. Absent on every other row, where the state's own number is
        # the answer.
        theirs = st_json.get("_fab_oracle_power")
        if theirs is None:
            theirs = combat.get("attack_power")
        if not chain or chain[0].get("card_id") != slug:
            continue
        if not isinstance(theirs, int):
            continue
        attacker = int(combat.get("attacker") or chain[0].get("player") or 1)
        try:
            st = pq_build(st_json)
            # pq_build uses conftest's _make_state, whose default agent answers
            # every prompt with options[0] -- and ask_yes_no offers YES first.
            # That auto-pays every optional on-attack cost, which is invention,
            # not replay. Same agent as the spectator replay, same reasoning.
            #
            # No explains_as_choice counterfactual here, unlike the spectator
            # check: a generated scenario RECORDS which branch it took, because
            # Talishar surfaces the cost prompt as real legal actions and the
            # generator chose one. So the choice is known rather than guessed --
            # replay it with the agent that matches. Comparing a paid-for state
            # against an engine that refused to pay would be a guaranteed
            # disagreement saying nothing about the card.
            took = bool((st_json.get("_fab_scenario") or {}).get("take_optional"))
            agent = accepting_agent if took else replay_agent
            st.player_agents = {1: agent, 2: agent}
            E._setup_dsl_listeners(st)
            rebuild_chain_links(st, st_json, attacker)
            card = DB.get(slug)
            if card is None:
                continue
            import copy as _copy
            card = _copy.deepcopy(card)
            card.owner = card.controller = attacker
            power = card.base_power or 0
            st.combat = CombatState(attacker_id=attacker, link_id=1,
                                    attack_power=power, attack_card=card,
                                    keywords=[])
            st.combat.base_attack_power = power
            E._apply_turn_attack_effects(st, card)
            E._register_card_continuous_effects(st, card)
            # Announce the attack, so pumps written as ON_ATTACK triggers fire.
            # Only continuous statics ran before this, which made every
            # "Combo — ... gains +N{p}" card read low against Talishar on the
            # very states built to exercise it.
            announce_attack(st, card)
            E._recalculate_attack_power(st)
            ours = st.combat.attack_power
        except Exception:
            continue
        checked += 1
        if ours == theirs:
            agree += 1
        else:
            deltas[ours - theirs] += 1
            # `static_buffs` on the chain entry NAMES the cards buffing this
            # attack, by set identifier. No inference needed, and it is the
            # single most direct answer to "why is the power different" —
            # kiss_of_death_red's only disagreement here resolved to OUT021,
            # spike_with_bloodrot_red, "target attack action card with stealth
            # gains +3{p}". Reported rather than replayed: naming the source is
            # what makes the disagreement readable.
            raw = str(chain[0].get("static_buffs") or "").strip()
            for ident in [x for x in raw.replace(";", ",").split(",") if x and x != "-"]:
                buffs[ident.strip()] += 1
    return checked, agree, deltas, buffs


def generated_check(slug):
    """States we made Talishar produce for this card, if any.

    scripts/generate_talishar_states.py drives the real engine locally and
    records the transitions, so a card nobody happened to play in a public game
    can still be verified. This is the answer to every "NO EVIDENCE" verdict.
    """
    path = GENERATED_DIR / ("%s.jsonl" % slug)
    if not path.exists():
        return None
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    if not rows:
        return None
    return compare_rows(rows, slug)


def parquet_check(slug, limit=40, max_files=260):
    """Verify the card against the OPEN-HAND corpus.

    The spectator feed shows hands as CardBack, and I kept calling everything
    that depends on a hand unverifiable. It is not — it is unverifiable *in
    that corpus*. FAB_Sim_Headless drives the same Talishar engine and records
    the full state, hands included, plus current_turn_effects /
    next_turn_effects (67% of states carry them). That covers exactly the
    classes the spectator check has to disclaim: hand-reading on-hits,
    turn-scoped pumps, marked, played-from-arsenal.

    This is talishar_outcome_diff.py's comparison narrowed to one card: rebuild
    the before-state, play the card, resolve, and compare the resulting zone
    and life deltas with Talishar's own next state.
    """
    import glob
    import random

    try:
        import pyarrow.parquet as pq
    except ImportError:
        return None, "pyarrow not installed"

    from scripts.talishar_outcome_diff import (
        NOT_COMPARED, build_state as pq_build, observe_ours, observe_talishar,
        usable,
    )
    import engine.engine as E
    from engine.actions import ActionType
    from engine.play import apply_action, available_actions

    files = sorted(glob.glob(
        "C:/Users/Joseph/Desktop/FAB_Sim_Headless/datasets/*/parquet/games/*.parquet"))
    if not files:
        return None, "no parquet corpus"
    random.Random(11).shuffle(files)

    checked = agree = 0
    diffs = collections.Counter()
    for path in files[:max_files]:
        if checked >= limit:
            break
        try:
            table = pq.read_table(path, columns=["state_json", "next_state_json",
                                                 "chosen_action_json"])
        except Exception:
            continue
        for row in table.to_pylist():
            if checked >= limit:
                break
            if slug not in (row.get("chosen_action_json") or ""):
                continue
            got, _why = usable(row)
            if got is None:
                continue
            stj, act, nxt, pid, played = got
            if played != slug:
                continue
            try:
                st = pq_build(stj)
                offers = [a for a in available_actions(st, pid)
                          if getattr(a.card, "slug", None) == slug
                          and a.type == ActionType.PLAY_CARD]
                if not offers:
                    continue
                before = observe_ours(st)
                apply_action(st, offers[0])
                E.resolve_stack(st)
                ours = observe_ours(st)
            except Exception:
                continue
            theirs, base = observe_talishar(nxt), observe_talishar(stj)
            checked += 1
            bad = [k for k in sorted(theirs)
                   if k in ours and k.split(".", 1)[1] not in NOT_COMPARED
                   and (ours[k] - before.get(k, 0)) != (theirs[k] - base.get(k, 0))]
            if bad:
                for k in bad:
                    diffs[k] += 1
            else:
                agree += 1
    return (checked, agree, diffs), None


def _ident_to_slug(ident):
    """Talishar names buff sources by set identifier ("OUT021")."""
    for slug, entry in _slug_index().items():
        if ident in [str(x) for x in (entry.get("setIdentifiers") or [])]:
            return slug
    return None


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


def is_implemented(slug):
    """Does this card have a DSL definition, or only printed stats?"""
    from engine.card_effects.dsl.loader import get_card as _get_def
    try:
        return _get_def(slug) is not None
    except Exception:
        return True  # never let a lookup failure fabricate a disclaimer


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


def verify(slug, db_path, explain=False, refresh=False, with_effects=False,
           parquet=False):
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
    optional_choice = 0
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
        # LATER CHAIN LINKS ARE NO LONGER EXCLUDED. That exclusion was set
        # early on the assumption that earlier links carry bonuses the visible
        # state cannot explain, and then never checked. Measured, later-link
        # attacks agree 94% against 98% for first-link ones — a 4-point
        # precision cost for the second-largest excluded bucket (~1,900
        # attacks), which for a PER-CARD verifier is a bad trade: plenty of
        # cards only ever attack in a later link, and for those the exclusion
        # was the difference between evidence and none.
        if cc.get("total_defense") or cc.get("reactions"):
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
            st = build_state(side, other, with_effects=with_effects,
                             chain_links=cc.get("chain_links"))
            ours = our_power(st, slug)
        except Exception:
            continue
        if ours != theirs and explains_as_choice(side, other, slug, theirs,
                                                 with_effects=with_effects,
                                                 chain_links=cc.get("chain_links")):
            # An optional the player took ("you may banish ... if you do, this
            # gets +2{p}") that the feed does not record. Both directions occur
            # in the corpus, so neither answering yes nor answering no is a
            # defensible default -- either one manufactures findings. Counted
            # apart from the score; the scenario path tests the taken branch
            # deliberately.
            optional_choice += 1
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

    if optional_choice:
        print("  not judgeable           : %d attack(s) turned on an optional "
              "cost the feed does not record" % optional_choice)

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

    gen_atk = generated_attack_check(slug)
    if gen_atk is not None:
        n, ok, deltas, buffs = gen_atk
        if n:
            print("  generated attacks       : %d/%d agree (%.0f%%)"
                  % (ok, n, 100 * ok / n))
            if deltas:
                print("     delta (ours-theirs): %s" % dict(deltas.most_common(5)))
            if buffs:
                # Resolve set identifiers to slugs; the identifier alone is
                # unreadable and the whole point is to name the cause.
                named = []
                for ident, count in buffs.most_common(6):
                    slug_ = _ident_to_slug(ident)
                    named.append("%s=%s x%d" % (ident, slug_ or "?", count))
                print("     static_buffs on the attack: %s" % ", ".join(named))
        else:
            print("  generated attacks       : recorded, but none comparable")

    gen = generated_check(slug)
    if gen is not None:
        n, ok, diffs = gen
        if n:
            print("  generated states        : %d/%d play(s) agree (%.0f%%)"
                  % (ok, n, 100 * ok / n))
            if diffs:
                print("     fields that disagreed: %s"
                      % ", ".join("%s x%d" % (k, c) for k, c in diffs.most_common(6)))
        else:
            print("  generated states        : recorded, but none comparable")

    if parquet:
        result, why = parquet_check(slug)
        if why:
            print("  open-hand corpus        : unavailable (%s)" % why)
        else:
            n, ok, diffs = result
            if n:
                print("  open-hand corpus        : %d/%d play(s) agree (%.0f%%)"
                      % (ok, n, 100 * ok / n))
                if diffs:
                    print("     fields that disagreed: %s"
                          % ", ".join("%s x%d" % (k, c)
                                      for k, c in diffs.most_common(6)))
            else:
                print("  open-hand corpus        : no comparable plays found")

    limits = known_limits(slug)
    if not is_implemented(slug):
        # Say it rather than leave it to be inferred. The card database carries
        # printed stats for every card, so an UNIMPLEMENTED card still replays
        # and still produces a number -- its base power, every time. Against a
        # state built to exercise a Combo that reads as a clean disagreement,
        # and open_the_center_red's 1/2 was very nearly read here as an engine
        # defect when the card simply has no JSON yet.
        limits = ["no JSON definition for this card yet - every effect is "
                  "absent, so a disagreement is expected, not a defect"] + limits
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
    ap.add_argument("--parquet", action="store_true",
                    help="Also check the OPEN-HAND corpus (FAB_Sim_Headless), "
                         "which shows hands and turn-scoped effects and so "
                         "covers what the spectator feed cannot.")
    ap.add_argument("--refresh-index", action="store_true",
                    help="Index games collected since the last run.")
    args = ap.parse_args()
    return verify(args.card, args.db, args.explain, args.refresh_index,
                  args.with_effects, args.parquet)


if __name__ == "__main__":
    raise SystemExit(main())

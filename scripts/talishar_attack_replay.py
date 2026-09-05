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

WHERE IT STANDS: 97% of 1,200 attacks, with later chain links now INCLUDED
(89 -> 94 -> 95 -> 96 -> 97 -> 98 on the old first-link-only slice). Two of
those steps were engine fixes; the rest were fixes to this harness.

INCLUDING LATER CHAIN LINKS costs about a point and roughly triples the
evidence, which is the right trade for a per-card tool. It does surface one
expected class of false positive: COMBO cards. `chain_links` carries only
{"result", "isDraconic"} across all 53,050 entries in the corpus and never
names the previous card, so "if Surging Strike was the last attack this combat
chain" cannot be evaluated and whelming_gustwave_red/yellow read 1 low every
time. That is a limit of the feed, not a defect, and the per-card verifier
reports it under KNOWN LIMITS. `isDraconic` is the one piece that IS usable —
"Draconic chain links you control" is reconstructible where the named-card form
is not.

100% IS NOT REACHABLE FROM THIS FEED, and the remaining ~2% says why rather
than hiding. Three classes, none of them an engine defect:

  * "you've been BOOED this turn" (the mocking_blow family, 24 cards reference
    booed/cheered). The crowd state appears nowhere in the structured
    gameState — grepping every key for "boo" finds nothing. It exists only as
    English in the chat log, "BOOOOO! The crowd jeers at Kayo". Recoverable
    only by parsing prose, which is not a dependency worth taking for a
    measurement tool.
  * PLAYED FROM ARSENAL, which Frailty's -1{p} keys off. 94% of the arsenal
    arrays a spectator sees are CardBack — the zone is face-down — so the
    "was it in arsenal a moment ago" reconstruction below works for the other
    6% and cannot close the class.
  * PLAYER CHOICE. rotten_remains_blue reads "you MAY banish a card with 1{p}
    from each hero's graveyard; if you do, this gets +1{p}, then repeat". The
    decision is not in the state at any point. Our agent accepts, the real
    player declined, and no amount of reconstruction fixes that — the state
    genuinely does not determine the answer.

The first two are limits of the spectator feed; the third is a limit of the
method. Excluding them until the number reads 100% would be measuring the
exclusion list, so they are left in and counted.

THE DAGGER CLUSTERS, worked through case by case, were two reconstruction gaps
and no engine defect:

  * hunters_klaive, graphene_chelicera and kiss_of_death_red all showed a
    consistent -4 in Arakni decks. Talishar's own chat log gave it away:
    "Player 1 played Up Sticks and Run" immediately before the activation. That
    card and cut_from_the_same_cloth_red both read "your next dagger attack
    this turn gets +4{p}" — a turn-scoped marker living in player state, not on
    the board. It IS visible as an effect token, but on the DEFENDER's effects
    array even though the attacker played it, so filtering only the attacker's
    effects let the entire cluster through.
  * the residual -1 on the two daggers with STEALTH was Arakni Marionette's
    "attacks with stealth against a marked hero get +1{p}". The marked
    condition is in the feed, riding on the hero's entry in the equipment
    array, and is now reconstructed into class_counters['marked'].

Checking one case's marked flags and finding them all False nearly closed this
off prematurely — that was a different game. Per-case, not per-cluster.

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

WHAT THE RESIDUAL ACTUALLY IS. I first concluded it was unreproducible — that
Talishar was counting banished cards the feed does not show — and that was
wrong. Reading the full board for the disagreeing cases instead of the summary
gave a different answer, and both causes are real coverage gaps:

  * felling_of_the_crown_red gets +4 for "4 or more Earth cards in your
    banished zone". In the failing cases the banish zone holds three Earth
    cards plus COLORS_OF_ARIA_RED, which reads "while this is face-up in any
    zone, it's Earth, Ice, and Lightning". Our data types it Elemental and the
    card has no DSL file, so its cross-zone type static does not exist and the
    count comes up one short. An UNIMPLEMENTED card silently corrupting an
    IMPLEMENTED card's condition is the most valuable thing this tool has
    surfaced, and nothing in the card-data comparison could have found it.
  * the one +1 is a Frailty token, whose "-1{p} to weapon attacks and
    arsenal-played attack actions" is explicitly unimplemented — the card's own
    JSON carries a TODO saying the static is not yet expressible.

So the method is not capped the way I claimed; it reaches real gaps. What it
cannot do is tell you WHICH kind of gap you are looking at without reading the
board, the card and the engine.

Treat a disagreement as a lead, never as a finding — and read the whole board
before concluding, not the aggregate.

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

#: Talishar combat-chain flag -> our keyword spelling. Shared with
#: verify_card_against_talishar.py, which reports the flags seen on one card.
FLAGS_TO_KEYWORDS = {
    "go_again": "GoAgain",
    "dominate": "Dominate",
    "overpower": "Overpower",
    "piercing": "Piercing",
    "phantasm": "Phantasm",
    "fusion": "Fusion",
    "wager": "Wager",
    "combo": "Combo",
}


#: Talishar decorates slugs in play. "_equip" marks an equipped Evo
#: (evo_beta_base_chest_blue_equip), "_r" the second copy of a dual-wielded
#: one-handed weapon. Neither is a distinct card. "NONE00" is an empty
#: equipment slot, not a card at all.
SLUG_SUFFIXES = ("_equip", "_r")
NOT_A_CARD = {"CardBack", "NONE00", "DYNAMIC", ""}


def _ids(entries):
    """Talishar zones hold either bare slugs or full card objects."""
    out = []
    for c in entries or []:
        slug = c.get("cardNumber") if isinstance(c, dict) else c
        if isinstance(slug, str) and slug not in NOT_A_CARD:
            out.append(slug)
    return out


def canonical(slug):
    """Strip Talishar's in-play decorations down to a card-data slug.

    Missing this dropped every equipped Evo from the reconstruction, because
    `evo_beta_base_chest_blue_equip` is not in card_data and _mk returned None.
    war_machine_red gets +3{p} for "4 or more Evos equipped" and was reading
    zero of them.
    """
    if DB.get(slug) is not None:
        return slug
    for suffix in SLUG_SUFFIXES:
        if slug.endswith(suffix) and DB.get(slug[:-len(suffix)]) is not None:
            return slug[:-len(suffix)]
    return slug


def _norm_name(text):
    """Talishar renders hero names with the card's own punctuation and leet
    spelling; compare on letters and digits only."""
    return "".join(ch for ch in str(text).lower() if ch.isalnum())


def _same_hero(target, name):
    return _norm_name(target) == _norm_name(name)


def is_marked(side):
    """Whether this side's HERO carries Talishar's `marked` flag.

    It rides on the hero's entry in the equipment array rather than anywhere
    obvious, which is why it was missed at first: Arakni Marionette gives
    stealth attacks against a marked hero +1{p}, and without this every such
    attack read 1 low.
    """
    for entry in side.get("equipment") or []:
        if not isinstance(entry, dict):
            continue
        card = DB.get(canonical(entry.get("cardNumber") or ""))
        if card is None:
            continue
        if {str(t).lower() for t in (card.types or [])} & {"hero", "demihero"}:
            return bool(entry.get("marked"))
    return False


def hero_name(side):
    """The side's hero name, lowercased, or "" — located by card type rather
    than by its position in the equipment list."""
    for slug in _ids(side.get("equipment")):
        card = DB.get(canonical(slug))
        if card is None:
            continue
        types = {str(t).lower() for t in (card.types or [])}
        if types & {"hero", "demihero"}:
            return (card.name or "").strip().lower()
    return ""


def _mk(slug, pid):
    proto = DB.get(canonical(slug))
    if proto is None:
        return None
    card = copy.deepcopy(proto)
    card.owner = card.controller = pid
    return card


def apply_active_effects(st, side, opp, attacker_id=1):
    """Re-create Talishar's ACTIVE EFFECTS list in our state.

    Talishar publishes, per side, the cards whose effects are currently live —
    which is exactly the list of reasons an attack's power differs from the
    printed number. Replaying each card's PLAY ability re-registers what it
    left pending: Up Sticks and Run's MODIFY_NEXT_ATTACK +4, and so on.

    THE ARRAYS ARE INVERTED relative to who controls the effect. Talishar's
    chat says "Player 1 played Up Sticks and Run" and "Player 1 activated
    Hunter's Klaive", yet the effect appears in the DEFENDER's array. Attributing
    it to the side it is listed under reproduces the un-pumped number;
    attributing it to the other side reproduces Talishar's exactly (1 vs 5).

    Only ACTION cards are replayed. Tokens (might, toughness) and heroes appear
    in the same list, and dispatching a play ability on those is meaningless.
    """
    import copy as _copy
    from engine.card_effects.dsl import dispatch

    for listed_pid, data in ((attacker_id, side), (3 - attacker_id, opp)):
        owner = 3 - listed_pid           # the inversion
        for slug in _ids(data.get("effects")):
            proto = DB.get(canonical(slug))
            if proto is None or "Action" not in (proto.types or []):
                continue
            card = _copy.deepcopy(proto)
            card.owner = card.controller = owner
            try:
                dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
            except Exception:
                pass                     # a card we cannot replay must not stop the run


def build_state(side, opp, attacker_id=1, with_effects=False):
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
        # CR 8.5.50 marked, as the engine stores it (effect_keywords.mark).
        if is_marked(data):
            player.class_counters["marked"] = 1
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

    # Board permanents carry continuous effects of their own, and putting them
    # in the zone is not the same as registering them. This did NOT move any
    # measured case — the one it was aimed at, a Frailty token giving -1{p},
    # turned out to be unimplemented in the card itself — but registering them
    # is the faithful reconstruction and the omission would bite silently the
    # moment such a card is authored.
    for pid in (1, 2):
        player = st.players[pid]
        for zone_name in ("auras", "items", "allies", "permanents",
                          "head", "chest", "arms", "legs", "weapon1", "weapon2"):
            zone = getattr(player, zone_name, None)
            if zone is None:
                continue
            for card in list(zone.cards):
                try:
                    E._register_card_continuous_effects(st, card)
                except Exception:
                    pass          # a card we cannot model must not kill the run
        if player.hero is not None:
            try:
                E._register_card_continuous_effects(st, player.hero)
            except Exception:
                pass
    if with_effects:
        apply_active_effects(st, side, opp, attacker_id)
    return st


def our_power(st, slug, attacker_id=1, played_from=None):
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
    # Whether this is a WEAPON attack is a property of the attacking object and
    # several statics key off it — Frailty's -1{p} hits "weapon attacks", and
    # with from_weapon left at its default the branch could never fire.
    st.combat.from_weapon = bool(
        {str(t).lower() for t in (card.types or [])} & {"weapon"})
    if played_from:
        card.played_from_zone = played_from
    E._apply_turn_attack_effects(st, card)
    E._register_card_continuous_effects(st, card)
    _announce_attack(st, card)
    E._recalculate_attack_power(st)
    return st.combat.attack_power


def _announce_attack(st, card):
    """Fire the ON_ATTACK triggers, the way announcing the attack does.

    Without this the harness applied only continuous statics, so any pump
    written as a TRIGGERED / ON_ATTACK ability read as absent. That is a large
    class -- every "Combo - ... gains +N{p}" card among them -- and it fails in
    the direction that looks like an engine defect: ours low, theirs right.
    whelming_gustwave's combo was reported as a -1 disagreement on exactly the
    states built to exercise it, while the engine itself had the card right.

    engine.engine emits 'attacking' at the same point for the same reason
    (engine.py: "7.2.4: attack event"); replaying the event rather than calling
    the DSL directly keeps granted triggers and the listener ordering intact.
    """
    from engine.state import Event
    try:
        st.event_manager.emit(Event(type="attacking", card=card.slug), st)
    except Exception:
        # A trigger that needs more of a real game than a reconstructed state
        # carries must not take the whole comparison down with it; the power
        # read below is still the engine's answer for everything else.
        pass


def attack_states(db_path, limit, wide=False):
    """Yield (slug, talishar_power, attacker_side, other_side) for the first
    state of each attack that meets the comparison criteria."""
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    prev: dict = {}
    #: Last seen arsenal per game per side. Talishar never says which zone an
    #: attack was played from, but "it was in that side's arsenal a moment ago
    #: and is now attacking" is the same fact. Frailty's -1{p} applies to attack
    #: action cards played FROM ARSENAL, so without this those attacks read 1
    #: high.
    last_arsenal: dict = {}
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
        was_in_arsenal = last_arsenal.get(gid) or {}
        # Talishar sends empty `data: {}` heartbeats to an authenticated
        # spectator; they decode to an all-null state. Letting one overwrite the
        # remembered arsenal wipes it a beat before the attack lands, which is
        # exactly when it is needed.
        if gs.get("turn_no") is not None:
            last_arsenal[gid] = {
                "player": set(_ids((gs.get("player") or {}).get("arsenal"))),
                "opponent": set(_ids((gs.get("opponent") or {}).get("arsenal"))),
            }
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
        # Later chain links are NOT excluded any more. The exclusion was set on
        # the assumption that earlier links carry bonuses the visible state
        # cannot explain, and never checked; measured, later-link attacks agree
        # 94% against 98% for first-link ones. Four points of precision for
        # roughly triple the evidence, and the entries themselves hold nothing
        # reconstructible anyway -- {"result": "hit", "isDraconic": false}.
        # verify_card_against_talishar.py made this change first; keeping the
        # two in step matters because they share the reconstruction.
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
        # FULL name, and it must match exactly one side. An 8-character prefix
        # looked sufficient until an Arakni mirror: "arakni, huntsman" and
        # "arakni, 5l!p3d 7hru 7h3 cr4x" share exactly "arakni, ", so both
        # matched, the first branch won, and the harness reconstructed the
        # DEFENDER as the attacker. Silent, and only in mirrors.
        p_hit = bool(target and p_name and _same_hero(target, p_name))
        o_hit = bool(target and o_name and _same_hero(target, o_name))
        if o_hit and not p_hit:
            side, other = p, o
        elif p_hit and not o_hit:
            side, other = o, p
        else:
            skipped["attacker side ambiguous"] += 1
            continue

        # EITHER side, not just the attacker. Talishar's `effects` arrays do not
        # sit on the side you would expect: "Up Sticks and Run — your next
        # dagger attack this turn gets +4" is played by the attacker and shows
        # up in the DEFENDER's effects list. Filtering only the attacker let the
        # whole dagger cluster through, and every one of those -4s was this
        # card or its twin cut_from_the_same_cloth_red, not an engine bug.
        #
        # These turn-scoped "your next X gets +N" markers are the one visible
        # thing the harness cannot restore: they live in player turn state, not
        # on the board, so the token is a marker that a pump exists rather than
        # something reconstructible. Excluded rather than reported.
        if not wide and (_ids(side.get("effects")) or _ids(other.get("effects"))):
            skipped["turn-scoped effect tokens in play"] += 1
            continue

        # Which side's arsenal held it a moment ago decides played_from.
        side_key = "player" if side is (gs.get("player") or {}) else "opponent"
        played_from = "arsenal" if slug in (was_in_arsenal.get(side_key) or set()) else None

        yielded += 1
        yield slug, power, side, other, played_from, skipped


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

    for slug, theirs, side, other, played_from, skip in attack_states(
            args.db, args.limit, args.wide):
        skipped = skip
        try:
            st = build_state(side, other)
            ours = our_power(st, slug, played_from=played_from)
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

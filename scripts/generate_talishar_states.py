#!/usr/bin/env python3
"""Make Talishar produce the states a card needs, instead of hunting for them.

Every other check in this repo SEARCHES a corpus: the spectator DB
(verify_card_against_talishar.py) and the headless parquet dumps
(talishar_outcome_diff.py). Both answer "no evidence" for any card nobody
happened to play, which is most of them, and neither can be aimed at the
situation a card actually needs.

FAB_Sim_Headless runs the real Talishar PHP engine locally behind an HTTP
adapter, so the states can be GENERATED. This script used to do that by
stacking twelve copies of the card into a deck and playing whole games until one
was drawn. That worked, slowly, and had a defect that only showed up on combo
cards: the stacker swaps the card in over the most-duplicated OTHER card, which
in a Katsu deck is Surging Strike -- the exact card whelming_gustwave combos
with. It made the card unverifiable by construction.

The adapter now has POST /scenario, which patches a booted game's state
directly (see scripts/talishar_scenario.py). So the board is built rather than
waited for: the card in hand, the combo partner already on the chain, the
resources paid. Seconds instead of minutes, and aimable.

    # one-time, from FAB_Sim_Headless:
    #   $env:ADAPTER_MODE = "real"; docker compose up -d adapter
    python scripts/generate_talishar_states.py --card whelming_gustwave_red
    python scripts/generate_talishar_states.py --card kiss_of_death_red --repeats 4

Output is unchanged, so verify_card_against_talishar.py needs no changes:
  card_data/generated_states/<slug>.jsonl          {state_json, chosen_action_json, next_state_json}
  card_data/generated_states/<slug>.attacks.jsonl  one active-combat state per line

--play-games keeps the old grind-a-real-game path. It is slower and cannot aim,
but a scenario patch only sets zones and turn scalars: situations that depend on
accumulated turn history (class-state counters, per-turn stats) are not
expressible yet, and playing a game is still the way to reach those.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.talishar_scenario import (  # noqa: E402
    ADAPTER, HEADLESS, Scenario, ScenarioError, build, combo_partners,
    slug_index, zone_requirements,
)

OUT_DIR = ROOT / "card_data" / "generated_states"


def situations(slug, index, repeats=1, seed=17):
    """The boards worth building for this card.

    Deliberately small and derived from the card's own text rather than a
    per-card table -- card-specific knowledge belongs in engine/card_effects/,
    not in tooling. `baseline` answers "what does this card do on a quiet
    board", which is what most cards need; the combo situations answer the
    question the spectator corpus structurally cannot, because its feed never
    names the previous chain link.
    """
    rng = random.Random(seed)
    fuel = zone_requirements(slug, index)
    out = []
    for _ in range(max(1, repeats)):
        s = rng.randrange(1, 10 ** 6)
        out.append(Scenario(card=slug, seed=s, label="baseline"))
        for partner in combo_partners(slug, index):
            out.append(Scenario(card=slug, seed=s, chain_links=[partner],
                                label="combo:%s" % partner))
        # An optional cost is unreachable on an empty board -- Talishar will not
        # even OFFER Decompose without 2 Earth cards and an action in the
        # graveyard -- so a baseline scenario says nothing about that clause.
        # Stock what the card's own CARD_IN_ZONE conditions ask for, then run
        # BOTH branches: the pump must appear when paid and stay absent when
        # not. Declining alone would pass just as well against a card whose
        # optional never fires at all.
        if fuel:
            # HAND fuel JOINS the card under test, it does not replace it.
            # Scenario.hand defaults to [card]; passing hand=<fuel> as a kwarg
            # overrode that and left the card out of hand entirely, so it could
            # not be played and the situation recorded nothing.
            kwargs = dict(fuel)
            hand_fuel = kwargs.pop("hand", [])
            if hand_fuel:
                kwargs["hand"] = [slug] + list(hand_fuel)
            for taken in (False, True):
                out.append(Scenario(card=slug, seed=s, take_optional=taken,
                                    label="optional:%s" % ("taken" if taken
                                                           else "declined"),
                                    **kwargs))
    return out


def run_scenario(sc, index, adapter):
    """Build one board, play the card, record what Talishar did.

    Returns (transition, attack_state, note). A None transition with a note is
    a finding worth printing: Talishar refusing to let the card be played in the
    state we asked for says something, and swallowing it would turn a real
    result into a silent zero.
    """
    built = build(sc, adapter=adapter, index=index)
    before = built.state
    action = built.action_for(sc.card)
    if action is None:
        offered = sorted({a.get("card_id") for a in built.legal_actions
                          if a.get("type") == "PLAY_FROM_HAND"} - {None})
        return None, None, ("not playable (offered: %s)" % (offered or "nothing"))

    result = built.step(action["action_id"])
    after = result["state"]

    transition = {
        "state_json": json.dumps(before),
        "chosen_action_json": json.dumps(action),
        "next_state_json": json.dumps(after),
        "situation": sc.label,
    }

    attack = _live_attack(built, result, sc.card, sc.take_optional)
    if attack is not None:
        # Tag which branch Talishar actually walked. Without it the verifier
        # replays every recorded attack with the DECLINING agent, so a state
        # recorded after PAYING the cost would be compared against an engine
        # that refused to pay -- a guaranteed disagreement that says nothing
        # about the card. Namespaced so it cannot collide with a Talishar key.
        attack = dict(attack)
        attack["_fab_scenario"] = {"label": sc.label,
                                   "take_optional": bool(sc.take_optional)}
    return transition, attack, None


#: How many priority passes to walk through looking for the live attack. An
#: attack action opens an instant-speed window for BOTH players before it
#: reaches the chain, so two is the common case; the cap only stops a runaway.
_PASS_BUDGET = 8

#: Extra steps allowed when PAYING an optional cost. Decompose banishes three
#: separate cards, each its own CHOOSE_ action, so the pass budget alone runs
#: out before the attack goes live.
_CHOICE_BUDGET = 10


def _live_attack(built, result, slug, take_optional=False):
    """The state where `slug` is the attack on the chain, or None.

    Playing an attack does not put it on the chain -- it goes to the stack and
    opens an instant-speed window for each player first. Reading the state
    immediately after the play therefore shows an empty combat chain, and an
    earlier version of this recorded nothing at all for cards whose window did
    not happen to auto-pass. So: walk forward until the attack is live.

    PASS and nothing else, normally: any other action would change the board the
    scenario asked for. The exception is `take_optional`, which answers the
    card's own cost prompt -- Talishar surfaces those as real legal actions
    (phase MAYCHOOSEMULTIZONE, CHOOSE_* options plus PASS), so the branch is
    something we can choose rather than guess. That is the whole reason the
    accepted branch is testable here and not in the spectator corpus.
    """
    budget = _PASS_BUDGET + (_CHOICE_BUDGET if take_optional else 0)
    first_live = None   # the attack on the chain, cost not yet paid
    pre_choice = None   # the board Talishar offered the choice on
    paid = False
    for _ in range(budget):
        state = result["state"]
        combat = state.get("combat") or {}
        chain = state.get("combat_chain") or []
        legal = result.get("legal_actions") or []
        choices = [a for a in legal
                   if str(a.get("type", "")).startswith("CHOOSE_")]
        live = bool(combat.get("active") and chain
                    and chain[0].get("card_id") == slug)
        if live and first_live is None:
            first_live = state

        if not take_optional:
            if live:
                return state
        elif choices:
            # KEEP THE BOARD AS IT WAS BEFORE PAYING. Paying SPENDS the cost:
            # once Decompose resolves the graveyard is empty, and replaying that
            # state cannot reproduce the pump it bought -- our engine's gate
            # wants the two Earth cards that are no longer there, so the paid
            # branch read ours=6 against theirs=8 for that reason alone. The
            # question is "given THIS board, what is the power once the optional
            # is taken", so the board comes from before the payment and only the
            # oracle number from after.
            if pre_choice is None:
                pre_choice = state
            result = built.step(choices[0]["action_id"])
            paid = True
            continue
        elif paid and live:
            out = dict(pre_choice)
            out["_fab_oracle_power"] = combat.get("attack_power")
            return out
        elif not live and first_live is not None:
            # Walked past the attack without ever being offered the choice.
            break

        # THE PROMPT CAN LAG THE ATTACK GOING LIVE. Talishar puts the card on
        # the chain and surfaces the cost prompt a step later, and whether it is
        # already up on the first live state varies with the deck shuffle. An
        # earlier version returned at the first live state, so the paid branch
        # silently became the declined branch on some runs and not others --
        # identical output, no error, and nothing to say the setup had failed.
        # So keep passing while the attack is live and look again.
        step_on = next((a for a in legal if a.get("type") == "PASS"), None)
        if step_on is None:
            break
        result = built.step(step_on["action_id"])

    if take_optional and not paid:
        # Report it rather than return a state indistinguishable from the
        # declined branch: an unpaid "taken" row would agree with our engine for
        # the wrong reason and quietly claim coverage the run never had.
        return None
    return first_live


def generate(slug, adapter=ADAPTER, repeats=1, seed=17, verbose=True):
    index = slug_index()
    if slug not in index:
        print("unknown slug %r" % slug)
        return 1

    plans = situations(slug, index, repeats=repeats, seed=seed)
    transitions, attacks, notes = [], [], []
    for sc in plans:
        try:
            tr, atk, note = run_scenario(sc, index, adapter)
        except ScenarioError as exc:
            notes.append("%s: %s" % (sc.label, exc))
            if verbose:
                print("  %-24s FAILED %s" % (sc.label, str(exc)[:200]))
            continue
        if note:
            notes.append("%s: %s" % (sc.label, note))
        if tr:
            transitions.append(tr)
        if atk:
            attacks.append(atk)
        if verbose:
            # On a paid-optional row the board is the PRE-payment one, so its
            # own combat.attack_power is the unpaid number; the oracle is what
            # Talishar settled on after. Printing the board's number there made
            # both branches read 6 and 6 and hid a working setup.
            power = (atk or {}).get("_fab_oracle_power")
            if power is None:
                power = ((atk or {}).get("combat") or {}).get("attack_power")
            print("  %-24s %s%s" % (
                sc.label,
                "transition" if tr else "no transition",
                "" if power is None else ", attack_power=%s" % power))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / ("%s.jsonl" % slug)
    if transitions:
        out.write_text("".join(json.dumps(r) + "\n" for r in transitions),
                       encoding="utf-8")
    atk_out = OUT_DIR / ("%s.attacks.jsonl" % slug)
    if attacks:
        atk_out.write_text("".join(json.dumps(r) + "\n" for r in attacks),
                           encoding="utf-8")

    print("\n%s: %d transition(s), %d attack state(s) across %d situation(s)"
          % (slug, len(transitions), len(attacks), len(plans)))
    if transitions:
        print("  -> %s" % out)
    if attacks:
        print("  -> %s" % atk_out)
    for note in notes:
        print("  note: %s" % note)
    return 0 if (transitions or attacks) else 1


# ----------------------------------------------------------------------
# Legacy path: play real games until the card shows up.
# ----------------------------------------------------------------------

DECK_TEMPLATES = HEADLESS / "decks" / "_cc_games"
GEN_DIR = HEADLESS / "decks" / "_generated"


def build_deck(slug, deck, copies=12):
    """Swap the card in over filler, keeping the deck the same size.

    STACKED ON PURPOSE, for the --play-games path only: that path waits for the
    card to be DRAWN, and three copies in a sixty-card deck means most games end
    without it appearing. The cost is that this evicts the most-duplicated other
    card, which can be the card under test's own combo partner -- which is why
    the default path builds the board instead of stacking for it.
    """
    from collections import Counter
    cards = list(deck.get("deck") or [])
    have = cards.count(slug)
    if have >= copies:
        return deck
    counts = Counter(c for c in cards if c != slug)
    for _ in range(copies - have):
        if not counts:
            break
        victim = counts.most_common(1)[0][0]
        cards[cards.index(victim)] = slug
        counts[victim] -= 1
        if counts[victim] <= 0:
            del counts[victim]
    out = dict(deck)
    out["deck"] = cards
    out["comment"] = "generated for %s" % slug
    return out


def run_game(env, slug, seed, step_cap=1200, want=6):
    """Record up to `want` transitions playing `slug`, then stop."""
    transitions = []
    attacks = []
    init = env.reset(hero1=env._hero1, hero2=env._hero2,
                     deck1=env._deck1, deck2=env._deck2,
                     seed=seed, format="cc")
    legal = init.legal_actions
    for _ in range(step_cap):
        if env.done:
            break
        if not legal:
            legal = env.get_actions(refresh=True)
            if not legal:
                break
        before = env.get_state()
        choice = None
        for a in legal:
            if slug in json.dumps(a.__dict__ if hasattr(a, "__dict__") else {}):
                choice = a
                break
        if choice is None:
            nonpass = [a for a in legal
                       if "pass" not in str(getattr(a, "label", "")).lower()]
            choice = (nonpass or legal)[0]
        # Precise, not a substring match: `slug in json.dumps(action)` also
        # matched pitching the card and blocking with it.
        cd = choice.__dict__ if hasattr(choice, "__dict__") else {}
        played_target = (str(cd.get("type") or "") == "PLAY_FROM_HAND"
                         and cd.get("card_id") == slug)
        result = env.step(getattr(choice, "action_id", getattr(choice, "id", 0)))
        legal = result.legal_actions

        now = env.get_state(refresh=True)
        combat = now.get("combat") or {}
        chain = now.get("combat_chain") or []
        if combat.get("active") and chain and chain[0].get("card_id") == slug:
            attacks.append(json.dumps(now))
        if played_target:
            transitions.append({
                "state_json": json.dumps(before),
                "chosen_action_json": json.dumps(cd),
                "next_state_json": json.dumps(env.get_state(refresh=True)),
            })
        # Stop only when BOTH are satisfied. Breaking on the transition quota
        # alone captured no attack states at all: the attack goes to the STACK
        # first and combat only becomes active on a later step.
        if len(transitions) >= want and len(attacks) >= want:
            break
    return transitions, attacks


def play_games(slug, adapter, games, seed, want, copies):
    from scripts.talishar_scenario import pick_template
    sys.path.insert(0, str(HEADLESS))
    try:
        from python.gameplay.env import TalisharEnv
    except ImportError as exc:
        print("cannot import the headless env (%s)" % exc)
        return 2

    index = slug_index()
    path, template, already = pick_template(slug, index)
    if template is None:
        print("no CC template deck for a hero that can legally play %s" % slug)
        return 1
    print("template: %s (hero=%s, already runs the card: %s)"
          % (path.name, template.get("hero"), already))

    deck = build_deck(slug, template, copies=copies)
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    mine = GEN_DIR / ("%s_seat0.json" % slug)
    mine.write_text(json.dumps(deck, indent=1), encoding="utf-8")
    opp = GEN_DIR / ("%s_seat1.json" % slug)
    opp.write_text(json.dumps(template, indent=1), encoding="utf-8")

    env = TalisharEnv(adapter, timeout=60.0)
    env._hero1 = deck["hero"]
    env._hero2 = template["hero"]
    env._deck1 = "decks/_generated/%s" % mine.name
    env._deck2 = "decks/_generated/%s" % opp.name

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / ("%s.jsonl" % slug)
    total = 0
    all_attacks = []
    rng = random.Random(seed)
    with out.open("w", encoding="utf-8") as fh:
        for i in range(games):
            try:
                rows, atks = run_game(env, slug, rng.randrange(1, 10 ** 6), want=want)
                all_attacks.extend(atks)
            except Exception as exc:
                print("  game %d failed: %r" % (i + 1, exc))
                continue
            for row in rows:
                fh.write(json.dumps(row) + "\n")
            total += len(rows)
            print("  game %d: %d transition(s) playing %s" % (i + 1, len(rows), slug))
    print("\nwrote %d transition(s) to %s" % (total, out))
    if all_attacks:
        atk_out = OUT_DIR / ("%s.attacks.jsonl" % slug)
        atk_out.write_text("\n".join(all_attacks) + "\n", encoding="utf-8")
        print("wrote %d attack state(s) to %s" % (len(all_attacks), atk_out))
    return 0 if (total or all_attacks) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", required=True)
    ap.add_argument("--adapter", default=ADAPTER)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--repeats", type=int, default=1,
                    help="Rebuild each situation this many times with different "
                         "seeds (varies the rest of the deck and the opponent).")
    ap.add_argument("--play-games", action="store_true",
                    help="Legacy path: stack the deck and play real games. "
                         "Slower and cannot aim, but reaches situations that "
                         "depend on accumulated turn history.")
    ap.add_argument("--games", type=int, default=3, help="--play-games only")
    ap.add_argument("--want", type=int, default=6, help="--play-games only")
    ap.add_argument("--copies", type=int, default=12, help="--play-games only")
    args = ap.parse_args()

    import urllib.request
    try:
        with urllib.request.urlopen("%s/health" % args.adapter, timeout=5) as fh:
            health = json.load(fh)
    except Exception as exc:
        print("adapter not reachable at %s (%r)" % (args.adapter, exc))
        print("start it:  cd FAB_Sim_Headless && "
              "ADAPTER_MODE=real docker compose up -d adapter")
        return 2
    if health.get("mode") != "real":
        print("adapter is in %r mode, not 'real' — it would not be Talishar's rules"
              % health.get("mode"))
        return 2

    if args.play_games:
        return play_games(args.card, args.adapter, args.games, args.seed,
                          args.want, args.copies)
    return generate(args.card, adapter=args.adapter, repeats=args.repeats,
                    seed=args.seed)


if __name__ == "__main__":
    raise SystemExit(main())

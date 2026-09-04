#!/usr/bin/env python3
"""Make Talishar play a card, instead of hunting for a game that happened to.

Every other check in this repo SEARCHES a corpus: the spectator DB
(verify_card_against_talishar.py) and the headless parquet dumps
(talishar_outcome_diff.py). Both answer "no evidence" for any card nobody
happened to play, which is most of them, and neither can be aimed at the
situation a card actually needs.

FAB_Sim_Headless runs the real Talishar PHP engine locally behind an HTTP
adapter, so the states can be GENERATED. Build a deck containing the card,
start a game, drive it until the card is played, and record the transition.
Talishar is the only thing mutating state; we just choose actions.

    # one-time, from FAB_Sim_Headless:
    #   $env:ADAPTER_MODE = "real"; docker compose up -d adapter
    python scripts/generate_talishar_states.py --card kiss_of_death_red
    python scripts/generate_talishar_states.py --card kiss_of_death_red --games 5

Output is JSONL of {state_json, chosen_action_json, next_state_json} — the same
shape talishar_outcome_diff.usable() already consumes, so the comparison code
is shared rather than rewritten.

DECKS ARE BUILT FROM A TEMPLATE, not from scratch. Talishar enforces legality
at game start (deck size, hero/weapon match), and a deck assembled by picking
"cards that name this hero as legal" fails that in ways that are tedious and
uninformative. decks/_cc_games holds real hero-vs-hero CC decks; the closest
one for a legal hero is used and the card under test is swapped in over the
filler, which keeps the deck legal by construction.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HEADLESS = Path("C:/Users/Joseph/Desktop/FAB_Sim_Headless")
ADAPTER = "http://localhost:8000"
DECK_TEMPLATES = HEADLESS / "decks" / "_cc_games"
#: Written where the adapter can see it — decks/ is bind-mounted read-only into
#: the container, so generated decks have to live under it.
GEN_DIR = HEADLESS / "decks" / "_generated"
OUT_DIR = ROOT / "card_data" / "generated_states"


def slug_index():
    return json.loads((ROOT / "card_data" / "slug_index.json")
                      .read_text(encoding="utf-8"))["by_slug"]


def pick_template(slug, index):
    """A real CC deck whose hero can legally play this card."""
    entry = index.get(slug) or {}
    legal = {h.lower() for h in (entry.get("legalHeroes") or [])}
    best = None
    for path in sorted(DECK_TEMPLATES.glob("*.json")):
        try:
            deck = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        hero = str(deck.get("hero") or "")
        # legalHeroes are display names ("Arakni"); deck heroes are slugs
        # ("arakni_marionette"), so match on the leading name.
        if legal and not any(hero.startswith(h) for h in legal):
            continue
        # Prefer a deck that already runs the card: its supporting cards are
        # the ones the card is designed to work with.
        if slug in (deck.get("deck") or []):
            return path, deck, True
        if best is None:
            best = (path, deck, False)
    return best if best else (None, None, False)


def build_deck(slug, deck, copies=12):
    """Swap the card in over filler, keeping the deck the same size.

    STACKED ON PURPOSE. The generator waits for the card to be DRAWN, and three
    copies in a sixty-card deck means most games end without it appearing --
    the first head_jab_red run ground through whole games for fifteen minutes
    and recorded nothing. Talishar adjudicates the card identically however
    many copies are in the list.
    """
    cards = list(deck.get("deck") or [])
    have = cards.count(slug)
    if have >= copies:
        return deck
    # Replace the most duplicated OTHER card, so the deck stays legal and we do
    # not delete the card's own support.
    from collections import Counter
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
    """Record up to `want` transitions playing `slug`, then stop.

    Playing on to the end of the game taught us nothing about the card and a
    full CC game is hundreds of steps.
    """
    transitions = []
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
        # Prefer the card under test; otherwise take the first non-pass action
        # so the game actually progresses, falling back to pass.
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
        if played_target:
            transitions.append({
                "state_json": json.dumps(before),
                "chosen_action_json": json.dumps(cd),
                "next_state_json": json.dumps(env.get_state(refresh=True)),
            })
            if len(transitions) >= want:
                break
    return transitions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", required=True)
    ap.add_argument("--games", type=int, default=3)
    ap.add_argument("--adapter", default=ADAPTER)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--want", type=int, default=6,
                    help="Stop a game after this many recorded transitions.")
    ap.add_argument("--copies", type=int, default=12,
                    help="Copies to stack into the deck so it is drawn.")
    args = ap.parse_args()

    sys.path.insert(0, str(HEADLESS))
    try:
        from python.gameplay.env import TalisharEnv
    except ImportError as exc:
        print("cannot import the headless env (%s)" % exc)
        return 2

    import requests
    try:
        health = requests.get("%s/health" % args.adapter, timeout=5).json()
    except Exception as exc:
        print("adapter not reachable at %s (%r)" % (args.adapter, exc))
        print("start it:  cd FAB_Sim_Headless && "
              "ADAPTER_MODE=real docker compose up -d adapter")
        return 2
    if health.get("mode") != "real":
        print("adapter is in %r mode, not 'real' — it would not be Talishar's rules"
              % health.get("mode"))
        return 2

    index = slug_index()
    path, template, already = pick_template(args.card, index)
    if template is None:
        print("no CC template deck for a hero that can legally play %s" % args.card)
        return 1
    print("template: %s (hero=%s, already runs the card: %s)"
          % (path.name, template.get("hero"), already))

    deck = build_deck(args.card, template, copies=args.copies)
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    mine = GEN_DIR / ("%s_seat0.json" % args.card)
    mine.write_text(json.dumps(deck, indent=1), encoding="utf-8")
    opp = GEN_DIR / ("%s_seat1.json" % args.card)
    opp.write_text(json.dumps(template, indent=1), encoding="utf-8")

    env = TalisharEnv(args.adapter, timeout=60.0)
    env._hero1 = deck["hero"]
    env._hero2 = template["hero"]
    env._deck1 = "decks/_generated/%s" % mine.name
    env._deck2 = "decks/_generated/%s" % opp.name

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / ("%s.jsonl" % args.card)
    total = 0
    rng = random.Random(args.seed)
    with out.open("w", encoding="utf-8") as fh:
        for i in range(args.games):
            try:
                rows = run_game(env, args.card, rng.randrange(1, 10 ** 6),
                                want=args.want)
            except Exception as exc:
                print("  game %d failed: %r" % (i + 1, exc))
                continue
            for row in rows:
                fh.write(json.dumps(row) + "\n")
            total += len(rows)
            print("  game %d: %d transition(s) playing %s" % (i + 1, len(rows), args.card))
    print("\nwrote %d transition(s) to %s" % (total, out))
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())

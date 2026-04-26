"""Practice game runner — runs one short game per deck and prints a play-by-play.

Usage:
    python practice_game.py [--turns N] [--deck Victor|Kayo|Arakni]
"""
import argparse
import random
from engine.card import CardDB
from engine.engine import new_game
from engine.actions import ActionType, Action

SLUG_INDEX = "card_data/slug_index.json"

DECKS = {
    "Victor": "decks/victor_goldmane_high_and_mighty_CC_lite.txt",
    "Kayo":   "decks/kayo_underhanded_cheat_CC_lite.txt",
    "Arakni": "decks/arakni_marionette_CC_lite.txt",
}

# Steps where CHOOSE is pitch-ordering — suppress individual lines, summarize
_PITCH_STEPS = {"END_PHASE", "end_phase"}

# Steps where CHOOSE is noisy internal resolution — suppress entirely
_SUPPRESS_CHOOSE_STEPS = {"BEGIN_GAME", "begin_game", "START_PHASE", "start_phase"}

# Significant action types to always print
_SIGNIFICANT = {
    ActionType.PLAY_CARD, ActionType.ACTIVATE_CARD,
    ActionType.DEFEND_CARDS, ActionType.PITCH_CARD,
    ActionType.STORE_ARSENAL,
}


def fmt_card(card):
    if card is None:
        return "-"
    name = getattr(card, 'raw_name', None) or getattr(card, 'name', None) or card.slug
    p = getattr(card, 'power', None)
    d = getattr(card, 'defense', None)
    parts = [name]
    if p is not None:
        parts.append(f"{p}p")
    if d is not None:
        parts.append(f"{d}d")
    return " ".join(parts)


def fmt_zone(zone):
    cards = getattr(zone, 'cards', [])
    if not cards:
        return "(empty)"
    return ", ".join(fmt_card(c) for c in cards)


def fmt_action(action):
    t = action.type
    card = getattr(action, 'card', None)
    card_list = getattr(action, 'card_list', None)

    if t == ActionType.PLAY_CARD and card:
        pitch = getattr(action, 'pitch_cards', None)
        s = f"PLAY {fmt_card(card)}"
        if pitch:
            s += f"  [pitch: {', '.join(fmt_card(c) for c in pitch)}]"
        return s
    if t == ActionType.ACTIVATE_CARD and card:
        label = "ATTACK" if getattr(action, 'is_attack_proxy', False) else "ACTIVATE"
        return f"{label} {fmt_card(card)}"
    if t == ActionType.DEFEND_CARDS:
        if card_list:
            return f"DEFEND [{', '.join(fmt_card(c) for c in card_list)}]"
        if card:
            return f"DEFEND {fmt_card(card)}"
        return "DEFEND"
    if t == ActionType.PITCH_CARD and card:
        return f"PITCH {fmt_card(card)}"
    if t == ActionType.PITCH_TO_DECK and card:
        return f"PITCH_TO_DECK {fmt_card(card)}"
    if t == ActionType.STORE_ARSENAL and card:
        return f"ARSENAL {fmt_card(card)}"
    if t == ActionType.CHOOSE:
        if card:
            return f"CHOOSE {fmt_card(card)}"
        ci = getattr(action, 'choose_index', None)
        return f"CHOOSE {ci}" if ci is not None else "CHOOSE"
    if t == ActionType.PASS:
        return "PASS"
    return t.name if hasattr(t, 'name') else str(t)


def print_board(state):
    for pid, player in state.players.items():
        hero = player.hero
        label = f"P{pid} {getattr(hero, 'raw_name', None) or hero.slug}"
        res = getattr(player, 'resources', 0)
        print(f"  {label}  HP={player.life}  Hand={len(player.hand.cards)}  Deck={len(player.deck.cards)}  Res={res}")
        if player.arsenal.cards:
            print(f"    Arsenal: {fmt_zone(player.arsenal)}")
        equip_parts = []
        for z in ('weapon1', 'weapon2', 'head', 'chest', 'arms', 'legs'):
            zone = getattr(player, z, None)
            if zone and zone.cards:
                equip_parts.append(f"{z}={fmt_zone(zone)}")
        if equip_parts:
            print(f"    Equip: {', '.join(equip_parts)}")
        for lbl2, attr in [("Permanents", "permanents"), ("Items", "items"), ("Allies", "allies")]:
            zone = getattr(player, attr, None)
            cards = getattr(zone, 'cards', []) if zone else []
            if cards:
                print(f"    {lbl2}: {', '.join(fmt_card(c) for c in cards)}")
        gy = player.graveyard.cards
        if gy:
            recent = gy[-3:]
            more = f"  +{len(gy)-3} more" if len(gy) > 3 else ""
            print(f"    GY({len(gy)}): {', '.join(fmt_card(c) for c in recent)}{more}")
    if state.combat:
        c = state.combat
        atk = fmt_card(c.attack_card) if c.attack_card else "?"
        kw = ", ".join(c.keywords) if getattr(c, 'keywords', None) else ""
        kw_str = f" [{kw}]" if kw else ""
        print(f"  >> COMBAT: {atk} (power={c.attack_power}{kw_str}) vs P{3 - c.attacker_id}")
    print()


class GameLogger:
    """Shared turn/step tracker between both agents — prints headers once."""

    def __init__(self):
        self._last_turn = object()  # sentinel
        self._last_step = object()
        self._pitch_buf = {}  # pid -> [cards]

    def flush_pitch(self, pid):
        buf = self._pitch_buf.pop(pid, [])
        if buf:
            names = " -> ".join(fmt_card(c) for c in buf)
            print(f"    P{pid} [pitch order]: {names}")

    def update(self, state, pid):
        """Check for turn/step transitions; print headers as needed. Returns step_name."""
        turn = getattr(state, 'turn_number', None)
        step = state.step
        step_name = step.name if hasattr(step, 'name') else str(step)
        active = getattr(state, 'active_player', None)

        if turn != self._last_turn:
            for p in list(self._pitch_buf):
                self.flush_pitch(p)
            self._last_turn = turn
            self._last_step = object()
            print(f"\n{'='*56}")
            print(f"  TURN {turn}  (Active: P{active})")
            print(f"{'='*56}")
            print_board(state)

        if step_name != self._last_step:
            for p in list(self._pitch_buf):
                self.flush_pitch(p)
            self._last_step = step_name
            print(f"  -- {step_name} --")

        return step_name


class VerboseRandomAgent:
    def __init__(self, player_id, seed, log: GameLogger):
        self.rng = random.Random(seed)
        self.pid = player_id
        self.log = log

    def __call__(self, state, actions, context=None):
        if not isinstance(actions, (list, tuple)) or not actions:
            return actions

        step_name = self.log.update(state, self.pid)

        if isinstance(actions[0], Action):
            choice = self.rng.choice(list(actions))

            # Pitch ordering: buffer and summarize
            if choice.type == ActionType.CHOOSE and step_name in _PITCH_STEPS:
                c = getattr(choice, 'card', None)
                if c:
                    self.log._pitch_buf.setdefault(self.pid, []).append(c)
                return choice

            # Suppress noisy CHOOSE in setup/resolution steps
            if choice.type == ActionType.CHOOSE and step_name in _SUPPRESS_CHOOSE_STEPS:
                return choice

            # Suppress PASS in non-main steps
            if choice.type == ActionType.PASS and step_name not in (
                "ACTION", "action", "COMBAT_ATTACK", "combat_attack",
                "COMBAT_DEFEND", "combat_defend", "COMBAT_REACTION", "combat_reaction",
            ):
                return choice

            # Suppress CHOOSE in clash/trigger resolution unless it's a card action
            if choice.type == ActionType.CHOOSE and choice.type not in _SIGNIFICANT:
                # Only print CHOOSE if it's meaningful (has a card and in main action steps)
                if step_name not in ("ACTION", "action"):
                    return choice

            self.log.flush_pitch(self.pid)
            print(f"    P{self.pid}: {fmt_action(choice)}")
            return choice

        # Non-Action primitive choice (yes/no, index, etc.) — only print with context
        self.log.flush_pitch(self.pid)
        choice = self.rng.choice(list(actions))
        if context:
            print(f"    P{self.pid} ({context}): {choice}")
        return choice


def run_practice_game(name, deck_path, card_db, max_turns=6, seed=42):
    print(f"\n{'='*56}")
    print(f"  PRACTICE GAME: {name} vs {name}")
    print(f"{'='*56}")

    log = GameLogger()
    p1_agent = VerboseRandomAgent(1, seed=seed, log=log)
    p2_agent = VerboseRandomAgent(2, seed=seed + 1, log=log)

    try:
        state = new_game(
            p1_deck_path=deck_path,
            p2_deck_path=deck_path,
            p1_agent=p1_agent,
            p2_agent=p2_agent,
            card_db=card_db,
            p1_seed=seed,
            p2_seed=seed + 1,
            max_turns=max_turns,
        )
    except Exception as e:
        print(f"\n  ERROR during game: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"\n{'='*56}")
    print("  FINAL BOARD STATE")
    print(f"{'='*56}")
    print_board(state)
    winner = getattr(state, 'winner', None)
    turns = getattr(state, 'turn_number', '?')
    if winner:
        print(f"  Result: P{winner} wins in {turns} turns")
    elif state.done:
        print(f"  Result: draw/timeout after {turns} turns")
    else:
        print(f"  Result: game stopped after {turns} turns (max_turns={max_turns})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--deck", type=str, default=None, help="Victor / Kayo / Arakni")
    args = parser.parse_args()

    card_db = CardDB(SLUG_INDEX)
    decks_to_run = {args.deck: DECKS[args.deck]} if args.deck and args.deck in DECKS else DECKS

    for name, path in decks_to_run.items():
        run_practice_game(name, path, card_db, max_turns=args.turns)


if __name__ == "__main__":
    main()

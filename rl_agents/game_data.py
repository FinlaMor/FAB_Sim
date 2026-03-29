"""rl_agents/game_data.py

SQLite-backed storage for Talishar game data, designed to feed IQL training.

Tables
------
decks
    One row per game.  Stores both decklists, hero identities, outcome, and
    metadata so you can filter / stratify training data by matchup.

transitions
    One row per decision point.  Stores the full game state visible to the
    acting player, the set of legal actions, the action that was taken, and
    the resulting next-state.  Terminal transitions carry the final reward.
    Denormalized columns avoid expensive JSON parsing during training.

Usage
-----
    store = GameDataStore("data/games.db")
    collector = TransitionCollector(game_id="abc123")
    # ... inside game loop, call collector.record(...)
    store.save_game(collector, deck_meta)
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


from rl_agents.utils.card_helpers import safe_int as _safe_int


def _generate_game_id() -> str:
    return uuid.uuid4().hex[:16]


# ── State extraction helpers ─────────────────────────────────────────


def _extract_turn_phase(state: dict) -> str:
    """Extract the raw turn phase code from a Talishar state dict."""
    tp = state.get("turnPhase")
    if isinstance(tp, dict):
        return str(tp.get("turnPhase", "")).upper()
    return str(tp or "").upper()


def _classify_decision(state: dict, action: dict) -> str:
    """Derive a human-readable decision type from state + action.

    Decision types:
        pass, pitch, choose_effect, defend_block, defense_reaction,
        attack_reaction, play_card, activate_equipment, arsenal, button, other
    """
    mode = action.get("mode")
    atype = action.get("type", "")
    phase = _extract_turn_phase(state)
    prompt = ""
    pp = state.get("playerPrompt")
    if isinstance(pp, dict):
        prompt = (pp.get("helpText") or "").lower()

    if atype == "pass_phase" or mode == 99:
        return "pass"
    if mode == 16 or "CHOOSEHAND" in phase:
        if "pitch" in prompt:
            return "pitch"
        return "choose_effect"
    if phase == "B":
        if atype in ("hand", "equipment"):
            return "defend_block"
        return "defense_reaction"
    if phase == "D" or phase == "A":
        return "attack_reaction" if phase == "A" else "defense_reaction"
    if phase == "ARS":
        return "arsenal"
    if mode == 27:
        return "play_card"
    if atype == "equipment":
        return "activate_equipment"
    if atype in ("button", "prompt_button"):
        return "button"
    return "other"


def _extract_combat_chain(state: dict) -> tuple[bool, int | None, int | None]:
    """Return (in_combat_chain, chain_attack, chain_defense)."""
    acl = state.get("activeChainLink")
    if not acl or not isinstance(acl, dict):
        return False, None, None
    attack = _safe_int(acl.get("totalPower"), 0) if acl.get("totalPower") is not None else None
    defense = _safe_int(acl.get("totalDefense"), 0) if acl.get("totalDefense") is not None else None
    return True, attack, defense


def _count_list(state: dict, key: str) -> int | None:
    """Return len(state[key]) if it's a list, else None."""
    v = state.get(key)
    return len(v) if isinstance(v, list) else None


_COMBAT_KEYWORD_KEYS = (
    "dominate", "overpower", "phantasm", "piercing", "tower",
    "combo", "highTide", "wager", "confidence", "fusion",
)


def _extract_zone_slugs(state: dict, key: str) -> str | None:
    """Extract card slugs from a zone as JSON list string.

    Returns JSON string like '["sink_below_red","command_and_conquer_red"]'
    or None if zone is absent.
    """
    cards = state.get(key)
    if not isinstance(cards, list):
        return None
    slugs = []
    for card in cards:
        if isinstance(card, dict):
            slug = card.get("cardNumber") or card.get("cardID") or ""
            if slug:
                slugs.append(slug)
    return json.dumps(slugs, separators=(",", ":")) if slugs else "[]"


def _extract_combat_keywords(acl: dict | None) -> str | None:
    """Return comma-separated active combat keywords, or None if not in combat."""
    if not acl or not isinstance(acl, dict):
        return None
    active = [k for k in _COMBAT_KEYWORD_KEYS if acl.get(k)]
    return ",".join(active) if active else None


# ── Data classes ─────────────────────────────────────────────────────


@dataclass
class DeckMeta:
    """Metadata about the decks used in a single game."""
    game_id: str
    p1_deck_file: str
    p2_deck_file: str
    p1_decklist: dict
    p2_decklist: dict
    winner: int | None
    p1_final_hp: int
    p2_final_hp: int
    turn_count: int
    ended_on_turn_cap: bool
    total_actions: int
    seed: int | None = None
    mode: str = "pvp"


@dataclass
class Transition:
    """A single (s, a, s', r, done) tuple with denormalized features."""
    game_id: str
    step: int
    player_id: int
    turn_number: int
    state: dict
    available_actions: list[dict]
    action_taken: dict
    action_index: int
    next_state: dict | None
    reward: float
    done: bool
    p1_hp: int
    p2_hp: int
    # --- denormalized columns (extracted from state at record time) ---
    decision_type: str
    hp_delta: int
    opp_hp_delta: int
    cards_in_deck: int | None
    opp_cards_in_deck: int | None
    num_actions: int
    action_points: int | None
    turn_phase: str
    card_id: str | None
    in_combat_chain: bool
    combat_chain_attack: int | None
    combat_chain_defense: int | None
    is_turn_player: bool
    hand_size: int | None
    opp_hand_size: int | None
    # --- zone sizes ---
    resources: int | None
    graveyard_size: int | None
    opp_graveyard_size: int | None
    banished_size: int | None
    opp_banished_size: int | None
    pitch_zone_size: int | None
    opp_pitch_zone_size: int | None
    equipment_count: int | None
    opp_equipment_count: int | None
    has_arsenal: bool
    opp_has_arsenal: bool
    # --- combat detail ---
    chain_link_count: int
    has_go_again: bool
    combat_keywords: str | None       # comma-separated: dominate,overpower,phantasm,...
    # --- zone content columns (JSON arrays of card slugs) ---
    player_hand: str | None = None
    player_graveyard: str | None = None
    player_banished: str | None = None
    player_arsenal: str | None = None
    player_equipment: str | None = None
    player_pitch_zone: str | None = None
    player_soul: str | None = None
    player_auras: str | None = None
    player_items: str | None = None
    player_permanents: str | None = None
    opp_graveyard: str | None = None
    opp_banished: str | None = None
    opp_equipment: str | None = None
    opp_pitch_zone: str | None = None
    opp_soul: str | None = None
    opp_auras: str | None = None
    opp_items: str | None = None
    opp_permanents: str | None = None
    # --- pitch stack columns ---
    player_pitch_stack: str | None = None       # JSON ordered list of all pitched cards
    opp_pitch_stack: str | None = None          # JSON turn-bucketed dict
    # --- deck remainder ---
    deck_remainder: str | None = None           # JSON alphabetically sorted list
    # --- additional metadata ---
    player_hero: str | None = None
    opp_hero: str | None = None
    combat_attack_card: str | None = None
    combat_defending_cards: str | None = None    # JSON array
    chain_link_history: str | None = None        # JSON array
    # --- backfilled after game ends ---
    game_progress: float | None = None
    steps_to_terminal: int | None = None
    next_transition_id: int | None = None       # set during DB insert


class TransitionCollector:
    """Accumulates transitions in memory during a single game.

    Thread-safe so it can be shared across the PvP game loop where both
    players record into the same collector.
    """

    def __init__(self, game_id: str | None = None):
        self.game_id = game_id or _generate_game_id()
        self._transitions: list[Transition] = []
        self._step = 0
        self._lock = threading.Lock()
        # Cumulative pitch stack tracking across transitions within a game
        # {player_id: [slug, slug, ...]} — flat ordered list
        self._player_pitch_stacks: dict[int, list[str]] = {}
        # {player_id: {turn_number: [slug, ...]}} — turn-bucketed
        self._opp_pitch_buckets: dict[int, dict[int, list[str]]] = {}
        # Track which pitch zone slugs we've already added per player per turn
        self._last_pitch_zone: dict[int, set[str]] = {}

    def record(
        self,
        player_id: int,
        turn_number: int,
        state: dict,
        available_actions: list[dict],
        action_taken: dict,
        next_state: dict | None,
        p1_hp: int,
        p2_hp: int,
        reward: float = 0.0,
        done: bool = False,
    ) -> None:
        """Record one decision point.

        All denormalized columns are extracted automatically from *state*,
        *next_state*, and *action_taken* so call sites stay simple.
        """
        # action index
        action_index = -1
        for i, a in enumerate(available_actions):
            if a is action_taken:
                action_index = i
                break
        else:
            for i, a in enumerate(available_actions):
                if a == action_taken:
                    action_index = i
                    break

        # decision classification
        decision_type = _classify_decision(state, action_taken)
        turn_phase = _extract_turn_phase(state)

        # HP deltas (computed from next_state if available)
        if next_state is not None:
            next_p1 = _safe_int(next_state.get("playerHealth"), p1_hp)
            next_p2 = _safe_int(next_state.get("opponentHealth"), p2_hp)
            if player_id == 1:
                hp_delta = next_p1 - p1_hp
                opp_hp_delta = next_p2 - p2_hp
            else:
                # player 2's view: playerHealth is P2, opponentHealth is P1
                hp_delta = next_p1 - p1_hp    # from P2's perspective
                opp_hp_delta = next_p2 - p2_hp
        else:
            hp_delta = 0
            opp_hp_delta = 0

        # card_id from the action
        card_id = action_taken.get("cardNumber") or action_taken.get("cardID") or None

        # combat chain
        in_cc, cc_atk, cc_def = _extract_combat_chain(state)

        # is_turn_player: current player has the main turn (not just reacting)
        # Talishar's mainPlayer would be ideal but isn't always exposed;
        # approximate via phase — defense/reaction phases mean you're not turn player
        is_turn_player = turn_phase not in ("B", "D", "A")

        # zone sizes
        acl = state.get("activeChainLink") if isinstance(state.get("activeChainLink"), dict) else None
        combat_keywords = _extract_combat_keywords(acl)
        has_go_again = bool(acl.get("goAgain")) if acl else False
        chain_links = state.get("combatChainLinks")
        chain_link_count = len(chain_links) if isinstance(chain_links, list) else 0

        player_arse = state.get("playerArse")
        opp_arse = state.get("opponentArse")
        has_arsenal = bool(player_arse) and isinstance(player_arse, list) and len(player_arse) > 0
        opp_has_arsenal = bool(opp_arse) and isinstance(opp_arse, list) and len(opp_arse) > 0

        # --- zone content extraction ---
        player_hand = _extract_zone_slugs(state, "playerHand")
        player_graveyard = _extract_zone_slugs(state, "playerDiscard")
        player_banished = _extract_zone_slugs(state, "playerBanish")
        player_arsenal = _extract_zone_slugs(state, "playerArse")
        player_equipment = _extract_zone_slugs(state, "playerEquipment")
        player_pitch_zone = _extract_zone_slugs(state, "playerPitch")
        player_soul = _extract_zone_slugs(state, "playerSoul")
        player_auras = _extract_zone_slugs(state, "playerAuras")
        player_items = _extract_zone_slugs(state, "playerItems")
        player_permanents = _extract_zone_slugs(state, "playerPermanents")
        opp_graveyard = _extract_zone_slugs(state, "opponentDiscard")
        opp_banished = _extract_zone_slugs(state, "opponentBanish")
        opp_equipment = _extract_zone_slugs(state, "opponentEquipment")
        opp_pitch_zone = _extract_zone_slugs(state, "opponentPitch")
        opp_soul = _extract_zone_slugs(state, "opponentSoul")
        opp_auras = _extract_zone_slugs(state, "opponentAuras")
        opp_items = _extract_zone_slugs(state, "opponentItems")
        opp_permanents = _extract_zone_slugs(state, "opponentPermanents")

        # --- cumulative pitch stack tracking ---
        # Extract current pitch zone slugs as a set
        current_pitch_slugs: list[str] = []
        pitch_cards = state.get("playerPitch")
        if isinstance(pitch_cards, list):
            for card in pitch_cards:
                if isinstance(card, dict):
                    slug = card.get("cardNumber") or card.get("cardID") or ""
                    if slug:
                        current_pitch_slugs.append(slug)

        # Initialize pitch stacks for this player if needed
        if player_id not in self._player_pitch_stacks:
            self._player_pitch_stacks[player_id] = []
        if player_id not in self._last_pitch_zone:
            self._last_pitch_zone[player_id] = set()

        # Detect newly pitched cards (current pitch zone minus what we last saw)
        current_set = set(current_pitch_slugs)
        last_set = self._last_pitch_zone[player_id]
        if current_set != last_set:
            # New cards appeared in pitch zone — add them to cumulative stack
            new_slugs = [s for s in current_pitch_slugs if s not in last_set]
            self._player_pitch_stacks[player_id].extend(new_slugs)
            self._last_pitch_zone[player_id] = current_set

        player_pitch_stack = json.dumps(
            self._player_pitch_stacks[player_id], separators=(",", ":")
        )

        # --- opponent pitch stack (turn-bucketed, alpha-sorted) ---
        opp_pitch_slugs: list[str] = []
        opp_pitch_cards = state.get("opponentPitch")
        if isinstance(opp_pitch_cards, list):
            for card in opp_pitch_cards:
                if isinstance(card, dict):
                    slug = card.get("cardNumber") or card.get("cardID") or ""
                    if slug:
                        opp_pitch_slugs.append(slug)

        if player_id not in self._opp_pitch_buckets:
            self._opp_pitch_buckets[player_id] = {}

        if opp_pitch_slugs:
            turn_key = turn_number
            self._opp_pitch_buckets[player_id][turn_key] = sorted(opp_pitch_slugs)

        opp_pitch_stack = json.dumps(
            {str(k): v for k, v in sorted(self._opp_pitch_buckets[player_id].items())},
            separators=(",", ":"),
        )

        # --- deck remainder (deck minus pitch stack, alpha-sorted) ---
        deck_remainder: str | None = None
        deck_cards = state.get("playerDeck")
        if isinstance(deck_cards, list):
            deck_slugs = []
            for card in deck_cards:
                if isinstance(card, dict):
                    slug = card.get("cardNumber") or card.get("cardID") or ""
                    if slug:
                        deck_slugs.append(slug)
            pitch_stack_set = set(self._player_pitch_stacks.get(player_id, []))
            # Remove pitch stack cards from deck (handle duplicates by count)
            remaining = list(deck_slugs)
            for ps in self._player_pitch_stacks.get(player_id, []):
                if ps in remaining:
                    remaining.remove(ps)
            deck_remainder = json.dumps(sorted(remaining), separators=(",", ":"))

        # --- hero slugs ---
        player_hero: str | None = None
        opp_hero: str | None = None
        p_hero_raw = state.get("playerHero")
        if isinstance(p_hero_raw, dict):
            player_hero = p_hero_raw.get("cardNumber") or p_hero_raw.get("cardID")
        elif isinstance(p_hero_raw, str):
            player_hero = p_hero_raw or None
        o_hero_raw = state.get("opponentHero")
        if isinstance(o_hero_raw, dict):
            opp_hero = o_hero_raw.get("cardNumber") or o_hero_raw.get("cardID")
        elif isinstance(o_hero_raw, str):
            opp_hero = o_hero_raw or None

        # --- combat chain details ---
        combat_attack_card: str | None = None
        combat_defending_cards: str | None = None
        if acl:
            atk_card = acl.get("attackCard") or acl.get("cardNumber")
            if isinstance(atk_card, dict):
                combat_attack_card = atk_card.get("cardNumber") or atk_card.get("cardID")
            elif isinstance(atk_card, str) and atk_card:
                combat_attack_card = atk_card
            def_cards = acl.get("defendingCards")
            if isinstance(def_cards, list):
                def_slugs = []
                for dc in def_cards:
                    if isinstance(dc, dict):
                        s = dc.get("cardNumber") or dc.get("cardID") or ""
                        if s:
                            def_slugs.append(s)
                    elif isinstance(dc, str) and dc:
                        def_slugs.append(dc)
                combat_defending_cards = json.dumps(def_slugs, separators=(",", ":"))

        chain_link_history: str | None = None
        if isinstance(chain_links, list) and chain_links:
            chain_link_history = json.dumps(chain_links, separators=(",", ":"))

        with self._lock:
            t = Transition(
                game_id=self.game_id,
                step=self._step,
                player_id=player_id,
                turn_number=turn_number,
                state=state,
                available_actions=available_actions,
                action_taken=action_taken,
                action_index=action_index,
                next_state=next_state,
                reward=reward,
                done=done,
                p1_hp=p1_hp,
                p2_hp=p2_hp,
                decision_type=decision_type,
                hp_delta=hp_delta,
                opp_hp_delta=opp_hp_delta,
                cards_in_deck=_count_list(state, "playerDeck"),
                opp_cards_in_deck=_count_list(state, "opponentDeck"),
                num_actions=len(available_actions),
                action_points=_safe_int(state.get("playerAP")) if state.get("playerAP") is not None else None,
                turn_phase=turn_phase,
                card_id=card_id,
                in_combat_chain=in_cc,
                combat_chain_attack=cc_atk,
                combat_chain_defense=cc_def,
                is_turn_player=is_turn_player,
                hand_size=_count_list(state, "playerHand"),
                opp_hand_size=_count_list(state, "opponentHand"),
                resources=_safe_int(state.get("playerPitchCount")) if state.get("playerPitchCount") is not None else None,
                graveyard_size=_count_list(state, "playerDiscard"),
                opp_graveyard_size=_count_list(state, "opponentDiscard"),
                banished_size=_count_list(state, "playerBanish"),
                opp_banished_size=_count_list(state, "opponentBanish"),
                pitch_zone_size=_count_list(state, "playerPitch"),
                opp_pitch_zone_size=_count_list(state, "opponentPitch"),
                equipment_count=_count_list(state, "playerEquipment"),
                opp_equipment_count=_count_list(state, "opponentEquipment"),
                has_arsenal=has_arsenal,
                opp_has_arsenal=opp_has_arsenal,
                chain_link_count=chain_link_count,
                has_go_again=has_go_again,
                combat_keywords=combat_keywords,
                player_hand=player_hand,
                player_graveyard=player_graveyard,
                player_banished=player_banished,
                player_arsenal=player_arsenal,
                player_equipment=player_equipment,
                player_pitch_zone=player_pitch_zone,
                player_soul=player_soul,
                player_auras=player_auras,
                player_items=player_items,
                player_permanents=player_permanents,
                opp_graveyard=opp_graveyard,
                opp_banished=opp_banished,
                opp_equipment=opp_equipment,
                opp_pitch_zone=opp_pitch_zone,
                opp_soul=opp_soul,
                opp_auras=opp_auras,
                opp_items=opp_items,
                opp_permanents=opp_permanents,
                player_pitch_stack=player_pitch_stack,
                opp_pitch_stack=opp_pitch_stack,
                deck_remainder=deck_remainder,
                player_hero=player_hero,
                opp_hero=opp_hero,
                combat_attack_card=combat_attack_card,
                combat_defending_cards=combat_defending_cards,
                chain_link_history=chain_link_history,
            )
            self._transitions.append(t)
            self._step += 1

    def record_simple(
        self,
        player_id: int,
        reward: float = 0.0,
        done: bool = False,
        turn_number: int = 0,
        p1_hp: int = 0,
        p2_hp: int = 0,
    ) -> None:
        """Record a simplified transition for local-engine games.

        Stores only the core RL tuple (game_id, step, player_id, reward,
        done) without requiring full Talishar JSON states.  All
        denormalized columns are filled with safe defaults.
        """
        with self._lock:
            t = Transition(
                game_id=self.game_id,
                step=self._step,
                player_id=player_id,
                turn_number=turn_number,
                state={},
                available_actions=[],
                action_taken={},
                action_index=-1,
                next_state=None,
                reward=reward,
                done=done,
                p1_hp=p1_hp,
                p2_hp=p2_hp,
                decision_type="other",
                hp_delta=0,
                opp_hp_delta=0,
                cards_in_deck=None,
                opp_cards_in_deck=None,
                num_actions=0,
                action_points=None,
                turn_phase="",
                card_id=None,
                in_combat_chain=False,
                combat_chain_attack=None,
                combat_chain_defense=None,
                is_turn_player=True,
                hand_size=None,
                opp_hand_size=None,
                resources=None,
                graveyard_size=None,
                opp_graveyard_size=None,
                banished_size=None,
                opp_banished_size=None,
                pitch_zone_size=None,
                opp_pitch_zone_size=None,
                equipment_count=None,
                opp_equipment_count=None,
                has_arsenal=False,
                opp_has_arsenal=False,
                chain_link_count=0,
                has_go_again=False,
                combat_keywords=None,
                # zone content columns — no state to extract from
                player_hand=None,
                player_graveyard=None,
                player_banished=None,
                player_arsenal=None,
                player_equipment=None,
                player_pitch_zone=None,
                player_soul=None,
                player_auras=None,
                player_items=None,
                player_permanents=None,
                opp_graveyard=None,
                opp_banished=None,
                opp_equipment=None,
                opp_pitch_zone=None,
                opp_soul=None,
                opp_auras=None,
                opp_items=None,
                opp_permanents=None,
                # pitch stacks
                player_pitch_stack=None,
                opp_pitch_stack=None,
                # deck remainder
                deck_remainder=None,
                # additional metadata
                player_hero=None,
                opp_hero=None,
                combat_attack_card=None,
                combat_defending_cards=None,
                chain_link_history=None,
            )
            self._transitions.append(t)
            self._step += 1

    def finalize(self, winner: int | None) -> None:
        """Retroactively set terminal rewards and backfill computed columns.

        Must be called after the game ends, before save_game().
        """
        with self._lock:
            if not self._transitions:
                return

            total_steps = len(self._transitions)

            # --- terminal rewards ---
            last_by_player: dict[int, int] = {}
            for i, t in enumerate(self._transitions):
                last_by_player[t.player_id] = i

            for pid, idx in last_by_player.items():
                t = self._transitions[idx]
                self._transitions[idx] = _replace_transition(t,
                    reward=_terminal_reward(pid, winner),
                    done=True,
                )

            # --- game_progress and steps_to_terminal ---
            for i, t in enumerate(self._transitions):
                self._transitions[i] = _replace_transition(t,
                    game_progress=round(i / max(total_steps - 1, 1), 4),
                    steps_to_terminal=total_steps - 1 - i,
                )

    # Keep old name as alias for backwards compat
    finalize_rewards = finalize

    @property
    def transitions(self) -> list[Transition]:
        with self._lock:
            return list(self._transitions)


def _replace_transition(t: Transition, **overrides: Any) -> Transition:
    """Return a copy of *t* with the given fields overridden."""
    d = {
        "game_id": t.game_id, "step": t.step, "player_id": t.player_id,
        "turn_number": t.turn_number, "state": t.state,
        "available_actions": t.available_actions,
        "action_taken": t.action_taken, "action_index": t.action_index,
        "next_state": t.next_state, "reward": t.reward, "done": t.done,
        "p1_hp": t.p1_hp, "p2_hp": t.p2_hp,
        "decision_type": t.decision_type, "hp_delta": t.hp_delta,
        "opp_hp_delta": t.opp_hp_delta,
        "cards_in_deck": t.cards_in_deck,
        "opp_cards_in_deck": t.opp_cards_in_deck,
        "num_actions": t.num_actions, "action_points": t.action_points,
        "turn_phase": t.turn_phase, "card_id": t.card_id,
        "in_combat_chain": t.in_combat_chain,
        "combat_chain_attack": t.combat_chain_attack,
        "combat_chain_defense": t.combat_chain_defense,
        "is_turn_player": t.is_turn_player,
        "hand_size": t.hand_size, "opp_hand_size": t.opp_hand_size,
        "resources": t.resources,
        "graveyard_size": t.graveyard_size,
        "opp_graveyard_size": t.opp_graveyard_size,
        "banished_size": t.banished_size,
        "opp_banished_size": t.opp_banished_size,
        "pitch_zone_size": t.pitch_zone_size,
        "opp_pitch_zone_size": t.opp_pitch_zone_size,
        "equipment_count": t.equipment_count,
        "opp_equipment_count": t.opp_equipment_count,
        "has_arsenal": t.has_arsenal,
        "opp_has_arsenal": t.opp_has_arsenal,
        "chain_link_count": t.chain_link_count,
        "has_go_again": t.has_go_again,
        "combat_keywords": t.combat_keywords,
        "player_hand": t.player_hand,
        "player_graveyard": t.player_graveyard,
        "player_banished": t.player_banished,
        "player_arsenal": t.player_arsenal,
        "player_equipment": t.player_equipment,
        "player_pitch_zone": t.player_pitch_zone,
        "player_soul": t.player_soul,
        "player_auras": t.player_auras,
        "player_items": t.player_items,
        "player_permanents": t.player_permanents,
        "opp_graveyard": t.opp_graveyard,
        "opp_banished": t.opp_banished,
        "opp_equipment": t.opp_equipment,
        "opp_pitch_zone": t.opp_pitch_zone,
        "opp_soul": t.opp_soul,
        "opp_auras": t.opp_auras,
        "opp_items": t.opp_items,
        "opp_permanents": t.opp_permanents,
        "player_pitch_stack": t.player_pitch_stack,
        "opp_pitch_stack": t.opp_pitch_stack,
        "deck_remainder": t.deck_remainder,
        "player_hero": t.player_hero,
        "opp_hero": t.opp_hero,
        "combat_attack_card": t.combat_attack_card,
        "combat_defending_cards": t.combat_defending_cards,
        "chain_link_history": t.chain_link_history,
        "game_progress": t.game_progress,
        "steps_to_terminal": t.steps_to_terminal,
        "next_transition_id": t.next_transition_id,
    }
    d.update(overrides)
    return Transition(**d)


def _terminal_reward(player_id: int, winner: int | None) -> float:
    if winner is None:
        return 0.0
    return 1.0 if player_id == winner else -1.0


# ── SQLite persistence ───────────────────────────────────────────────


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS decks (
    game_id         TEXT PRIMARY KEY,
    mode            TEXT NOT NULL,
    p1_deck_file    TEXT NOT NULL,
    p2_deck_file    TEXT NOT NULL,
    p1_decklist     TEXT NOT NULL,   -- JSON
    p2_decklist     TEXT NOT NULL,   -- JSON
    p1_hero         TEXT NOT NULL,
    p2_hero         TEXT NOT NULL,
    winner          INTEGER,         -- 1, 2, or NULL
    p1_won          INTEGER NOT NULL,
    p2_won          INTEGER NOT NULL,
    p1_final_hp     INTEGER NOT NULL,
    p2_final_hp     INTEGER NOT NULL,
    turn_count      INTEGER NOT NULL,
    ended_on_turn_cap INTEGER NOT NULL,
    total_actions   INTEGER NOT NULL,
    seed            INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transitions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id              TEXT NOT NULL,
    step                 INTEGER NOT NULL,
    player_id            INTEGER NOT NULL,
    turn_number          INTEGER NOT NULL,
    state                TEXT NOT NULL,           -- JSON
    available_actions    TEXT NOT NULL,           -- JSON
    action_taken         TEXT NOT NULL,           -- JSON
    action_index         INTEGER NOT NULL,
    next_state           TEXT,                    -- JSON (NULL if unavailable)
    reward               REAL NOT NULL,
    done                 INTEGER NOT NULL,
    p1_hp                INTEGER NOT NULL,
    p2_hp                INTEGER NOT NULL,
    -- decision context
    decision_type        TEXT,                    -- play_card, pitch, defend, pass, etc.
    turn_phase           TEXT,                    -- M, B, D, A, CHOOSEHANDCANCEL, etc.
    is_turn_player       INTEGER NOT NULL DEFAULT 1,
    -- reward shaping
    hp_delta             INTEGER NOT NULL DEFAULT 0,
    opp_hp_delta         INTEGER NOT NULL DEFAULT 0,
    -- action space
    num_actions          INTEGER NOT NULL DEFAULT 1,
    action_points        INTEGER,
    card_id              TEXT,                    -- card slug for the action taken
    -- combat chain
    in_combat_chain      INTEGER NOT NULL DEFAULT 0,
    combat_chain_attack  INTEGER,
    combat_chain_defense INTEGER,
    -- resource / hand info
    hand_size            INTEGER,
    opp_hand_size        INTEGER,
    cards_in_deck        INTEGER,
    opp_cards_in_deck    INTEGER,
    -- zone sizes
    resources            INTEGER,
    graveyard_size       INTEGER,
    opp_graveyard_size   INTEGER,
    banished_size        INTEGER,
    opp_banished_size    INTEGER,
    pitch_zone_size      INTEGER,
    opp_pitch_zone_size  INTEGER,
    equipment_count      INTEGER,
    opp_equipment_count  INTEGER,
    has_arsenal           INTEGER NOT NULL DEFAULT 0,
    opp_has_arsenal       INTEGER NOT NULL DEFAULT 0,
    -- combat detail
    chain_link_count     INTEGER NOT NULL DEFAULT 0,
    has_go_again         INTEGER NOT NULL DEFAULT 0,
    combat_keywords      TEXT,            -- comma-separated: dominate,overpower,...
    -- zone content (JSON arrays of card slugs)
    player_hand          TEXT,
    player_graveyard     TEXT,
    player_banished      TEXT,
    player_arsenal       TEXT,
    player_equipment     TEXT,
    player_pitch_zone    TEXT,
    player_soul          TEXT,
    player_auras         TEXT,
    player_items         TEXT,
    player_permanents    TEXT,
    opp_graveyard        TEXT,
    opp_banished         TEXT,
    opp_equipment        TEXT,
    opp_pitch_zone       TEXT,
    opp_soul             TEXT,
    opp_auras            TEXT,
    opp_items            TEXT,
    opp_permanents       TEXT,
    -- pitch stacks
    player_pitch_stack   TEXT,
    opp_pitch_stack      TEXT,
    -- deck remainder
    deck_remainder       TEXT,
    -- additional metadata
    player_hero          TEXT,
    opp_hero             TEXT,
    combat_attack_card   TEXT,
    combat_defending_cards TEXT,
    chain_link_history   TEXT,
    -- trajectory linking
    game_progress        REAL,                   -- 0.0 to 1.0
    steps_to_terminal    INTEGER,
    next_transition_id   INTEGER,                -- FK to transitions(id)
    FOREIGN KEY (game_id) REFERENCES decks(game_id)
);

CREATE INDEX IF NOT EXISTS idx_transitions_game_step
    ON transitions(game_id, step, player_id);
CREATE INDEX IF NOT EXISTS idx_transitions_done
    ON transitions(done);
CREATE INDEX IF NOT EXISTS idx_transitions_curriculum
    ON transitions(decision_type, turn_phase, game_progress);
CREATE INDEX IF NOT EXISTS idx_transitions_num_actions
    ON transitions(num_actions);
"""


class GameDataStore:
    """Thread-safe SQLite store for game data."""

    def __init__(self, db_path: str = "data/talishar_games.db"):
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._local = threading.local()
        conn = self._get_conn()
        conn.executescript(_SCHEMA_SQL)
        conn.commit()

    @classmethod
    def create_fresh(cls, base_dir: str = "data", prefix: str = "local_pipeline") -> "GameDataStore":
        """Create a new GameDataStore with a unique timestamped database path."""
        os.makedirs(base_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_path = os.path.join(base_dir, f"{prefix}_{timestamp}.db")
        return cls(db_path)

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, timeout=30)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def save_game(self, collector: TransitionCollector, meta: DeckMeta) -> None:
        """Persist one completed game (deck info + all transitions).

        Inserts all transitions, then backfills ``next_transition_id``
        so trajectory walking is a single PK lookup.
        """
        conn = self._get_conn()

        # --- decks row ---
        conn.execute(
            """INSERT OR REPLACE INTO decks
               (game_id, mode, p1_deck_file, p2_deck_file,
                p1_decklist, p2_decklist, p1_hero, p2_hero,
                winner, p1_won, p2_won,
                p1_final_hp, p2_final_hp,
                turn_count, ended_on_turn_cap, total_actions, seed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                meta.game_id, meta.mode,
                meta.p1_deck_file, meta.p2_deck_file,
                json.dumps(meta.p1_decklist, separators=(",", ":")),
                json.dumps(meta.p2_decklist, separators=(",", ":")),
                meta.p1_decklist.get("hero", ""),
                meta.p2_decklist.get("hero", ""),
                meta.winner,
                int(meta.winner == 1), int(meta.winner == 2),
                meta.p1_final_hp, meta.p2_final_hp,
                meta.turn_count, int(meta.ended_on_turn_cap),
                meta.total_actions, meta.seed,
            ),
        )

        # --- transition rows ---
        transitions = collector.transitions
        if not transitions:
            conn.commit()
            return

        _INSERT_SQL = """INSERT INTO transitions
            (game_id, step, player_id, turn_number,
             state, available_actions, action_taken, action_index,
             next_state, reward, done, p1_hp, p2_hp,
             decision_type, turn_phase, is_turn_player,
             hp_delta, opp_hp_delta,
             num_actions, action_points, card_id,
             in_combat_chain, combat_chain_attack, combat_chain_defense,
             hand_size, opp_hand_size, cards_in_deck, opp_cards_in_deck,
             resources, graveyard_size, opp_graveyard_size,
             banished_size, opp_banished_size,
             pitch_zone_size, opp_pitch_zone_size,
             equipment_count, opp_equipment_count,
             has_arsenal, opp_has_arsenal,
             chain_link_count, has_go_again, combat_keywords,
             player_hand, player_graveyard, player_banished,
             player_arsenal, player_equipment, player_pitch_zone,
             player_soul, player_auras, player_items, player_permanents,
             opp_graveyard, opp_banished, opp_equipment, opp_pitch_zone,
             opp_soul, opp_auras, opp_items, opp_permanents,
             player_pitch_stack, opp_pitch_stack, deck_remainder,
             player_hero, opp_hero,
             combat_attack_card, combat_defending_cards, chain_link_history,
             game_progress, steps_to_terminal)
            VALUES (?,?,?,?, ?,?,?,?, ?,?,?,?,?, ?,?,?, ?,?, ?,?,?, ?,?,?, ?,?,?,?,
                    ?,?,?, ?,?, ?,?, ?,?, ?,?, ?,?,?,
                    ?,?,?, ?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?,
                    ?,?,?, ?,?, ?,?,?,
                    ?,?)"""

        rows = [
            (
                t.game_id, t.step, t.player_id, t.turn_number,
                json.dumps(t.state, separators=(",", ":")),
                json.dumps(t.available_actions, separators=(",", ":")),
                json.dumps(t.action_taken, separators=(",", ":")),
                t.action_index,
                json.dumps(t.next_state, separators=(",", ":")) if t.next_state else None,
                t.reward, int(t.done), t.p1_hp, t.p2_hp,
                t.decision_type, t.turn_phase, int(t.is_turn_player),
                t.hp_delta, t.opp_hp_delta,
                t.num_actions, t.action_points, t.card_id,
                int(t.in_combat_chain), t.combat_chain_attack, t.combat_chain_defense,
                t.hand_size, t.opp_hand_size, t.cards_in_deck, t.opp_cards_in_deck,
                t.resources, t.graveyard_size, t.opp_graveyard_size,
                t.banished_size, t.opp_banished_size,
                t.pitch_zone_size, t.opp_pitch_zone_size,
                t.equipment_count, t.opp_equipment_count,
                int(t.has_arsenal), int(t.opp_has_arsenal),
                t.chain_link_count, int(t.has_go_again), t.combat_keywords,
                t.player_hand, t.player_graveyard, t.player_banished,
                t.player_arsenal, t.player_equipment, t.player_pitch_zone,
                t.player_soul, t.player_auras, t.player_items, t.player_permanents,
                t.opp_graveyard, t.opp_banished, t.opp_equipment, t.opp_pitch_zone,
                t.opp_soul, t.opp_auras, t.opp_items, t.opp_permanents,
                t.player_pitch_stack, t.opp_pitch_stack, t.deck_remainder,
                t.player_hero, t.opp_hero,
                t.combat_attack_card, t.combat_defending_cards, t.chain_link_history,
                t.game_progress, t.steps_to_terminal,
            )
            for t in transitions
        ]
        conn.executemany(_INSERT_SQL, rows)

        # --- backfill next_transition_id ---
        # Get the range of inserted rowids (executemany inserts sequentially)
        last_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        first_id = last_id - len(rows) + 1
        updates = [
            (first_id + i + 1, first_id + i)
            for i in range(len(rows) - 1)
        ]
        conn.executemany(
            "UPDATE transitions SET next_transition_id = ? WHERE id = ?",
            updates,
        )

        conn.commit()

    def record_local_game(
        self,
        collector: TransitionCollector | None,
        game_state: Any,
        p1_deck_file: str,
        p2_deck_file: str,
        seed: int | None = None,
        game_id: int | None = None,
    ) -> None:
        """Save a game played via the local engine.

        Converts the local engine's final ``GameState`` into a ``DeckMeta``
        and delegates to :meth:`save_game`.  The *game_state* object is
        expected to have ``.winner``, ``.turn_number``, and
        ``.players[1].health`` / ``.players[2].health`` attributes (matching
        ``engine.state.GameState``).

        If *collector* is ``None`` a stub collector with no transitions is
        created automatically, using *game_id* for identification.
        """
        p1 = game_state.players[1]
        p2 = game_state.players[2]

        if collector is None:
            collector = TransitionCollector(game_id=game_id or 0)

        # Build minimal decklists – the local engine doesn't expose the
        # original list in the same format as Talishar, so we store the
        # hero name and the deck file path for traceability.
        p1_decklist = {"hero": getattr(p1, "hero_name", getattr(p1, "name", ""))}
        p2_decklist = {"hero": getattr(p2, "hero_name", getattr(p2, "name", ""))}

        meta = DeckMeta(
            game_id=collector.game_id,
            p1_deck_file=p1_deck_file,
            p2_deck_file=p2_deck_file,
            p1_decklist=p1_decklist,
            p2_decklist=p2_decklist,
            winner=game_state.winner,
            p1_final_hp=p1.health,
            p2_final_hp=p2.health,
            turn_count=game_state.turn_number,
            ended_on_turn_cap=False,
            total_actions=len(collector.transitions),
            seed=seed,
            mode="local",
        )
        self.save_game(collector, meta)

    def game_count(self) -> int:
        conn = self._get_conn()
        return conn.execute("SELECT COUNT(*) FROM decks").fetchone()[0]

    def transition_count(self) -> int:
        conn = self._get_conn()
        return conn.execute("SELECT COUNT(*) FROM transitions").fetchone()[0]

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._local.conn.close()
            self._local.conn = None

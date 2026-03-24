"""Simple heuristic bot that prioritises dealing attack damage.

Used to generate higher-quality training data for IQL — random-vs-random
games have almost no strategic signal, but heuristic-vs-heuristic games
reward attacking, blocking efficiently, and pitching correctly.

Strategy:
  Main phase  → play the highest-power attack card that can be paid for
  Block phase → block with the lowest-value card (preserve strong cards)
  Otherwise   → fall back to random

The bot loads the slug_index to look up card power/defense/cost by slug.
"""
from __future__ import annotations

import json
import random
from pathlib import Path


def _safe_int(val, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


class HeuristicBot:
    """Greedy attack-first heuristic agent for Talishar games."""

    def __init__(
        self,
        slug_index_path: str = "card_data/slug_index.json",
        seed: int | None = None,
    ):
        self._rng = random.Random(seed)
        # Build slug → card stats lookup
        self._cards: dict[str, dict] = {}
        path = Path(slug_index_path)
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            by_slug = raw.get("by_slug", {})
            for slug, card in by_slug.items():
                self._cards[slug] = {
                    "power": _safe_int(card.get("power"), 0),
                    "defense": _safe_int(card.get("defense"), 0),
                    "cost": _safe_int(card.get("cost"), 0),
                    "pitch": _safe_int(card.get("pitch"), 0),
                    "types": card.get("types", []),
                }

    def _card_stats(self, slug: str) -> dict:
        return self._cards.get(slug, {"power": 0, "defense": 0, "cost": 0, "pitch": 0, "types": []})

    def _is_attack(self, slug: str) -> bool:
        stats = self._card_stats(slug)
        return "Attack" in stats["types"] and stats["power"] > 0

    def choose_talishar_action(self, state: dict, actions: list[dict], player_id: int) -> dict | None:
        if not actions:
            return None

        phase = str((state.get("turnPhase") or {}).get("turnPhase") or "").upper()

        # --- Main phase: play highest-power attack ---
        if phase == "M":
            return self._pick_main_phase(actions)

        # --- Pitch phase: pitch the lowest-value card ---
        if phase == "P":
            return self._pick_pitch_phase(actions)

        # --- Block phase: block with lowest-power card ---
        if phase == "B":
            return self._pick_block_phase(state, actions)

        # --- Everything else: fall back to random ---
        return None  # signals caller to use random fallback

    # ── Main Phase ──────────────────────────────────────────────────

    def _pick_main_phase(self, actions: list[dict]) -> dict | None:
        # Find attack cards from hand and equipment (weapon swings)
        attack_actions = []
        for a in actions:
            if a.get("type") not in ("hand", "equipment"):
                continue
            slug = a.get("cardNumber", "")
            stats = self._card_stats(slug)
            power = stats["power"]
            if power > 0:
                attack_actions.append(a)

        if attack_actions:
            # Pick the highest-power attack
            return max(attack_actions, key=lambda a: self._card_stats(a.get("cardNumber", ""))["power"])

        # No attacks available — check for non-attack hand actions (auras, etc.)
        # Fall back to random
        return None

    # ── Pitch Phase ─────────────────────────────────────────────────

    def _pick_pitch_phase(self, actions: list[dict]) -> dict | None:
        # Pitch the card with the highest pitch value (blue=3 > yellow=2 > red=1)
        # Among equal pitch, prefer pitching lowest-power cards
        pitch_actions = []
        for a in actions:
            if a.get("type") != "hand":
                continue
            pitch_actions.append(a)

        if pitch_actions:
            # Higher pitch value = better to pitch; lower power = less loss
            return max(pitch_actions, key=lambda a: (
                self._card_stats(a.get("cardNumber", ""))["pitch"],
                -self._card_stats(a.get("cardNumber", ""))["power"],
            ))

        return None

    # ── Block Phase ─────────────────────────────────────────────────

    def _pick_block_phase(self, state: dict, actions: list[dict]) -> dict | None:
        # Check if we've already committed blockers
        selected_defenders = bool((state.get("activeChainLink") or {}).get("reactions"))

        if selected_defenders:
            # Already blocking — finalize (done blocking / pass)
            finalize = [a for a in actions
                        if a.get("type") == "pass_phase"
                        or _safe_int(a.get("mode"), -1) in (99, 101)]
            if finalize:
                return self._rng.choice(finalize)
            return None

        # Pick block cards: prefer equipment first (preserves hand),
        # then hand cards with highest defense but lowest power (sacrifice weak cards)
        eq_blocks = []
        hand_blocks = []
        for a in actions:
            if a.get("type") == "equipment":
                eq_blocks.append(a)
            elif a.get("type") == "hand":
                hand_blocks.append(a)

        # Use equipment blocks first
        if eq_blocks:
            return max(eq_blocks, key=lambda a: self._card_stats(a.get("cardNumber", ""))["defense"])

        # Then hand cards: highest defense, lowest power (sacrifice weak cards)
        if hand_blocks:
            return max(hand_blocks, key=lambda a: (
                self._card_stats(a.get("cardNumber", ""))["defense"],
                -self._card_stats(a.get("cardNumber", ""))["power"],
            ))

        # No block cards — try to finalize
        finalize = [a for a in actions
                    if a.get("type") == "pass_phase"
                    or _safe_int(a.get("mode"), -1) in (99, 101)]
        if finalize:
            return self._rng.choice(finalize)

        return None

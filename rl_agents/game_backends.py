from __future__ import annotations

import argparse
import inspect
import os
import random
import html as _html
import re
import unicodedata as _unicodedata
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import json as _json

import requests

from engine.engine import new_game


def _parse_json(response: requests.Response) -> Any:
    """Parse JSON from a PHP response, stripping any HTML warning prefix."""
    body = response.text
    idx = body.find("{")
    if idx == -1:
        idx = body.find("[")
    if idx > 0:
        body = body[idx:]
    return _json.loads(body)


@dataclass(frozen=True)
class GameRunRequest:
    p1_deck: str
    p2_deck: str
    p1_agent: Any
    p2_agent: Any
    card_db: Any
    p1_seed: int
    p2_seed: int
    max_turns: int | None = None
    max_actions: int = 0


@dataclass
class TalisharGameResult:
    """Result of a Talishar-backend game run."""
    winner: int | None          # 1 or 2, or None if draw/cap
    turn_number: int
    ended_on_turn_cap: bool
    p1_final_hp: int
    p2_final_hp: int
    game_name: int
    total_actions: int


class _NullTalisharAgent:
    pass


class LocalEngineBackend:
    name = "local"

    def run_game(self, req: GameRunRequest):
        kwargs: dict[str, Any] = {
            "card_db": req.card_db,
            "p1_seed": req.p1_seed,
            "p2_seed": req.p2_seed,
        }
        if req.max_turns is not None:
            kwargs["max_turns"] = req.max_turns

        return new_game(
            req.p1_deck,
            req.p2_deck,
            req.p1_agent,
            req.p2_agent,
            **kwargs,
        )


_CARD_SLOT_DB: dict | None = None


def _get_card_slot_db() -> dict:
    """Lazy-load the slug_index card database (by_slug entries)."""
    global _CARD_SLOT_DB
    if _CARD_SLOT_DB is None:
        import pathlib
        import msgpack as _msgpack
        db_path = pathlib.Path(__file__).parent.parent / "card_data" / "slug_index.msgpack"
        with open(db_path, "rb") as _f:
            _CARD_SLOT_DB = _msgpack.unpack(_f, raw=False).get("by_slug", {})
    return _CARD_SLOT_DB


def _arena_card_slot(slug: str) -> str:
    """Return the Talishar slot for an arena card slug: head|chest|arms|legs|hands|offhand|quiver."""
    db = _get_card_slot_db()
    entry = db.get(slug)
    if entry is None:
        return "hands"  # unknown → assume weapon
    types = [t.lower() for t in entry.get("types", [])]
    if "weapon" in types:
        if "off-hand" in types or "offhand" in types:
            return "offhand"
        return "hands"
    if "equipment" in types:
        for slot in ("head", "chest", "arms", "legs"):
            if slot in types:
                return slot
        if "off-hand" in types or "offhand" in types:
            return "offhand"
        if "quiver" in types:
            return "quiver"
    return "hands"  # fallback


def _deck_file_to_talishar_slugs(deck_file: str) -> dict:
    """Parse a FAB_Sim deck text file and return a Talishar local-deck submission dict.

    The deck file format used by FAB_Sim is the Fabrary export format:
      Hero: <name>
      [Arena cards section with NxCard lines]
      [Deck cards section with NxCard (color) lines]

    This converts card names to Talishar slugs using a simple normalization
    (lowercase, replace spaces/special chars with underscores, append color).
    """
    hero_slug = ""
    equip_by_slot: dict[str, str] = {}   # head/chest/arms/legs → slug
    weapons: list[str] = []              # hands (1H weapons, can have 2)
    offhand: str = "-"
    quiver: str = "-"
    deck_cards: list[str] = []

    # Color word → Talishar suffix
    COLOR_MAP = {"red": "red", "yellow": "yellow", "blue": "blue"}

    def to_slug(name: str, color: str = "") -> str:
        slug = _html.unescape(name)          # &#x27; → '
        # Some generated decks include a trailing color tag in the card name itself
        # (e.g. "voltic_impact_yellow (yellow)"). Strip it before normalization so
        # color suffixing below stays canonical.
        slug = re.sub(r"\s*\((red|yellow|blue)\)\s*$", "", slug, flags=re.IGNORECASE)
        # Normalize unicode: decompose accented chars (í→i) and drop non-ASCII (ð dropped)
        slug = _unicodedata.normalize("NFKD", slug).encode("ascii", "ignore").decode("ascii")
        slug = slug.replace("'", "")         # Autumn's → Autumns
        slug = slug.replace("!", "")         # Smash! → Smash
        slug = re.sub(r"\s*//\s*", "SPLITCARD", slug)  # placeholder for split cards
        slug = slug.replace("/", "")         # I/O → IO
        slug = slug.lower()
        slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
        slug = slug.replace("splitcard", "__")  # Burn Up // Shock → burn_up__shock
        if color and color in COLOR_MAP:
            slug = slug + "_" + color
        return slug

    in_arena = False
    in_deck = False

    with open(deck_file, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("Made with") or line.startswith("See the full"):
                continue
            if line.startswith("Hero:"):
                hero_name = line[5:].strip()
                hero_slug = to_slug(hero_name)
                continue
            if line.lower().startswith("arena cards"):
                in_arena = True
                in_deck = False
                continue
            if line.lower().startswith("deck cards"):
                in_deck = True
                in_arena = False
                continue
            if line.startswith("Format:") or line.startswith("Name:"):
                continue

            # Parse "NxCard Name (Color)" or "NxCard Name"
            m = re.match(r'^(\d+)x\s+(.+?)(?:\s+\((\w+)\))?$', line)
            if not m:
                continue
            count = int(m.group(1))
            card_name = m.group(2).strip()
            color = (m.group(3) or "").lower()
            slug = to_slug(card_name, color)

            if in_arena:
                slot = _arena_card_slot(slug)
                for _ in range(count):
                    if slot in ("head", "chest", "arms", "legs"):
                        equip_by_slot[slot] = slug          # last write wins if dupes
                    elif slot == "offhand":
                        offhand = slug
                    elif slot == "quiver":
                        quiver = slug
                    else:  # "hands"
                        weapons.append(slug)
            elif in_deck:
                for _ in range(count):
                    deck_cards.append(slug)

    return {
        "hero": hero_slug,
        "head": equip_by_slot.get("head", "-"),
        "chest": equip_by_slot.get("chest", "-"),
        "arms": equip_by_slot.get("arms", "-"),
        "legs": equip_by_slot.get("legs", "-"),
        "hands": weapons,
        "offhand": offhand,
        "quiver": quiver,
        "deck": deck_cards,
        "inventory": [],
    }


class TalisharClient:
    """Thin Python client for a locally-running Talishar PHP server."""

    def __init__(self, base_url: str = "http://localhost:8080/game", request_timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout
        self._session = requests.Session()

    def create_game(self, deck: dict, format: str = "cc", *, deck_test_mode: bool = True) -> tuple[int, str]:
        """Create a game. Returns (game_name, auth_key) for player 1."""
        payload = {
            "deck": deck,
            "format": format,
            "visibility": "private",
        }
        if deck_test_mode:
            payload["deckTestMode"] = "1"
        r = self._session.post(
            f"{self.base_url}/APIs/CreateGame.php",
            json=payload,
            timeout=self.request_timeout,
        )
        r.raise_for_status()
        data = _parse_json(r)
        if "error" in data:
            raise RuntimeError(f"Talishar CreateGame error: {data['error']}")
        return int(data["gameName"]), data["authKey"]

    def join_game(self, game_name: int, deck: dict, player_id: int = 2) -> str:
        payload = {
            "gameName": game_name,
            "playerID": player_id,
            "deck": deck,
        }
        r = self._session.post(
            f"{self.base_url}/APIs/JoinGame.php",
            json=payload,
            timeout=self.request_timeout,
        )
        r.raise_for_status()
        data = _parse_json(r)
        if "error" in data:
            raise RuntimeError(f"Talishar JoinGame error: {data['error']}")
        return data["authKey"]

    def start_game(self, game_name: int, auth_key: str) -> bool:
        r = self._session.get(
            f"{self.base_url}/Start.php",
            params={"gameName": game_name, "playerID": 1, "authKey": auth_key},
            timeout=self.request_timeout,
        )
        r.raise_for_status()
        data = _parse_json(r)
        return bool(data.get("success"))

    def get_state(self, game_name: int, auth_key: str, player_id: int = 1) -> dict:
        r = self._session.get(
            f"{self.base_url}/GetNextTurn.php",
            params={"gameName": game_name, "playerID": player_id, "authKey": auth_key, "lastUpdate": 0},
            timeout=self.request_timeout,
        )
        r.raise_for_status()
        body = r.text
        if "Fatal error" in body or "Cannot redeclare" in body:
            raise RuntimeError(f"Talishar PHP error in GetNextTurn: {body[:400]}")
        return _parse_json(r)

    def process_input(
        self,
        game_name: int,
        auth_key: str,
        mode: str | int,
        player_id: int = 1,
        card_id: str = "",
        button_input: str = "",
        input_text: str = "",
    ) -> None:
        params: dict = {"gameName": game_name, "playerID": player_id, "authKey": auth_key, "mode": mode}
        if card_id:
            params["cardID"] = card_id
        if button_input:
            params["buttonInput"] = button_input
        if input_text:
            params["inputText"] = input_text
        r = self._session.get(
            f"{self.base_url}/ProcessInput.php",
            params=params,
            timeout=self.request_timeout,
        )
        r.raise_for_status()

    def is_game_over(self, state: dict) -> tuple[bool, int | None]:
        """Returns (game_over, winner). winner is 1 or 2, or None for draw."""
        p1_hp = int(state.get("playerHealth", 1))
        p2_hp = int(state.get("opponentHealth", 1))
        if p1_hp <= 0 and p2_hp <= 0:
            return True, None
        if p1_hp <= 0:
            return True, 2
        if p2_hp <= 0:
            return True, 1
        # Check for game-over button/prompt
        prompt = state.get("playerPrompt", {})
        if isinstance(prompt, dict):
            text = (prompt.get("helpText") or "").lower()
            if "wins" in text or "game over" in text:
                return True, None
        return False, None

    def get_available_actions(self, state: dict) -> list[dict]:
        """Collect all legal actions from the current state."""
        actions = []

        # Hand cards
        for card in state.get("playerHand", []):
            if isinstance(card, dict) and card.get("action") is not None:
                mode = card["action"]
                override = card.get("actionDataOverride", "0")
                if mode != 0:  # 0 = not playable
                    actions.append({"type": "hand", "mode": mode, "cardID": str(override),
                                    "cardNumber": card.get("cardNumber", "")})

        # Equipment activations
        for eq in state.get("playerEquipment", []):
            if isinstance(eq, dict):
                for act in eq.get("actions", []):
                    if isinstance(act, dict):
                        actions.append({"type": "equipment", "mode": act.get("mode"),
                                        "cardID": str(act.get("cardID", "")),
                                        "cardNumber": eq.get("cardNumber", "")})

        # Other zone card selections — discard, arsenal, banish, soul, auras, items,
        # permanents, pitch cards, and top-of-deck.  These zones expose cards with
        # action != 0 when the game is in a CHOOSE* phase for that zone.
        _ZONE_FIELDS = (
            ("playerDiscard",    "discard"),
            ("playerArse",       "arsenal"),   # note: Talishar key is playerArse
            ("playerBanish",     "banish"),
            ("playerSoul",       "soul"),
            ("playerAuras",      "aura"),
            ("playerItems",      "item"),
            ("playerPermanents", "permanent"),
            ("playerPitch",      "pitch"),
            ("playerDeck",       "deck"),
            ("playerDeckCard",   "deck"),  # single top-of-deck card (different key)
        )
        for zone_key, zone_type in _ZONE_FIELDS:
            raw = state.get(zone_key)
            if not raw:
                continue
            # playerDeckCard is a single dict, others are lists
            zone_cards = [raw] if isinstance(raw, dict) else raw
            for card in zone_cards:
                if not isinstance(card, dict):
                    continue
                mode = card.get("action") or 0
                if mode == 0:
                    continue
                override = card.get("actionDataOverride") or card.get("cardID") or card.get("cardNumber", "")
                actions.append({
                    "type": zone_type,
                    "mode": mode,
                    "cardID": str(override),
                    "cardNumber": card.get("cardNumber", ""),
                })

        # Popup cardsArray — for CHOOSEZONE, PITCH, and similar popups where selectable
        # cards are placed inside the popup's cardsArray rather than in a zone.
        pip_for_cards = state.get("playerInputPopUp") or {}
        if isinstance(pip_for_cards, dict) and pip_for_cards.get("active"):
            popup_for_cards = pip_for_cards.get("popup") or {}
            popup_id_for_cards = (popup_for_cards.get("id") or "").upper()
            # Only scrape popup cardsArray for popups that aren't slider-based
            if popup_id_for_cards not in ("NEWOPT", "TRIGGERORDER"):
                for card in (popup_for_cards.get("cards") or []):
                    if not isinstance(card, dict):
                        continue
                    mode = card.get("action") or 0
                    if mode == 0:
                        continue
                    override = card.get("actionDataOverride") or card.get("cardID") or card.get("cardNumber", "")
                    actions.append({
                        "type": "popup_card",
                        "mode": mode,
                        "cardID": str(override),
                        "cardNumber": card.get("cardNumber", ""),
                    })

        # Button actions from popup — also handle OPT/TRIGGERORDER slider popups
        pip = state.get("playerInputPopUp", {})
        if isinstance(pip, dict) and pip.get("active"):
            popup = pip.get("popup") or {}
            popup_id = (popup.get("id") or "").upper()

            if popup_id == "NEWOPT":
                # Drag-to-top/bottom slider: no buttons. Emit a synthetic opt action
                # carrying the current card lists so the agent can submit mode 107.
                top_cards = [c.get("cardID", c.get("cardNumber", "")) for c in (popup.get("topCards") or []) if isinstance(c, dict)]
                bottom_cards = [c.get("cardID", c.get("cardNumber", "")) for c in (popup.get("bottomCards") or []) if isinstance(c, dict)]
                actions.append({
                    "type": "opt",
                    "mode": 107,
                    "cardListTop": top_cards,
                    "cardListBottom": bottom_cards,
                    "cardID": "",
                })
            elif popup_id == "TRIGGERORDER":
                # Trigger reorder slider: emit a synthetic trigger_order action.
                ordered_cards = [c.get("cardID", c.get("cardNumber", "")) for c in (popup.get("topCards") or []) if isinstance(c, dict)]
                actions.append({
                    "type": "trigger_order",
                    "mode": 109,
                    "cardListTop": ordered_cards,
                    "cardID": "",
                })
            elif popup_id == "INPUTCARDNAME":
                # Free-text card name prompt (e.g. Chains of Eminence, Censor, Null Time Zone).
                # Submit mode 30 with a fixed card name — same as EncounterAI.php.
                actions.append({
                    "type": "input_card_name",
                    "mode": 30,
                    "cardID": "",
                    "input_text": "Crouching Tiger",
                })
            else:
                for btn in pip.get("buttons", []):
                    if isinstance(btn, dict):
                        actions.append({"type": "button", "mode": btn.get("mode", ""),
                                        "buttonInput": str(btn.get("buttonInput", "")),
                                        "cardID": str(btn.get("cardID", ""))})

        # Prompt buttons
        prompt = state.get("playerPrompt", {})
        if isinstance(prompt, dict):
            for btn in prompt.get("buttons", []):
                if isinstance(btn, dict):
                    actions.append({"type": "prompt_button", "mode": btn.get("mode", ""),
                                    "buttonInput": str(btn.get("buttonInput", "")),
                                    "cardID": str(btn.get("cardID", ""))})

        # Pass phase / end turn (mode 99 in Talishar)
        if state.get("canPassPhase") and state.get("havePriority"):
            actions.append({"type": "pass_phase", "mode": 99, "cardID": ""})

        return actions

    def submit_action(self, game_name: int, auth_key: str, action: dict, player_id: int = 1) -> None:
        atype = action["type"]
        mode = action["mode"]
        card_id = action.get("cardID", "")
        if atype in ("hand", "equipment"):
            self.process_input(game_name, auth_key, mode, player_id=player_id, card_id=card_id)
        elif atype in ("button", "prompt_button"):
            self.process_input(game_name, auth_key, mode,
                               player_id=player_id,
                               button_input=action.get("buttonInput", ""),
                               card_id=card_id)
        elif atype == "input_card_name":
            self.process_input(game_name, auth_key, mode, player_id=player_id,
                               input_text=action.get("input_text", "Crouching Tiger"))
        elif atype == "pass_phase":
            self.process_input(game_name, auth_key, 99, player_id=player_id)
        else:
            self.process_input(game_name, auth_key, mode, player_id=player_id, card_id=card_id)

    def process_input_fused(
        self,
        game_name: int,
        auth_key: str,
        mode: str | int,
        player_id: int = 1,
        card_id: str = "",
        button_input: str = "",
        input_text: str = "",
    ) -> dict | None:
        """Send an action AND return the new game state in one HTTP round-trip.

        Requires the patched ProcessInput.php that honours ``returnState=1``.
        Falls back to ``None`` when the server doesn't return JSON (unpatched PHP).
        """
        params: dict = {
            "gameName": game_name,
            "playerID": player_id,
            "authKey": auth_key,
            "mode": mode,
            "returnState": "1",
        }
        if card_id:
            params["cardID"] = card_id
        if button_input:
            params["buttonInput"] = button_input
        if input_text:
            params["inputText"] = input_text
        r = self._session.get(
            f"{self.base_url}/ProcessInput.php",
            params=params,
            timeout=self.request_timeout,
        )
        r.raise_for_status()
        body = r.text.strip()
        idx = body.find("{")
        if idx == -1:
            return None  # unpatched server — caller should fall back to get_state
        try:
            return _parse_json(r)
        except Exception:
            return None

    def submit_opt(
        self,
        game_name: int,
        auth_key: str,
        player_id: int,
        card_list_top: list[str],
        card_list_bottom: list[str],
        mode: int = 107,
    ) -> dict | None:
        """Submit an OPT (order/place top/bottom) decision.

        Talishar modes:
          106 = update OPT order preview (intermediate drag step — can skip)
          107 = submit final OPT decision

        POSTs JSON so the server can read submission->cardListTop / cardListBottom.
        """
        payload = {
            "gameName": game_name,
            "playerID": player_id,
            "authKey": auth_key,
            "mode": mode,
            "returnState": "1",
            "submission": {
                "cardListTop": card_list_top,
                "cardListBottom": card_list_bottom,
            },
        }
        r = self._session.post(
            f"{self.base_url}/ProcessInputAPI.php",
            json=payload,
            timeout=self.request_timeout,
        )
        r.raise_for_status()
        body = r.text.strip()
        if "{" not in body:
            return None
        try:
            return _parse_json(r)
        except Exception:
            return None

    def submit_trigger_order(
        self,
        game_name: int,
        auth_key: str,
        player_id: int,
        card_list: list[str],
    ) -> dict | None:
        """Submit a TRIGGERORDER (reorder trigger stack) decision — mode 109."""
        payload = {
            "gameName": game_name,
            "playerID": player_id,
            "authKey": auth_key,
            "mode": 109,
            "returnState": "1",
            "submission": {
                "cardListTop": card_list,
            },
        }
        r = self._session.post(
            f"{self.base_url}/ProcessInputAPI.php",
            json=payload,
            timeout=self.request_timeout,
        )
        r.raise_for_status()
        body = r.text.strip()
        if "{" not in body:
            return None
        try:
            return _parse_json(r)
        except Exception:
            return None

    def submit_action_fused(self, game_name: int, auth_key: str, action: dict, player_id: int = 1) -> dict | None:
        """submit_action + get_state in a single HTTP call.  Returns the new state dict, or None on fallback."""
        atype = action["type"]
        mode = action["mode"]
        card_id = action.get("cardID", "")
        if atype == "opt":
            return self.submit_opt(
                game_name, auth_key, player_id,
                card_list_top=action.get("cardListTop", []),
                card_list_bottom=action.get("cardListBottom", []),
            )
        elif atype == "trigger_order":
            return self.submit_trigger_order(
                game_name, auth_key, player_id,
                card_list=action.get("cardListTop", []),
            )
        elif atype in ("hand", "equipment"):
            return self.process_input_fused(game_name, auth_key, mode, player_id=player_id, card_id=card_id)
        elif atype in ("button", "prompt_button"):
            return self.process_input_fused(
                game_name, auth_key, mode,
                player_id=player_id,
                button_input=action.get("buttonInput", ""),
                card_id=card_id,
            )
        elif atype == "input_card_name":
            return self.process_input_fused(game_name, auth_key, mode, player_id=player_id,
                                            input_text=action.get("input_text", "Crouching Tiger"))
        elif atype == "pass_phase":
            return self.process_input_fused(game_name, auth_key, 99, player_id=player_id)
        else:
            return self.process_input_fused(game_name, auth_key, mode, player_id=player_id, card_id=card_id)

    def parallel_get_states(
        self,
        game_name: int,
        auth_keys: dict[int, str],
        player_ids: tuple[int, ...] = (1, 2),
    ) -> dict[int, dict]:
        """Fetch game states for multiple players in parallel."""
        with ThreadPoolExecutor(max_workers=len(player_ids)) as ex:
            futures: dict[int, Future] = {
                pid: ex.submit(self.get_state, game_name, auth_keys[pid], pid)
                for pid in player_ids
            }
            return {pid: f.result() for pid, f in futures.items()}


class TalisharIQLAgent:
    """Wraps a trained IQL checkpoint for use as a Talishar game agent.

    Converts Talishar JSON state/actions to engine format via talishar_adapter,
    runs the IQL actor to pick the best action, then returns the corresponding
    Talishar action dict.  Falls back to random on any conversion error.
    """

    def __init__(
        self,
        checkpoint_path: str,
        bundle_path: str,
        card_db_path: str,
        player_id: int = 1,
        device: str = "cpu",
        seed: int = 42,
    ):
        """Load a trained IQL checkpoint as a Talishar game agent.

        bundle_path may be:
          - A separate embedder_bundle.pt file, OR
          - The same as checkpoint_path if the bundle is embedded in the
            checkpoint's extra["embedder_bundle"] field.

        The bundle dict (with keys action_embedder_state_dict, etc.) is
        extracted correctly in both cases.
        """
        import torch as _torch
        from rl_agents.evaluate_iql_vs_random import IQLPolicyAgent
        from engine.card import CardDB as _CardDB

        self._rng = random.Random(seed)
        self._device = device
        self._seed = seed
        self._checkpoint_path = checkpoint_path
        self._card_db = _CardDB(card_db_path)

        # Load the bundle — handle both a standalone bundle file and a
        # bundle embedded inside the checkpoint's extra dict.
        raw = _torch.load(bundle_path, map_location="cpu", weights_only=False)
        if "action_embedder_state_dict" in raw:
            # Standalone bundle file
            bundle = raw
        elif isinstance(raw.get("extra"), dict) and raw["extra"].get("embedder_bundle"):
            # Bundle embedded in checkpoint
            bundle = raw["extra"]["embedder_bundle"]
        else:
            raise ValueError(
                f"Could not find embedder bundle in {bundle_path}. "
                "Pass --iql-bundle pointing to the embedder_bundle.pt file."
            )

        self._bundle = bundle
        # Build a per-player-id agent cache so seat-2 games use correct perspective
        self._agents: dict[int, IQLPolicyAgent] = {}
        self._IQLPolicyAgent = IQLPolicyAgent

    def _get_agent(self, player_id: int):
        """Return (or create) an IQLPolicyAgent for the given player perspective."""
        if player_id not in self._agents:
            self._agents[player_id] = self._IQLPolicyAgent(
                checkpoint_path=self._checkpoint_path,
                player_id=player_id,
                device=self._device,
                seed=self._seed,
                embedder_bundle=self._bundle,
            )
        return self._agents[player_id]

    def choose_talishar_action(self, state: dict, actions: list[dict], player_id: int) -> dict | None:
        """Select an action using the trained IQL actor.

        Returns a Talishar action dict, or None to fall back to random.

        The positional correspondence between *actions* (from get_available_actions)
        and engine_actions (from talishar_actions_to_engine_actions) is preserved
        because both iterate the same state fields in the same order.  On count
        mismatch we fall back to random rather than risking mis-mapping.
        """
        try:
            from rl_agents.talishar_adapter import (
                talishar_state_to_observed_game_state,
                talishar_actions_to_engine_actions,
            )
            engine_state = talishar_state_to_observed_game_state(
                state, player_id=player_id, card_db=self._card_db,
            )
            engine_actions = talishar_actions_to_engine_actions(
                state, card_db=self._card_db, player_id=player_id,
            )
            if not engine_actions:
                return None
            # Positional correspondence: fall back if counts diverge
            if len(engine_actions) != len(actions):
                return None

            agent = self._get_agent(player_id)
            chosen_engine = agent(engine_state, engine_actions)
            try:
                idx = engine_actions.index(chosen_engine)
            except ValueError:
                return None
            if 0 <= idx < len(actions):
                return actions[idx]
        except Exception:
            pass
        return None


def _call_talishar_agent_selector(agent: Any, state: dict, actions: list[dict], player_id: int):
    if agent is None or isinstance(agent, _NullTalisharAgent):
        return None

    selector = None
    for name in ("choose_talishar_action", "select_talishar_action", "act_talishar"):
        maybe = getattr(agent, name, None)
        if callable(maybe):
            selector = maybe
            break

    if selector is None:
        return None

    params = list(inspect.signature(selector).parameters)
    if len(params) >= 3:
        return selector(state, actions, player_id)
    if len(params) == 2:
        return selector(state, actions)
    if len(params) == 1:
        return selector(actions)
    return selector()


from rl_agents.utils.card_helpers import safe_int as _safe_int


def _is_talishar_pass_action(action: dict) -> bool:
    action_type = str(action.get("type") or "")
    mode = _safe_int(action.get("mode"), default=-1)

    if action_type == "pass_phase":
        return True

    if action_type in ("button", "prompt_button") and mode in (99, 101):
        return True

    caption = str(action.get("caption") or "").strip().lower()
    if action_type in ("button", "prompt_button") and caption.startswith("pass"):
        return True

    return False


def _auto_pass_when_only_option(actions: list[dict]) -> dict | None:
    if len(actions) != 1:
        return None
    action = actions[0]
    if _is_talishar_pass_action(action):
        return action
    return None


def _state_changed(before: dict, after: dict) -> bool:
    """Return True if the game state meaningfully changed between two snapshots.

    When Talishar silently rejects an action (e.g. IsPlayable fails on
    re-check in ProcessInput), the returned state is identical to the
    previous one.  We use a broad set of checks including a full-state
    hash to catch hero-specific counters (Kassai gold, Levia shadow, etc.)
    that aren't reflected in standard fields.
    """
    _KEYS = (
        "turnNo", "playerHealth", "opponentHealth",
        "lastPlayed", "lastUpdate", "playerAP",
        "havePriority", "canPassPhase",
    )
    for k in _KEYS:
        if before.get(k) != after.get(k):
            return True
    # Compare hand size — a played/pitched card changes this
    bh = before.get("playerHand")
    ah = after.get("playerHand")
    if isinstance(bh, list) and isinstance(ah, list) and len(bh) != len(ah):
        return True
    # Compare prompt text — many state transitions change the prompt
    bp = before.get("playerPrompt")
    ap = after.get("playerPrompt")
    if bp != ap:
        return True
    # Full-state hash as fallback — catches hero-specific counter updates
    # (gold, arrows, shadow counters, etc.) not tracked in standard fields
    import json as _j
    if _j.dumps(before, sort_keys=True) != _j.dumps(after, sort_keys=True):
        return True
    return False


def _pick_talishar_random_fallback_action(state: dict, actions: list[dict], rng: random.Random) -> dict:
    """Pick a reasonable random action when no Talishar-specific agent selector is provided.

    In defend step, avoid random prompt-button picks that can clear selected defenders,
    and prefer selecting defending cards first before finalizing defense.

    Mandatory popup decisions (top/bottom of deck, clash results, modal choices) are
    always answered immediately — the popup must be resolved before anything else.
    """
    forced_pass = _auto_pass_when_only_option(actions)
    if forced_pass is not None:
        return forced_pass

    # --- Mandatory popup: must be answered before any other action ---
    # playerInputPopUp being active means the game is waiting for a forced decision
    # (e.g. "put this card on top or bottom of your deck" after clash/OPT).
    pip = state.get("playerInputPopUp") or {}
    if pip.get("active"):
        # OPT slider — submit cards randomly split between top and bottom
        opt_actions = [a for a in actions if a.get("type") == "opt"]
        if opt_actions:
            opt = opt_actions[0]
            all_cards = opt.get("cardListTop", []) + opt.get("cardListBottom", [])
            if all_cards:
                rng.shuffle(all_cards)
                mid = rng.randint(0, len(all_cards))
                return {**opt, "cardListTop": all_cards[:mid], "cardListBottom": all_cards[mid:]}
            return opt

        # Trigger reorder slider — submit current order as-is (arbitrary choice)
        trig_actions = [a for a in actions if a.get("type") == "trigger_order"]
        if trig_actions:
            return trig_actions[0]

        # Card name input popup — single synthetic action, submit immediately
        name_actions = [a for a in actions if a.get("type") == "input_card_name"]
        if name_actions:
            return name_actions[0]

        # Standard button popup
        popup_actions = [a for a in actions if a.get("type") == "button"]
        if popup_actions:
            return rng.choice(popup_actions)

    phase_code = str((state.get("turnPhase") or {}).get("turnPhase") or "").upper()
    if phase_code != "B":
        return rng.choice(actions)

    hand_or_eq_idxs = [
        i for i, a in enumerate(actions)
        if a.get("type") in ("hand", "equipment")
    ]
    prompt_idxs = [
        i for i, a in enumerate(actions)
        if a.get("type") in ("button", "prompt_button", "pass_phase")
    ]

    finalize_idxs = []
    undo_idxs = []
    for i in prompt_idxs:
        action = actions[i]
        mode = _safe_int(action.get("mode"), default=-1)
        if mode in (99, 101) or action.get("type") == "pass_phase":
            finalize_idxs.append(i)
        if mode == 10001:
            undo_idxs.append(i)

    selected_defenders = bool((state.get("activeChainLink") or {}).get("reactions"))

    if selected_defenders:
        safe_finalize = [i for i in finalize_idxs if i not in undo_idxs]
        if safe_finalize:
            return actions[rng.choice(safe_finalize)]
        if finalize_idxs:
            return actions[rng.choice(finalize_idxs)]
        if prompt_idxs:
            return actions[rng.choice(prompt_idxs)]
        return rng.choice(actions)

    if hand_or_eq_idxs:
        return actions[rng.choice(hand_or_eq_idxs)]

    safe_finalize = [i for i in finalize_idxs if i not in undo_idxs]
    if safe_finalize:
        return actions[rng.choice(safe_finalize)]
    if finalize_idxs:
        return actions[rng.choice(finalize_idxs)]

    return rng.choice(actions)


def _pick_talishar_action(agent: Any, state: dict, actions: list[dict], rng: random.Random, player_id: int) -> dict:
    forced_pass = _auto_pass_when_only_option(actions)
    if forced_pass is not None:
        return forced_pass

    selected = _call_talishar_agent_selector(agent, state, actions, player_id)
    if isinstance(selected, dict):
        return selected
    if isinstance(selected, int) and 0 <= selected < len(actions):
        return actions[selected]
    return _pick_talishar_random_fallback_action(state, actions, rng)


def _run_talishar_random_game(
    client: TalisharClient,
    p1_deck_submission: dict,
    max_turns: int = 200,
    rng: random.Random | None = None,
    verbose: bool = False,
    collector: Any | None = None,
    cancel_token: Any | None = None,
) -> TalisharGameResult:
    """Run one game vs Practice Dummy using random action selection.

    Optimised: uses fused ProcessInput+GetState calls (1 HTTP round-trip per
    action instead of 2) when the server supports ``returnState=1``.
    """
    rng = rng or random.Random()

    game_name, auth_key = client.create_game(p1_deck_submission, deck_test_mode=True)
    if not client.start_game(game_name, auth_key):
        raise RuntimeError("Talishar Start.php failed")

    if verbose:
        print(f"  [talishar] Game {game_name} started")

    total_actions = 0
    turn_num = 0
    stall_count = 0
    no_act_stall = 0
    no_act_force_passes = 0
    consecutive_rejections = 0
    MAX_STALL = 50
    action_limit = max_turns * 20
    t_start = time.time()
    wall_timeout = max(action_limit * 0.5, 300)
    # OPT-loop detection
    last_turn_change_action = 0
    last_known_turn = 0
    MAX_ACTIONS_PER_TURN = 300

    # Initial state fetch (only time we call get_state without a preceding action)
    state = client.get_state(game_name, auth_key, player_id=1)

    for _iter in range(action_limit * 3):
        if cancel_token is not None and getattr(cancel_token, 'cancelled', False):
            break
        if time.time() - t_start > wall_timeout:
            break

        turn_num = int(state.get("turnNo", 0))
        p1_hp = int(state.get("playerHealth", 1))
        p2_hp = int(state.get("opponentHealth", 1))

        # OPT-loop detection
        if turn_num != last_known_turn:
            last_known_turn = turn_num
            last_turn_change_action = total_actions
        elif total_actions - last_turn_change_action > MAX_ACTIONS_PER_TURN:
            break

        over, winner = client.is_game_over(state)
        if over:
            return TalisharGameResult(
                winner=winner, turn_number=turn_num, ended_on_turn_cap=False,
                p1_final_hp=p1_hp, p2_final_hp=p2_hp,
                game_name=game_name, total_actions=total_actions,
            )

        if turn_num >= max_turns:
            cap_winner = 1 if p1_hp > p2_hp else 2 if p2_hp > p1_hp else None
            return TalisharGameResult(
                winner=cap_winner, turn_number=turn_num, ended_on_turn_cap=True,
                p1_final_hp=p1_hp, p2_final_hp=p2_hp,
                game_name=game_name, total_actions=total_actions,
            )

        if not state.get("havePriority"):
            time.sleep(0.005)
            stall_count += 1
            if stall_count >= MAX_STALL:
                break
            state = client.get_state(game_name, auth_key, player_id=1)
            continue
        stall_count = 0

        actions = client.get_available_actions(state)
        if not actions:
            if state.get("canPassPhase"):
                new_state = client.process_input_fused(game_name, auth_key, 99, player_id=1)
                state = new_state if new_state else client.get_state(game_name, auth_key, player_id=1)
                total_actions += 1
                if total_actions >= action_limit:
                    break
            else:
                no_act_stall += 1
                if no_act_stall >= MAX_STALL:
                    client.process_input_fused(game_name, auth_key, 99, player_id=1)
                    no_act_stall = 0
                    no_act_force_passes += 1
                    if no_act_force_passes >= 5:
                        break
                time.sleep(0.005)
                state = client.get_state(game_name, auth_key, player_id=1)
            continue

        no_act_stall = 0

        # --- Pick and validate action (retry on silent rejection) ---
        valid_actions = list(actions)
        pre_state = state
        accepted = False
        while valid_actions:
            forced_pass = _auto_pass_when_only_option(valid_actions)
            action = forced_pass if forced_pass is not None else _pick_talishar_action(
                _NullTalisharAgent(), state, valid_actions, rng, player_id=1,
            )
            new_state = client.submit_action_fused(game_name, auth_key, action, player_id=1)
            post = new_state if new_state else client.get_state(game_name, auth_key, player_id=1)
            # Button/prompt_button actions are mandatory popup choices (top/bottom, modal,
            # clash result). The game may wait for the other player before updating this
            # player's visible state, so always accept them rather than misidentifying
            # them as silently rejected.
            is_mandatory = action.get("type") in ("button", "prompt_button", "opt", "trigger_order", "input_card_name")
            if is_mandatory or _state_changed(pre_state, post):
                state = post
                accepted = True
                consecutive_rejections = 0
                break
            # Talishar silently rejected this action — remove and retry
            valid_actions = [a for a in valid_actions if a is not action]
            if not valid_actions:
                state = post
                break

        if not accepted:
            consecutive_rejections += 1
            if consecutive_rejections >= 10:
                # Stuck — force-pass to try to advance the game
                client.process_input_fused(game_name, auth_key, 99, player_id=1)
                consecutive_rejections = 0

        total_actions += 1
        if total_actions >= action_limit:
            break

        if accepted and collector is not None:
            collector.record(
                player_id=1, turn_number=turn_num,
                state=pre_state, available_actions=valid_actions,
                action_taken=action, next_state=state,
                p1_hp=p1_hp, p2_hp=int(state.get("opponentHealth", 0)),
            )

        if verbose and total_actions % 20 == 0:
            print(f"    action #{total_actions} turn={turn_num} hp={p1_hp}/{p2_hp}")

    return TalisharGameResult(
        winner=None, turn_number=turn_num, ended_on_turn_cap=True,
        p1_final_hp=int(state.get("playerHealth", 0)),
        p2_final_hp=int(state.get("opponentHealth", 0)),
        game_name=game_name, total_actions=total_actions,
    )


def _run_talishar_pvp_game(
    client: TalisharClient,
    p1_deck_submission: dict,
    p2_deck_submission: dict,
    *,
    p1_agent: Any = None,
    p2_agent: Any = None,
    p1_seed: int | None = None,
    p2_seed: int | None = None,
    max_turns: int = 200,
    max_actions: int = 0,
    verbose: bool = False,
    collector: Any | None = None,
    cancel_token: Any | None = None,
) -> TalisharGameResult:
    """Run one Talishar PvP game with both seats controlled by local callers.

    Optimised vs the naive 3-HTTP-per-action loop:
      * **Fused submit**: ProcessInput.php returns the new state in the same
        response (``returnState=1``), cutting submit+get_state to 1 call.
      * **Lazy P2 fetch**: only fetches P2's state when P1 doesn't have priority.
      * **Parallel fetches**: when both states are needed, fetches them in parallel.
      * **Reduced stall sleep**: 5 ms instead of 50 ms.
    """
    p1_rng = random.Random(p1_seed)
    p2_rng = random.Random(p2_seed)

    game_name, p1_auth = client.create_game(p1_deck_submission, deck_test_mode=False)
    p2_auth = client.join_game(game_name, p2_deck_submission, player_id=2)
    if not client.start_game(game_name, p1_auth):
        raise RuntimeError("Talishar Start.php failed")

    if verbose:
        print(f"  [talishar-pvp] Game {game_name} started")

    auth_keys = {1: p1_auth, 2: p2_auth}
    rngs = {1: p1_rng, 2: p2_rng}
    agents = {1: p1_agent, 2: p2_agent}

    total_actions = 0
    turn_num = 0
    stall_count = 0
    max_stall = 1000
    no_act_stall = 0       # separate counter for "has priority but no actions, can't pass"
    no_act_force_passes = 0  # how many times we've force-passed to try to unblock
    consecutive_rejections = 0
    max_consecutive_rejections = 10  # bail after 10 rounds of all-actions-rejected
    action_limit = max_actions if max_actions > 0 else max_turns * 60
    iteration_limit = action_limit * 3  # generous cap to prevent infinite loops
    t_start = time.time()
    wall_timeout = max(action_limit * 0.5, 300)  # wall-clock safety net
    # OPT-loop detection: if turn doesn't advance in 300 actions, we're in a trigger loop
    last_turn_change_action = 0
    last_known_turn = 0
    MAX_ACTIONS_PER_TURN = 300

    # --- Initial state fetch (parallel) ---
    states = client.parallel_get_states(game_name, auth_keys, (1, 2))
    state1, state2 = states[1], states[2]

    for _iter in range(iteration_limit):
        # Check cancellation token (set when external timeout fires)
        if cancel_token is not None and getattr(cancel_token, 'cancelled', False):
            break

        # Wall-clock safety net
        if time.time() - t_start > wall_timeout:
            break

        turn_num = int(state1.get("turnNo", 0))
        p1_hp = int(state1.get("playerHealth", 1))
        p2_hp = int(state1.get("opponentHealth", 1))

        # OPT-loop detection: break out if turn hasn't advanced in too many actions
        if turn_num != last_known_turn:
            last_known_turn = turn_num
            last_turn_change_action = total_actions
        elif total_actions - last_turn_change_action > MAX_ACTIONS_PER_TURN:
            break  # stuck in a trigger loop (e.g. repeated OPT/ORDERTRIGGERS)

        over, winner = client.is_game_over(state1)
        if over:
            return TalisharGameResult(
                winner=winner, turn_number=turn_num, ended_on_turn_cap=False,
                p1_final_hp=p1_hp, p2_final_hp=p2_hp,
                game_name=game_name, total_actions=total_actions,
            )

        if turn_num >= max_turns:
            cap_winner = 1 if p1_hp > p2_hp else 2 if p2_hp > p1_hp else None
            return TalisharGameResult(
                winner=cap_winner, turn_number=turn_num, ended_on_turn_cap=True,
                p1_final_hp=p1_hp, p2_final_hp=p2_hp,
                game_name=game_name, total_actions=total_actions,
            )

        # --- Determine who acts ---
        if state1.get("havePriority"):
            actor_id = 1
            actor_state = state1
        elif state2.get("havePriority"):
            actor_id = 2
            actor_state = state2
        else:
            # Neither player has priority — stall, then re-fetch both in parallel
            stall_count += 1
            if stall_count >= max_stall:
                break
            time.sleep(0.005)
            states = client.parallel_get_states(game_name, auth_keys, (1, 2))
            state1, state2 = states[1], states[2]
            continue

        stall_count = 0
        actor_auth = auth_keys[actor_id]
        actor_rng = rngs[actor_id]
        actor_agent = agents[actor_id]

        # --- Pick action ---
        actions = client.get_available_actions(actor_state)
        if not actions:
            if actor_state.get("canPassPhase"):
                new_state = client.process_input_fused(game_name, actor_auth, 99, player_id=actor_id)
                if new_state:
                    if actor_id == 1:
                        state1 = new_state
                    else:
                        state2 = new_state
                    # If priority switched, lazy-fetch the other player
                    if not new_state.get("havePriority"):
                        other_id = 3 - actor_id
                        other_state = client.get_state(game_name, auth_keys[other_id], other_id)
                        if other_id == 1:
                            state1 = other_state
                        else:
                            state2 = other_state
                else:
                    # Fallback: server doesn't support fused — fetch both
                    states = client.parallel_get_states(game_name, auth_keys, (1, 2))
                    state1, state2 = states[1], states[2]
                total_actions += 1
                if total_actions >= action_limit:
                    break
            else:
                # Player has priority but no actions available and can't pass —
                # use a dedicated counter that doesn't reset when a player has priority.
                no_act_stall += 1
                if no_act_stall >= max_stall:
                    # Force-pass as a last resort to try to unblock the game
                    client.process_input_fused(game_name, actor_auth, 99, player_id=actor_id)
                    no_act_stall = 0
                    no_act_force_passes += 1
                    if no_act_force_passes >= 5:
                        break  # truly stuck — abort the game
                time.sleep(0.005)
                states = client.parallel_get_states(game_name, auth_keys, (1, 2))
                state1, state2 = states[1], states[2]
            continue

        no_act_stall = 0  # reset when we have real actions to pick from

        # --- Pick and validate action (retry on silent rejection) ---
        valid_actions = list(actions)
        pre_state = actor_state
        accepted = False
        while valid_actions:
            forced_pass = _auto_pass_when_only_option(valid_actions)
            action = forced_pass if forced_pass is not None else _pick_talishar_action(
                actor_agent, actor_state, valid_actions, actor_rng, actor_id,
            )
            new_state = client.submit_action_fused(game_name, actor_auth, action, player_id=actor_id)
            post = new_state if new_state else client.get_state(game_name, auth_keys[actor_id], actor_id)
            # Button/prompt_button = mandatory popup choice (top/bottom, clash result, modal).
            # Always accept: the other player may not have chosen yet so this player's
            # visible state may not change until both sides resolve.
            is_mandatory = action.get("type") in ("button", "prompt_button", "opt", "trigger_order", "input_card_name")
            if is_mandatory or _state_changed(pre_state, post):
                accepted = True
                consecutive_rejections = 0
                no_act_stall = 0
                no_act_force_passes = 0
                break
            # Talishar silently rejected — remove and retry
            valid_actions = [a for a in valid_actions if a is not action]
            if not valid_actions:
                break

        if not accepted:
            consecutive_rejections += 1
            if consecutive_rejections >= max_consecutive_rejections:
                # Stuck in a rejection loop — force-pass to try to advance
                client.process_input_fused(game_name, actor_auth, 99, player_id=actor_id)
                consecutive_rejections = 0
                # If still stuck after force-pass attempts, bail out
                if _iter > 0 and total_actions > 0 and consecutive_rejections == 0:
                    pass  # reset worked, keep going

        total_actions += 1
        if total_actions >= action_limit:
            break

        # Update states from the accepted (or last-tried) result
        new_state = post if accepted else None
        if new_state:
            if actor_id == 1:
                state1 = new_state
            else:
                state2 = new_state
            # Lazy P2/P1 fetch: only when priority switches away
            if not new_state.get("havePriority"):
                other_id = 3 - actor_id
                other_state = client.get_state(game_name, auth_keys[other_id], other_id)
                if other_id == 1:
                    state1 = other_state
                else:
                    state2 = other_state
        else:
            # Fallback for unpatched server or all actions rejected
            states = client.parallel_get_states(game_name, auth_keys, (1, 2))
            state1, state2 = states[1], states[2]

        if accepted and collector is not None:
            post_state = new_state if new_state else (state1 if actor_id == 1 else state2)
            collector.record(
                player_id=actor_id, turn_number=turn_num,
                state=pre_state, available_actions=valid_actions,
                action_taken=action, next_state=post_state,
                p1_hp=p1_hp, p2_hp=p2_hp,
            )

        if verbose and total_actions % 25 == 0:
            print(f"    action #{total_actions} turn={turn_num} active={actor_id} hp={p1_hp}/{p2_hp}")

    return TalisharGameResult(
        winner=None, turn_number=turn_num, ended_on_turn_cap=True,
        p1_final_hp=int(state1.get("playerHealth", 0)),
        p2_final_hp=int(state1.get("opponentHealth", 0)),
        game_name=game_name, total_actions=total_actions,
    )


class TalisharBackend:
    name = "talishar"

    def __init__(self, base_url: str = "", api_key: str = "", mode: str = "pvp", request_timeout: float = 15.0):
        resolved_url = base_url.strip() or os.environ.get("TALISHAR_BASE_URL", "http://localhost:8080/game").strip()
        self.base_url = resolved_url
        self.api_key = api_key.strip() or os.environ.get("TALISHAR_API_KEY", "").strip()
        self.mode = (mode or os.environ.get("TALISHAR_MODE", "pvp")).strip().lower()
        self.request_timeout = request_timeout

    def _new_client(self) -> TalisharClient:
        return TalisharClient(base_url=self.base_url, request_timeout=self.request_timeout)

    def run_game(self, req: GameRunRequest) -> TalisharGameResult:
        """Run a game on local Talishar.

        By default this uses true PvP mode so both seats are controlled locally.
        Until Talishar-native agent adapters are implemented, agent selection
        falls back to seeded random choice unless an agent exposes a
        choose_talishar_action/select_talishar_action method.
        """
        client = self._new_client()
        p1_deck_submission = _deck_file_to_talishar_slugs(req.p1_deck)
        p2_deck_submission = _deck_file_to_talishar_slugs(req.p2_deck)
        max_t = req.max_turns if req.max_turns is not None else 150
        if self.mode == "dummy":
            return _run_talishar_random_game(
                client,
                p1_deck_submission,
                max_turns=max_t,
                rng=random.Random(req.p1_seed),
            )
        return _run_talishar_pvp_game(
            client,
            p1_deck_submission,
            p2_deck_submission,
            p1_agent=req.p1_agent,
            p2_agent=req.p2_agent,
            p1_seed=req.p1_seed,
            p2_seed=req.p2_seed,
            max_turns=max_t,
            max_actions=req.max_actions,
        )

    def run_games_parallel(
        self,
        deck_file: str,
        num_games: int = 4,
        max_turns: int = 150,
        verbose: bool = False,
        p2_deck_file: str | None = None,
        mode: str | None = None,
    ) -> list[TalisharGameResult]:
        """Run multiple Talishar games in parallel with one client per worker.

        Args:
            deck_file: Path to FAB_Sim player 1 deck file
            num_games: Number of parallel games
            max_turns: Max turns per game
            verbose: Print progress
            p2_deck_file: Optional player 2 deck path (defaults to same deck)
            mode: Override backend mode for this batch ('pvp' or 'dummy')

        Returns:
            List of TalisharGameResult, one per game
        """
        effective_mode = (mode or self.mode).lower()
        p1_deck_submission = _deck_file_to_talishar_slugs(deck_file)
        p2_deck_submission = _deck_file_to_talishar_slugs(p2_deck_file or deck_file)
        results = []

        def _worker(seed: int) -> TalisharGameResult:
            worker_client = self._new_client()
            if effective_mode == "dummy":
                return _run_talishar_random_game(
                    worker_client,
                    p1_deck_submission,
                    max_turns=max_turns,
                    rng=random.Random(seed),
                    verbose=verbose,
                )
            return _run_talishar_pvp_game(
                worker_client,
                p1_deck_submission,
                p2_deck_submission,
                p1_agent=_NullTalisharAgent(),
                p2_agent=_NullTalisharAgent(),
                p1_seed=seed,
                p2_seed=seed + 10_000,
                max_turns=max_turns,
                verbose=verbose,
            )

        with ThreadPoolExecutor(max_workers=num_games) as executor:
            futures = []
            for i in range(num_games):
                future = executor.submit(_worker, i)
                futures.append(future)

            # Collect results as they complete
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if verbose:
                    print(f"  [game {result.game_name}] Turn {result.turn_number} Winner={result.winner} HP={result.p1_final_hp}/{result.p2_final_hp}")

        return results


def add_game_backend_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--game-backend",
        type=str,
        choices=["local", "talishar"],
        default="local",
        help="Game execution backend to use for simulation",
    )
    parser.add_argument(
        "--talishar-base-url",
        type=str,
        default=os.environ.get("TALISHAR_BASE_URL", ""),
        help="Talishar base URL (used when --game-backend talishar)",
    )
    parser.add_argument(
        "--talishar-api-key",
        type=str,
        default=os.environ.get("TALISHAR_API_KEY", ""),
        help="Talishar API key/token if required by local deployment",
    )
    parser.add_argument(
        "--talishar-mode",
        type=str,
        choices=["pvp", "dummy"],
        default=os.environ.get("TALISHAR_MODE", "pvp"),
        help="Talishar game mode: pvp controls both seats locally, dummy uses Practice Dummy",
    )
    parser.add_argument(
        "--talishar-request-timeout",
        type=float,
        default=float(os.environ.get("TALISHAR_REQUEST_TIMEOUT", "15")),
        help="Per-request timeout in seconds for Talishar HTTP calls",
    )
    return parser


def build_game_backend(
    backend_name: str,
    *,
    talishar_base_url: str = "",
    talishar_api_key: str = "",
    talishar_mode: str = "pvp",
    talishar_request_timeout: float = 15.0,
):
    normalized = (backend_name or "").strip().lower()
    if normalized in ("local", "engine", "fab_sim"):
        return LocalEngineBackend()
    if normalized == "talishar":
        return TalisharBackend(
            base_url=talishar_base_url,
            api_key=talishar_api_key,
            mode=talishar_mode,
            request_timeout=talishar_request_timeout,
        )
    raise ValueError(f"Unsupported backend: {backend_name}")

"""Token card data and per-token setup hooks (CR 8.5.2).

This module owns everything token-SPECIFIC so that the canonical
``effect_keywords.create_token`` can stay fully generic:

- Zone routing is derived from the card DB template (types/subtypes) first;
  the tables here are only a fallback for minimal test states without a
  card DB.
- ``TOKEN_KEYWORDS`` restores numbered keywords the card DB drops
  (e.g. "Ward 1" — the DB only stores "Ward").
- ``TOKEN_ENTRY_HOOKS`` run just after a token's prevention effects are
  registered and before zone entry, for token text that isn't a keyword
  (e.g. Zen State's "prevent the next 1 damage").

Never add card-specific logic to engine/*.py — register it here instead.
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.card import Card
    from engine.state import GameState


# ---------------------------------------------------------------------------
# Numbered keywords (card DB stores un-numbered keyword names for tokens)
# ---------------------------------------------------------------------------

TOKEN_KEYWORDS: dict[str, list[str]] = {
    "spectral_shield": ["Ward 1"],          # CR 8.6.8
    "spellbane_aegis": ["Spellvoid 1"],     # CR 8.6.18
    "aether_ashwing": ["Arcane Barrier 1"], # CR 8.6.15
}


# ---------------------------------------------------------------------------
# Ally token stats not present on the card DB template
# ---------------------------------------------------------------------------

ALLY_TOKEN_STATS: dict[str, dict] = {
    "aether_ashwing": {"power": 1, "life": 1},
}


# ---------------------------------------------------------------------------
# Fallback zone routing — used ONLY when the game state has no card DB
# template for the token (minimal unit-test states). Real games route by the
# template's types/subtypes.
# ---------------------------------------------------------------------------

AURA_TOKENS: frozenset[str] = frozenset({
    "runechant", "seismic_surge", "quicken", "spectral_shield",
    "frostbite", "bloodrot_pox", "soul_shackle", "ponder",
    "embodiment_of_earth", "embodiment_of_lightning", "inertia",
    "frailty", "courage", "might", "vigor", "agility",
    "eloquence", "confidence", "toughness", "fealty",
    "zen_state", "spellbane_aegis", "bait",
})

ITEM_TOKENS: frozenset[str] = frozenset({
    "gold", "silver", "copper", "hyper_driver", "golden_cog", "goldkiss_rum",
})

ALLY_TOKENS: frozenset[str] = frozenset(ALLY_TOKEN_STATS)


# ---------------------------------------------------------------------------
# Per-token entry hooks — fn(state, token) run before zone entry
# ---------------------------------------------------------------------------

def _zen_state_entry(state: "GameState", token: "Card") -> None:
    """Zen State: "Prevent the next 1 damage that would be dealt to you" —
    text-based prevention, not a keyword, so it can't come from
    register_prevention_effects."""
    from engine.effects import ReplacementEffect, ReplacementType

    effect_mngr = getattr(state, "effect_manager", None)
    if effect_mngr is None:
        return

    def _condition(ev, _state, _card=token):
        return (ev.get("type") == "damage"
                and ev.get("amount", 0) > 0
                and ev.get("target_player_id") == _card.controller
                and _card.zone in (
                    "auras", "items", "tokens", "allies",
                    "head", "chest", "arms", "legs", "weapon", "hero"))

    def _replace(ev, _state):
        ev["amount"] = max(0, ev.get("amount", 0) - 1)
        return ev

    effect_mngr.add_replacement(ReplacementEffect(
        source_card=token,
        replacement_type=ReplacementType.PREVENTION,
        condition_fn=_condition,
        replace_fn=_replace,
        owner_id=token.controller,
        prevention_amount=1,
        is_shielding=True,
    ))


TOKEN_ENTRY_HOOKS: dict[str, Callable[["GameState", "Card"], None]] = {
    "zen_state": _zen_state_entry,
}

"""DSL REPLACEMENT ability implementations.

A card JSON may declare ``{"ability_type": "REPLACEMENT", "replacement": "<name>"}``.
At game start the engine records the name per player; keyword functions in
engine/effect_keywords.py consult REPLACEMENT_ABILITIES to run the handler.

The handlers here contain the card-specific behavior so engine files stay
generic. Register new replacement names in REPLACEMENT_ABILITIES.
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.state import GameState


def fail_clash_retry(state: "GameState", pid: int, revealed: dict) -> bool:
    """Victor Goldmane: the first time each turn you would fail to win a
    clash, you may destroy a Gold you control; if you do, put 1 of the
    revealed cards on the bottom of its owner's deck, then clash again.

    Returns True if the retry was taken (decks were modified → caller re-clashes).
    """
    from engine.effect_keywords import destroy
    from engine.card_effects.ability_keywords import _ask_player

    player = state.players[pid]
    flag = "victor_clash_retry_used"
    if flag in player.current_turn_effects:
        return False
    gold = player.permanents.find("gold")
    if gold is None:
        return False
    # "may" — ask the controller (default agents pick the first option = yes).
    choice = _ask_player(state, pid, ["retry", "decline"],
                         context="Destroy a Gold to bottom a revealed card and clash again?")
    if str(choice) == "decline":
        return False
    player.current_turn_effects.append(flag)
    destroy(state, gold, None)
    # Put 1 of the revealed cards on the bottom of its owner's deck. Prefer
    # bottoming an opponent's higher card; default to the controller's choice of
    # any revealed card (agents pick the first — bottom this player's own card).
    options = [c for c in revealed.values() if c is not None]
    if options:
        pick = options[0]
        owner = state.players[pick.owner]
        if pick in owner.deck.cards:
            owner.deck.cards.remove(pick)
            owner.deck.add_bottom(pick)
    return True


#: replacement name (from card JSON) → handler
REPLACEMENT_ABILITIES: dict[str, Callable] = {
    "fail_clash_retry": fail_clash_retry,
}

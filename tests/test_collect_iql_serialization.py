from __future__ import annotations

from config import SLUG_INDEX_PATH
from engine.actions import Action, ActionType
from engine.card import CardDB
from rl_agents.collect_iql_mixed_data import _serialise_action


def test_serialize_defend_cards_includes_selected_defenders() -> None:
    card_db = CardDB(SLUG_INDEX_PATH)
    defender_a = card_db.get("sink_below_red")
    defender_b = card_db.get("fate_foreseen_red")

    action = Action(
        type=ActionType.DEFEND_CARDS,
        player_id=2,
        card_list=[defender_a, defender_b],
    )

    payload = _serialise_action(action)
    selected = payload["selected_action"]

    assert selected["type"] == "defend_cards"
    assert selected["defend_cards"] == ["sink_below_red", "fate_foreseen_red"]
    assert "target" in selected
    assert "targets" in selected

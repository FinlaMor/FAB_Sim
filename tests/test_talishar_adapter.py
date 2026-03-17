from __future__ import annotations

from config import SLUG_INDEX_PATH
from engine.actions import ActionType
from engine.card import CardDB
from engine.state import Step
from rl_agents.talishar_adapter import (
    talishar_actions_to_engine_actions,
    talishar_card_to_card,
    talishar_state_to_observed_game_state,
)


def test_talishar_card_to_card_overlays_runtime_fields() -> None:
    card_db = CardDB(SLUG_INDEX_PATH)
    raw_card = {
        "cardNumber": "sink_below_red",
        "controller": "1",
        "facing": "DOWN",
        "tapped": True,
        "uniqueID": "1;sink_below_red;16",
        "countersMap": {
            "attack": "3",
            "charge": "1",
        },
        "powerCounters": "4",
        "defCounters": "2",
        "lifeCounters": "0",
    }

    card = talishar_card_to_card(
        raw_card,
        card_db,
        owner_id=1,
        zone_name="arsenal",
    )

    assert card is not None
    assert card.slug == "sink_below_red"
    assert card.controller == 1
    assert card.owner == 1
    assert card.zone == "arsenal"
    assert card.is_public is False
    assert card.face_down is True
    assert card.tapped is True
    assert card.exhausted is True
    assert card.object_id == 16
    assert card.counters["plus_power"] == 3
    assert card.counters["charge"] == 1
    assert card.counters["plus_defense"] == 2


def test_talishar_state_adapter_loads_visibility_sensitive_zones() -> None:
    card_db = CardDB(SLUG_INDEX_PATH)
    state_view = {
        "playerEquipment": [
            {
                "cardNumber": "kayo_underhanded_cheat",
                "controller": "1",
                "marked": True,
                "facing": "UP",
                "tapped": False,
                "countersMap": {"defense": "0"},
            },
            {
                "cardNumber": "scabskin_leathers",
                "controller": "1",
                "facing": "UP",
                    "sType": "Legs",
                "tapped": True,
                "countersMap": {"defense": "0"},
            },
        ],
        "opponentEquipment": [
            {
                "cardNumber": "kayo_underhanded_cheat",
                "controller": "2",
                "marked": False,
                "facing": "UP",
                "tapped": False,
                "countersMap": {"defense": "0"},
            }
        ],
        "playerHealth": "38",
        "opponentHealth": "34",
        "playerAP": "2",
        "opponentAP": "1",
        "turnNo": 7,
        "havePriority": True,
        "amIActivePlayer": True,
        "turnPhase": {"turnPhase": "M"},
        "playerHand": [
            {
                "cardNumber": "big_bully_red",
                "controller": "1",
            }
        ],
        "playerArse": [
            {
                "cardNumber": "sink_below_red",
                "controller": "1",
                "facing": "DOWN",
                "uniqueID": "1;sink_below_red;16",
                "countersMap": {"attack": "0"},
            }
        ],
        "opponentArse": [
            {
                "cardNumber": "fate_foreseen_red",
                "controller": "2",
                "facing": "DOWN",
                "uniqueID": "2;fate_foreseen_red;22",
                "countersMap": {"attack": "0"},
            }
        ],
        "playerSoul": [
            {
                "cardNumber": "big_bully_red",
                "controller": "1",
            }
        ],
        "opponentSoul": [
            {
                "cardNumber": "big_bully_red",
                "controller": "2",
            }
        ],
        "playerAuras": [
            {
                "cardNumber": "booze_blue",
                "controller": "1",
                "tapped": False,
                "countersMap": {"attack": "1"},
            }
        ],
        "opponentAuras": [],
        "playerItems": [],
        "opponentItems": [],
        "playerAllies": [],
        "opponentAllies": [],
        "playerDiscard": [],
        "opponentDiscard": [],
        "playerPitch": [],
        "opponentPitch": [],
        "playerBanish": [],
        "opponentBanish": [],
        "playerInventory": [],
    }

    observed = talishar_state_to_observed_game_state(
        state_view,
        player_id=1,
        card_db=card_db,
    )

    player = observed.players[1]
    opponent = observed.players[2]

    assert observed.turn_number == 7
    assert player.action_points == 2
    assert opponent.action_points == 1
    assert player.marked is True
    assert opponent.marked is False

    assert len(player.hand.cards) == 1
    assert player.hand.cards[0].slug == "big_bully_red"
    assert player.hand.cards[0].is_public is False

    assert len(player.arsenal.cards) == 1
    assert player.arsenal.cards[0].slug == "sink_below_red"
    assert player.arsenal.cards[0].face_down is True
    assert player.arsenal.cards[0].is_public is False
    assert player.arsenal.cards[0].object_id == 16

    assert len(player.soul.cards) == 1
    assert player.soul.cards[0].slug == "big_bully_red"
    assert player.soul.cards[0].zone == "soul"

    assert len(player.auras.cards) == 1
    assert player.auras.cards[0].counters["plus_power"] == 1

    assert len(player.legs.cards) == 1
    assert player.legs.cards[0].slug == "scabskin_leathers"
    assert player.legs.cards[0].tapped is True

    assert len(opponent.arsenal.cards) == 1
    assert opponent.arsenal.cards[0].slug == "card_back"
    assert opponent.arsenal.cards[0].is_public is False
    assert len(opponent.soul.cards) == 1


def test_talishar_state_adapter_maps_gamestate_fields() -> None:
    card_db = CardDB(SLUG_INDEX_PATH)
    state_view = {
        "playerEquipment": [
            {
                "cardNumber": "kayo_underhanded_cheat",
                "controller": "1",
                "marked": False,
                "facing": "UP",
                "tapped": False,
            }
        ],
        "opponentEquipment": [
            {
                "cardNumber": "kayo_underhanded_cheat",
                "controller": "2",
                "marked": True,
                "facing": "UP",
                "tapped": False,
            }
        ],
        "playerHealth": "35",
        "opponentHealth": "28",
        "playerAP": "1",
        "opponentAP": "0",
        "turnNo": "5",
        "turnPlayer": "2",
        "otherPlayer": "2",
        "havePriority": False,
        "amIActivePlayer": False,
        "turnPhase": {"turnPhase": "B", "caption": "Choose a card to block"},
        "tracker": {"color": "blue", "position": "Defense"},
        "playerHand": [
            {
                "cardNumber": "sink_below_red",
                "controller": "1",
            }
        ],
        "opponentHand": [
            {"cardNumber": "CardBack"},
            {"cardNumber": "CardBack"},
        ],
        "playerDeck": [],
        "opponentDeck": [],
        "playerDeckCount": 50,
        "opponentDeckCount": 44,
        "playerArse": [],
        "opponentArse": [
            {
                "cardNumber": "CardBack",
                "controller": "2",
                "facing": "DOWN",
            }
        ],
        "playerDiscard": [],
        "opponentDiscard": [],
        "playerPitch": [
            {
                "cardNumber": "big_bully_red",
                "controller": "1",
            }
        ],
        "opponentPitch": [
            {
                "cardNumber": "fate_foreseen_red",
                "controller": "2",
            }
        ],
        "playerBanish": [],
        "opponentBanish": [],
        "playerSoul": [],
        "opponentSoul": [],
        "playerAuras": [],
        "opponentAuras": [],
        "playerItems": [],
        "opponentItems": [],
        "playerAllies": [],
        "opponentAllies": [],
        "playerInventory": [],
        "activeChainLink": {
            "attackingCard": {
                "cardNumber": "big_bully_red",
                "controller": "2",
            },
            "totalPower": 6,
            "totalDefense": 3,
            "reactions": [
                {
                    "cardNumber": "sink_below_red",
                    "controller": "1",
                }
            ],
            "goAgain": True,
            "dominate": False,
            "overpower": False,
            "activeOnHits": False,
            "wager": False,
            "phantasm": False,
            "fusion": False,
            "fused": False,
            "attackTarget": "Kayo, Underhanded Cheat",
            "damagePrevention": 0,
        },
        "combatChainLinks": [
            {"result": "hit", "isDraconic": True},
            {"result": "no-hit", "isDraconic": False},
        ],
        "layerDisplay": {
            "target": "Kayo, Underhanded Cheat",
            "layerContents": [
                {
                    "cardNumber": "sink_below_red",
                    "controller": "1",
                }
            ],
            "reorderableLayers": [
                {
                    "card": {
                        "cardNumber": "sink_below_red",
                        "controller": "1",
                    },
                    "layerID": 2,
                    "isReorderable": True,
                }
            ],
        },
        "newEvents": {
            "eventArray": [
                {"eventType": "ADDBOTDECK", "eventValue": "1"},
                {"eventType": "DAMAGE", "eventValue": "2"},
            ]
        },
        "landmarks": [
            {"playerID": "2", "eventType": "Test Landmark"},
            "Shared Landmark",
        ],
        "playerEffects": [
            {"cardNumber": "pummel_red"},
        ],
        "opponentEffects": [
            {"cardNumber": "up_sticks_and_run_red"},
        ],
    }

    observed = talishar_state_to_observed_game_state(
        state_view,
        player_id=1,
        card_db=card_db,
    )

    assert observed.step == Step.COMBAT_DEFEND
    assert observed.turn_number == 5
    assert observed.active_player == 2
    assert observed.priority_player == 2
    assert observed.last_acted_player == 1

    assert observed.combat is not None
    assert observed.combat.attacker_id == 2
    assert observed.combat.attack_card.slug == "big_bully_red"
    assert observed.combat.attack_power == 6
    assert observed.combat.total_defense == 3
    assert len(observed.combat.defending_cards) == 1
    assert observed.combat.defending_cards[0].slug == "sink_below_red"
    assert "go again" in observed.combat.keywords

    assert len(observed.chain_links) == 2
    assert observed.chain_links[0].hit is True
    assert "draconic" in observed.chain_links[0].keywords

    assert len(observed.stack.cards) == 1
    assert observed.stack.cards[0].slug == "sink_below_red"
    assert len(observed.stack_entries) == 1
    assert observed.stack_entries[0].layer_position == 3
    assert getattr(observed.stack_entries[0], "talishar_reorderable", False) is True

    assert observed.events_this_turn == {"addbotdeck", "damage_dealt"}
    assert observed.pitch_history[1][5] == ["big_bully_red"]
    assert observed.pitch_history[2][5] == ["fate_foreseen_red"]
    assert (2, "Test Landmark") in observed.landmarks
    assert (0, "Shared Landmark") in observed.landmarks

    assert observed.players[1].current_turn_effects == ["pummel_red"]
    assert observed.players[2].current_turn_effects == ["up_sticks_and_run_red"]

    assert len(observed.players[1].deck.cards) == 50
    assert len(observed.players[2].deck.cards) == 44
    assert len(observed.players[2].hand.cards) == 2
    assert len(observed.players[2].arsenal.cards) == 1
    assert observed.players[2].arsenal.cards[0].slug == "card_back"
    assert observed.players[2].arsenal.cards[0].is_public is False

    assert observed.observed_opponent_hand_count == 2
    assert observed.observed_player_deck_count == 50
    assert observed.observed_opponent_deck_count == 44
    assert observed.talishar_layer_target == "Kayo, Underhanded Cheat"


def test_talishar_actions_adapter_maps_context_and_economy_fields() -> None:
    card_db = CardDB(SLUG_INDEX_PATH)
    state_view = {
        "turnPhase": {"turnPhase": "B", "caption": "Choose a card to block"},
        "havePriority": True,
        "canPassPhase": True,
        "playerAP": "2",
        "turnPlayer": "2",
        "otherPlayer": "2",
        "combatChainLinks": [],
        "activeChainLink": {
            "attackingCard": {
                "cardNumber": "big_bully_red",
                "controller": "2",
            },
            "reactions": [],
            "goAgain": False,
        },
        "playerHand": [
            {
                "cardNumber": "sink_below_red",
                "action": 27,
                "actionDataOverride": "2",
                "controller": "1",
                "restriction": "",
                "label": "",
            }
        ],
        "playerEquipment": [
            {
                "cardNumber": "kayo_underhanded_cheat",
                "controller": "1",
                "facing": "UP",
            },
            {
                "cardNumber": "scabskin_leathers",
                "controller": "1",
                "facing": "UP",
                "sType": "Legs",
                "actions": [
                    {
                        "mode": 27,
                        "cardID": "15",
                    }
                ],
            },
        ],
        "playerPrompt": {
            "helpText": "Choose a card to block",
            "buttons": [
                {
                    "mode": 101,
                    "buttonInput": 0,
                    "caption": "Pass Block and Reactions",
                }
            ],
        },
        "playerInputPopUp": {
            "active": False,
            "buttons": [],
        },
    }

    actions = talishar_actions_to_engine_actions(
        state_view,
        card_db=card_db,
        player_id=1,
    )

    hand_defend = next(
        a for a in actions
        if a.type == ActionType.DEFEND_CARDS and a.card is not None and a.card.slug == "sink_below_red"
    )
    assert hand_defend.player_id == 1
    assert hand_defend.card_idx == 2
    assert hand_defend.card_list is not None and len(hand_defend.card_list) == 1
    assert hand_defend.phase == "action"
    assert hand_defend.step == Step.COMBAT_DEFEND
    assert hand_defend.chain_link_number == 1
    assert hand_defend.priority_player == 1
    assert hand_defend.action_points_available == 2
    assert hand_defend.resources_available == 0
    assert hand_defend.action_cost == 0
    assert hand_defend.resource_cost == 0
    assert hand_defend.has_go_again is False
    assert hand_defend.is_instant_speed is False
    assert hand_defend.is_action_speed is False
    assert hand_defend.played_as_instant is False
    assert hand_defend.modes_selected == []
    assert hand_defend.x_value_declared is None
    assert hand_defend.is_melded is False
    assert hand_defend.alternative_cost_used is None

    equip_defend = next(
        a for a in actions
        if a.type == ActionType.DEFEND_EQUIPMENT and a.card is not None and a.card.slug == "scabskin_leathers"
    )
    assert equip_defend.slot == "Legs"
    assert equip_defend.card_idx == 15
    assert equip_defend.action_cost == 0
    assert equip_defend.resource_cost == 0
    assert equip_defend.card_list is not None and len(equip_defend.card_list) == 1

    assert any(a.type == ActionType.PASS for a in actions)


def test_talishar_actions_adapter_maps_pitch_target_and_alt_cost_fields() -> None:
    card_db = CardDB(SLUG_INDEX_PATH)

    pitch_state = {
        "turnPhase": {"turnPhase": "P", "caption": "Choose a card to pitch"},
        "havePriority": True,
        "canPassPhase": False,
        "playerAP": "1",
        "turnPlayer": "1",
        "otherPlayer": "2",
        "combatChainLinks": [],
        "activeChainLink": {"reactions": []},
        "playerHand": [
            {
                "cardNumber": "big_bully_red",
                "action": 27,
                "actionDataOverride": "0",
                "controller": "1",
                "restriction": "",
                "label": "",
            }
        ],
        "playerEquipment": [
            {
                "cardNumber": "kayo_underhanded_cheat",
                "controller": "1",
                "facing": "UP",
            }
        ],
        "playerPrompt": {
            "helpText": "Choose a card to pitch (1 of 2)",
            "buttons": [],
        },
        "playerInputPopUp": {"active": False, "buttons": []},
    }

    pitch_actions = talishar_actions_to_engine_actions(
        pitch_state,
        card_db=card_db,
        player_id=1,
    )
    pitch_action = next(a for a in pitch_actions if a.card is not None and a.card.slug == "big_bully_red")
    assert len(pitch_action.pitch_cards) == 1
    assert pitch_action.pitch_cards[0].slug == "big_bully_red"

    target_state = {
        "turnPhase": {"turnPhase": "MAYCHOOSEHAND", "caption": "Choose a card from hand"},
        "havePriority": True,
        "canPassPhase": True,
        "playerAP": "0",
        "turnPlayer": "1",
        "otherPlayer": "2",
        "combatChainLinks": [],
        "activeChainLink": {"reactions": []},
        "playerHand": [
            {
                "cardNumber": "big_bully_red",
                "action": 27,
                "actionDataOverride": "3",
                "controller": "1",
                "restriction": "Rune Gate",
                "label": "",
            }
        ],
        "playerEquipment": [
            {
                "cardNumber": "kayo_underhanded_cheat",
                "controller": "1",
                "facing": "UP",
            }
        ],
        "playerPrompt": {
            "helpText": "Choose a card to banish",
            "buttons": [],
        },
        "playerInputPopUp": {"active": False, "buttons": []},
    }

    target_actions = talishar_actions_to_engine_actions(
        target_state,
        card_db=card_db,
        player_id=1,
    )
    target_action = next(a for a in target_actions if a.card is not None and a.card.slug == "big_bully_red")
    assert target_action.target is not None
    assert target_action.target.slug == "big_bully_red"
    assert target_action.targets == ["big_bully_red"]
    assert target_action.alternative_cost_used == "rune_gate"

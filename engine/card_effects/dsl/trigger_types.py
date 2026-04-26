"""Maps JSON trigger/ability_type values to engine event name strings."""

# JSON trigger name → engine event name
TRIGGER_TO_EVENT: dict[str, str] = {
    "ON_PLAY":          "ON_PLAY",
    "ON_HIT":           "ON_HIT",
    "ON_ATTACK":        "ON_ATTACK",
    "ON_DEFEND":        "ON_DEFEND",
    "ON_DEFEND_NONE":   "ON_DEFEND_NONE",
    "END_OF_TURN":      "END_OF_TURN",
    "START_OF_TURN":    "START_OF_TURN",
    "ON_ACTIVATE":      "ON_ACTIVATE",
    "ON_DEATH":         "ON_DEATH",
    "ON_ENTER_PLAY":    "ON_ENTER_PLAY",
    "ON_LEAVE_PLAY":    "ON_LEAVE_PLAY",
    "START_OF_COMBAT":  "START_OF_COMBAT",
    "END_OF_COMBAT":    "END_OF_COMBAT",
}

# ability_type → the event that fires this ability
ABILITY_TYPE_TO_EVENT: dict[str, str] = {
    "PLAY":             "ON_PLAY",
    "ATTACK_REACTION":  "ON_PLAY",
    "DEFENSE_REACTION": "ON_PLAY",
    "ACTIVATE":         "ON_ACTIVATE",
}

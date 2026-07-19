"""Maps JSON trigger/ability_type values to engine event name strings."""

# JSON trigger name → engine event name
TRIGGER_TO_EVENT: dict[str, str] = {
    "ON_PLAY":                  "ON_PLAY",
    "ON_HIT":                   "ON_HIT",
    "ON_ATTACK":                "ON_ATTACK",
    "ON_CRUSH":                 "ON_CRUSH",
    "ON_DEFEND":                "ON_DEFEND",
    "ON_DEFEND_NONE":           "ON_DEFEND_NONE",
    "END_OF_TURN":              "END_OF_TURN",
    "BEGINNING_OF_END_PHASE":   "BEGINNING_OF_END_PHASE",
    "START_OF_TURN":            "START_OF_TURN",
    "ON_ACTIVATE":              "ON_ACTIVATE",
    "ON_DEATH":                 "ON_DEATH",
    "ON_ENTER_PLAY":            "ON_ENTER_PLAY",
    "ON_LEAVE_PLAY":            "ON_LEAVE_PLAY",
    "START_OF_COMBAT":          "START_OF_COMBAT",
    "END_OF_COMBAT":            "END_OF_COMBAT",
    "ON_DISCARD":               "ON_DISCARD",
    "ON_PLAY_ACTIVATE_ATTACK":  "ON_PLAY_ACTIVATE_ATTACK",
    "ON_PITCH":                 "ON_PITCH",
    "ON_DEFEND":                "ON_DEFEND",
    "ON_BOO":                   "ON_BOO",
    "ON_TOKEN_CREATED":         "ON_TOKEN_CREATED",
    # Sugar: fires on ON_TOKEN_CREATED, gated on the created token's slug.
    "ON_GOLD_CREATED":          "ON_TOKEN_CREATED",
    "ON_CLASH_WIN_REVEALED":    "ON_CLASH_WIN_REVEALED",
    "RECALC_ATTACK_POWER":      "RECALC_ATTACK_POWER",
    "ON_BECOME":                "ON_BECOME",
    "ON_COMBAT_CLOSE":          "ON_COMBAT_CLOSE",
    "ON_EQUIP":                 "ON_EQUIP",
    "START_OF_TURN_IN_GRAVEYARD": "START_OF_TURN_IN_GRAVEYARD",
}


def _event_data(event) -> dict:
    """Extract the payload dict from an engine Event object or a plain dict."""
    if event is None:
        return {}
    data = getattr(event, "data", None)
    if isinstance(data, dict):
        return data
    return event if isinstance(event, dict) else {}


# JSON trigger name → gate fn(event) -> bool, for sugar triggers that map to
# a broader engine event and must filter on the event payload.
TRIGGER_EVENT_GATES: dict[str, callable] = {
    "ON_GOLD_CREATED": lambda event: _event_data(event).get("slug") == "gold",
}

# Simple ability_type → event mappings.
# STATIC_TRIGGERED, DELAYED_TRIGGERED, and WHILE_STATIC require special
# dispatch logic and are handled explicitly in dispatch_event.
ABILITY_TYPE_TO_EVENT: dict[str, str] = {
    "PLAY":             "ON_PLAY",
    "ACTION":           "ON_PLAY",
    "MODAL":            "ON_PLAY",
    "ATTACK_REACTION":  "ON_PLAY",
    "DEFENSE_REACTION": "ON_PLAY",
    "ACTIVATE":         "ON_ACTIVATE",
    "INSTANT":          "ON_ACTIVATE",
}

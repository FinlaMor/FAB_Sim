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
    # "At the start of EACH hero's turn" / "each OTHER hero's turn". Dispatched
    # to BOTH players' permanents; START_OF_TURN reaches only the turn player's,
    # so a card keyed to the opponent's turn never received the event and its
    # condition was never even evaluated.
    "START_OF_ANY_TURN":        "START_OF_ANY_TURN",
    "START_OF_EACH_TURN":       "START_OF_ANY_TURN",
    "ON_ACTIVATE":              "ON_ACTIVATE",
    "ON_DEATH":                 "ON_DEATH",
    "ON_ENTER_PLAY":            "ON_ENTER_PLAY",
    "ON_LEAVE_PLAY":            "ON_LEAVE_PLAY",
    "START_OF_COMBAT":          "START_OF_COMBAT",
    "END_OF_COMBAT":            "END_OF_COMBAT",
    "ON_DISCARD":               "ON_DISCARD",
    # "Whenever a hero draws a card ..." — dispatched to BOTH players'
    # permanents, since the text says "a hero" rather than "you". The event
    # carries draw_player, which effects read via player: "EVENT_PLAYER".
    "ON_DRAW":                  "ON_DRAW",
    "ON_PLAY_ACTIVATE_ATTACK":  "ON_PLAY_ACTIVATE_ATTACK",
    "ON_PITCH":                 "ON_PITCH",
    "ON_DEFEND":                "ON_DEFEND",
    "ON_BOO":                   "ON_BOO",
    "ON_CHEER":                 "ON_CHEER",
    "ON_CROWD_CHEER":           "ON_CHEER",
    "ON_TOKEN_CREATED":         "ON_TOKEN_CREATED",
    # Sugar: fires on ON_TOKEN_CREATED, gated on the created token's slug.
    "ON_GOLD_CREATED":          "ON_TOKEN_CREATED",
    "ON_CLASH_WIN_REVEALED":    "ON_CLASH_WIN_REVEALED",
    # CR 8.5.46 — "wagers with the defending hero. The winner loses 1{h}."
    # A wager could only ever pay out a token; this is how a card expresses any
    # other outcome. Dispatched to the card that made the wager.
    "ON_WAGER_RESOLVED":        "ON_WAGER_RESOLVED",
    # "Whenever you play your second non-attack action card each turn" — hero
    # text about the act of playing a card, dispatched to that player's hero.
    "ON_CARD_PLAYED":           "ON_CARD_PLAYED",
    # CR 4.3.1 — "at the beginning of your action phase", which is NOT the start
    # of the turn (that is the start phase, and it happens earlier).
    "START_OF_ACTION_PHASE":    "START_OF_ACTION_PHASE",
    # "If an activated ability or action card effect puts this face up into a
    # zone from your deck" — dispatched from Zone.add, the only place that
    # knows all of: previous zone, face-up-ness, and effect-vs-rule source.
    "ON_PUT_FACEUP_FROM_DECK":  "ON_PUT_FACEUP_FROM_DECK",
    # "When this is put face up into your arsenal" — origin-agnostic, unlike
    # ON_PUT_FACEUP_FROM_DECK, which the card above needs to be from the deck.
    # Dispatched from Zone.add, which is where the destination zone and the
    # face-up-ness are both known.
    "ON_PUT_FACEUP_IN_ARSENAL": "ON_PUT_FACEUP_IN_ARSENAL",
    "ON_DEAL_DAMAGE":           "ON_DEAL_DAMAGE",
    "RECALC_ATTACK_POWER":      "RECALC_ATTACK_POWER",
    # The defence-side mirror, dispatched once per declared defender by
    # engine._recalculate_total_defense.
    "RECALC_DEFENSE":           "RECALC_DEFENSE",
    "ON_BECOME":                "ON_BECOME",
    # CR 8.5.48 — "whenever you transcend" (Twelve Petal Kasaya).
    "ON_TRANSCEND":             "ON_TRANSCEND",
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

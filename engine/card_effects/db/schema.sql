-- FAB Sim card effects database schema
-- Each table covers one category of card behavior.
-- "custom" rows delegate to a named Python function in triggers.py / registry.py.
-- All JSON columns use SQLite TEXT with valid JSON objects/arrays.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;


-- ---------------------------------------------------------------------------
-- card_triggers
-- One row per trigger per card. A card with 3 triggers has 3 rows.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS card_triggers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT    NOT NULL,

    -- Event that fires this trigger. Valid values:
    --
    -- Turn structure (CR 4.x):
    --   'start_of_game'              — CR 4.1.8: game start event
    --   'start_of_turn'              — CR 4.2.1: start of Start Phase
    --   'beginning_of_action_phase'  — CR 4.3.1: start of Action Phase (distinct from start_of_turn)
    --   'start_of_action_phase'      — alias for beginning_of_action_phase (engine internal)
    --   'start_of_end_phase'         — CR 4.4.1: start of End Phase
    --   'end_of_turn'                — CR 4.4.5: after cleanup
    --
    -- Card play / zone events:
    --   'on_play'                    — this card is played and placed on the stack
    --   'enters_arena'               — this card enters the arena zone
    --   'leaves_arena'               — this card leaves the arena zone
    --   'card_destroyed'             — this card is destroyed
    --   'card_pitched'               — CR 8.5.44: a card is pitched to pay a cost
    --   'target_of_attack'           — this card / controller is targeted by an attack (CR 8.3.14 Spectra)
    --
    -- Combat chain (CR 7.x):
    --   'attacking'                  — CR 7.2: this card is declared as the attack
    --   'defend'                     — CR 7.3: this card is declared as a defender
    --   'hit'                        — CR 7.5.3: attack hit (damage >= defense total)
    --   'chain_link_resolves'        — CR 7.6.2: chain link becomes a resolved chain link
    --   'combat_chain_close'         — CR 7.7.1: combat chain closes (no further attack declared)
    --   'damage_dealt'               — damage was dealt this chain link
    --   'arcane_damage_dealt'        — arcane damage was dealt this chain link
    --
    -- Arena trigger events (fired by engine for all arena permanents to observe):
    --   'attack_played'              — any attack action card was played by the controller's turn
    --   'weapon_activated'           — any weapon attack was activated by the controller
    --
    -- Misc:
    --   'charged'                    — CR 8.5.29: a card was moved to a hero's soul via charge
    --   'crowd_boos'                 — crowd boos event (showstopper mechanic)
    --   'gold_created'               — a Gold token was created
    event_type      TEXT    NOT NULL,

    -- Guard condition evaluated before effect fires. Valid values:
    --   'none'                       — always fires
    --   'is_attacking'               — this card is the current attack card
    --   'is_defending'               — this card is in defending_cards
    --   'player_is_active'           — controller is the active player
    --   'player_is_non_active'       — controller is NOT the active player (opponent's turn)
    --   'health_more_than_opp'       — controller.health > opponent.health
    --   'coplayer_power_gte'         — another defending card has power >= condition_params.min_power
    --   'has_counter_lt'             — counter count < condition_params.{type, max}
    --   'has_counter_gte'            — counter count >= condition_params.{type, min}
    --   'flag_set'                   — flag in condition_params.flag is in current_turn_effects
    --   'card_in_zone'               — this card is in condition_params.zone
    --   'controller_has_card_type'   — controller has a card of condition_params.card_type in play
    --   'opponent_has_supertype'     — opponent hero is condition_params.supertype (e.g. 'Illusionist')
    --   'attacking_hero_is'          — attacking hero is condition_params.supertype
    --   'defending_hero_is'          — defending hero is condition_params.supertype
    --   'reprise_check'              — CR 8.4.3: defending hero defended with a hand card this chain link
    --   'crush_check'                — CR 8.4.2: attack power >= defense total + condition_params.threshold (default 0)
    --   'combo_check'                — CR 8.4.1: condition_params.names list includes a card played this turn
    --   'surge_check'                — CR 8.4.8: condition_params.threshold arcane dealt this chain link
    --   'rupture_check'              — CR 8.4.6: condition_params.threshold non-equipment cards in graveyard
    --   'custom'                     — Python function named in condition_fn
    condition_type  TEXT    NOT NULL DEFAULT 'none',
    condition_params TEXT   NOT NULL DEFAULT '{}',
    condition_fn    TEXT,   -- Python function name (only when condition_type = 'custom')

    -- Effect to execute when the trigger fires. Valid values:
    --   'gain_life'       — params: {amount: N}
    --   'lose_life'       — params: {amount: N}
    --   'deal_damage'     — params: {amount: N, target: 'opponent'|'self'}
    --   'deal_arcane'     — params: {amount: N, target: 'opponent'|'self'}
    --   'deal_physical'   — params: {amount: N, target: 'opponent'|'self'} (explicit physical damage)
    --   'draw'            — params: {amount: N}
    --   'discard'         — params: {amount: N, target: 'self'|'opponent'}
    --   'create_token'    — params: {token: slug_string, count: N}
    --   'grant_go_again'  — params: {} (idempotent per CR 8.3.5c: fails if attack already has go again)
    --   'grant_keyword'   — params: {keyword: str} (for non-go-again keyword grants)
    --   'intimidate'      — params: {}
    --   'dominate'        — params: {}
    --   'mark'            — params: {}
    --   'amp'             — params: {amount: N}
    --   'gain_resources'  — params: {amount: N}
    --   'power_bonus'     — params: {amount: N, target: 'attack'|'this'} (combat power modifier)
    --   'set_flag'        — params: {flag: str, scope: 'current'|'next'} (appends to turn effects)
    --   'put_counter'     — params: {counter_type: str}
    --   'remove_counter'  — params: {counter_type: str, amount: N}
    --   'banish_top_deck' — params: {target: 'opponent'|'self', infiltrate: bool}
    --   'reload'          — params: {} (CR 8.5.23: move card to arsenal if empty, optional)
    --   'opt'             — params: {amount: N} (CR 8.5.22: look at top N, reorder)
    --   'charge'          — params: {} (CR 8.5.29: move card to hero's soul)
    --   'custom'          — delegates to Python function named in effect_fn
    effect_type     TEXT    NOT NULL,
    effect_params   TEXT    NOT NULL DEFAULT '{}',
    effect_fn       TEXT,   -- Python function name (only when effect_type = 'custom')

    is_optional     INTEGER NOT NULL DEFAULT 0,  -- 1 = player may decline
    -- Ordering within this card's trigger list only.
    -- Inter-card ordering at runtime is always determined by the active player per CR 6.6.6b.
    intra_card_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_card_triggers_slug ON card_triggers(slug);
CREATE INDEX IF NOT EXISTS idx_card_triggers_event ON card_triggers(event_type);


-- ---------------------------------------------------------------------------
-- equipment_activations
-- One row per piece of equipment with an activated ability.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS equipment_activations (
    slug                TEXT    PRIMARY KEY,

    -- Resource cost to activate. NULL means look up activation_cost_fn.
    activation_cost     INTEGER,
    activation_cost_fn  TEXT,   -- Python function name returning int

    -- When activation is legal. Valid values:
    --   'instant'          — can be activated as an instant (any time you have priority)
    --   'action'           — uses an action point; only during action phase
    --   'attack_reaction'  — only during Reaction Step as attack reaction
    --   'defense_reaction' — only during Reaction Step as defense reaction
    -- Default: 'instant'
    activation_timing   TEXT    NOT NULL DEFAULT 'instant',

    -- How many times this can be activated. Valid values:
    --   'unlimited'             — no limit
    --   'once_per_turn'         — once per turn (tracked via flag in current_turn_effects)
    --   'once_per_combat_chain' — once per combat chain
    -- For numeric limits: set activation_limit to 'custom' and use condition_fn.
    activation_limit    TEXT    NOT NULL DEFAULT 'unlimited',

    -- Condition(s) that must be true to activate (beyond cost and timing).
    -- Stored as JSON array of condition objects: [{"type": ..., "params": {...}}, ...]
    -- Simple single-condition cases may use condition_type + condition_params for convenience.
    -- Valid condition types (same vocabulary as card_triggers, plus):
    --   'none'                    — always activatable (if cost + timing met)
    --   'not_tapped'              — equip card must not be tapped
    --   'arsenal_face_down'       — player.arsenal_face_up == False
    --   'has_counter_gte'         — condition_params: {counter_type, min}
    --   'has_blue_arrow_in_arsenal' — specific to Sealace Sarong
    --   'custom'                  — Python function named in condition_fn
    condition_type      TEXT    NOT NULL DEFAULT 'none',
    condition_params    TEXT    NOT NULL DEFAULT '{}',
    condition_fn        TEXT,
    -- Extended: JSON array for compound (AND) conditions when condition_type = 'compound'
    -- e.g. [{"type": "not_tapped"}, {"type": "has_counter_gte", "params": {"counter_type": "steam", "min": 1}}]
    conditions          TEXT    NOT NULL DEFAULT '[]',

    -- What activating does (same vocabulary as card_triggers effect_type).
    effect_type         TEXT    NOT NULL,
    effect_params       TEXT    NOT NULL DEFAULT '{}',
    effect_fn           TEXT,

    -- Deprecated: use activation_limit = 'once_per_turn' instead.
    -- Kept for backwards compatibility during migration.
    once_per_turn       INTEGER NOT NULL DEFAULT 0
);


-- ---------------------------------------------------------------------------
-- turn_attack_effects
-- Flags in current_turn_effects that modify the next declared attack.
-- Consumed by actions.py when an attack is declared.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turn_attack_effects (
    flag            TEXT    PRIMARY KEY,

    -- Which attacks this applies to.
    --   'any'                 — any attack action card
    --   'cost_lte'            — condition_params: {max_cost: N}
    --   'type_is'             — condition_params: {card_type: str}  e.g. 'stealth'
    --   'has_keyword'         — condition_params: {keyword: str}
    --   'custom'              — Python function named in condition_fn
    condition_type  TEXT    NOT NULL DEFAULT 'any',
    condition_params TEXT   NOT NULL DEFAULT '{}',
    condition_fn    TEXT,

    -- What to do to the attack card when the flag is consumed.
    --   'add_power'           — effect_params: {amount: N}
    --   'set_power'           — effect_params: {amount: N}
    --   'add_defense'         — effect_params: {amount: N}
    --   'grant_go_again'      — effect_params: {} (idempotent per CR 8.3.5c)
    --   'grant_keyword'       — effect_params: {keyword: str} (for non-go-again keywords)
    --   'custom'              — Python function named in effect_fn
    effect_type     TEXT    NOT NULL,
    effect_params   TEXT    NOT NULL DEFAULT '{}',
    effect_fn       TEXT
);


-- ---------------------------------------------------------------------------
-- turn_defend_effects
-- Flags in current_turn_effects that modify the next defending card.
-- Mirrors turn_attack_effects for defense-scoped buffs (e.g. Toughness token CR 8.6.36).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turn_defend_effects (
    flag            TEXT    PRIMARY KEY,

    -- Which defending cards this applies to.
    --   'any'                 — any defending card
    --   'type_is'             — condition_params: {card_type: str}
    --   'custom'              — Python function named in condition_fn
    condition_type  TEXT    NOT NULL DEFAULT 'any',
    condition_params TEXT   NOT NULL DEFAULT '{}',
    condition_fn    TEXT,

    -- What to do to the defending card.
    --   'add_defense'         — effect_params: {amount: N}
    --   'grant_keyword'       — effect_params: {keyword: str}
    --   'custom'              — Python function named in effect_fn
    effect_type     TEXT    NOT NULL,
    effect_params   TEXT    NOT NULL DEFAULT '{}',
    effect_fn       TEXT
);


-- ---------------------------------------------------------------------------
-- token_keywords
-- Static keyword grants for token slugs (drives TOKEN_KEYWORDS in keywords.py).
-- For tokens whose abilities are keywords or prevention effects expressible as strings.
-- See token_effects for tokens with complex static abilities (cost increases, etc.).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS token_keywords (
    token_slug      TEXT    NOT NULL,
    -- FAB keyword string as printed on the card (e.g. 'Ward 1', 'Arcane Barrier 1'),
    -- OR engine-internal ability descriptor (e.g. 'prevent_damage_1') for non-keyword statics.
    keyword         TEXT    NOT NULL,
    PRIMARY KEY (token_slug, keyword)
);


-- ---------------------------------------------------------------------------
-- token_effects
-- Continuous/static effects for tokens that cannot be expressed as a keyword string.
-- e.g. Frostbite cost increase, Embodiment of Earth conditional defense bonus.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS token_effects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    token_slug      TEXT    NOT NULL,

    -- Type of continuous effect:
    --   'cost_increase'       — effect_params: {amount: N} — all cards cost N more for the token's controller
    --   'defense_bonus'       — effect_params: {amount: N, condition: str} — conditional defense modifier
    --   'prevent_damage'      — effect_params: {amount: N} — static damage prevention per instance
    --   'grant_keyword_static'— effect_params: {keyword: str, target: 'controller'|'opponent'|'permanent'}
    --   'custom'              — Python function named in effect_fn
    effect_type     TEXT    NOT NULL,
    effect_params   TEXT    NOT NULL DEFAULT '{}',
    effect_fn       TEXT
);

CREATE INDEX IF NOT EXISTS idx_token_effects_slug ON token_effects(token_slug);


-- ---------------------------------------------------------------------------
-- card_costs
-- Override cost data for cards whose cost != their cost field
-- (e.g. equipment with activation cost in functional text).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS card_costs (
    slug            TEXT    PRIMARY KEY,
    play_cost       INTEGER,            -- NULL = use card data field
    activation_cost INTEGER             -- NULL = use equipment_activations
);

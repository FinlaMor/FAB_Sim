# engine/ — Module Reference

## Entry Points

### `engine.py` (1694 lines)
**Does:** Complete game loop. Turn phases, action dispatch, combat resolution.
**Key functions:**
- `new_game()` — initialise GameState from deck paths + agents
- `run_game()` — step through game until done or max_turns
- `_start_of_turn()` — CR 4.3: draw, reset resources, aura upkeep
- `_end_turn()` — CR 4.4: pitch ordering, hand replenishment
- `_apply_action()` — routes to step-specific handlers
- `_apply_attack_step()`, `_apply_defend_declare()`, `_apply_reaction_step()`, `_calculate_damage()`
- `_setup_static_ability_listeners()` — wires keyword statics (Piercing etc.) at game start
**Imports from:** state, actions, play, effects, card_effects.triggers, card_effects.effect_cost

---

### `play.py` (594 lines)
**Does:** Higher-level action interface used by agents and engine.
**Key functions:**
- `available_actions(state, player_id)` — combines playability + affordability checks; always includes PASS
- `apply_action(state, action)` — applies a chosen action to state
- `recalculate_playable()`, `recalculate_activatable()` — refresh card flags based on continuous effects
- `_legality_check()` — keyword/type-based gate (e.g. Instant-only windows)
- `_cost_check()` — affordability given current resources + pitch
**Note:** This is the layer agents interact with. `engine.py` calls lower-level `_apply_*` directly.

---

## State

### `state.py` (1273 lines)
**Does:** All game data structures. Zone entry rules.
**Key classes:**
- `GameState` — top-level: players dict, step, combat, event_manager, effect_manager, chain_links
- `Player` — zones (hand, deck, graveyard, arsenal, pitch, banished, permanents, items, auras, allies, equipment slots), stats, resources
- `CombatState` — attack_card, attack_power, defending_cards, keywords, from_weapon, defender_used_hand_card, is_dagger_attack, is_stealth_attack
- `Zone` — list of Cards with `add()`/`remove()` that update `card.zone`/`card.prev_zone`
- `ZoneEntryResult` — ALLOW / CLEAR / CEASE_TO_EXIST / FAIL (CR 3.0.11-12)
- `EventManager` — pub/sub for game events (start_of_turn, hit, on_play, etc.)
- `ChainLink` — snapshot of one resolved attack
- `StackEntry` — items on the effect stack
- `Step` (Enum) — BEGIN_GAME, START_OF_TURN, ACTION_PHASE, REACT_ATTACK, REACT_DEFENSE, DAMAGE, END_PHASE

---

## Action Generation

### `actions.py` (1086 lines)
**Does:** Generate the list of legal `Action` objects for the current game state and step.
**Key exports:**
- `ActionType` (Enum) — PASS, PLAY_CARD, DEFEND_CARDS, STORE_ARSENAL, ACTIVATE_CARD, ATTACK_ALLY, CHOOSE, PITCH_CARD, PITCH_TO_DECK (several more commented out, pending implementation)
- `Action` (dataclass) — type, player_id, card, pitch_cards, from_arsenal, slot, target, targets, has_go_again, played_as_instant, etc.
- `legal_actions(state, player_id)` — main entry point; dispatches by `state.step`
- `can_pay_cost(state, player_id, cost)` — resource check
- `get_defendable_cards(state, player_id)` — cards eligible to block
**Imports registries from:** `card_effects/registry.py` for per-card conditions

---

## Effect Systems

### `effect_keywords.py` (3659 lines) — CR 8.5
**Does:** Primitive effect functions. These are the atomic operations all card effects compose from.
**Available primitives:**
`draw`, `gain`, `lose`, `banish`, `destroy`, `discard`, `deal_damage`, `deal_arcane_damage`,
`intimidate`, `create_token`, `put_counter`, `remove_counter`, `gets`, `gets_property`,
`look`, `reveal`, `put_object`, `roll`, `search`, `shuffle`, `name`, `opt`, `reload`, `turn`,
`add_defend`, `transcend`, `retrieve`, `return_to_brood`, `give`, `steal`, `wager`, `awaken`,
`contract`, `create_card`, `transform`, `attack`
**CR reference:** Each function docstring cites the relevant CR 8.5.x clause.

### `effects.py` (570 lines) — CR 6.2/6.3
**Does:** Continuous and replacement effect data structures.
**Key classes:**
- `ContinuousEffect` — source_card, source_type (LAYER/STATIC), stage (1-8), substage (1-7), mod_fn
- `EffectManager` — add/remove/query continuous effects; applies staging order
- `ModType` — ADD_PROPERTY, SET, MULTIPLY, DIVIDE, ADD, SUBTRACT, DEPENDENT
- `ReplacementEffect` — intercepts and redirects an event before it fires

### `continuous_effects.py` (212 lines) — CR 6.3
**Does:** Lower-level staging system + cost modifier pipeline (CR 5.1.6a).
**Key class:** `ContinuousEffectManager` — applies effects in stage/substage/timestamp order
**Note:** There are two `ContinuousEffect` definitions (effects.py and continuous_effects.py). The one in `continuous_effects.py` is the active staging implementation; `effects.py` version is the older model.

---

## Card Effects Layer

### `card_effects/registry.py` (3052 lines)
**Does:** All callable registries that map card slugs to effect functions. Also static abilities.
**Registries:**
- `PLAY_ABILITIES` — slug → fn(state, player_id, card_db, ...) — on-play effects
- `HIT_EFFECTS` — slug → fn(state, attacker_id, card_db) — on-hit effects
- `ATTACK_REACTION_CONDITIONS` — slug → fn(combat) → bool — AR targeting gate
- `ATTACK_REACTION_POWER` — slug → fn(combat, card) → int — AR power bonus
- `ATTACK_REACTION_EFFECTS` — slug → fn(state, player_id, card_db)
- `DEFENSE_REACTION_CONDITIONS` — slug → fn(combat) → bool
- `DEFENSE_REACTION_BONUS` — slug → fn(combat, card, from_arsenal) → int
- `EQUIPMENT_ACTIVATION_CONDITIONS` / `EQUIPMENT_ACTIVATION_COST`
- `HERO_ACTIVATION_CONDITIONS`
- `DISCARD_ACTIVATE_EFFECTS`, `PLAY_TARGET_CONDITIONS`, `WEAPON_ATTACK_CONDITIONS`
- `BLOCK_EFFECTS` — slug → fn(state, player_id) — on-block effects
- `PITCH_EFFECTS` — slug → fn(state, player_id) — end-turn pitch effects
- `AURA_START_OF_TURN_EFFECTS` — slug → fn(state, player_id, card_db) → bool
- `STATIC_ABILITY_ZONES`, `KEYWORD_STATIC_ABILITIES`, `CARD_STATIC_ABILITIES`
**Pattern:** Always look up by slug. Never use slug-prefix hacks or if-chains in engine.py.

### `card_effects/card_keywords.py` (1984 lines)
**Does:** Mechanic implementations for ability/label keywords + reusable effect primitives.
**Keyword mechanics:** `battleworn`, `blade_break`, `temper`, `guardwell`, `go_again`,
`dominate_check`, `overpower_check`, `piercing`, `phantasm_check`, `spectra_destroy`,
`blood_debt`, `suspense_*`, `watery_grave`, `boost`, `heave`, `crank`, `fusion`,
`arcane_barrier`, `spellvoid`, `ward`, `quell`, `arcane_shelter`, `crush_check`,
`reprise_check`, `combo_check`, `surge_check`, `rupture_check`, `channel_upkeep`, `galvanize`
**Effect primitives (wrappers over effect_keywords.py):**
`effect_draw`, `effect_discard`, `effect_banish`, `effect_deal_damage`, `effect_deal_arcane`,
`effect_gain_life`, `effect_lose_life`, `effect_gain_action_point`, `effect_gain_resources`,
`effect_destroy`, `effect_opt`, `effect_intimidate`, `effect_put_counter`, `effect_remove_counter`,
`effect_shuffle`, `effect_amp`, `effect_charge`
**Helper:** `reprise_active(combat)` — always use this, not `combat.defender_used_hand_card` directly

### `card_effects/triggers.py` (3505 lines)
**Does:** Trigger system. Maps cards to triggered effects via three tiers.
**Tiers:**
1. `KEYWORD_TRIGGERS` — auto-applied based on card keywords field (e.g. "Battleworn")
2. `text_trigger_parser` — auto-generated from functional_text (standard patterns)
3. `CARD_TRIGGERS` — manual per-card entries (highest priority, override parser)
**Key class:** `TriggerDef(event, condition_fn, effect_fn, once_per_turn)`
**Key function:** `get_triggers_for_card(card)` — returns all TriggerDefs for a card
**Events:** start_of_game, start_of_turn, start_of_action_phase, start_of_end_phase,
attacking, defend, combat_chain_close, damage_dealt, hit, on_play, card_destroyed,
enters_arena, target_of_attack, card_pitched, card_banished

### `card_effects/card_triggers_extended.py` (5473 lines)
**Does:** Houses the bulk of per-card `CARD_TRIGGERS` entries. Imported by triggers.py.
**Pattern:** Add entries here for any card whose triggers can't be auto-parsed by text_trigger_parser.

### `card_effects/text_trigger_parser.py` (1172 lines)
**Does:** Data-driven parser. Reads `card.functional_text`, recognises standard patterns
(e.g. "When this hits, draw a card"), returns `TriggerDef` list without manual coding.
**Skips:** Cards already in `CARD_TRIGGERS` (manual entries win).
**Add patterns here** when you see many cards share the same text template.

### `card_effects/effect_cost.py` (113 lines)
**Registries:** `ALTERNATE_COSTS` (e.g. banish cost), `KEYWORD_COSTS` (e.g. Chi payment)

### `card_effects/additional_conditions.py` / `additional_costs.py`
**Currently minimal** — extension points for card-specific play conditions and costs.

### `card_effects/db/`
- `loader.py` — loads slug_index, builds CardDB
- `db.py` — CardDB queries
- `generate_seed.py` — seed data utilities

---

## Adding a New Card — Quick Reference

1. **On-play effect** → add slug to `PLAY_ABILITIES` in registry.py
2. **On-hit effect** → add slug to `HIT_EFFECTS`
3. **Attack/Defense Reaction** → `ATTACK_REACTION_CONDITIONS` + `ATTACK_REACTION_POWER`/`DEFENSE_REACTION_BONUS`
4. **Triggered effect** (standard pattern) → add pattern to `text_trigger_parser.py`
5. **Triggered effect** (unique) → add `TriggerDef` to `card_triggers_extended.py`
6. **Static ability** → `CARD_STATIC_ABILITIES` or `KEYWORD_STATIC_ABILITIES` in registry.py
7. **Equipment activation** → `EQUIPMENT_ACTIVATION_CONDITIONS` + `EQUIPMENT_ACTIVATION_COST`

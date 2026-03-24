# Subtask 1-1: Local Engine Completeness Inventory

## 1. Game Phases — Implementation Status

| Phase | Step Enum | Function(s) | Status |
|-------|-----------|-------------|--------|
| Begin Game | `Step.BEGIN_GAME` | `new_game()` | **Complete** — coin flip, deck load, opening hands, trigger/prevention registration, `start_of_game` event |
| Start Phase (CR 4.2) | `Step.START_PHASE` | `_start_of_turn_phase()` | **Complete** — resets per-turn state (weapon, resources, AP, allies, equipment tracking), clears `end_of_next_turn` effects, emits `start_of_turn` |
| Action Phase (CR 4.3) | `Step.ACTION` | `_action_phase_iter()`, `_continue_action_phase()` | **Complete** — emits `start_of_action_phase`, grants 1 AP, enters priority loop; `_continue_action_phase` resumes after combat without re-emitting/re-granting |
| Combat — Layer Step (CR 7.1) | `Step.COMBAT_LAYER` | `_combat_phase_iter()` | **Complete** — resolves pending stack, priority loop before attack resolves |
| Combat — Attack Step (CR 7.2) | `Step.COMBAT_ATTACK` | `_attack_step()` | **Complete** — creates `CombatState`, applies turn attack effects, emits `attacking`, priority loop, recalculates power |
| Combat — Defend Step (CR 7.3) | `Step.COMBAT_DEFEND` | `_defend_step()` | **Complete** — defender declares cards, emits `defend` per card, priority loop |
| Combat — Reaction Step (CR 7.4) | `Step.COMBAT_REACTION` | `_reaction_step()` | **Complete** — priority loop for attack/defense reactions, recalculates power |
| Combat — Damage Step (CR 7.5) | `Step.COMBAT_DAMAGE` | `_damage_step()`, `_resolve_damage()` | **Complete** — calculates net damage, applies replacement/prevention effects, emits `hit` + `damage_dealt`, SBA check |
| Combat — Resolution Step (CR 7.6) | `Step.COMBAT_RESOLUTION` | `_resolution_step()` | **Complete** — emits `chain_link_resolves`, go_again AP grant, supports recursive chain links |
| Combat — Close Step (CR 7.7) | `Step.COMBAT_CLOSE` | `_close_step()`, `_close_combat_chain()` | **Complete** — emits `combat_chain_close`, resolves triggers, moves cards to graveyard, weapons stay equipped |
| End Phase (CR 4.4) | `Step.END_PHASE_BEGINNING`, `Step.END_PHASE_CLEANUP` | `_end_phase_iter()` | **Complete** — emits `start_of_end_phase`, arsenal from hand, pitch-to-deck-bottom (player-ordered), untap permanents, clear AP/resources, draw up to intellect, first-turn opponent draw-up, clear turn effects, emits `end_of_turn`, switch active player |
| End Game | `Step.END_GAME` | `check_state_based_actions()`, `_end_game_on_turn_cap()` | **Complete** — health<=0 check, turn-cap tiebreaker by life then active player |

**Summary: All 13 Step enum values have corresponding implementation. No game phase is stubbed or missing.**

---

## 2. Event Types Emitted

All events emitted via `EventManager.emit()` in `engine.py`:

| Event Type | Location | Context |
|------------|----------|---------|
| `start_of_game` | `new_game()` L117 | After trigger registration, before game loop |
| `start_of_turn` | `_start_of_turn_phase()` L231 | After clearing effects, before action phase |
| `start_of_action_phase` | `_action_phase_iter()` L247 | Beginning of action phase |
| `attacking` | `_attack_step()` L353 | Attack card placed on combat chain |
| `defend` | `_apply_defend()` L708 | Per defending card |
| `chain_link_resolves` | `_resolution_step()` L413 | Chain link resolved |
| `combat_chain_close` | `_close_step()` L466 | Combat chain closing |
| `start_of_end_phase` | `_end_phase_iter()` L494 | Beginning of end phase |
| `end_of_turn` | `_end_phase_iter()` L561 | After cleanup, before player switch |
| `hit` | `_resolve_damage()` L647 | Physical damage dealt > 0 |
| `damage_dealt` | `_resolve_damage()` L648 | Alongside `hit` with damage amount |
| `on_play` | `_apply_play_card()` L1027, `_apply_play_arsenal()` L1069, `_apply_play_banish()` L1114, `_apply_react()` L1256 | Card enters stack |
| `card_pitched` | Multiple `_apply_*` functions | Each card pitched for resources |

**Notable:** The `hit` listener `_clear_marked_on_hit` (L106-113) implements CR 9.3.3 (marked condition cleared on hit).

---

## 3. Action Types (ActionType Enum)

| ActionType | Legal Action Generator | Apply Function | Status |
|------------|----------------------|----------------|--------|
| `PASS` | All steps | N/A (no-op) | **Complete** |
| `ATTACK_WEAPON` | `_legal_action_step()` | `_apply_weapon_attack()` | **Complete** — pitch sequences, exhaust weapon, activated-layer on stack |
| `PLAY_CARD` | `_legal_action_step()`, `_legal_reaction_step()` | `_apply_play_card()` | **Complete** — hand cards, pitch, cost, AP deduction, meld support (top/bottom/both) |
| `PLAY_ARSENAL` | `_legal_action_step()`, `_legal_reaction_step()` | `_apply_play_arsenal()` | **Complete** — face-up arsenal cards, pitch from hand |
| `DEFEND_CARDS` | `_legal_defend_step()` | `_apply_defend()` | **Complete** — hand + equipment subsets, Dominate/Overpower restrictions |
| `DEFEND_EQUIPMENT` | Declared in enum | — | **Unused** — equipment defense is folded into `DEFEND_CARDS` via `_legal_defend_step()` |
| `STORE_ARSENAL` | Declared in enum | — | **Unused** — arsenaling is handled directly in `_end_phase_iter()` via `player_decision_raw()` |
| `PLAY_ATTACK_REACTION` | `_legal_reaction_step()` | `_apply_react()` | **Complete** — registry-driven conditions |
| `PLAY_DEFENSE_REACTION` | `_legal_reaction_step()` | `_apply_react()` | **Complete** — registry-driven conditions |
| `REACTION_PASS` | `_legal_reaction_step()` | N/A | **Complete** |
| `ACTIVATE_ITEM` | `_legal_action_step()` | `_apply_activate()` | **Complete** — registry dispatch |
| `ATTACK_ALLY` | Declared in enum | — | **Not implemented** — commented-out placeholder in `_legal_action_step()` L474-479 |
| `ACTIVATE_EQUIPMENT` | `_legal_action_step()` | `_apply_activate()` | **Complete** — registry-driven conditions/costs/effects |
| `ACTIVATE_WEAPON` | `_legal_action_step()` | `_apply_activate()` | **Complete** — non-attacking weapon abilities |
| `ACTIVATE_HERO` | `_legal_action_step()` | `_apply_activate_hero()` | **Complete** — registry-driven, supports tap/pay/target |
| `DISCARD_ACTIVATE` | `_legal_action_step()` | `_apply_discard_activate()` | **Complete** — "Instant - Discard this:" hand abilities |
| `PLAY_BANISH` | `_legal_action_step()` | `_apply_play_banish()` | **Complete** — trap-door/infiltrate flagged cards |

**Summary: 14 of 17 ActionTypes are fully implemented. 3 are declared but unused/not-implemented (`DEFEND_EQUIPMENT`, `STORE_ARSENAL`, `ATTACK_ALLY`), though the first two have equivalent functionality elsewhere.**

---

## 4. Known TODOs, Stubs, and Future-Code Comments

| File | Line | Text | Severity |
|------|------|------|----------|
| `engine.py` | L47 | `"Reveal Heroes - for future code, reveal hero cards to both players then they decide on which cards to include in deck."` | Low — pre-sideboard decks work; hero reveal is a draft/sideboard feature |
| `engine.py` | L502 | `"4.4.3a: ally life totals reset (TODO when allies are implemented)"` | **Medium** — ally mechanics not implemented |
| `actions.py` | L474-479 | `"ATTACK_ALLY - Placeholder"` (commented-out code) | **Medium** — ally attacks not implemented |
| `state.py` | L196 | `"inventory zone is for future code"` | Low — sideboard/inventory zone exists but unused |

---

## 5. Missing / Incomplete Game Mechanics

| Mechanic | Status | Evidence |
|----------|--------|----------|
| **Allies** | Not implemented | `ATTACK_ALLY` commented out (actions.py L474); ally life reset TODO (engine.py L502); `allies_exhausted` tracking exists but no attack/damage logic |
| **Evo Upgrade** | Not implemented | No references to "evo" or "upgrade" in engine/actions/effects/state |
| **Transform** | Not implemented | No transform logic in any core file |
| **Transcend** | Not implemented | No transcend logic in any core file |
| **Soul zone mechanics** | Partial | `Player.soul` Zone exists (state.py L210) but no engine logic uses it |
| **Token creation** | Partial | `Player.tokens` Zone exists (state.py L209) but no token generation logic in engine.py |
| **Aura mechanics** | Partial | `Player.auras` Zone exists (state.py L207) but no aura lifecycle management |
| **Arcane damage (non-combat)** | Partial | Prevention effects handle arcane damage type; no standalone arcane damage source in engine.py (relies on card effects) |
| **Hero reveal / sideboarding** | Not implemented | Noted as "future code" in engine.py L47 |
| **Multiple weapon zones** | Implemented | `weapon1`/`weapon2` Zones exist with backward-compat `weapon` property; only `weapon1` (`player.weapon.top`) used in action generation |
| **Dominate keyword** | Implemented | Enforced in `_legal_defend_step()` — limits hand defense cards to 1 |
| **Overpower keyword** | Implemented | Enforced in `_legal_defend_step()` — limits action card defense to 1 |
| **Go Again** | Implemented | Checked in `_resolution_step()` (combat) and `resolve_stack()` (non-combat) |
| **Meld** | Implemented | Full 3-mode support (top/bottom/both) with two-pass resolution in `resolve_stack()` |
| **Battleworn / Temper / Blade Break** | Tracked | `equipment_defended_this_turn` exists in Player; actual keyword logic delegated to card_effects |
| **Marked condition (CR 9.3)** | Implemented | `Player.marked` bool + global `_clear_marked_on_hit` listener |
| **Continuous effects (CR 6.2-6.3)** | Implemented | Full staging system (stages 1-8, substages 1-7) in `EffectManager` |
| **Replacement effects (CR 6.4)** | Implemented | Self/Identity/Standard/Prevention/Outcome ordering |
| **Prevention keywords** | Implemented | Ward, Arcane Barrier, Spellvoid, Quell, Arcane Shelter — all built as `ReplacementEffect` objects |
| **Pitch system (CR 5.1.6-7)** | Implemented | `find_all_valid_pitch_sequences()` generates all valid combinations |
| **Priority system (CR 1.10)** | Implemented | `priority_loop()` with consecutive-pass tracking, stack resolution |
| **Stack/Layer system (CR 3.15)** | Implemented | `StackEntry` with card/activated/triggered layer types, LIFO resolution |
| **Last-Known Information** | Implemented | `GameState.remember_last_known()`, `get_last_known()`, `process_cease_to_exist()` |

---

## 6. Effect System Completeness (effects.py)

| Component | Status |
|-----------|--------|
| `ContinuousEffect` dataclass | **Complete** — source, stage, substage, mod_type, duration, condition/target/apply functions |
| `EffectSource` enum (LAYER, STATIC) | **Complete** |
| `ModType` enum (ADD_PROPERTY, SET, MULTIPLY, DIVIDE, ADD, SUBTRACT, DEPENDENT) | **Complete** — all 7 substages |
| `ReplacementEffect` dataclass | **Complete** — condition, replace, consumed, prevention_amount, shielding |
| `ReplacementType` enum (SELF, IDENTITY, STANDARD, PREVENTION, OUTCOME) | **Complete** — all 5 types |
| `EffectManager.apply_continuous_effects()` | **Complete** — staged ordering |
| `EffectManager.apply_replacements()` | **Complete** — type-ordered application |
| `EffectManager.clear_turn_effects()` | **Complete** — CR 6.2.2a |
| `EffectManager.clear_start_of_turn_effects()` | **Complete** — CR 4.2.2 |
| Prevention builders: Ward, Arcane Barrier, Spellvoid, Quell, Arcane Shelter | **Complete** |

---

## 7. State Model Completeness (state.py)

| Component | Status |
|-----------|--------|
| `Step` enum (13 values) | **Complete** |
| `Zone` class | **Complete** — add, remove, find, pop_top, pop_last, extend, add_bottom, to_dict |
| `EventManager` | **Complete** — register/emit with Event objects or strings |
| `Event` dataclass | **Complete** — type, card, target, data |
| `TriggeredAbility` | **Complete** — register, trigger (creates StackEntry), resolve |
| `Player` class (18 zones) | **Complete** — hand, deck, arsenal, inventory, graveyard, banished, head, chest, arms, legs, weapon1, weapon2, items, auras, allies, tokens, soul, hero_zone, pitch |
| `StackEntry` dataclass | **Complete** — layer types, meld two-pass, modal/targeting metadata |
| `ChainLink` dataclass | **Complete** — attack resolution record |
| `CombatState` dataclass | **Complete** — attacker, defender, power, defense, keywords, equipment tracking |
| `GameState` dataclass | **Complete** — players, stack, combat_chain, chain_links, pitch_history, LKI cache, serialization |

---

## Summary

The local engine core is **substantially complete** for the Classic Constructed game flow. All game phases, the priority system, stack/layer resolution, continuous/replacement effects, and the combat chain are fully implemented. The primary gaps are:

1. **Ally mechanics** — zones exist but attack/damage/life-reset logic is missing
2. **Evo Upgrade / Transform / Transcend** — newer FAB mechanics with no implementation
3. **Soul zone usage** — zone exists but unused by engine logic
4. **Token generation** — zone exists but no creation logic
5. **Second weapon zone** — `weapon2` exists but action generation only checks `weapon1`
6. **Card effect coverage** — the engine framework is complete, but only ~118 card-specific triggers are implemented (see subtask-1-2)

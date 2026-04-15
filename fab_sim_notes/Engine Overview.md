# Engine Overview

See also: [[Architecture Hub]] | [[Card Effects System]] | [[Work Tracks]]

## What the engine/ folder does
Implements FAB Comprehensive Rules as a Python state machine. A game is a sequence of `GameState` snapshots advanced by agent-chosen `Action` objects.

## Data Flow

```
play.available_actions()    ← playability + affordability
  ↓
actions.legal_actions()     ← filter by game step + card conditions
  ↓
Agent picks action
  ↓
play.apply_action()         ← change gamestate according to action selection
  ↓
engine._apply_*()           ← step-specific logic
  ↓
effect_keywords.*()         ← draw / damage / banish / etc (CR 8.5)
registry.*()                ← card-specific effects
triggers.*()                ← fire registered triggers
continuous_effects.*()      ← apply ongoing modifiers
```

## Turn Phase Flow (engine.py)

```
START_OF_TURN
  → _start_of_turn(): draw, resource reset, aura upkeep
ACTION_PHASE
  → agent chooses: play card / attack / pass
  → REACT_ATTACK: attack reaction window
  → REACT_DEFENSE: defense reaction window
  → DAMAGE: _calculate_damage()
  → combat_chain_close or pass
END_PHASE
  → _end_turn(): pitch ordering, draw to intellect
```

## Key Classes

### GameState (`state.py`)
Top-level container. Has:
- `players: dict[int, Player]`
- `step: Step` — current phase
- `combat: CombatState | None` — active during combat
- `event_manager: EventManager` — pub/sub events
- `effect_manager: EffectManager` — continuous effects
- `chain_links: list[ChainLink]` — resolved attack history

### Player (`state.py`)
All zones + stats:
- Zones: `hand`, `deck`, `graveyard`, `arsenal`, `pitch`, `banished`, `permanents`, `items`, `auras`, `allies`
- Equipment: `head`, `chest`, `arms`, `legs`, `weapon1`, `weapon2`
- Stats: `life`, `resources`, `action_points`, `intellect`
- `class_counters: dict` — arbitrary per-card counters (Chi, booed_this_turn, etc.)

### CombatState (`state.py`)
Lives during an attack:
- `attack_card`, `attack_power`, `defending_cards`, `defending_equipment_defense`
- `keywords: set` — e.g. "Dominate", "Piercing", "Stealth"
- `from_weapon: bool`
- `defender_used_hand_card: bool` — Reprise trigger
- `is_dagger_attack`, `is_stealth_attack` — for Arakni/HNT

### Zone (`state.py`)
- `Zone.add(card)` — sets `card.zone = self.name`
- `Zone.remove(card)` — sets `card.prev_zone = card.zone`
- **Always pair remove → add** to keep zone tracking accurate

## Effect Systems

### Continuous Effects (CR 6.2/6.3)
Two files with overlapping roles:
- `effects.py` — `ContinuousEffect`, `EffectManager`, `ReplacementEffect` (higher-level model)
- `continuous_effects.py` — `ContinuousEffectManager` with staging/substage/timestamp ordering

Stages 1-8 per CR 6.3.2. Within a stage, substages 1-7 determine apply order (set before add, etc.).

### Replacement Effects (CR 6.4)
Intercept an event before it fires and redirect it (e.g. "prevent the next N damage").

## Key Invariants
- Effect functions **mutate state in place** — never return new state
- Legal action generation must be **pure** (no state mutation)
- `card.owner` is immutable (player that brought the card to the table)
- `card.controller` changes with regular play/gain-control effects
- Tokens cease to exist entering graveyard/banished (CR 3.0.12a — `ZoneEntryResult.CEASE_TO_EXIST`)

## Known Gaps
See [[Work Tracks#Track 1 — Engine Rules]]

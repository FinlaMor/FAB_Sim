# FAB Simulator — Architecture Guide

## Project Goal
Offline Flesh and Blood simulator → AlphaZero-style self-play model.
Priority: engine correctness → card coverage → IQL training → deck evaluation.

---

## Layer Map (top-down)

```
┌─────────────────────────────────────────────┐
│  rl_agents/        Training & evaluation     │
│  encoder/          State → tensors           │
│  draft/            Draft format support      │
├─────────────────────────────────────────────┤
│  engine/           Core rules engine         │
│    ├── engine.py         Game loop           │
│    ├── play.py           Action dispatch     │
│    ├── actions.py        Legal action gen    │
│    ├── state.py          Data structures     │
│    ├── effects.py        Continuous effects  │
│    ├── effect_keywords.py  CR 8.5 primitives │
│    └── card_effects/    Card implementations │
│         ├── registry.py      Registries      │
│         ├── card_keywords.py Keyword impls   │
│         ├── triggers.py      Trigger system  │
│         ├── card_triggers_extended.py        │
│         └── text_trigger_parser.py           │
├─────────────────────────────────────────────┤
│  card_data/        Slug index, card CSV      │
│  data/             Gamestates, replays       │
└─────────────────────────────────────────────┘
```

---

## Module Responsibilities

| File | Responsibility | Key exports |
|------|---------------|-------------|
| `engine/engine.py` | Game loop, turn phases, action dispatch | `new_game()`, `run_game()` |
| `engine/play.py` | Playability check + action application | `available_actions()`, `apply_action()` |
| `engine/actions.py` | Legal action generation per game step | `legal_actions()`, `Action`, `ActionType` |
| `engine/state.py` | All game data structures | `GameState`, `PlayerState`, `CombatState`, `Zone`, `EventManager` |
| `engine/effects.py` | CR 6.2/6.3 continuous/replacement effects | `ContinuousEffect`, `EffectManager`, `ModType` |
| `engine/continuous_effects.py` | CR 6.3 staging system + cost pipeline | `ContinuousEffectManager` |
| `engine/effect_keywords.py` | CR 8.5 effect primitives | `draw`, `gain`, `banish`, `destroy`, `deal_damage`, etc. |
| `engine/card.py` | Card data model and database | `Card`, `CardDB` |
| `engine/deck.py` | Deck loading, player creation | `load_deck()`, `create_player()` |
| `engine/context.py` | Effect context flag | `is_effect_context()` |
| `card_effects/registry.py` | All card registries + static abilities | `PLAY_ABILITIES`, `HIT_EFFECTS`, `ATTACK_REACTION_CONDITIONS`, etc. |
| `card_effects/card_keywords.py` | Keyword mechanic implementations + effect primitives | `battleworn`, `go_again`, `dominate`, `effect_draw`, etc. |
| `card_effects/triggers.py` | Trigger registry, keyword→trigger mapping | `TriggerDef`, `CARD_TRIGGERS`, `get_triggers_for_card()` |
| `card_effects/card_triggers_extended.py` | Per-card trigger definitions | Extends `CARD_TRIGGERS` |
| `card_effects/text_trigger_parser.py` | Parse card functional_text → TriggerDef | `parse_triggers_from_text()` |
| `card_effects/effect_cost.py` | Alternate and keyword costs | `ALTERNATE_COSTS`, `KEYWORD_COSTS` |
| `card_effects/db/` | Card database loader | `loader.py`, `db.py` |

---

## Data Flow: A Single Game Action

```
Agent selects action
  → play.available_actions()      check playability + affordability
  → actions.legal_actions()       filter by game step + card conditions
  → play.apply_action()           execute the action
      → engine._apply_*()         step-specific logic
          → effect_keywords.*()   primitive effects (draw, damage, etc.)
          → registry.*()          card-specific effects (HIT_EFFECTS etc.)
          → triggers.*()          fire registered triggers
          → effects / continuous_effects  apply ongoing modifiers
```

---

## Two Work Tracks

### Track 1 — Engine Rules Completeness
Goal: full CR coverage so any legal FAB play is correctly modelled.

- `effect_keywords.py` — CR 8.5 effect primitives (~80% done)
- `continuous_effects.py` — CR 6.3 layer/staging system (partially implemented)
- `actions.py` — some `ActionType` variants still commented out
- See `fab_sim_notes/Work Tracks.md` for checklist

### Track 2 — Card Implementation
Goal: every card in target decks has correct effects registered.

- Registries: `card_effects/registry.py` (PLAY_ABILITIES, HIT_EFFECTS, etc.)
- Triggers: `card_effects/triggers.py` + `card_triggers_extended.py`
- Parser: `text_trigger_parser.py` auto-generates common patterns
- See `fab_sim_notes/Card Set Status.md` for per-set progress

---

## Key Invariants
- All zone moves go through `Zone.remove()` → `Zone.add()` (keeps `card.zone` accurate)
- Effect functions mutate `state` in place — never return new state
- Legal action generation must be pure (no state mutation)
- `card.owner` is immutable; `card.controller` changes with gain-control effects
- Tokens cease to exist on entry to graveyard/banished (CR 3.0.12a)

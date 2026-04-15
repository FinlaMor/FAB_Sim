# Card Effects System

See also: [[Architecture Hub]] | [[Engine Overview]] | [[Card Set Status]]

## Folder: `engine/card_effects/`

This layer bridges the rules engine and individual card text. It has three sub-systems:

---

## 1. Registries (`registry.py`)
Dict maps: `slug → callable`. The engine looks up slugs here — never uses if-chains. might use slug-prefix hacks for color variants.

| Registry | When called | Signature |
|----------|-------------|-----------|
| `PLAY_ABILITIES` | Card played | `fn(state, player_id, card_db, from_arsenal, from_item, **kw)` |
| `HIT_EFFECTS` | Attack hits | `fn(state, attacker_id, card_db)` |
| `ATTACK_REACTION_CONDITIONS` | AR targeting gate | `fn(combat) → bool` |
| `ATTACK_REACTION_POWER` | AR power bonus | `fn(combat, card) → int` |
| `ATTACK_REACTION_EFFECTS` | AR on-play effect | `fn(state, player_id, card_db)` |
| `DEFENSE_REACTION_CONDITIONS` | DR targeting gate | `fn(combat) → bool` |
| `DEFENSE_REACTION_BONUS` | DR defense bonus | `fn(combat, card, from_arsenal) → int` |
| `EQUIPMENT_ACTIVATION_CONDITIONS` | Equipment activate | `fn(state, player_id) → bool` |
| `EQUIPMENT_ACTIVATION_COST` | Equipment cost | `fn(state, player_id)` |
| `HERO_ACTIVATION_CONDITIONS` | Hero ability gate | `fn(state, player_id) → bool` |
| `BLOCK_EFFECTS` | Card blocks | `fn(state, player_id)` |
| `PITCH_EFFECTS` | Card pitched end-turn | `fn(state, player_id)` |
| `AURA_START_OF_TURN_EFFECTS` | Aura upkeep | `fn(state, player_id, card_db) → bool` |
| `DISCARD_ACTIVATE_EFFECTS` | Discard-to-activate | `fn(state, player_id, card_db)` |
| `PLAY_TARGET_CONDITIONS` | Target selection gate | `fn(state, player_id, target) → bool` |
| `WEAPON_ATTACK_CONDITIONS` | Weapon attack gate | `fn(state, player_id) → bool` |

**Static ability registries:**
- `STATIC_ABILITY_ZONES` — event → fn(state) → list[Card] (which cards to inspect)
- `KEYWORD_STATIC_ABILITIES` — keyword_prefix → fn(n, state, card) (e.g. Piercing)
- `CARD_STATIC_ABILITIES` — slug → list[tuple[event, fn(event, state, card)]]

---

## 2. Keyword Implementations (`card_keywords.py`)
Implements the game mechanics behind ability/label keywords.

**Ability Keywords (CR 8.3):** `battleworn`, `blade_break`, `temper`, `guardwell`, `go_again`, `boost`, `heave`, `crank`, `arcane_barrier`, `spellvoid`, `ward`, `quell`, `galvanize`, `channel_upkeep`

**Label Keywords (CR 8.4):** `combo_check`, `crush_check`, `reprise_check`, `surge_check`, `rupture_check`, `dominate_check`, `overpower_check`, `phantasm_check`, `fusion`

**Effect primitives (thin wrappers over effect_keywords.py):**
`effect_draw`, `effect_discard`, `effect_banish`, `effect_deal_damage`, `effect_deal_arcane`, `effect_gain_life`, `effect_lose_life`, `effect_gain_action_point`, `effect_gain_resources`, `effect_destroy`, `effect_opt`, `effect_intimidate`, `effect_put_counter`, `effect_remove_counter`, `effect_shuffle`, `effect_amp`, `effect_charge`

**Important helper:**
```python
reprise_active(combat)  # always use this — never combat.defender_used_hand_card directly
```

---

## 3. Trigger System (`triggers.py` + `card_triggers_extended.py` + `text_trigger_parser.py`)

Three tiers, applied in this priority order:

```
KEYWORD_TRIGGERS          lowest priority (auto from card.keywords field)
text_trigger_parser       middle (auto from card.functional_text)
CARD_TRIGGERS             highest priority (manual, override everything)
```

### TriggerDef
```python
TriggerDef(
    event: str,           # e.g. "hit", "on_play", "start_of_turn"
    condition_fn,         # fn(card, event, state) → bool
    effect_fn,            # fn(card, event, state) → None
    once_per_turn: bool
)
```

### Events emitted by engine
`start_of_game`, `start_of_turn`, `start_of_action_phase`, `start_of_end_phase`,
`attacking`, `defend`, `combat_chain_close`, `damage_dealt`, `hit`, `on_play`,
`card_destroyed`, `enters_arena`, `target_of_attack`, `card_pitched`, `card_banished`

---

## 4. Cost System (`effect_cost.py`)
- `ALTERNATE_COSTS` — e.g. banish a card instead of paying resources
- `KEYWORD_COSTS` — e.g. Beat Chest, Scrap

---

## Adding a New Card — Decision Tree

```
Does it have an on-play effect?
  YES → PLAY_ABILITIES[slug] = fn

Does it hit and do something?
  YES → HIT_EFFECTS[slug] = fn

Is it an Attack Reaction?
  Add targeting gate → ATTACK_REACTION_CONDITIONS[slug]
  Add power bonus   → ATTACK_REACTION_POWER[slug]
  Add other effect  → ATTACK_REACTION_EFFECTS[slug]

Is it a Defense Reaction?
  Add targeting gate → DEFENSE_REACTION_CONDITIONS[slug]
  Add defense bonus  → DEFENSE_REACTION_BONUS[slug]

Does it have a triggered ability?
  Matches a common text pattern?
    YES → add pattern to text_trigger_parser.py
    NO  → add TriggerDef to card_triggers_extended.py

Is it equipment with an activation?
  → EQUIPMENT_ACTIVATION_CONDITIONS + EQUIPMENT_ACTIVATION_COST

Is it a static ability?
  Keyword-based? → KEYWORD_STATIC_ABILITIES
  Card-specific? → CARD_STATIC_ABILITIES[slug]
```

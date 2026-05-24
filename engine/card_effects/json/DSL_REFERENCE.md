# Card Effect DSL Reference

JSON schema patterns for card effect definitions. All files live under `json/<set>/`.

---

## Top-Level Structure

```json
{
  "slug": "card_slug",
  "cost": { ... },
  "conditions": { ... },
  "abilities": [ ... ]
}
```

| Field | Required | Description |
|---|---|---|
| `slug` | Yes | Unique card identifier |
| `cost` | No | Additional cost to **play** the card (play-time only) |
| `conditions` | No | Targeting or play restrictions (e.g. AR target must be Ninja) |
| `abilities` | Yes | Array of ability objects |

---

## Target Object (inside ability)

Declares a targeted effect per CR 1.8.5. The player must declare a legal target when the card is put on the stack. The ability is illegal to play if no legal target exists. Legal targets are any public objects in the arena or on the stack that pass the filter.

```json
"target": {
  "filter": [
    {"type": "ATTACK_CLASS_IN", "classes": ["Ninja"]},
    {"type": "ATTACK_TYPE_IN", "types": ["Action"]},
    {"type": "ATTACK_SUBTYPE_IN", "subtypes": ["Attack"]}
  ]
}
```

The `filter` array uses the same condition objects as ability-level `conditions`. All filter conditions must pass for an object to be a legal target. Boolean logic (`AND`, `OR`, `NOT`) is supported.

Do not use ability-level `conditions` to restrict targeting — conditions check game state at resolution time, targets are declared at play time (CR 5.1.4).

---

## Cost Object (top-level)

Used for additional costs to play the card. Activated ability costs go inside the ability's own `cost` field.

```json
"cost": {
  "play_activate": "PLAY",
  "optional": "FALSE",
  "type": "DISCARD_RANDOM",
  "amount": 1
}
```

| Field | Values | Description |
|---|---|---|
| `play_activate` | `"PLAY"` | When the cost is paid |
| `optional` | `"TRUE"` / `"FALSE"` | Whether the cost is optional |
| `type` | effect type string | The cost effect |
| `amount` | integer | How many / how much |

---

## Ability Object

```json
{
  "ability_type": "TRIGGERED",
  "trigger": "ON_CRUSH",
  "conditions": [ ... ],
  "cost": [ ... ],
  "additional_cost": [ ... ],
  "choose": 1,
  "modes": [ ... ],
  "effects": [ ... ]
}
```

### `ability_type` Values

| Value | Description | CR Reference |
|---|---|---|
| `PLAY` | Resolves when the card is played | 1.7.4c |
| `ACTION` | Non-attack action card effect | — |
| `ACTIVATE` | Activated ability (once per turn unless noted) | 1.7.3a |
| `INSTANT` | Activated ability usable as an instant | 1.7.4b |
| `ATTACK_REACTION` | Played in the reaction step targeting current attack | 7.4 |
| `DEFENSE_REACTION` | Played in the reaction step while defending | 7.4 |
| `MODAL` | Mode selected at play time; chosen mode becomes base ability | 1.7.5, 1.7.5a |
| `WHILE_STATIC` | Applies continuously while a `conditions` array is satisfied | 1.7.4g, 5.4.7 |
| `PLAY_STATIC` | Functional when source is public and being played (e.g. "play from banished zone") | 1.7.4e, 5.4.4 |
| `PROPERTY_STATIC` | Defines a property by formula; functional in any zone at all times | 1.7.4f, 5.4.5 |
| `STATIC_TRIGGERED` | Always watching; fires a triggered-layer each time the trigger condition is met ("whenever / at") | 1.7.3, 6.6.4 |
| `DELAYED_TRIGGERED` | Created once, persists until the trigger condition is met, then fires and expires ("the next time") | 6.6.3 |
| `TRIGGERED_STATIC` | Static ability that triggers when source meets a condition while outside the arena | 1.7.4i |

### `trigger` Values

| Value | Description |
|---|---|
| `ON_ATTACK` | When the card attacks (enters combat chain) |
| `ON_HIT` | When the attack hits |
| `ON_CRUSH` | When the attack crushes (deals 4+ damage) |
| `ON_PLAY_ACTIVATE_ATTACK` | When the affected player plays or activates an attack |
| `START_OF_TURN` | At the start of the controller's turn |

### Ability-level `cost` (activated abilities only)

Array of effect objects representing the cost to activate.

```json
"cost": [
  {"type": "DESTROY_PERMANENT", "target": "self"}
]
```

### `additional_cost` (play abilities)

Array of effect objects representing extra costs paid when playing.

```json
"additional_cost": [
  {"type": "REMOVE_COUNTERS", "counter_type": "energy", "amount": 3}
]
```

### Modal Abilities

```json
{
  "ability_type": "MODAL",
  "choose": 1,
  "modes": [
    {"type": "MODIFY_ATTACK", "mod": "add", "amount": 2},
    {"type": "GAIN", "keyword": "GO_AGAIN"},
    {"type": "DRAW", "amount": 1}
  ]
}
```

Modes are selected when the card is added to the stack (CR 1.7.5a). The chosen mode becomes the card's base ability and is non-functional until the source is in the arena (CR 1.7.4).

---

## Effect Objects

All effects use `{"type": "EFFECT_TYPE", ...}`. Effects are always arrays.

### Attack Power

```json
{"type": "MODIFY_ATTACK", "mod": "add", "amount": 4}
{"type": "MODIFY_ATTACK", "mod": "add", "amount": -2}
{"type": "MODIFY_NEXT_ATTACK", "mod": "add", "conditions": [...], "amount": 3}
```

| Type | Description |
|---|---|
| `MODIFY_ATTACK` | Modifies the current attack's power |
| `MODIFY_NEXT_ATTACK` | Modifies the next qualifying attack's power |

`mod` values: `"add"` (subtraction uses negative `amount`). Future values: `"multiply"`, `"set"`.

`MODIFY_NEXT_ATTACK` takes an optional `conditions` array to filter which attacks it applies to.

### Gain (Asset)

```json
{"type": "GAIN", "asset": "RESOURCE_POINTS", "amount": 1}
{"type": "GAIN", "asset": "LIFE_POINTS", "amount": 3}
{"type": "GAIN", "asset": "ACTION_POINTS", "amount": 1}
{"type": "GAIN", "asset": "CHI_POINTS", "amount": 1}
```

Asset types match CR 1.13.1. Do not use `GAIN_RESOURCES`, `GAIN_LIFE`, etc.

### Gain (Keyword)

```json
{"type": "GAIN", "keyword": "GO_AGAIN"}
```

Used in modal modes where the card gains a keyword as a base ability.

### Draw / Discard

```json
{"type": "DRAW", "amount": 1}
{"type": "DISCARD", "player": "DEFENDING", "amount": 1}
{"type": "DISCARD_RANDOM", "amount": 1}
```

### Counters

```json
{"type": "PUT_COUNTER", "counter_type": "energy", "amount": 1}
{"type": "REMOVE_COUNTERS", "counter_type": "energy", "amount": 3}
```

### Zone Movement

```json
{"type": "PUT_HAND_CARD_BOTTOM", "optional": "TRUE", "conditional_effect": {"type": "DRAW", "amount": 1}}
{"type": "PUT_ARSENAL_BOTTOM", "player": "OPPONENT"}
```

`optional: "TRUE"` means the effect may be skipped. `conditional_effect` fires only if the optional effect was taken.

### Destroy

```json
{"type": "DESTROY_PERMANENT", "target": "self"}
```

| `target` | Description |
|---|---|
| `"self"` | Destroys the source card |

### Roll

```json
{"type": "ROLL", "faces": 6}
```

The result is referenced by subsequent effects using a string `amount` value:

| String | Meaning |
|---|---|
| `"ROLL_NUMBER"` | The full die result |
| `"ROLL_NUMBER_HALF_ROUND_DOWN"` | The result divided by 2, rounded down |

### Intimidate

```json
{"type": "INTIMIDATE"}
```

Opponent banishes a random card from hand face-down; returned at end phase (CR 8.5.10).

### Choose (runtime choice)

```json
{
  "type": "CHOOSE",
  "amount": 1,
  "options": [ ... ]
}
```

Player chooses `amount` options at resolution time. Distinct from `MODAL` (which chooses at play time).

### Inject Trigger

```json
{
  "type": "INJECT_TRIGGER",
  "object": "OPPONENT",
  "trigger": "ON_PLAY_ACTIVATE_ATTACK",
  "consume": true,
  "span": "NEXT_TURN",
  "conditions": [ ... ],
  "effects": [ ... ]
}
```

Registers a deferred trigger on a player or object.

| Field | Description |
|---|---|
| `object` | Who the trigger is registered on (`"OPPONENT"`, `"PLAYER"`) |
| `trigger` | The trigger event |
| `consume` | If `true`, fires once then removes itself |
| `span` | How long the trigger persists before expiring if unused |

### Inject Replacement

```json
{
  "type": "INJECT_REPLACEMENT",
  "object": "PLAYER",
  "replace": {"type": "DRAW"},
  "with": "NO_EFFECT",
  "span": "NEXT_TURN"
}
```

Registers a replacement effect. When the `replace` event would occur, it is replaced by `with` instead.

### Apply Continuous

```json
{
  "type": "APPLY_CONTINUOUS",
  "target": "OPPONENT_CARDS",
  "filter": { ... },
  "modifications": [ ... ],
  "span": "NEXT_ACTION_PHASE"
}
```

Applies a continuous property modification to matching objects (CR 8.5.13).

| `target` | Description |
|---|---|
| `"OPPONENT_CARDS"` | All cards controlled by the opponent |
| `"PLAYER_ATTACKS"` | All attacks the controller makes this turn |

The optional `filter` narrows which objects are affected. Uses the same condition objects as `conditions` arrays.

#### Modifications

```json
{"type": "LOSES", "property": "GO_AGAIN"}
{"type": "CANT_GAIN", "property": "GO_AGAIN"}
```

| Type | CR Reference | Description |
|---|---|---|
| `LOSES` | 8.5.13 | Object loses the specified non-numerical base property |
| `CANT_GAIN` | — | Object cannot gain the specified property (TODO: model as replacement effect) |

---

## Condition Objects

Conditions are arrays evaluated against the current game state.

| Type | Fields | Description |
|---|---|---|
| `ATTACK_CLASS_IN` | `classes: []` | Attack's class matches one of the listed classes |
| `ATTACK_TYPE_IN` | `types: []` | Attack's type matches (e.g. `"Action"`) |
| `ATTACK_SUBTYPE_IN` | `subtypes: []` | Attack's subtype matches (e.g. `"Attack"`) |
| `ATTACK_COST_GTE` | `amount` | Attack's cost is >= amount |
| `ATTACK_COST_LTE` | `cost` | Attack's cost is <= cost |
| `ATTACK_IS_WEAPON` | — | Current attack is from a weapon |
| `ATTACK_IS_NOT_WEAPON` | — | Current attack is not from a weapon |
| `WEAPON_SUBTYPE_IN` | `values: []` | Weapon's subtype matches (e.g. `"Hammer"`) |
| `CARD_IN_ZONE` | `zone`, `filter_cost_gte`, `count_gte` | Cards in zone matching filter meet count threshold |
| `COUNTER_GTE` | `counter_type`, `min` | Source has at least `min` counters of given type |
| `ABILITY_TYPE_IN` | `types: []` | Ability type matches |
| `CARD_TYPE_IN` | `types: []` | Card type matches |
| `CARD_SUBTYPE_IN` | `subtypes: []` | Card subtype matches |

### Boolean Logic

```json
{"type": "AND", "all": [ ... ]}
{"type": "OR", "any": [ ... ]}
{"type": "NOT", "inner_type": "COUNTER_GTE", "counter_type": "energy", "min": 3}
```

---

## `span` Values

| Value | Description |
|---|---|
| `"NEXT_TURN"` | Expires at end of current turn if unused |
| `"NEXT_ACTION_PHASE"` | Expires at end of the next action phase |
| `"THIS_TURN"` | Active for the remainder of the current turn |

---

## Player Targeting

| Value | Context |
|---|---|
| `"OPPONENT"` | The opposing player |
| `"DEFENDING"` | The defending player (in combat context) |
| `"PLAYER"` | The controlling player |

---

## `optional` Values

Always a string, not a boolean.

| Value | Meaning |
|---|---|
| `"TRUE"` | Effect may be skipped by the player |
| `"FALSE"` | Effect is mandatory |

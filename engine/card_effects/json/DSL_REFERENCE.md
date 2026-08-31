# Card Effect DSL Reference

JSON schema patterns for card effect definitions. All files live under `json/<set>/`.

**Every card the engine touches must have a JSON definition here** — deck cards,
heroes, equipment, weapons, and tokens. A card with no special abilities still
needs a stub with `"abilities": []`. Games refuse to start (raising
`MissingCardImplementation` with the full list) if any card lacks a definition.

**Unknown types fail at load time.** `type` values for effects, conditions, and
costs must be spelled exactly as implemented in `dsl/effect_types.py`,
`dsl/condition_types.py`, and `dsl/cost_types.py` — an unrecognized type raises
`ValueError` when the JSON is loaded, and the card counts as unimplemented.

---

## Top-Level Structure

```json
{
  "slug": "card_slug",
  "activation_cost": 2,
  "per_turn": 1,
  "cost": { ... },
  "conditions": { ... },
  "conditional_keywords": ["GO_AGAIN"],
  "abilities": [ ... ]
}
```

| Field | Required | Description |
|---|---|---|
| `slug` | Yes | Unique card identifier |
| `activation_cost` | No | Resource ({r}) cost to **activate** the ability or make the weapon/ally **attack**. DSL-authoritative: overrides the loader's printed-text heuristic. Set it whenever the card has an activated ability or attacks for a resource cost (use `0` for free abilities). Do **not** also model this {r} as a `PAY_RESOURCES` cost — that double-charges. |
| `per_turn` | No | Activations allowed per turn (e.g. `1` for "Once per Turn"). DSL-authoritative; omit for no limit. |
| `cost` | No | Additional cost to **play** the card (play-time only). Prefer this over an ability-level `additional_cost` whenever the ability is dispatched more than once — `_run_ability` re-pays an ability's additional costs on **every** dispatch. |
| `conditional_keywords` | No | Printed keywords this card only has **conditionally**. See below. |
| `conditions` | No | Targeting or play restrictions (e.g. AR target must be Ninja) |
| `abilities` | Yes | Array of ability objects |

> **`conditional_keywords`** — the card DB has no way to mark a printed keyword conditional. Out Muscle ships as `"GoAgain"` although its text gates it, so the engine grants it unconditionally and the gate is decoration: the card plays as strictly stronger than printed. `loader.conditional_keywords()` normally **infers** the answer, recognising exactly one shape — a `WHILE_STATIC` gated on `SOURCE_IS_ATTACK` that grants the keyword. Use that shape when you can; it is what distinguishes "**this** gains go again" from Luminaris's "your Illusionist attacks get go again", where the printed keyword belongs to some other card.
>
> Declare the keyword here **only** when the grant must stay on a trigger — when the condition is a timed event ("if this **hits**", "if you **do**", "when this attacks, **if** …") rather than a state that can be re-read. A `WHILE_STATIC` re-evaluates its condition continuously (CR 6.2.3d), which for those cards answers at the wrong moment.
>
> The inference is deliberately not widened to cover conditional triggered grants, because it cannot be done safely: for `INTIMIDATE` and `OVERPOWER` the same DSL name is both a keyword a card *gains* and an effect a card *performs*, so Instill Fear ("when this attacks a hero, **intimidate them**") would lose the keyword it really has.
>
> Declaring without a working trigger turns a fail-**open** bug into a fail-**closed** one, so always test both directions: the keyword must appear once the trigger fires and be absent before it does.

> `activation_cost` / `per_turn` are card-level because a weapon's attack cost isn't tied to a DSL ability (attacks are engine-offered). When omitted, the loader falls back to parsing the printed text — reliable, but prefer the explicit field for implemented cards. Non-resource activation costs (tap, destroy, discard, remove counters) still go in the ability-level `cost` array.

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

`BANISH_FROM_HAND` — "banish a random card from your hand", "you may banish a
card with blood debt from your hand". Fields: `amount`, `random`, `optional`,
plus the shared hand filters (`keyword`, `card_type`, `card_name`, `color`,
`class_filter`, `filter`). An `optional: true` cost never blocks the play
(CR 5.1.6); gate the payoff on `BANISHED_TO_PLAY_THIS` instead. What it took is
recorded on the card being played, so "this way" is answerable later.

> **Put a cost on the CARD (`"cost"`), not on an ability, whenever the ability is
> dispatched more than once.** `interpreter._run_ability` re-checks and re-pays
> an ability's `additional_cost` on *every* dispatch — on a `WHILE_STATIC` that
> means paying it once per attack-power recalculation, and once it can no longer
> be paid the ability returns early and stops working. An ability holding only a
> cost is not an option either: an ability with no effects is a silent no-op the
> hygiene tests reject.

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

### Attack / Wager

```json
{"type": "ATTACK"}
{"type": "WAGER", "prize": "gold"}
```

`ATTACK` — for a weapon/hero "Action - [cost]: Attack" ability. The attack is put
on the stack as an attack PROXY (activated-layer, source = the card), which the
engine resolves as a real attack per CR 1.6.2b — never a shortcut. A weapon with
printed power + an activation cost is already offered its attack by the engine, so
`ATTACK` mainly declares the ability (satisfies the "must implement something"
check) and provides the proxy for a granted extra attack.

`WAGER` — CR 8.5.46. Registers a wager on the current attack; if it hits, the
controller wins and creates the `prize` token (else the opponent wins it). Resolves
automatically at chain-link resolution.

### Attack Power

```json
{"type": "MODIFY_ATTACK", "mod": "add", "amount": 4}
{"type": "MODIFY_ATTACK", "mod": "add", "amount": -2}
{"type": "MODIFY_NEXT_ATTACK", "mod": "add", "amount": 3,
 "filter": [{"type": "ATTACK_COST_LTE", "cost": 1},
            {"type": "ATTACK_TYPE_IN", "types": ["Action"]},
            {"type": "ATTACK_SUBTYPE_IN", "subtypes": ["Attack"]}]}
```

| Type | Description |
|---|---|
| `MODIFY_ATTACK` | Modifies the current attack's power |
| `MODIFY_NEXT_ATTACK` | Modifies the next qualifying attack's power |
| `DESTROY_SELF` / `DESTROY_PERMANENT` | Destroys this card (canonical `destroy()` resolves its zone) |
| `PAY_OR_ELSE` | `player` (SELF/OPPONENT) pays `resources` N, or else the `on_failure` effect list resolves (e.g. "discard a card unless you pay {r}"). on_failure effect `player` params are relative to the same source card. |
| `CONDITIONAL` (aliases `IF`, `CONDITIONAL_EFFECT`) | Branch: `{"when": [<conditions>], "then": [<effects>], "else": [<effects>]}`. Runs `then` if every `when` holds, else `else`. Use `when` for the test — NOT `conditions` (the loader pops that key into an effect-level gate, which would skip the whole branch). |

**Ref family** — a "look at / choose a card, then act on it" register (set by `LOOK_AT`, `REVEAL_TOP_DECK`, `SELECT_FROM_REF`, …; read by these). The `ref` param names the register (default varies per effect).

| Type | Description |
|---|---|
| `PUT_REF_BOTTOM` / `PUT_REF_TOP` | Put the referenced card(s) on the bottom/top of a deck. `player`: OWNER (default) / SELF / OPPONENT. Thin alias over `MOVE_REF`'s deck path. |
| `TAP_REF` | Tap the referenced card(s) (`untap: true` to untap instead). |
| `DESTROY_REF` / `BANISH_REF` / `MOVE_REF` / `FLIP_REF` / `PUT_COUNTER_REF` / `REORDER_REF` / `SELECT_FROM_REF` | Act on referenced card(s) — destroy / banish / move to a zone / turn face up-down / add counters / reorder / choose a subset. |

`mod` values: `"add"` (subtraction uses negative `amount`). Future values: `"multiply"`, `"set"`.

`MODIFY_NEXT_ATTACK` takes an optional `filter` array of condition specs
describing which future attacks qualify. It is deliberately named `filter`, not
`conditions` — `conditions` on an effect gate whether the effect runs *now*,
while `filter` is pass-through data evaluated later against each attack. The
mod is queued on the card's controller and consumed by the first matching
attack that turn (unused mods expire at end of turn).

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
{"type": "DRAW", "amount": 1, "player": "OPPONENT"}
{"type": "DISCARD", "player": "DEFENDING", "amount": 1}
{"type": "DISCARD_RANDOM", "amount": 1}
```

`DRAW` and `DISCARD` default to `"SELF"`; pass `"player": "OPPONENT"` to target the
other player (e.g. "each hero draws a card" = a SELF draw + an OPPONENT draw).

`DISCARD` stores what it discarded under `into` (default `"discarded"`), so an "if you do" payoff has something to ask about. A filtered discard that finds no match, and an empty hand, both store nothing — which is what makes "if you do" fall out for free rather than needing its own gate.

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

### Composable primitives (references + optional blocks)

Prefer these over writing a new single-card effect type. Effects in one ability
share objects through named references scoped to that ability's execution: an
effect stores with `"into"`, a later one reads with `"ref"`. This lets a card
sentence like "look at the top card, and if it's red you may destroy it for
+4{p}" be assembled in JSON instead of compiled into one bespoke function.

| Type | Fields | Description |
|---|---|---|
| `LOOK_AT` | `zone` (DECK_TOP/ARSENAL/HAND), `player`, `amount` (int or "ALL"), `filter` ({keyword, subtype, face_down}), `into` | Peek at cards **without moving them**; store under `into` (a single card unwrapped, multiple/filtered as a list). A `filter` scans the whole zone |
| `SELECT_FROM_REF` | `ref`, `mode` (SAME_NAME/ANY), `min`, `max`, `into`, `rest_into` | Choose a subset of a referenced list; `SAME_NAME` picks a name and takes all copies. `rest_into` stores the complement |
| `DESTROY_REF` | `ref` | Destroy the referenced card(s) via the canonical `destroy` |
| `BANISH_REF` | `ref`, `from_zone` (optional) | Banish referenced card(s); origin zone is derived from the card if not given |
| `MOVE_REF` | `ref`, `to_zone`, `position` (top/bottom), `player` (SELF/OPPONENT/OWNER) | Move referenced card(s) to a zone |
| `REORDER_REF` | `ref`, `player` | Let the controller order referenced cards back on top of the deck (first chosen ends up on top) |
| `PUT_COUNTER_REF` | `ref`, `counter_type`, `amount` | Put counters on the referenced card(s) (vs `PUT_COUNTER`, which targets the ability's own source) |
| `FLIP_REF` | `ref`, `face_up` | Turn referenced card(s) face-up or face-down (`is_public`) |
| `MAY` | `prompt`, `conditions`, `effects` | "You may X. If you do, Y." — offers the block only when `conditions` hold; declining runs none of `effects`, so "if you do" needs no separate plumbing |

Reference-reading conditions: `REF_PITCH_IS` (`ref`, `pitch` — 1 red / 2 yellow
/ 3 blue), `REF_EXISTS` (`ref`), and `ATTACK_TARGET_IS_HERO` (the attack was
declared at a hero, not a permanent or ally).

```json
"effects": [
  {"type": "LOOK_AT", "zone": "DECK_TOP", "player": "OPPONENT", "into": "seen"},
  {"type": "MAY",
   "conditions": [{"type": "REF_PITCH_IS", "ref": "seen", "pitch": 1}],
   "effects": [
     {"type": "DESTROY_REF", "ref": "seen"},
     {"type": "MODIFY_ATTACK", "amount": 4, "mod": "add"}
   ]}
]
```

### Inject Trigger

Grants a trigger to an attack — "this attack gains: if it hits, …" — or, with a
scope, "whenever an attack … this turn, …". The inner trigger's `conditions` and
`effects` MUST be nested under a `trigger` dict; a top-level `conditions` key is
consumed by the loader as an effect-level gate (evaluated once at registration,
when there may be no attack) and will not behave as a per-hit filter.

```json
{
  "type": "INJECT_TRIGGER",
  "scope": "TURN",
  "player": "SELF",
  "trigger": {
    "trigger_type": "ON_HIT",
    "conditions": [ {"type": "ATTACK_TARGET_IS_HERO"} ],
    "effects": [ {"type": "DEAL_GENERIC", "amount": 1} ]
  }
}
```

| Field | Description |
|---|---|
| `trigger` | Nested `{trigger_type, conditions, effects}`; or a bare event string (e.g. `"ON_HIT"`) when there are no inner conditions. |
| `scope` | `"COMBAT"` (default) fires once, on the current attack. `"TURN"` re-injects onto **every** attack for the rest of this turn. `"NEXT_TURN"` activates at the target player's next turn start and lasts that turn. `"CHAIN"` re-injects onto every attack of the current combat chain and expires when the chain closes ("… this combat chain …"). |
| `player` | `"SELF"` (default) or `"OPPONENT"` — whose turn the TURN/NEXT_TURN hook lives on. |

Turn-scoped hooks are stored on `Player.turn_attack_hooks` / `next_turn_attack_hooks`
and re-applied per attack by `engine._apply_turn_attack_effects`; a `TURN` hook also
covers the source card's own attack.

### Modify Attacks This Turn

Turn-scoped attack-power modifier — "until the start of your next turn, attacks
that target you have -1{p}"; "your attacks this turn get +N".

```json
{
  "type": "MODIFY_ATTACKS_THIS_TURN",
  "amount": 1,
  "mod": "subtract",
  "scope": "NEXT_TURN",
  "player": "OPPONENT",
  "filter": [ {"type": "ATTACK_TARGET_IS_HERO"} ]
}
```

| Field | Description |
|---|---|
| `amount` / `mod` | Power delta; `mod` is `"add"` (default) or `"subtract"`. |
| `scope` | `"TURN"` (default) or `"NEXT_TURN"`. |
| `player` | `"SELF"` (default) or `"OPPONENT"` — whose attacks are modified. |
| `filter` | Per-attack condition list selecting which attacks to modify. Use `filter`, **not** `conditions` (the loader pops `conditions`). |

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
| `AMOUNT_GTE` / `AMOUNT_GT` / `AMOUNT_LTE` / `AMOUNT_LT` / `AMOUNT_EQ` | `amount`, `value` | Compare any resolvable **amount** against a number. See below. |
| `BANISHED_TO_PLAY_THIS` | `power_gte` (optional) | Something was banished by this card's own cost. Bare = "if you do"; with `power_gte` = "if a card with N or more {p} is banished this way". |
| `REF_HAS_KEYWORD` | `ref`, `keyword` / `keywords` | The card a previous effect stored has a printed keyword. Matching is normalised, so the DB's `"WateryGrave"` answers to `"watery grave"`. |

**`AMOUNT_*`** is the general comparison, for quantities that have no condition
type of their own. Every other comparison here names one specific quantity
(`HAND_SIZE_GTE`, `SOUL_COUNT_GTE`, `CHAIN_HIT_COUNT_GTE`, …), so a card asking
about anything else had nowhere to go — and cards were being authored against
whichever named condition happened to compile, which is how "if X is 2 or more"
and "if this deals more than 3 damage" both ended up counting chain hits.

`amount` takes the same expression forms an effect can use as a count
(`{"type": "X"}`, `{"type": "LAST_DAMAGE_DEALT"}`, `{"type": "PAID_AMOUNT"}`, a
literal, …), so:

```json
{"type": "AMOUNT_GTE", "amount": {"type": "X"}, "value": 2}
{"type": "AMOUNT_GT",  "amount": {"type": "LAST_DAMAGE_DEALT"}, "value": 3}
```

Mind `GT` vs `GTE` — "more than 3 damage" excludes exactly 3, which is the
common case on a card that prints 3.

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

## Continuous attack-power statics (`WHILE_STATIC`)

A `WHILE_STATIC` ability is re-evaluated every attack-power recalculation and
fires only on the `RECALC_ATTACK_POWER` event (dispatched by the engine to the
attack card, both heroes, and in-play permanents/weapons). Its `conditions`
gate it; its `MODIFY_ATTACK` lands in the stage-8 static window so it is never
double-applied by unrelated dispatches. Use it for "while … has +N{p}"
(Anothos), pitch-conditioned bonuses (Savage Claw), and hero auras that watch
the current attack (Arakni's stealth-vs-marked +1{p}).

## Hero and clash vocabulary (added for Victor / Kayo / Arakni)

Triggers: `ON_PITCH`, `ON_DEFEND`, `ON_BOO`, `ON_TOKEN_CREATED`,
`ON_CLASH_WIN_REVEALED`, `RECALC_ATTACK_POWER`.

`ON_TOKEN_CREATED` fires on the creator's hero whenever any token is created;
the event payload carries `{"player_id", "slug", "count"}`. `ON_GOLD_CREATED`
is sugar for `ON_TOKEN_CREATED` gated on `slug == "gold"` (see
`TRIGGER_EVENT_GATES` in `dsl/trigger_types.py` — add new gated sugar triggers
there rather than new engine events).

Effects:
- `SET_BASE_POWER` `{amount}` — set the current combat attack's base power;
  only an attack ACTION card controlled by the ability's controller qualifies.
- `CLASH` `{opponent, repeat, reveal_dest, on_winner, on_loser, on_sweep}` —
  clash with the attacking hero (CR 8.5.45). Outcome specs are
  `{"action": "create_token"|"discard", "who": ROLE, ...}` with ROLE ∈
  `WINNER`/`LOSER`/`SWEEPER`/`SELF`/`OPPONENT`.
- `TRANSFORM_HERO` `{mode}` — `random_agent_of_chaos` or `return_to_brood`.
- `LOOK` `{target, amount}`, `BANISH_FROM_LOOKED` `{same_name, min}`,
  `PUT_LOOKED_BACK` — look at top N of a deck, banish a same-name group, order
  the rest back on top (Righteous Cleansing).
- `PUT_CARDS_BOTTOM` `{from_zones}`, `PAY_OR_DAMAGE` `{resources, damage}`,
  `DESTROY_SELF` — token effects (Inertia, Bloodrot Pox).

Costs: `TAP_SELF` (`{t}`). Conditions: `ATTACK_PITCH_POWER_GTE` `{amount}`
(a card of that power was pitched to pay for THIS attack — not the pitch zone),
`ATTACK_CONTROLLED_BY_YOU`.

Card-level fields: `"setup": {"weapon_zones": 1}` (Kayo starts with 1 weapon
zone); a `REPLACEMENT` ability with `"replacement": "fail_clash_retry"` is
registered at game start (Victor's clash retry).

## Hero activated abilities and demi-hero reactions

Heroes are offered their DSL activated abilities by `play.available_actions`
(`_add_hero_dsl_activations`) when timing/costs/conditions/target-filter allow:
- `INSTANT` — any priority window.
- `ACTIVATE` — action phase, action point, empty stack.
- `ATTACK_REACTION` — combat reaction step, targeting the current attack. Runs
  the specific ability directly (not the ON_ACTIVATE broadcast). Use ability
  `conditions` (e.g. `NOT FLAG_SET`) for once-per-turn gating, set the flag with
  a `SET_FLAG` effect, and `target.filter` for what the reaction may target
  (`ATTACK_CLASS_IN`, `ATTACK_SUBTYPE_IN`).

Conditional (stealth-rider) effects: put an effect-level `conditions` array on
the sub-effect (e.g. `INJECT_TRIGGER` gated by `ATTACK_HAS_KEYWORD stealth`) —
the loader turns it into a gate, so the sub-effect runs only when it holds.

Hero `COST_MODIFIER` abilities (no effects — read by the engine's cost pipeline):
`{"ability_type": "COST_MODIFIER", "applies_to": "<slug>", "activation_delta": -1}`
reduces that card's activation cost while this hero is in play (orb_weaver's
"Graphene Chelicerae cost you {r} less to activate"). Weapon attacks themselves
are offered engine-side (`play._add_weapon_attacks`) for any weapon-zone card
with printed power + a parsed activation cost — including weapon tokens, which
inherit power/activation fields and keywords from the card-DB template.

Optional "you may destroy a Gold" style additional play costs: use a `CHOOSE`
effect whose option 0 is `[DESTROY_TOKEN{token}, ...buffs]` and option 1 is
`[]`, gated by a `CONTROLS_TOKEN_TYPE` condition (see the_golden_son_yellow).

More vocabulary added for the Arakni demi-heroes:
- Cost `DISCARD_CARD` `{class_filter|type_filter, amount}` — filtered discard;
  when filtered, the controller chooses which matching card.
- Cost `PITCH` `{amount, pitch_value?}` — pitch N cards from hand as a cost (CR
  8.5.44: to the pitch zone, gaining resources per pitch value). Optional
  `pitch_value` (1=red, 2=yellow, 3=blue) filters which cards qualify.
- `BANISH` `{from_zone}` now includes `ARSENAL` (and `HAND`, `DECK`, `GRAVEYARD`).
- `CREATE_TOKEN` `{destination: "weapon_slot"}` equips a weapon token into a free
  weapon zone (respects `weapon_zone_count`); tokens inherit keywords from the
  card-DB template (a Graphene Chelicera token carries Stealth).
- `SEARCH_BANISH_FACE_DOWN` — search your deck, banish a card face-down, shuffle
  (trap_door). Trigger `ON_BECOME` fires when a hero transforms into that form
  (`become_agent_of_chaos`). If the banished card is a Trap it is added to
  `player.playable_from_banished` — playable from the banished zone until the
  start of that player's next turn (cleared in `start_of_turn_refresh_player`).
- `DESTROY_TOKEN` `{token}` — destroy one such permanent you control.

## Combo / "last attack this combat chain"

`LAST_CHAIN_ATTACK` asks about the attack that immediately preceded this one on
the combat chain. Use it for every "**Combo** - If <Card> was the last attack
this combat chain", "If a Draconic attack was the last attack this combat
chain", and "If the last attack on this combat chain hit".

**The type is `LAST_CHAIN_ATTACK`, never `COMBO`.** `COMBO` is a DIFFERENT,
older condition that reads a `names` LIST via `combo_check`; a card authored
`{"type":"COMBO","name":"Surging Strike"}` reaches that handler instead, finds
no `names`, and gates on an empty list. `COMBO_CONTAINS` is a third one, doing a
looser SUBSTRING match on the last link's slug — prefer `LAST_CHAIN_ATTACK`,
which matches the name exactly and also supports talent/class/subtype/hit.

```json
{"type": "LAST_CHAIN_ATTACK", "name": "Surging Strike"}
{"type": "LAST_CHAIN_ATTACK", "talent": "Draconic"}
{"type": "LAST_CHAIN_ATTACK", "hit": true}
```

| Param | Matches |
|---|---|
| `name` | the card NAME as printed — matches every colour printing (`Rising Knee Thrust` matches `rising_knee_thrust_red/yellow/blue`) |
| `talent` / `class` / `subtype` | the previous attack's category |
| `hit` | whether the previous attack hit (`true`/`false`) |

Params combine with AND. With no params it asks only that some attack preceded
this one. If there is no previous link (this is the first attack of the chain)
every form is false.

**Do not invent a flag for this.** Cards previously each rolled their own
(`SURGING_STRIKE_LAST_ATTACK`, `LEG_TAP_LAST_ATTACK`, `LAST_ATTACK_WAS_DRACONIC`,
`LAST_ATTACK_HIT`), none of which anything ever set, so the Combo clause could
never fire.

Model the pump itself as `TRIGGERED` + `ON_ATTACK` + `MODIFY_ATTACK` — an
Action - Attack card is NOT an `ATTACK_REACTION`, and using that ability_type
means the ability never fires.

## Dynamic amounts ("where X is ...")

An amount may be an integer, or an expression dict. **An unknown amount resolves
to 0**, so an invented token ("BOOST_COUNT", "DAMAGE_AMOUNT") makes the effect
silently do nothing while looking implemented — that is why the audit reports
invented amounts as defects.

```json
{"type": "CREATE_TOKEN", "token": "runechant",
 "amount": {"type": "COUNT_CHAIN_LINKS", "talent": "Draconic"}}

{"type": "DESTROY_TOKEN",
 "amount": {"type": "COUNT_COUNTERS", "counter": "doom"}}
```

| Expression | Value |
|---|---|
| `COUNT_CHAIN_LINKS` | chain links **you control**, filtered by `talent` / `class` / `subtype` / `hit` |
| `COUNT_COUNTERS` | counters named `counter` on this card |
| `ROLL_RESULT`, `ROLL_NUMBER` | the last die roll |
| `HALF` | `{"type":"HALF","value":<expr>}`, rounded down |
| `VALUE` | a literal wrapper |

The same expressions work as a threshold in `ATTACK_COST_LTE` / `ATTACK_COST_GTE`.
**Never author a threshold as a bare invented string**: those conditions compare
it against an int, so a string raised `TypeError` and aborted resolution
mid-game rather than merely failing. An unresolvable threshold now fails closed
(condition unmet).

## "Your next <filtered> attack this turn gets +N"

Use `MODIFY_NEXT_ATTACK` with a `filter`. **Never a SET_FLAG plus a flag-gated
`STATIC`**: that buffs EVERY attack for the rest of the turn, not just the next
one, so it is wrong as well as usually dead.

```json
{"type": "MODIFY_NEXT_ATTACK", "mod": "add", "amount": 3,
 "filter": [{"type": "ATTACK_SUBTYPE_IN", "subtypes": ["Arrow"]}]}
```

The filter takes any condition spec, evaluated against the attacking card:

| Text says | Filter |
|---|---|
| next **arrow / dagger / sword / angel** attack | `ATTACK_SUBTYPE_IN` — these are SUBTYPES (dagger and sword live on WEAPONS, which attack as themselves) |
| next **Brute / Ninja** attack | `ATTACK_CLASS_IN` — talent/class, not subtype |
| next attack on a **marked** hero | `OPPONENT_IS_MARKED` |
| next attack with cost ≤ N | `ATTACK_COST_LTE` |

`ATTACK_SUBTYPE_IN` uses key `subtypes`; `ATTACK_CLASS_IN` uses `classes`.

### `INSTANT` is not "the card is an Instant"

`ability_type: INSTANT` means an ACTIVATED ability with instant timing
("**Instant** - Destroy this: ..."), and maps to `ON_ACTIVATE`. An Instant CARD
whose effect happens when you play it is `ability_type: PLAY`. Getting this
wrong means the ability never fires.

### "marked" has two representations

`effect_mark` writes `player.class_counters["marked"]`, and `OPPONENT_IS_MARKED`
reads it. `Player.marked` is a separate, older boolean that neither touches —
do not assert on it in tests.

### "instead" replaces, it does not stack

"gains +3{p}. If you've X, instead it gains +5{p}" is ONE bonus chosen by the
condition. Authoring two effects (+3 and +5) gated on the same condition yields
+8.

## Transcend (CR 8.5.48)

`{"type": "TRANSCEND"}` puts THIS card into its owner's hand with its back-face
active, and records that its controller transcended this turn (CR 8.5.48a).

Checkers ask through the turn event, never a flag:

```json
{"type": "EVENT_THIS_TURN", "event": "transcend"}
```

"**Whenever** you transcend" is the `ON_TRANSCEND` TRIGGER, not a this-turn
check — and it is dispatched to the hero AND to equipment/permanents, since the
cards with that text are equipment.

Do not model transcend as `TRANSFORM_HERO`: that is the Arakni Agent-of-Chaos
transform and is unrelated (its `hero` param is not even read).

## Starfall / "put into your graveyard this turn"

```json
{"type": "EVENT_THIS_TURN", "event": "graveyard", "qualifier": "instant"}
```

Recorded in `Zone.add`, so EVERY path into the graveyard counts (destroy,
discard, attack resolution, chain close, the CR 3.0.12 CLEAR redirect, ...).
Qualifiers are the card's slug, types and subtypes; omit `qualifier` to ask
"any card". It records against the graveyard's OWNER, so it means *your*
graveyard.

Pair it with `CONDITIONAL_EFFECT` then/else for the "instead" wording:

```json
{"type": "CONDITIONAL_EFFECT",
 "when": [{"type": "EVENT_THIS_TURN", "event": "graveyard", "qualifier": "instant"}],
 "then": [{"type": "DEAL_ARCANE", "amount": 4}],
 "else": [{"type": "DEAL_ARCANE", "amount": 3}]}
```

Two effects both gated on the condition would deal 3 **and** 4.

## Never stage state with a hand-set flag in tests

Three tests in this repo asserted a card worked by appending an UPPERCASE flag
(`TRANSCENDED`, `STARFALL_FLAG`, `BOOSTED_THIS_TURN`) to `current_turn_effects`.
Nothing in the engine wrote any of them, so each test passed while proving only
that the card behaved in a state the game could never reach — and each failed
honestly the moment the mechanic became real. Drive the actual keyword function
instead. A test that stages state this way is strong evidence the flag is dead.

## Reprise (CR 8.4.3)

"**Reprise** - If the defending hero has defended with a card from their hand
this chain link, ..." — use the EXISTING condition, which reads
`combat.defender_used_hand_card`:

```json
{"type": "REPRISE"}
```

Reprise cards are usually **Attack Reactions**, and the reprise clause is part of
the SAME resolution — put it on a second `ATTACK_REACTION` ability gated by
`REPRISE`, not on a `STATIC` or a `DEFENSE_REACTION`. Both cards with this text
got that wrong, so their reprise halves were unreachable regardless of the flag.

## Scrap (CR 8.3.32)

Scrap is an **optional additional cost to play**: "you may banish an item or
equipment from your graveyard". Put it on the card's PLAY ability:

```json
{"ability_type": "PLAY", "additional_cost": [{"type": "SCRAP"}], "effects": []}
```

Then gate the payoff with `SCRAPPED`:

```json
{"type": "SCRAPPED"}                      // did THIS card scrap?
{"type": "SCRAPPED", "name": "Hyper Driver"}   // what was scrapped?
```

`SCRAPPED` with no `name` is keyed to the ASKING card, because the text reads
"if **it** scrapped a card", not "if you scrapped" — a player-level flag would
also fire for a different scrap card played earlier the same turn.

Being optional, scrap never blocks play (unlike a mandatory additional cost,
which must gate legality). With no item or equipment in the graveyard, the cost
simply cannot be paid (8.3.32b) and the payoff does not fire.

**Banishing takes an origin zone.** `banish(state, card, pid, "graveyard")` —
passing `None` adds the card to the banished zone WITHOUT removing it from the
graveyard, leaving it in both at once. Pass `None` only when the caller has
already removed the card itself.

## Counting, not just testing ("where X is the number of ...")

`EVENT_THIS_TURN` **tests** a turn event; `COUNT_TURN_EVENT` **counts** one. The
condition existed and the amount expression did not, so every card phrased "X is
the number of \<thing\> you've done this turn" invented a private counter that
nothing incremented — X was 0 and the card did nothing.

```json
{"type": "MODIFY_ATTACK", "mod": "add",
 "amount": {"type": "COUNT_TURN_EVENT", "event": "play",
            "qualifier": "non_attack_action"}}
```

Same `event`/`qualifier` vocabulary as the condition, so a card that tests and a
card that counts speak one language.

**Magnitudes are not counts.** Markers record that something happened, so four
1-point arcane hits look identical to one. Anything phrased "the total damage
you've dealt" needs the tally instead:

```json
{"type": "DAMAGE_DEALT_THIS_TURN", "damage_type": "arcane", "target": "hero"}
```

Other amount expressions added for the same reason: `DESTROYED_COUNT` (how many
an optional destroy-cost actually destroyed), `LAST_DAMAGE_DEALT` (what a
preceding damage effect actually landed, which the printed number does not give
once prevention has had its say), `COUNT_REF` (a filtered count over cards a
preceding `LOOK_AT` / `REVEAL_TOP_DECK` stored), `COUNT_OPPOSING_HEROES`, and
`X` — the amount a player chose to pay for a card with an X in its cost.
Arithmetic is `{"type": "X", "plus": 1}` or `{"type": "SUM", "values": [...]}`;
there is no need for an expression per offset.

## "The first time ... this turn" is `once_per_turn`, never a flag

An ability-level key, not a condition:

```json
{"ability_type": "TRIGGERED", "trigger": "ON_DEAL_DAMAGE",
 "once_per_turn": "earth",
 "conditions": [...], "effects": [...]}
```

The value names the use, so two once-per-turn abilities on one card do not share
a single one. It is checked **after** every other gate, so a trigger whose
conditions failed does not burn the turn's use — "the first time X happens" means
the first time it actually happens.

For "your **second** \<thing\> each turn", add `"exact": true` to
`EVENT_THIS_TURN`. A `>=` test stays true for the third and every later one,
turning "the second" into "the second and every one after".

## Timing words are not interchangeable

- `START_OF_TURN` is the start phase. **`START_OF_ACTION_PHASE`** (CR 4.3.1) is
  later and is what "at the beginning of your action phase" means.
- `ON_ATTACK` fires even when the attack is fully blocked. "When this **deals
  damage**" is `ON_DEAL_DAMAGE`.
- `ON_CARD_PLAYED` is dispatched to the player's **hero** — for hero text about
  the act of playing a card. It is not `ON_PLAY` on the played card.
- `ON_WAGER_RESOLVED` is dispatched to the card that made the wager, for a payoff
  that is not a token ("the winner loses 1{h}"; use `"player": "WAGER_WINNER"`).
- `ON_PUT_FACEUP_FROM_DECK` fires from `Zone.add`, the only place that knows the
  previous zone, face-up-ness, and whether an effect rather than a rule moved it.

## Declarative statics (read by the engine, never "resolved")

Some abilities are properties, not events. `STATIC` maps to **no event**, so a
`STATIC` ability whose effects were meant to run simply never ran — several cards
had their entire text under one and did nothing at all. Declare these instead:

- `PLAYABLE_FROM_BANISHED` — "you may play this from your banished zone"
- `RUNE_GATE` (CR 8.3.27) — the same, free, while you control Runechants ≥ its
  {r} cost; the card and player are then marked as having rune gated
  (`WAS_RUNE_GATED`, and the `rune_gate` turn event)
- `DEFENSE_EQUALS` — a printed {d} that is an expression

## "Next \<card\> you play" and "unless"

`MODIFY_NEXT_CARD_COST` is the one-shot cost reduction; its `filter` is ordinary
DSL conditions over the card being played, and `on_consume` runs effects against
whichever card used it — which is how "**that** card deals 1 more damage" can
name a card nobody has chosen yet. As a turn-long flag plus a flag-gated modifier
it would discount every matching card for the rest of the turn.

`MAY` takes an `else` block. "Lose 2{h} **unless** you discard a card" is one
effect, not two with inverted conditions — there is nothing to invert against,
because the choice is not recorded anywhere.

## A parameter name the compiler does not read fails silently

`WEAPON_SUBTYPE_IN` read `values`; three of the five cards using it authored
`subtypes`, so they gated on an empty list and never fired. This fails exactly
like an invented type but is **invisible to a type-name audit** — when adding a
condition, check the compiler's `params.get(...)` keys, not what the name suggests.

## Material (CR 3.0.14) — a grant that must END when its source leaves

"While this is under a permanent, that permanent has \<property\>." Declared, not
resolved:

```json
{"ability_type": "STATIC",
 "effects": [{"type": "MATERIAL", "keyword": "Phantasm"}]}
{"ability_type": "STATIC",
 "effects": [{"type": "MATERIAL", "power": 1}]}
{"ability_type": "STATIC",
 "effects": [{"type": "MATERIAL", "keyword": "Phantasm", "except_slug": "miragai"}]}
```

`engine._setup_material_statics` registers two continuous effects — one at stage
6 (`keywords`), one at stage 7 (`power`) — that ask each card what is under it at
the moment of every recalculation.

**Why derived rather than registered.** Granting the property when the sub-card
arrives would require undoing it on every path by which a sub-card stops being
underneath: banished to pay a cost, the top card leaving the arena, the sub-card
ceasing to exist. Miss one and a permanent keeps phantasm forever. Deriving makes
the "while" true by construction — a sub-card that is no longer there cannot
still be granting anything. This is the same choke-point argument that put the
graveyard turn event inside `Zone.add`.

The general rule: **an ability whose text begins "while" is a property of a
relationship, not an event.** If a condition can stop being true, do not write
the consequence down anywhere it can outlive the condition.

## Transform (CR 8.5.36)

Transform puts the object **under** the permanent (3.0.14) — it is not a swap and
not a destroy, which is why Nitro Mechanoid can later pay "banish a card from
under this" with the very parts it was built from.

```json
{"type": "TRANSFORM", "from": "ash", "to": "aether_ashwing", "amount": 1, "up_to": true}
{"type": "TRANSFORM", "to": "aether_ashwing", "amount": 3, "each": true}
{"type": "TRANSFORM", "to": "nitro_mechanoid",
 "sources": [{"zone": "head"}, {"zone": "permanents", "from": "hyper_driver", "amount": 3}]}
```

- `each` — one permanent per source ("into Aether Ashwing**s**") versus all
  sources under one ("into Nitro Mechanoid"). The card text distinguishes these
  by pluralising the target, and they are different board states.
- `sources` — several different requirements at once. Equipment lives in the slot
  zones and never in `permanents`, so a permanents-only scan finds none of it.
- CR 8.5.36d is **all-or-nothing**: if any named part is missing, nothing
  transforms. On Nitro Mechanoid that rule *is* the printed "if you don't,
  negate this".

Do not author this as `TRANSFORM_HERO` — that is Arakni's "become a random Agent
of Chaos" and does something else entirely. Five cards did, and a real type doing
the wrong thing is invisible to a type-name audit.

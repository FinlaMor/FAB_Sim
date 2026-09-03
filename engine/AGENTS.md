# engine/ — Module Reference

**Architecture rule:** `engine/*.py` is a generic, rules-accurate FAB engine
(rules authority: `docs/ref/en-fab-cr-comprehensive-rules.txt`, "CR" below).
**No card-specific code in engine files.** All card behavior is declared in
JSON under `engine/card_effects/json/` and interpreted by
`engine/card_effects/dsl/`. If you are implementing a card, read
`card_effects/json/IMPLEMENTATION_GUIDE.md` — you should not need this file.

## Entry Points

### `engine.py` (~1760 lines)
**Does:** Complete game loop. Turn phases, combat steps, stack/priority, damage.
**Key functions:**
- `new_game()` / `_game_loop()` — initialise GameState from deck paths + agents; step until done
- `_start_of_turn_phase()` / `_end_phase_iter()` — CR 4.3 / 4.4
- `_action_phase_iter()`, `_combat_phase_iter()` — phase drivers
- `_attack_step()`, `_defend_step()`, `_reaction_step()`, `_damage_step()`, `_resolution_step()`, `_close_step()` — CR 7.x combat steps
- `check_state_based_actions()` — CR 1.10
- `resolve_stack()`, `order_stack()`, `priority_loop()` — CR 3.15 / 1.6 layers & priority
- `_recalculate_attack_power()` — staged power recalc; emits `RECALC_ATTACK_POWER` for DSL `WHILE_STATIC` abilities (stage-8 window)
- `_setup_dsl_listeners()` — bridges engine events → DSL dispatch (`ON_HIT`, `ON_PITCH`, `ON_DEFEND`, `ON_BOO`, `ON_TOKEN_CREATED`, `ON_CLASH_WIN_REVEALED`, …). Listeners are generic; DSL-side gates filter payloads (see `dsl/trigger_types.py TRIGGER_EVENT_GATES`)
- `_setup_static_ability_listeners()` — wires keyword statics (Piercing etc.) at game start

### `play.py` (~970 lines)
**Does:** The action interface agents use. Legal action generation + application.
**Key functions:**
- `available_actions(state, player_id)` — playability + affordability; always includes PASS
- `apply_action(state, action)` — applies a chosen action
- `_add_weapon_attacks()` — offers weapon attacks for any weapon-zone card with printed power + activation cost (incl. weapon tokens)
- `_add_hero_dsl_activations()` — offers hero DSL `ACTIVATE`/`INSTANT`/`ATTACK_REACTION` abilities when timing/cost/conditions/target-filter allow
- `_legality_check()`, `_cost_check()`, `evaluate_play_cost()` — gates
- `_calculate_resource_cost()` — cost pipeline incl. DSL `COST_MODIFIER` hero abilities
**Note:** legal-action generation is migrating here from `actions.py`; put new logic here.

## State

### `state.py` (~1310 lines)
**Key classes:**
- `GameState` — players, step, combat, event_manager, effect_manager, stack_entries, chain_links, `events_this_turn`
- `Player` — zones (hand, deck, graveyard, arsenal, pitch, banished, permanents, items, auras, allies, tokens, equipment slots, weapon1/2, hero_zone), stats, resources, `weapon_zone_count`, `playable_from_banished`
- `CombatState` — attack_card, attack_power, defending_cards, keywords, from_weapon, defender_used_hand_card, …
- `Zone` — add/remove keep `card.zone`/`card.prev_zone` in sync; `ZoneEntryResult` (CR 3.0.11-12)
- `EventManager` — pub/sub; every emitted event type is also recorded in `state.events_this_turn`
- `StackEntry`, `ChainLink`, `Step` (enum)

### `card.py` (~840 lines)
`Card` (runtime object; properties may be modified by continuous effects) and
`CardDB` (loads `card_data/slug_index.json`; templates for all printed cards
including tokens — token zone routing derives from template subtypes).

### `deck.py` (~340 lines)
`load_deck(path, card_db)` — plain and Fabrary deck-file formats; applies hero
DSL `setup` (e.g. weapon-zone count) via `create_player`.

### `actions.py` (~1110 lines)
`ActionType`/`Action` + older legal-action generation (being migrated to
play.py — do not add new generation here).

## Effect Systems

### `effect_keywords.py` (~3810 lines) — CR 8.5
Canonical effect primitives — the atomic operations every card effect must
compose from (they emit events so replacement effects can intercept, CR 6.4):
`draw, gain, lose, banish, destroy, discard, deal_damage, deal_arcane_damage,
intimidate, create_token, put_counter, remove_counter, gets, look, reveal,
put_object, roll, search, shuffle, name, opt, reload, turn, add_defend,
transcend, retrieve, give, steal, wager, awaken, contract, create_card,
transform, attack, clash, amp, charge, mark, negate, …`
Each docstring cites its CR 8.5.x clause. Card-specific data consulted here
comes from `card_effects.token_meta` (token entry hooks, numbered keywords)
and `card_effects.replacement_abilities` (named REPLACEMENT handlers) — keep
it that way.

### `effects.py` (~570 lines) — CR 6.2/6.3
`ContinuousEffect` (staged property modification), `EffectManager`,
`ReplacementEffect` (incl. prevention/shielding), `ModType`.

### `continuous_effects.py` (~210 lines)
Older staging + cost-modifier pipeline (CR 5.1.6a). Contains a second,
legacy `ContinuousEffect` — do **not** use it in new designs; prefer
`effects.py`. Slated to be folded into EffectManager.

### `context.py` (~40 lines)
`effect_context()` — re-entrancy guard used around DSL dispatch.

### `recorder.py` — observability hooks
Attach `GameRecorder`s via `new_game(..., recorders=[...])` or
`recorder.attach(state, rec)`. Hooks: `on_game_start/end`, `on_event` (every
EventManager event), `on_decision` (EVERY agent invocation — the full options
list presented to the model, the chosen option, its index, and the prompt
context), `on_action_applied`, `on_step_change`, `on_layer_resolved`.
`snapshot_state(state)` serializes the complete game state (all zones, stats,
combat, stack, chain links) to a JSON-able dict at any moment.
Built-ins: `MemoryRecorder` (in-memory records; `snapshot_on={"decision"}`
embeds full snapshots per decision) and `JsonlRecorder(path)` (streams one
JSON line per record — game troubleshooting). For IQL data collection,
subclass `GameRecorder` and implement `on_decision` + `on_game_end`.
Recorder exceptions are swallowed (observability never breaks a game);
`GameState.copy()` excludes recorders so simulated copies don't emit records.
Zero overhead when no recorder is attached.

## Card Effects Layer (`card_effects/`)

### `dsl/` — the JSON card interpreter
- `loader.py` — loads `json/**/*.json` → `CardDef`; `require_card`/`validate_slugs`
  raise `MissingCardImplementation` for any slug without a definition;
  `LOAD_ERRORS` collects files that failed to compile (they count as unimplemented)
- `schema.py` — `CardDef`, `AbilityDef`, `EffectDef`, `ConditionDef`, `CostDef`
- `interpreter.py` — `dispatch_event()`: matches abilities to engine events, runs them
- `effect_types.py` / `condition_types.py` / `cost_types.py` — implementations
  of every JSON `type` string; unknown type = load-time `ValueError`
- `trigger_types.py` — JSON trigger name → engine event; `TRIGGER_EVENT_GATES`
  for sugar triggers that filter a broader event's payload (e.g.
  `ON_GOLD_CREATED` = `ON_TOKEN_CREATED` gated on `slug == "gold"`)
- `__init__.py` — `dispatch(state, event_type, slug, …)`, the entry the engine bridges call

### `json/` — **all card behavior lives here**
One JSON per card under `json/<set>/`; tokens in `json/tokens/`.
Docs: `DSL_REFERENCE.md` (schema), `IMPLEMENTATION_GUIDE.md` (workflow).
`<set>_work_queue.json` files are authoring TODO lists (not card defs).
Tooling: `python scripts/dsl_work_queue.py --status | --deck <file> | --set <code> [--write-queue]`.

### `ability_keywords.py` (~1520 lines) — CR sections 8.3/8.4/8.6
Keyword mechanic implementations fired from card-DB keywords: `battleworn,
blade_break, temper, guardwell, dominate_check, overpower_check, piercing,
phantasm_check, spectra_destroy, blood_debt, boost, heave, crank, fusion,
arcane_barrier, spellvoid, ward, quell, crush_check, reprise_check,
combo_check, surge_check, …` plus shared helpers (`_ask_player`, transform
machinery for hero forms, `create_token_card`).

### `token_meta.py`
Token-specific data: numbered keywords the card DB drops (`TOKEN_KEYWORDS`),
ally token stats, per-token entry hooks (`TOKEN_ENTRY_HOOKS`, e.g. Zen State's
text-based prevention), and fallback zone tables for card-DB-less test states.

### `replacement_abilities.py`
Handlers for DSL `{"ability_type": "REPLACEMENT", "replacement": "<name>"}`
abilities (e.g. `fail_clash_retry`). Registered per player at game start;
consulted generically by keyword functions.

### `triggers/triggers.py` (~510 lines)
Keyword-derived `TriggerDef`s only (`build_keyword_triggers`); registration
queues triggered-layers on the stack (CR 6.6.5-6). `CARD_TRIGGERS` is empty
by design — card triggers are DSL abilities.

### `registry.py` (95 lines)
Structural hooks only: `STATIC_ABILITY_ZONES`, `KEYWORD_STATIC_ABILITIES`
(e.g. piercing), plus legacy per-card registries that are all **empty** —
do not repopulate them; author JSON instead.

### `costs/`
Mostly-empty registries for keyword costs (`effect_costs.py` KEYWORD_COSTS);
card alternate costs are DSL `alternative_cost` entries now.

### `db/`
`loader.py`/`db.py` — CardDB init helpers. `generate_seed.py` is legacy seed
data (unused by the DSL path).

## Player-scoped restrictions ("they can't X until Y")

A restriction on a PLAYER rather than a card is a string marker on
`player.current_turn_effects`, with `player.next_turn_effects` for anything that
outlives this turn — `engine.py` rotates next→current at that player's turn
start and clears current at their turn end, which is exactly "until the end of
their next turn".

**Write the marker with a named effect type and read it somewhere real.** A
`SET_FLAG` writes an arbitrary string that nothing consults, and a flag with no
reader has no correct spelling: two printings of Humble invented two different
names for the same effect, and both did nothing. If you find yourself adding a
`SET_FLAG`, the effect is almost certainly not implemented.

Existing pairs, each a writer in `effect_keywords.py` plus a reader on the path
that actually decides:

| effect type | marker | read by |
|---|---|---|
| `DISABLE_HERO_ABILITIES` | `hero_abilities_disabled` | `interpreter.dispatch_event`, `play._add_hero_dsl_activations`, `play._hero_activation_cost_delta`, the clash-retry site in `effect_keywords.clash`, `actions.py` ACTIVATE_HERO |
| `FORBID_PLAYING_NAMED` | `cant_play_named:<name>` | `play._legality_check` |
| `RESTRICT_PLAYS_TO_ARSENAL` | `only_play_from_arsenal` | `play._legality_check` |

Two things to check when adding one:

* **`play.py` is the live path; `actions.py` is the audit-only mirror.** A
  reader in only one of them is enforced in only one of them.
* **Ask what else reads the thing you are switching off.** "Loses all hero card
  abilities" turned out to span five call sites, two of which never touch
  `dispatch_event` — one reads the hero's DSL abilities directly for cost
  deltas, and one is registered once at game start, so only a check at the point
  of USE can see the restriction at all.

## Attack-proxies (CR 1.4.3) — what "this" means during an attack

Activating a weapon, ally, demi-hero or granted permanent to attack creates an
**attack-proxy**: a non-card object representing the attack-source. It inherits
the source's properties *except* the source's activated and resolution
abilities (1.4.3a), ceases to exist when the chain link changes (1.4.3c), and
effects applying to it do not apply to the source (1.4.3e).

**This engine models the proxy as a flag on the Action** (`is_attack_proxy`) and
puts the SOURCE OBJECT itself in `combat.attack_card`. That is a deliberate
simplification, and it is the reason three separate defects landed here:

* **`ON_HIT` means "when THIS hits."** It is dispatched only to the attack.
  `ON_ANY_HIT` is the broadcast to the attacker's hero and permanents ("when an
  attack you control hits"). They were once the same dispatch, so a weapon
  reading "when this hits a hero, mark them" marked on *any* attack, from inside
  its weapon zone. Seven weapons said that; four cards meant the broadcast.
* **A granted trigger lives on whatever the attack IS.** For an attack ACTION
  CARD the attack is the card, so an `INJECT_TRIGGER` at COMBAT scope attaches
  to `card.granted_abilities` and travels with the object — Flick that card
  later and the granted trigger fires with it. For a WEAPON the attack is the
  proxy, so the grant stays on `combat.injected_triggers` and dies with the
  chain link; the weapon card never had it. Combat-scoped storage *is* proxy
  lifetime, which is why only the card case needed splitting out.
* **The attack ability's own cost is not a resource cost.** `_pay_costs` covers
  resources and action points; the clause before the colon ("Remove a steam
  counter from this", "banish 2 cards from your soul") is a DSL ability cost,
  checked at offer time by `_attack_ability_costs_payable` and paid in
  `_apply_activate`'s proxy branch. Both go through `attack_ability_of`, so an
  attack that is offered is an attack whose cost gets paid.

**Who may attack**: `_add_weapon_attacks` (weapon zones, gated on
`weapon_exhausted`), `_add_granted_permanent_attacks` (the `GRANTED_ATTACK`
counter), and `_add_object_attack_activations` (everything else with a printed
attack ability — allies, demi-heroes, equipment). The last is NOT gated on
`weapon_exhausted`: that is the weapon rule, and an ally is not a weapon.

## Known engine limitations (the remaining engine-side work)

A full CR audit lives in `docs/cr_audit_2026-07.md` (findings + fix status —
the open items there: attack-layer-on-stack representation, triggered-layer
target declaration, defend compound events, chi end-of-turn policy).
Additionally, each of these fails loudly or is harmless until a card needs it:

1. **Per-ability activation choice** — a card with 2+ activated abilities
   raises `NotImplementedError` in `play.py` (`_apply_activate`). The `Action`
   object needs an ability index so the player can choose which to activate.
2. **`CANT_GAIN` continuous modification** — currently a property flag; should
   be modeled as a replacement effect (noted in `DSL_REFERENCE.md`).
3. **`continuous_effects.py` legacy class** — fold into `effects.py`
   `EffectManager`; do not build on the old class.
4. **`actions.py` → `play.py` migration** — legal-action generation still
   partially lives in `actions.py`.
5. **A conditional keyword cannot gate a keyword TRIGGER** — `conditional_keywords`
   is honoured on the two paths that read a keyword as a *value*
   (`_recalculate_attack_power` for attacks, `resolve_stack` for non-attack
   layers), but NOT by `triggers.build_keyword_triggers`, which registers
   triggered-static keywords straight from the card DB's `keywords` list.

   Live consequence: `gloves_of_azure_waves` reads "**High Tide** — if there
   are 2 or more blue cards in your pitch zone, this gets +3{d} and **blade
   break**", and Blade Break is "when the combat chain closes, if this
   defended, destroy it" (CR 8.3.3). The trigger is registered unconditionally,
   so the gloves are destroyed **every** time they defend, whether or not High
   Tide is on — the player loses their Arms slot for a bonus they never got.
   The +3{d} half is correctly gated; only the keyword is not.

   Definition of done: `build_keyword_triggers` skips a keyword that
   `conditional_keywords` reports for the card, and the card's own gating
   ability re-registers it — which needs a way to say "gains a *triggered*
   static keyword while X", since a `GAIN` of a keyword currently only reaches
   `combat.keywords`. 27 cards print Blade Break; today only this one gates it,
   which is why it is recorded rather than half-built.

6. **`Fragment` is not implemented** — 27 cards print it (Omens of the Third
   Age / GEM) and 32 mention it in text. Nothing in the engine emits a fragment
   event, so "whenever this fragments" cannot fire; the cards that have it are
   currently authored against `ON_BECOME`, which is only emitted when a HERO
   transforms (`ability_keywords`, the Arakni path), so those clauses are dead.

   **Blocked on rules text, not on effort.** Fragment appears in neither
   `docs/ref/en-fab-cr-comprehensive-rules.txt` nor any release notes in
   `docs/ref/` — Omens of the Third Age has no notes there. Implementing a
   keyword mechanic by inferring it from card text would put a guess where the
   rules go, and every card printing it would then be wrong in the same way at
   once.

   Definition of done: OMN rules text in `docs/ref/`, a fragment event emitted
   by a canonical keyword function, and `ON_FRAGMENT` in `dsl/trigger_types.py`.
   Two cards are waiting on it — `ebbing_arcstride_red` / `_blue`, the last
   entries in the gated-go-again backlog
   (`tests/test_conditional_go_again_ratchet.py`). Do **not** declare their
   `conditional_keywords` before the trigger works: that would strip the printed
   go again with nothing to grant it back, turning a fail-open bug into a
   fail-closed one.

## Adding a New Card

Do **not** touch this directory's Python for a card. Follow
`card_effects/json/IMPLEMENTATION_GUIDE.md`:
1. JSON definition in `json/<set>/<slug>.json` (schema: `DSL_REFERENCE.md`)
2. Behavioral test in `tests/`
3. If a genuinely new effect/condition/cost type is needed, add it
   *generically* to `dsl/*_types.py` (composing `effect_keywords` primitives)
   and document it in `DSL_REFERENCE.md`

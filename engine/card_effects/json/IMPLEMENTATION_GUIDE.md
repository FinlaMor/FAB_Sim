# Card Implementation Guide

**Audience:** any model or developer picking up card-implementation work with no
prior context on this repo. Read this file top to bottom once; then you only
need `DSL_REFERENCE.md` (same directory) while authoring.

## The one rule

**All card behavior lives in JSON files in this directory tree.** The Python
engine (`engine/*.py`) is a generic, rules-accurate FAB rules engine and must
never contain card-specific code. If a card seems to need engine changes, the
correct move is almost always to add a new *generic* DSL effect/condition/cost
type (see "Extending the DSL" below), never a slug check in an engine file.

A game refuses to start if any card in either deck lacks a JSON definition —
`MissingCardImplementation` is raised naming the missing slugs. A card with no
abilities still needs a stub: `{"slug": "...", "abilities": []}`.

## Where things live

| Path | What |
|---|---|
| `engine/card_effects/json/<set>/<slug>.json` | Card definitions (this is what you author) |
| `engine/card_effects/json/<set>/<set>_work_queue.json` | Authoring TODO list per set (`"status": "pending"` / `"done"`) |
| `engine/card_effects/json/DSL_REFERENCE.md` | Full JSON schema: ability types, triggers, effects, conditions, costs |
| `engine/card_effects/dsl/effect_types.py` | Implementations of effect `type` strings |
| `engine/card_effects/dsl/condition_types.py` | Implementations of condition `type` strings |
| `engine/card_effects/dsl/cost_types.py` | Implementations of cost `type` strings |
| `engine/card_effects/dsl/trigger_types.py` | JSON trigger name → engine event mapping |
| `engine/effect_keywords.py` | Canonical CR 8.5 effect primitives (`draw`, `destroy`, `deal_damage`, `create_token`, …) — effect types must call these, never mutate state directly |
| `card_data/slug_index.json` | Card database — `by_slug[<slug>]`, card text in `functionalText` (camelCase) |
| `docs/ref/en-fab-cr-comprehensive-rules.txt` | The comprehensive rules (CR). The rules-accuracy authority |
| `scripts/dsl_work_queue.py` | Status/queue tool (see workflow) |

Tokens live in `json/tokens/`. Every token a card creates must also have a
JSON definition.

## Workflow for implementing a card

1. **Pick a card.** Either from a set's work queue
   (`python scripts/dsl_work_queue.py --set hnt` lists missing cards) or
   because a deck needs it (`python scripts/dsl_work_queue.py --deck decks/foo.txt`).

2. **Read the real card text** from `card_data/slug_index.json` →
   `by_slug[<slug>].functionalText`. Do not implement from memory — wordings
   matter. Color variants (`_red`/`_yellow`/`_blue`) are separate JSON files;
   they usually differ only in an amount.

3. **Check the CR** (`docs/ref/en-fab-cr-comprehensive-rules.txt`) for any
   keyword or timing the card uses. Keyword mechanics (section 8) are already
   engine-implemented and fire from the card DB `keywords` field — do NOT
   re-implement Go Again, Dominate, Piercing, Ward, etc. in JSON. Only author
   the card's unique text.

4. **Author the JSON** in `json/<set>/<slug>.json` following
   `DSL_REFERENCE.md`. Type strings must exist in the `dsl/*_types.py`
   modules — an unknown type raises `ValueError` at load and the card counts
   as unimplemented. Grep an existing card for a similar wording first;
   consistency beats novelty.

   **Pick `<set>` from the card's own data, never from its class.** Derive the
   folder from the card's `sets` / `setIdentifiers` in `card_data/slug_index.json`
   (e.g. `SUP092` → `sup`, `PEN297` → `pen` (Compendium of Rathe), `EVR002` →
   `evr`, `SEA222` → `sea`). Do NOT infer the set from the card's class — a Brute
   card is *not* automatically an Outsiders (`out`) card; most Brute staples are
   actually SuperSlam (`sup`) or Compendium of Rathe (`pen`). Only file a card in
   `out/` if `Outsiders`/an `OUT###` identifier is actually in its data. Foldering
   is organizational only (the loader walks the tree and keys by slug), but a
   wrong folder is misleading and gets audited later.

5. **Validate it loads:**
   ```
   python -c "from engine.card_effects.dsl.loader import load_all_cards, LOAD_ERRORS; load_all_cards(); print(LOAD_ERRORS or 'OK')"
   ```

6. **Write a behavioral test** in `tests/` (pattern: `test_<set>_<thing>_dsl.py`,
   or extend an existing file). Tests must assert **observable GameState
   outcomes** — life totals, zone contents, hand size, attack power — never
   internal queues, flags, or registry contents. Use the helpers in
   `tests/conftest.py` and mimic e.g. `tests/test_wtr_crush_dsl.py`:
   build a minimal `GameState`, `dispatch(state, "ON_HIT", slug, ...)` or play
   through `engine.play`, then assert on the state.

7. **Run the tests:** the file you wrote plus the DSL core:
   ```
   python -m pytest tests/test_<yours>.py tests/test_dsl_interpreter.py tests/test_loader_effects.py -q
   ```
   Before finishing a batch, run the full suite (`python -m pytest tests/ -q`,
   ~8 minutes).

8. **Update the work queue:** `python scripts/dsl_work_queue.py --set <set> --write-queue`
   flips entries to `"done"` automatically based on which JSON files exist.

## Batch automation

`scripts/auto_implement_wtr.py` drives the whole workflow automatically per
set: for each `"pending"` card in `json/<set>/<set>_work_queue.json` it builds
an implementation prompt (embedding `DSL_REFERENCE.md`), calls the claw-code
CLI, runs a verification pass on the produced JSON, generates tests into
`tests/test_<set>_generated.py`, and updates the queue status
(`done`/`needs_review`/`failed`). Queue state is saved after every card, so
re-running resumes where it left off.

```
python scripts/auto_implement_wtr.py --set <code> [--limit N] [--dry-run] [--reset-failed]
```

Cards it marks `needs_review` get a note in `json/<set>/needs_review/` —
handle those manually with the workflow above. For one-off manual work,
`scripts/implement_card.sh "Card Name"` sends `scripts/card_prompt_template.txt`
to the claude CLI.

## Extending the DSL (when no existing type fits)

Most cards compose from existing types. When one genuinely doesn't:

1. Add the new type to the right `dsl/*_types.py` module. The implementation
   **must** route through the canonical functions in `engine/effect_keywords.py`
   / `engine/card_effects/ability_keywords.py` so events are emitted and
   replacement effects can intercept (CR 6.4). Never move cards between zones
   or change life/resources by direct attribute assignment.
2. Name it generically after what it does, not after the card
   (`PUT_CARDS_BOTTOM`, not `INERTIA_EFFECT`).
3. Document it in `DSL_REFERENCE.md` — the reference must stay complete;
   it is the contract for everyone who comes after you.
4. If the effect needs a new engine event, emit it via `state.event_manager`
   with a **generic** payload (e.g. `token_created` carries `slug` in
   `event.data`; a DSL-side gate filters for the card's token — see
   `TRIGGER_EVENT_GATES` in `dsl/trigger_types.py`).
5. Card-specific behavior that can't be declarative goes in
   `engine/card_effects/` registries consulted by generic engine hooks:
   - `token_meta.py` — token entry hooks / numbered keywords / ally stats
   - `replacement_abilities.py` — named `REPLACEMENT` ability handlers
   Never in `engine/*.py`.

## Known pitfalls

- `"optional"` values are the strings `"TRUE"`/`"FALSE"`, not booleans.
- Ability-level `conditions` are checked at **resolution**; `target.filter`
  is checked at **play/declare** time (CR 5.1.4). Don't use `conditions` to
  restrict targeting.
- `MODIFY_NEXT_ATTACK` uses `filter` (evaluated later per attack), not
  `conditions` (evaluated now).
- `GAIN` assets use CR 1.13.1 names: `RESOURCE_POINTS`, `LIFE_POINTS`,
  `ACTION_POINTS`, `CHI_POINTS` — not `GAIN_RESOURCES`/`GAIN_LIFE`.
- "Dagger" is a card **subtype** (Kiss of Death has it). Damage from
  dagger-triggered effects (Pain in the Backside, Flick Knives) is
  `DEAL_GENERIC`, not `DEAL_PHYSICAL`.
- `CREATE_TOKEN` / `DESTROY_ARSENAL` / `BANISH` accept `"player": "OPPONENT"`.
- Modal choice happens at **play** time (`MODAL` + `modes`); runtime choice is
  the `CHOOSE` effect.
- If a card puts a layer on the stack, both players get priority before and
  after it resolves — the engine handles this; don't simulate it in the JSON.
- Once-per-turn gating: condition `{"type": "NOT", "inner_type": "FLAG_SET", "flag": "<name>"}`
  plus a `SET_FLAG` effect with `"scope": "CURRENT"`.

## Definition of done (per card)

- [ ] `pytest tests/test_card_json_hygiene.py -p no:randomly` passes (<1s).
      This catches the mechanical mistakes that otherwise load cleanly and
      silently do nothing: wrong set folder, a `slug` that disagrees with the
      filename, an ability with an empty `effects` list, rules text with no
      implementation at all.
- [ ] JSON loads with no entry in `LOAD_ERRORS`
- [ ] Behavior matches `functionalText` and the CR (not your memory of the card)
- [ ] Behavioral test(s) added and passing
- [ ] No engine file was edited (if one had to be, the change is generic and
      card-free, and `DSL_REFERENCE.md` documents any new type)
- [ ] Work queue status refreshed

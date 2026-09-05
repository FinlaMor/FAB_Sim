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

   **The exception is a keyword the card's own text GATES** ("if this hits, it
   gains go again"). The card DB has no way to say a printed keyword is
   conditional, so the engine grants it unconditionally and the gate becomes
   decoration — the card plays as strictly stronger than printed, silently.
   Either author the grant as a `WHILE_STATIC` gated on `SOURCE_IS_ATTACK`
   (which `loader.conditional_keywords()` infers from), or, when the condition
   is a timed event and must stay on a trigger, declare it in the card-level
   `conditional_keywords` field. `DSL_REFERENCE.md` has the full rule. Test
   BOTH directions: a declaration whose trigger never fires converts a
   fail-open bug into a fail-closed one.

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

8. **Check it against real games:**
   ```
   python scripts/verify_card_against_talishar.py --card <slug>
   ```
   This asks a different question than your test does. The test asks "does it
   do what I think the text says"; this asks "does it do what an independent
   implementation of the rules did, in games real people played". It finds
   every real Talishar game that attacked with the card, rebuilds the board
   from the spectator feed, puts the attack on the chain, and compares our
   computed power against Talishar's own.

   Three verdicts matter:

   - `AGREES` — the strongest evidence available that the card is right.
   - `NO EVIDENCE` — the card never attacks in the corpus. Common and fine;
     it means this step can say nothing, not that the card is wrong.
   - `DISAGREES` — a LEAD, not a verdict. Re-run with `--explain` and read the
     board before changing anything. The harness fails in the direction that
     manufactures findings: a gap in the reconstruction looks exactly like a
     defect in the card, and historically most disagreements were the harness.
     The tool prints `KNOWN LIMITS` when the card depends on state the feed
     cannot carry (crowd/booed state, played-from-arsenal, player choices) and
     softens its verdict accordingly.

   The first run builds an index of the event store (~1 min); later runs are
   seconds. `--refresh-index` picks up newly collected games.

   **Attack power decides the verdict. The on-hit line is ADVISORY** — read the
   disagreements, don't treat the percentage as a score. Talishar resolves
   combat damage and the on-hit into separate states, so the on-hit's effect on
   life / deck / banish / discard / arsenal / soul / items / auras / allies can
   be compared against dispatching `ON_HIT` in our engine. What makes it
   advisory is attribution: the window from damage to the chain clearing also
   contains defenders hitting the graveyard and any other trigger, and several
   card texts are simply unreplayable from a spectator's view — anything
   reading a HAND most of all, since we rebuild with an empty one. A card whose
   on-hit banishes "a card from their hand" will report near-0% agreement and
   be perfectly correct.

   Keyword flags Talishar reported but our data lacks are printed too.

   **Add `--parquet` when the card reads a hand**, or a turn-scoped effect, or
   anything the spectator feed shows as CardBack. That checks the headless
   open-hand corpus, which records the full state — hands, current/next turn
   effects, marked — and so covers exactly what the spectator check has to
   disclaim. `mark_of_the_black_widow_red` ("banish a card from their hand")
   reads 32% on the spectator on-hit check and 10/10 on the open-hand one.
   It is a smaller corpus, so "no comparable plays found" is a common and
   honest answer.

   **If the verdict is `NO EVIDENCE`, generate some.** Both checks above SEARCH
   for games that happened to play the card, which most cards never get.
   FAB_Sim_Headless runs the real Talishar engine locally, so the states can be
   made to order:

   ```
   # once, in FAB_Sim_Headless:  $env:ADAPTER_MODE="real"; docker compose up -d adapter
   python scripts/generate_talishar_states.py --card <slug>
   python scripts/verify_card_against_talishar.py --card <slug>
   ```

   The generator borrows a real CC deck whose hero can legally play the card,
   then **builds the board directly** through the adapter's `POST /scenario`:
   the card in hand, the resources paid, the combo partner already on the
   chain. Seconds per card, and aimable. Talishar is still the only thing
   deciding what happens — we only choose the starting state and the action.

   Two things get recorded, because they answer different questions:

   - `generated states` — play/outcome transitions, for NON-attack cards.
   - `generated attacks` — states where the card is the live attack, carrying
     Talishar's own `combat.attack_power`. This is the one that works for
     ATTACK cards: the outcome comparison needs a quiet board and same-input
     resolution, and a chained attack gives neither.

   Situations come from the card's own text and DSL, not a per-card table:

   - `baseline` — a quiet board.
   - `combo:<partner>` — one per attack the card names, with that attack as the
     previous chain link. The spectator feed never names the previous link, so
     this is what makes combo cards checkable at all: `whelming_gustwave_red`
     reads 20% there and 100% on built states.
   - `optional:declined` / `optional:taken` — when the card has an optional cost.
     The zones it draws from are stocked from its own `CARD_IN_ZONE` conditions
     (`zone_requirements()`), because **Talishar does not offer the choice at
     all on a bare board** — Decompose needs 2 Earth cards and an action in the
     graveyard first, so a baseline scenario says nothing about that clause.
     Both branches run: the pump must appear when paid and stay absent when not.

   Two things about the paid branch that are easy to get wrong, and were:

   - **The attack goes live before the cost is paid.** Talishar puts the card on
     the chain and surfaces the prompt a step later, and whether it is up on the
     first live state varies with the shuffle. Stopping at the first live state
     made the paid branch silently identical to the declined one on some runs.
   - **Paying spends the cost**, so the state afterwards no longer contains it
     and cannot reproduce the pump it bought. The recorded row is therefore the
     board from *before* the payment, with Talishar's post-payment number in
     `_fab_oracle_power`; the verifier prefers that and replays with an
     accepting agent. If the choice is never offered, the generator records
     nothing rather than an unpaid row that would agree for the wrong reason.

   **Build your own board** when the default situations miss the point:

   ```python
   from scripts.talishar_scenario import Scenario, build
   built = build(Scenario(card="whelming_gustwave_red",
                          chain_links=["surging_strike_red"],
                          arsenal=["head_jab_red"], discard=[...], resources=3))
   after = built.play("whelming_gustwave_red")
   ```

   Zones take plain slugs (`hand`, `arsenal`, `discard`, `banish`, `pitch`,
   `deck_top`, `chain_links`), plus `health` / `opp_health` / `resources`.
   `actor=2` puts the card in the other seat, which is the only way to reach a
   defence reaction — it can only be played while the opponent is attacking.
   `resources` defaults to 3 because Talishar does not gate legality on cost: it
   offers the play and then drops into the phase-P pitch prompt, and pre-paying
   skips a decision that has nothing to do with the effect under test.

   `/scenario` re-reads the state it wrote and refuses the request if it did
   not round-trip, so a field that fails to land is an error rather than a
   quietly different board. It cannot catch a field you never asked for,
   though: setting a chain link without its summary row produced a chain that
   was visible in the state and invisible to every combo card. **Assert on the
   outcome — the power, the damage — never on the scenario echo.**

   What a scenario cannot express yet: anything resting on accumulated turn
   history (class-state counters, per-turn stats), since the patch sets zones
   and turn scalars only. `--play-games` keeps the old stack-the-deck-and-play
   path for those.

9. **Update the work queue:** `python scripts/dsl_work_queue.py --set <set> --write-queue`
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
- [ ] `python scripts/verify_card_against_talishar.py --card <slug>` run, and
      the verdict is `AGREES` or `NO EVIDENCE`. A `DISAGREES` is a lead to
      read, not necessarily a defect — but it must be read, not skipped.
- [ ] Work queue status refreshed

## Verifying a batch of cards

Three layers, each catching what the others structurally cannot. Run them in
this order — each is slower and noisier than the last.

1. **Mechanical** — `pytest tests/test_card_json_hygiene.py`. Sub-second, fully
   deterministic, part of the suite. Proves the JSON is well-formed and filed
   correctly. Cannot tell you whether it does the right thing, or anything.

2. **Execution** — `python scripts/dsl_coverage.py --seeds 10`. Plays real
   games and reports authored effects that never fired. An ability whose
   trigger the engine never dispatches passes layer 1 and is inert; this is the
   only layer that catches it. Read the two sections separately: cards in a
   tested deck that never fired are real suspects, cards no deck can draw are
   merely untested.

3. **Semantic** — `python scripts/dsl_semantic_audit.py --set <code> -o report.md`.
   Asks an LLM whether the JSON implements every clause of the printed text.
   Slow, costs money, and produces suspicions rather than verdicts, so it is a
   batch job you triage — never a test.

   Two rules. It **never edits card JSON**, and neither should you wire it to:
   a model that fixes its own work confirms its own misreadings. And run it in
   a *different session* from the one that authored the cards, for the same
   reason.

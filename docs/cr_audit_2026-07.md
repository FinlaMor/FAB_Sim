# Comprehensive Rules Audit — 2026-07-14

Engine audited against `docs/ref/en-fab-cr-comprehensive-rules.txt` (sections 1,
3, 4, 5, 6, 7, and the implemented parts of 8). Scope: `engine/engine.py`,
`play.py`, `actions.py`, `state.py`, `effects.py`, `effect_keywords.py`,
`card_effects/registry.py`. Findings are ordered by severity; each cites the
CR clause and the code location.

## Gameplay-review round 2 (2026-07-14)

More bugs found reviewing recorded games, all fixed with coverage in
`tests/test_cr_audit_fixes.py`:

- **`card.controller` was never set** (stayed `None` from deck build). Most
  logic tolerated it via `_controller_id`'s owner fallback, but conditions
  reading `card.controller` directly did not — e.g. `ATTACK_CONTROLLED_BY_YOU`,
  so **Kayo's instant ("target attack action card you control") was never
  offered** even when attacking with an attack action card (12 affordable
  windows missed in one game). CR 1.3.1b fix: set controller when a card is
  played (`_apply_play_card`), when it becomes the active attack
  (`_attack_step`, covers weapon proxies), when it defends
  (`_apply_defend` / `add_defend`), and centrally on any arena entry
  (`Zone.add`).
- **Equipment/permanent activated abilities were never offered.** The generic
  `activatable`-flag path was dead (`base_activatable` is never set True), so
  Scabskin Leathers, Fyendal's Spring Tunic's instant, etc. could not be
  activated. `_add_hero_dsl_activations` generalized to offer DSL
  ACTIVATE/INSTANT/ATTACK_REACTION abilities of the hero AND every arena
  permanent, with per-type timing, per-turn-limit, cost, and target-filter
  gates (attack-effect abilities still routed through the weapon path).
- **"Attack action card you control" now includes a defending attack action
  card** (CR: defending with an attack action card counts as controlling it).
  New `CONTROLS_ATTACK_ACTION` condition + `controlled_attack_action_cards`
  helper; `SET_BASE_POWER` targets the controlled card (active attack or
  defending card), asking the controller to choose when several qualify.
- **`GO_AGAIN` effect type was unimplemented** (Blacktek Whisperers,
  Enlightened Strike). Never reached before because equipment activated
  abilities were never offered; the generalized activation path surfaced it.
  Implemented: grants the attack "Go Again" (matched to the resolution-step
  check). Also canonicalised the `GAIN` keyword form so `"GO_AGAIN"`/`"go_again"`
  spellings are recognised at resolution.
- **On-attack power buffs were lost at the defend step.** `MODIFY_ATTACK`
  bumped `combat.attack_power` in place, which `_recalculate_attack_power`
  (run at the defend and damage steps) overwrote from base — so Reckless
  Arithmetic's rolled "+X{p}" vanished after the Attack Step. Fixed by
  recording one-shot modifiers on a new per-`CombatState` `power_mods` list
  that every recalculation re-applies (resets per attack, so no leak across
  chain links/turns); WHILE_STATIC abilities still apply transiently each
  recalc (they carry the `recalculate_attack_power` event).
- **`SET_BASE_POWER` overwrote instead of restaging.** Kayo's "has 6 base {p}"
  set `attack_power = 6` directly, wiping a stage-8 "+{p}" already applied
  (Reckless Arithmetic rolled 3 → attacking for 4, then Kayo should make it
  base 6 + 3 = 9, but it became 6). Fixed to set base power then recalculate,
  so stage-8 modifiers (`power_mods`) reapply on top of the new base.
- **Activation resource cost counted `{r}` in the effect text.** `card.py`
  parsed the resource cost by counting every `{r}` in an ability, so Fyendal's
  Spring Tunic ("Remove 3 energy counters: Gain {r}") was read as costing 1
  resource instead of 0. Fixed to count `{r}` only in the cost portion
  (between the type dash and the colon). (The old `split(r"\n\n")` never
  actually split — the fix parses real ability blocks; the downstream
  ability-flag parser is left on the original split to avoid behavior change.)
- **Instants were charged 1 action point.** `_apply_play_card` deducted an AP
  for any played card unless it was type Instant AND `played_as_instant` — so
  Sigil of Solace (type Instant) cost 1 AP. Fixed to CR 5.1.6b: 1 AP only when
  the card has type Action and is not played as an instant (instants and
  reactions cost 0).
- **Apex Bonebreaker triggered on every defend.** Its JSON was a bare
  `ON_DEFEND` create-token with no condition, so it made a Might whenever it
  defended (against any attack, alone, or with a weak co-defender). Added a
  new `CODEFENDER_POWER_GTE` condition ("defends together with a card with
  6+ {p}", CR 7.0.5e); also made `_apply_defend` add all blockers before
  firing the `defend` events (CR 7.3.2d compound event) so "defends together"
  triggers see every co-defender. (The "two Mights" the player saw was a
  display artifact — see next.)
- **Snapshot double-listed typed permanents.** `snapshot_state` listed
  `items`/`auras`/`allies`/`tokens` and then `permanents` (the backing zone)
  including those same cards — so an aura token (e.g. Might) showed up twice
  in the replay. Fixed: `permanents` now excludes cards already in a typed
  view.
- **Kayo's instant offered the wrong target.** The hero-activation offering set
  the action's target to `combat.attack_card` (the active attack) for every
  ability, so when Kayo defended with an attack action card, his "target attack
  action card you control" was presented targeting the opponent's active
  weapon (Miller's Grindstone — an illegal target), while the defending card he
  could legally target wasn't listed. (The effect still resolved on the right
  card via `controlled_attack_action_cards`, so it looked like "nothing
  happened".) Fixed: the offering now enumerates the legal targets for a
  CONTROLS_ATTACK_ACTION ability (one action per controlled attack action card),
  and the declared target is threaded through to `SET_BASE_POWER` (CR 5.1.4)
  instead of being re-resolved.
- **Defense reactions were declarable as blockers in the Defend Step.**
  `get_defendable_cards` excluded cards whose type is `"Defense Reaction"`
  (with a space), but the card DB stores `"DefenseReaction"` — so Sink Below
  was offered as a blocker during the Defend Step (CR 7.3.2a: only
  non-defense-reaction cards may be declared; DRs are played in the Reaction
  Step). Fixed to use the normalized `is_defense_reaction`.
- **Savage Claw buffed the opponent's attack.** Its "+1{p} if a 6+ card was
  pitched to attack WITH THIS" was a `WHILE_STATIC` gated only by
  `ATTACK_PITCH_POWER_GTE` — it didn't check that Savage Claw was the attack,
  so it added +1 to any attack in combat (e.g. an opponent's Miller's
  Grindstone). Added a `SOURCE_IS_ATTACK` condition so the self-buff applies
  only to Savage Claw's own attack.
- **Replay viewer: counters now shown.** `snapshot_state` carries per-card
  counters (`{slug: {type: count}}`), and the viewer renders a badge on the
  card (e.g. energy counters accumulating on Fyendal's Spring Tunic).
- **Activated DEFENSE_REACTION abilities were never offered.** The activation
  path handled ACTIVATE/INSTANT/ATTACK_REACTION but not DEFENSE_REACTION, and
  Quickdodge Flexors had an empty JSON. So an equipment defense reaction
  ("Defense Reaction - {r}: Add this to the active chain link as a defending
  card…") was never presented. Fixed: `_add_hero_dsl_activations` now offers
  DEFENSE_REACTION activations to the defender during the reaction step
  (gated by 7.4.2c; Dominate is hand-scoped so it doesn't block an equipment
  DR); new `ADD_DEFEND` effect (add self as a defender with N {d}); Quickdodge
  JSON authored, including its "beginning of the end phase" self-destroy via a
  new `BEGINNING_OF_END_PHASE` trigger that fires for both players' permanents
  (it defends on the opponent's turn, so a turn-player-only END_OF_TURN would
  miss it).

## Fix status (updated 2026-07-14, same session)

| Finding | Status |
|---|---|
| H1 resolution-at-announce | **FIXED** — non-attack card layers carry their DSL dispatch in `StackEntry.effect_fn` (resolved by `resolve_stack` after priority); attacks dispatch `ON_PLAY` at the Attack Step (CR 7.2.3); the announce-time `on_play` event remains for "when a player plays" triggers only |
| H2 damage always to hero | **FIXED** — `_resolve_damage` deals to `combat.attack_target_card` when set (7.5.2b ceased-target and 8.5.3c non-living checks included); ally *targeting* still not offered in legal actions (deferred until ally decks) |
| M1 target legality at Attack Step | **FIXED** — declared target gone → attack goes to owner's graveyard, chain closes (7.2.2/7.7.3) |
| M2 attack not on stack during priority | open |
| M3 triggered-layer target declaration | **partially fixed** — DSL `target.filter` is now enforced at announce for card plays (CR 1.8.5: "Target attack with stealth" is unplayable without a stealth attack); resolution-time target recheck (5.3.2a) still open |
| M4 SBA approximation | open |
| L1 ally life reset (all players) | **FIXED** |
| L2 chi cleared at end of turn | open — confirm intended policy |
| L3 defend compound event | open |
| L4 DR resolution timing | **FIXED** — a DR card-layer becomes a defending card via `add_defend` when its layer resolves (7.4.2d/8.1.3b) |
| L5–L8 | open (L5/L6 by design) |

Additional bugs found and fixed while implementing:
- **AR/DR cards were never playable**, for three stacked reasons, all fixed:
  1. `_attack_reaction_legal_check` / `_defense_reaction_legal_check` compared
     a `Step` enum to a string (always unequal) and required `attack_target`
     to be non-None (it is None for normal hero attacks).
  2. `_legality_check` supplemented `card.types` with substring scans of the
     functional text — `'action' in text` matches inside "re**action**" and
     rules text like "Target attack **action** card", so every reaction was
     also flagged as an Action card and failed `_action_legal_check` during
     combat. The text scan is removed; `card.types` is authoritative.
  3. `Card.is_defense_reaction` checked for `"Defense Reaction"` while the
     card DB stores `"DefenseReaction"`. Now normalized.
  DR legality also now enforces Dominate-from-hand (8.3.4b) and
  `no_defense_reactions` (7.4.2c). Regression coverage:
  `tests/test_cr_audit_fixes.py`.
- **Every DB-built card had `pitch/cost/power/defense = None`** —
  `CardDB.get` constructed the `Card` before assigning raw stats, so the
  raw→base→current cascade in `__post_init__` ran on empty values (base_*
  was later re-synced, current values were not). Consequences: nothing
  could ever be pitched, all play costs were effectively zero, and no card
  could ever block (`has_defense` False). One sync block in `card.py` fixed
  pitching, paying, and blocking game-wide.
- **`order_stack` reordered card-layers** — a card played in response to
  another card triggered the CR 6.6.6b "who resolves first" prompt and let
  players reorder the stack. Rewritten: only newly-created triggered-layers
  are ordered (once); card-layers keep their LIFO positions (CR 3.15.4).
- **Targeting authored as resolution `conditions`** — five attack reactions
  (both Stains of the Redback, Take Up the Mantle, Shred, Blacktek
  Whisperers) modeled "Target attack …" restrictions as ability `conditions`
  (resolution-time no-op) instead of `target.filter`; combined with the
  missing 1.8.5 gate they were playable against illegal targets.
- **Temper/Battleworn counter bookkeeping crashed** (`_apply_defense_counter`
  unpacked `card.effects` as tuples; they are `CardEffect` objects) — latent
  until the stat fix made equipment blocks actually happen.
- **`_fire_on_discard` called `.slug` on the weapon zone** instead of the
  cards in it — crash whenever a discard trigger fired with a weapon equipped.
- **Resolved cards leaked into stack-zone limbo**: resolved non-attack card
  layers were removed from the stack list but never cleared to the graveyard
  (CR 5.3.7/3.0.12) — played instants/actions were unreachable for
  graveyard-count effects. Attacks similarly left stale references in the
  stack zone. Both fixed in `resolve_stack`/`_attack_step`.

## HIGH — rules deviations with interaction-correctness impact

### H1. Card resolution abilities fire at announce time, not at layer resolution
**CR 5.1.10, 5.3.1–5.3.4, 1.11.5** — after a card is played, players receive
priority and the card's resolution abilities generate effects only when the
card-layer *resolves* (all players pass in succession).
**Engine** — `play.py:_apply_play_card` emits `on_play` immediately after
putting the card on the stack (`play.py:546`); `engine.py:_dsl_on_play_listener`
(`engine.py:1088`) dispatches the DSL `PLAY`/`ACTION`/`MODAL` abilities
synchronously. The `StackEntry` created for the card has no `effect_fn`, so the
later `resolve_stack` pop is a no-op for the card's own effects.
**Consequence** — opponents can never respond *before* a non-attack card's
effect resolves (instants in response are impossible); negate/counter-style
effects can't function; "while a layer is on the stack" interactions see a
completed effect. Attack cards' `ON_ATTACK` effects fire at the correct time
(Attack Step, 7.2.4), but any `PLAY`-typed ability on an attack also fires early.
**Fix direction** — move the DSL dispatch into `StackEntry.effect_fn` (executed
by `resolve_stack`), keep the `on_play` *event* at announce for "when a player
plays a card" triggers only. This is the single largest structural change and
affects reaction-step DR/AR timing too (see M2).

### H2. Combat damage is always dealt to the defending hero
**CR 7.5.2, 1.4.5a** — damage is dealt to the *attack-target*; any living
object (including opposing allies) is attackable.
**Engine** — `engine.py:_resolve_damage` applies
`defender.health -= net_damage` unconditionally, ignoring
`combat.attack_target_card`. Legal-action generation never offers opposing
allies as attack targets (only heroes, plus Spectra auras via
`declared_targets`).
**Consequence** — latent today (Spectra targets self-destruct before the
Damage Step), but wrong the moment ally-heavy decks (Guardians of Rathe /
Uprising allies) are implemented: the ally would be untouched and the hero
damaged instead. The `hit`/`hit_hero` split and the "ally-hit path to be
added" comment (`engine.py:1318`) acknowledge this.

## MEDIUM — timing/structural deviations

### M1. Attack-target legality is not rechecked at the Attack Step
**CR 7.2.2** — at the start of the Attack Step, at least one attack-target must
still be legal, otherwise the Close Step begins.
**Engine** — `engine.py:_attack_step` resolves `declared_targets[0]` by
searching permanents; if the target card no longer exists it silently leaves
`attack_target = None`, which the rest of the engine interprets as "targets
the hero". An attack whose Spectra-aura target was destroyed during the Layer
Step should close the chain; instead it retargets the hero. (7.5.2b damage-time
legality is also unchecked, moot while H2 stands.)

### M2. The attack layer is not on the stack during Layer/Resolution Step priority
**CR 7.1.3, 3.15.4-5** — the attack sits on the stack as the bottom layer; the
Layer Step ends when it is the *top* layer and all players pass.
**Engine** — `engine.py:_combat_phase_iter` and `_resolution_step` *remove* the
attack `StackEntry` before running the priority window. Players do get the
priority window (functionally close), but the attack is invisible to anything
that inspects the stack (negate target attack, layer-counting effects), and
new layers can't be ordered relative to it. `priority_loop`'s `only_attack`
check papers over the same distinction.

### M3. Triggered-layer parameters are not declared when the layer is added
**CR 6.6.6a, 5.3.2a-b** — when a triggered-layer goes on the stack, its
controller declares modes/targets; with no legal target the layer ceases to
exist; on resolution, targets and state-trigger conditions are rechecked and
the layer can fail to resolve.
**Engine** — triggered `StackEntry`s carry a closure (`effect_fn`) with no
declared targets; there is no generic fail-to-resolve check (Phantasm's
state recheck is implemented ad hoc inside its own keyword functions).
Acceptable for currently implemented cards, but the DSL will need
layer-level target declaration for reactive trigger interaction.

### M4. Game state actions are approximated
**CR 1.10.2** — SBAs run on every transition to a priority state.
**Engine** — `check_state_based_actions` (hero + ally death) is called after
actions, resolutions, and damage — a good approximation — but not after every
arbitrary event (e.g. a mid-resolution life loss is only caught at the next
call site). 1.10.2e (chain-close as a game state action) is handled by ad-hoc
`Step.COMBAT_CLOSE` checks sprinkled through the combat code rather than one
SBA gate. Ally deaths `destroy()` (→ graveyard) rather than "clear"; identical
for token allies, slightly off for card allies (destroy-triggers could fire
where CR says cleared — verify per-card as ally cards get implemented).

## LOW — minor deviations and simplifications

- **L1. Ally life reset covers only the turn-player's allies** — CR 4.4.3a
  resets *all* allies' life at the end-of-turn procedure; `engine.py:715`
  iterates `player.allies` (turn player) only.
- **L2. Chi is cleared at end of turn** — CR 4.4.3e clears only action and
  resource points; `engine.py:770-773` also zeroes `chi`. Confirm intended
  behavior (official rulings on chi persistence may differ from the CR text
  snapshot in this repo; the doc as written says chi persists).
- **L3. Defend declarations are not a single compound event** — CR 7.3.2d puts
  all declared cards on the chain link as one compound event ("defend
  together"); `_defend_step`/`_apply_defend` add cards and emit `defend`
  events sequentially. "Defends together/alone" triggers (e.g. Bastion of
  Unity) would mis-evaluate.
- **L4. Reaction-step DRs become defending cards immediately** — CR 7.4.2d has
  a DR become a defending card when its layer *resolves* (and it can fail to
  resolve, e.g. vs Dominate with a hand card already defending). The engine
  applies the DR effect at play time (consequence of H1). The Dominate
  play-legality gate (8.3.4b) is correctly enforced (`actions.py:1062`), so
  only the two-DRs-on-the-stack corner case misbehaves.
- **L5. Turn-cap game end** (`_end_game_on_turn_cap`) — not a CR rule
  (approximates 4.5.4d stalemate). Intentional simulation guard; fine, keep.
- **L6. Loop safety caps** — `priority_loop` (2000 iterations) and
  `_resolve_all_triggers` (500) force-exit pathological loops. Simulation
  guard; only deviates in states that would be a judge call anyway.
- **L7. Pitch mechanics simplified** — CR 1.14.2a/d requires chi to be spent
  before resources and pitching one card at a time during payment; the engine
  precomputes pitch sequences and tracks chi as a separate pool without the
  strict chi-first ordering. Outcomes match for current decks.
- **L8. Start-of-turn refresh resets both players' per-turn activations and
  weapon exhaustion** — equivalent to CR per-turn limits for current cards;
  the CR's untap (4.4.3d) applies to the turn-player only, which the end-phase
  untap (`engine.py:762`) does correctly.

## Verified correct (spot-checked against CR)

- **Turn structure 4.1–4.4**: start-of-game event + equip + intellect draw-up;
  Start Phase without priority (4.2.1-2); AP=1 without gain-triggers (4.3.2a);
  action→combat→continue-action flow (4.3.4, 7.7.7 — AP and
  beginning-of-action-phase fire once per turn); End Phase procedure order
  4.4.3a-f including arsenal-if-empty, per-player pitch-to-bottom with player
  ordering (hidden), AP/RP loss, first-turn both-players draw-up (4.4.3f),
  effect expiry at 4.4.4 before turn hand-off.
- **Combat 7.1–7.7**: step sequence with priority at each step; chain-link
  continuation on new attack during Resolution (7.6.3a) with per-link
  Layer→…→Resolution recursion; Close Step without priority; combat-chain
  close event → triggers → permanents return / non-permanents to graveyard
  (7.7.3-7.7.6); chain-link history retained.
- **Damage 7.5**: power − total defense; replacements applied before the hit
  determination, so fully-prevented damage is not a hit (7.5.5b); hit events
  only on damage > 0.
- **Priority & stack 1.11 / 3.15 / 5.3**: actor regains priority (1.11.5);
  both-pass → top layer resolves LIFO; turn-player regains priority after each
  resolution (5.3.7); go again grants at the correct times for attacks
  (7.6.2/8.3.5b) vs non-attack layers (5.3.5/8.3.5a) with non-turn-player AP
  denial (1.13.2b/8.5.7b); permanents (Aura/Ally/Figment/Landmark) leave the
  stack into the arena on resolution (5.3.6a) with Landmark uniqueness.
- **Triggers 6.6.6b / 1.10.2d**: turn player picks the first orderer; each
  player orders their own triggered-layers.
- **Replacements 6.4/6.5**: type ordering self/identity → standard →
  prevention → outcome; shielding vs fixed prevention; unpreventable damage
  still fires self-sacrifice effects without reducing damage (6.4.10h).
- **Keywords**: Dominate 8.3.4 (hand-card cap + DR-from-hand block), Overpower
  8.3.22 (action-card cap), Piercing 8.3.23 (current "+N{p} if defended by
  equipment" wording), Phantasm 8.3.13 (destroy + close-only-before-damage),
  Ward/Spellvoid/Arcane Barrier prevention forms, Intimidate 8.5.10 (random
  face-down banish + END_PHASE_BEGINNING return), Boost/Fusion/Heave/Crank
  optional-cost forms, Temper/Battleworn/Blade Break/Guardwell equipment
  triggers at chain close.
- **Effect keywords 8.5**: draw fails silently on empty deck (8.5.6b — no
  deck-out loss in FAB); discard/destroy/banish as composite events through
  canonical functions; damage types segregated (8.5.3b/e/f); clash 8.5.45
  including tie-no-winner and the outcome-replacement hook (6.4.11).
- **Zones 3.x**: zone privacy defaults; arsenal single-card limit (3.3.2);
  public/private transitions on move (3.0.8); clearing to graveyard vs tokens
  ceasing to exist (3.0.12/3.0.12a); LKI snapshots at chain close (1.2.3).

## Suggested priority order for fixes

1. **H1** — route DSL play-ability dispatch through `StackEntry.effect_fn`
   (largest change, unlocks correct instant/reaction interaction everywhere).
2. **M1** — close the chain when the declared attack target is gone at the
   Attack Step (small, self-contained).
3. **H2 + attack-target plumbing** — deal damage to `attack_target_card` when
   set; add ally targeting to legal actions when ally decks arrive.
4. **L1/L2** — one-line end-phase fixes (all allies reset; decide chi policy).
5. **M2/M3** — represent the attack and triggered-layer targets on the stack
   properly (do together with H1 if rewriting stack handling).

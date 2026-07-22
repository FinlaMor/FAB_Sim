# Game-transcript rules audit — 2026-07-22

Ran 9 sample games across the three test decks (Victor / Kayo / Arakni CC_lite,
HeuristicBot both seats) with full `JsonlRecorder` transcripts, then checked
each transcript against FAB comprehensive-rules invariants with
`scripts/game_transcript_audit.py`.

## Method

`scripts/collect_sample_games.py --games 3` produced one JSONL transcript per
game (every decision + full state snapshot, events, actions, outcome).
`scripts/game_transcript_audit.py <dir>` then checked, per snapshot:

- **Starting conditions** — opening hand == hero intellect; start life.
- **Life / winner integrity** — no player at <=0 life in a live state; the game
  ends with the loser at <=0 (or a turn cap) and the winner alive.
- **Zone sanity** — arsenal <=1 card; non-negative resources / deck_count.
- **Card conservation** — the count of real (non-token) cards never rises above
  the opening count (a rise = a card created from nothing). Tokens are excluded
  via the slug index; in-flight cards on the stack / in combat are counted.

## Findings

### 1. CONFIRMED BUG — Victor drew a card during the start-of-game procedure

Every game with Victor as P1 opened with a **5-card hand instead of 4**.

Root cause: **Crown of Dominion** (`ON_EQUIP` -> create a Gold) fires as
starting equipment is placed during setup (CR 4.1.8), and Victor's hero
ability *"The first time each turn you create a Gold token from an effect you
control, draw a card"* triggered off that Gold — before turn 1.

This is the **verbatim example in CR 4.1.8b**:
> If an effect would only trigger during a player's turn, it does not trigger
> during the start-of-game procedure. *Example:* Victor ... "The first time each
> turn you create a Gold token ... draw a card." If a player creates a Gold
> token ... during the start-of-game procedure, Victor's effect will **not**
> trigger because it is not during a player's turn.

**Fix:** added a reusable `DURING_TURN` DSL condition (true iff
`individual_turns >= 1`, i.e. not the start-of-game procedure) and gated
Victor's `ON_GOLD_CREATED` trigger on it. Victor now opens with 4 and still
draws off the first Gold he creates during an actual turn.

- `engine/card_effects/dsl/condition_types.py` — `DURING_TURN` primitive
- `engine/card_effects/json/hvy/victor_goldmane_high_and_mighty.json` — gate
- `tests/test_cr_audit_fixes.py` — `test_victor_gold_draw_not_during_start_of_game`,
  `test_victor_gold_draw_fires_once_per_turn_during_a_turn`

Re-collected transcripts after the fix: **0 violations across all games**.

Note: CR 4.1.8b is a **general** rule. Victor is the only turn-restricted
trigger reachable at setup in these three decks, but any future card whose
trigger is limited to "each turn" / "during your turn" needs the same
`DURING_TURN` guard (or a general engine implementation of 4.1.8b).

### 2. No other violations (9-game sample)

Life totals, win conditions, arsenal-size, resource, and deck-count invariants
all held. Real-card conservation held exactly.

---

## Larger batch — 2026-07-22 (240 games)

Re-ran with 120 heuristic + 120 random games (both seatings, `--games 20
--both-seatings` each). Random games are longer and exercise far more card
interactions, and surfaced two more findings plus one auditor false positive.

### 3. CONFIRMED BUG — destroying an equipped weapon could duplicate it

Flick Knives ("Target dagger you control ... deals 1 damage ... Destroy the
dagger") destroying one of two equipped Hunter's Klaive daggers — while the
other was the active attacking weapon — left the destroyed dagger **both**
equipped in its slot **and** added a copy to the graveyard. The phantom copy
persisted to game end (3 Klaive where the deck has 2).

Root cause in `engine/effect_keywords.py::destroy`: removal was keyed off
`destroy_target.zone` (a name). A weapon sitting in the weapon2 slot but whose
`.zone` is the generic `"weapon"` (which `zone_by_name` maps to weapon1) was not
found, so `Zone.remove` failed — but the function added it to the graveyard
anyway, materialising a duplicate.

**Fix:** `destroy` now falls back to an identity sweep across every zone when the
name lookup fails, and refuses to add a graveyard copy if the target was never
removed from any zone. The stale shared-zone fallback (which also never set
`removed`) was corrected. Test: `test_destroying_weapon2_card_with_generic_zone_
does_not_duplicate`. Re-collected random games: `hunters_klaive` duplication
gone; `kiss_of_death` (also a dagger) dropped 3 games -> 1.

### 4. FIXED — the loss (SBA) is now applied before triggers resolve (CR 1.10.2a)

24 of 240 games had a snapshot where a player was at <=0 life but the game was
not yet done, resolving triggered effects — sometimes prompting the **defeated**
player — before `game_end`. CR 1.10.2 performs game-state actions when the game
transitions to a priority state, and 1.10.2a (a hero at 0 life -> that player
loses) runs *before* 1.10.2d (triggered-layers are added to the stack).

Two paths were affected:
- **Combat on-hit** (the `combat_damage` cases): `_resolve_damage` applied damage
  and emitted the `hit` event — whose listener resolves on-hit effects
  synchronously — *before* the loss check. Now it checks the loss immediately
  after applying damage and returns without firing `hit` if the hit was lethal.
- **No-priority-window damage** (`action`/`end_phase` cases): a player taken to
  <=0 by a start-of-turn Bloodrot Pox DoT kept playing because no SBA ran until
  a later checkpoint. `priority_loop` now performs the loss game-state action at
  the top of the loop (the transition into a priority state).

Result across a fresh 120-game random batch: **0 life<=0-not-done snapshots**
(was 24). Regression tests: `test_lethal_combat_hit_ends_game_before_on_hit_
triggers`, `test_nonlethal_combat_hit_still_fires_on_hit`,
`test_priority_loop_ends_game_when_a_player_is_already_dead`.

### 5. FIXED — Take Up the Mantle copy did not revert (CR 3.0.9)

The "banish/play-from-banish duplication" was mostly one bug plus tooling noise.
Take Up the Mantle ("the target becomes a copy of the banished card") permanently
overwrote the target attack's identity (`COPY_BANISHED_STEALTH_ATTACK`) and never
reverted, so when the copied attack went to the graveyard it stayed labelled as
the copied card — a mislabelled duplicate. CR 3.0.9: an object entering a
non-arena, non-stack zone resets to a new object with no relation to its previous
existence, i.e. its printed card. Fix: save the target's printed identity and
restore it when the combat chain closes. Test:
`test_take_up_the_mantle_copy_reverts_when_chain_closes`.

The auditor's conservation check also over-reported: it flagged transient
mid-game peaks (a card briefly counted in two zones during a multi-event window)
as "card created." It now flags only rises that persist to game end. After both
fixes, a fresh 120-game random batch shows **1** persistent +1 (a hidden-deck
card in a single game) — down from the original class of 4 cards across many
games — left as a documented, much-reduced follow-up.

### Auditor false positive fixed — `reviled` token

The conservation check first reported ~64 random-game "card created" flags, 50 of
them the `reviled` token, whose `slug_index` entry has no type metadata so the
typeText heuristic missed it. `scripts/game_transcript_audit.py` now treats every
`engine/card_effects/json/tokens/*.json` stem as a token (authoritative), which
removed those false positives.

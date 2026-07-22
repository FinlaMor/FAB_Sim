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

### 2. No other violations

Life totals, win conditions (loser reaches <=0, SBA ends the game, winner
alive), arsenal-size, resource, and deck-count invariants all held across every
game. Real-card conservation held exactly: totals only dipped while cards were
mid-resolution (on the stack / in combat) and never exceeded the opening count,
so no card was created or destroyed illegitimately.

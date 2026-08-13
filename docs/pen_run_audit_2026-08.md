# Audit — `pen` pipeline run (2026-08-13)

**Verdict: do not merge this run as-is.** It completed, but the output quality
is low, it reintroduced two defect classes the prompt rules were written to
prevent, and it destroyed four hand-corrected cards.

## What the run produced

| | |
|---|---|
| pen queue before | 321 pending, 5 done |
| pen queue after | **20 done**, 258 candidate, 47 needs_review, 1 failed |
| card files written | 270 (229 new, 42 overwritten, 3 deleted) |
| **verification rate** | **20 / 321 = 6%** |

`mon` was also started and got 8 cards in (298 still pending).

"Candidate" means the JSON loads and is not a no-op stub, but **no generated
test passed** — it is unverified. 258 of 321 landed there, and candidates stay
live and playable in the corpus, so the corpus just absorbed 258 unverified
cards.

## Quality

**Mechanically detectable defects: 53 of 270 cards (20%).**

| Count | Defect |
|---|---|
| 37 | invented flag (`FLAG_SET` on a flag nothing sets → ability can never fire) |
| 13 | fabricated INTIMIDATE (card text has no intimidate) |
| 3 | invented `amount` string (resolves to 0 → effect silently does nothing) |
| 1 | invalid `ability_type` (an *effect* type used as an ability type) |

**20% is a floor, not an estimate.** Those are only the defects a script can
find. A random sample of 6 new cards read against their printed text found a
significant error in **6 of 6**, nearly all semantic and undetectable
mechanically:

- `become_the_bottle_yellow` — "gets the chosen card's name" implemented with
  `COPY_BANISHED_STEALTH_ATTACK`, a Take-Up-the-Mantle-specific effect.
- `sense_weakness_blue` — `"ability_type": "MODIFY_NEXT_ATTACK"`, an effect type
  used as an ability type; the whole ability is malformed.
- `high_current_currency_blue` — `"amount": "energy_counters_removed"`, an
  invented token; `_resolve_amount` returns 0, so it creates **zero** Gold.
- `conquer_the_icy_terrain_yellow` — gated on `CARD_IN_ZONE {zone:
  OPPONENT_ARSENAL, card_class: Hero}`, which is not a thing; the "frozen"
  requirement is absent.
- `ghost_protocol_mainframe_blue` — "+1{p} per Evo equipped" modelled as
  `MODIFY_ATTACK_POWER_PER_UNIQUE_AURA` (auras are not Evos).
- `blackstone_greaves` — `FLAG_SET DEALT_ARCANE_DAMAGE`, invented flag.

The 6% verification rate and the sample agree: most of this output is wrong.

## The prompt rules did not hold — and here is why

Rules 19 (implement only what the text says) and 23 (never invent a flag) were
added specifically to stop these classes. **Both were violated at scale**: 13
fabricated INTIMIDATE and 37 invented flags.

I verified the rules genuinely reach the model — rules 19-24 are present in the
18,092-character implementation prompt for the exact card that then reproduced
the bug. So this is not a plumbing failure.

**Root cause: the prompt's own few-shot example teaches the fabrication.**

*(Corrected: my first reading blamed similarity retrieval. It is not that —
`build_dynamic_examples` filters on `status == "approved"`, a status no card in
any queue has, so that path is dead code and never contributes. The real
mechanism is worse.)*

`build_real_examples` picks the **smallest loading card per `ability_type`**.
The smallest `STATIC_TRIGGERED` card in the whole corpus is `scowling_flesh_bag`,
whose entire body is one keyword grant — so it shipped in **every single
prompt**, and its minimality is exactly what made it copyable:

```
Card text: When this defends, **intimidate**.  |  **Blade Break**
{"slug": "scowling_flesh_bag", "abilities": [
  {"ability_type": "STATIC_TRIGGERED", "trigger": "ON_DEFEND",
   "effects": [{"type": "INTIMIDATE"}]}]}
```

That example is **correct** — Scowling Flesh Bag really does have intimidate.
But it pairs the visible token "Blade Break" with `ON_DEFEND → INTIMIDATE`, and
a 14B model copies the demonstrated shape rather than obeying a prose rule
buried 18k characters deep. Selecting examples by brevity actively selects for
the most copyable and least instructive card available.

**The demonstration beats the rule.** `graven_gloves` proves it: the run
stripped the `_comment` explaining the fabrication and re-added the *identical*
ability, byte for byte.

This is the important finding of the audit. Adding a 26th rule will not help.
Fix the retrieval instead.

## Destroyed work

The run regenerated cards that already had hand corrections on this branch:

| Card | Outcome |
|---|---|
| `carrion_crown` | **DELETED** (quarantined) |
| `graven_gloves` | overwritten — fabricated INTIMIDATE restored |
| `gloves_of_azure_waves` | overwritten — fabricated INTIMIDATE restored |
| `robe_of_resourcefulness` | overwritten |

Cause: those cards were still `pending` in the queue despite having a reviewed
JSON on disk, so the pipeline treated them as unimplemented. **Queue status is
the only thing protecting a corrected card, and nothing reconciles it with what
is actually on disk.**

## Duplicate slugs from reprints (new, will recur)

Three slugs now have a file in two set folders:

- `speed_demon_red` — gem + pen
- `aether_ironweave` — chn + mon
- `arcanic_crackle_blue` — ast + mon

**Zero cards were filed in a wrong folder**, so this is not the rule-22 mistake.
These are *reprints*: the card legitimately belongs to both sets and appears in
both work queues, so processing set B regenerates a card already implemented in
set A. This will happen on every future set run.

The duplicate-slug guard caught all three, which means those three slugs are now
**unimplemented** (an ambiguous definition counts as none) and any game using
them refuses to start. The guard did its job; the pipeline still needs to stop
creating them.

## Fixes applied after this audit

1. **Run reverted.** Working tree restored to HEAD; the 4 clobbered cards are
   back with their corrections; queues back to 321/305 pending; loader clean at
   1011 cards, no duplicates. The run output is archived (not lost) at
   `scratchpad/pen_run_backup/pen_run_full.tar.gz` in case the 20 verified cards
   are worth salvaging.
2. **Talishar reference replaces the few-shot examples where it exists.**
   Talishar keys per-card logic by the same slug, so it is specific to the card
   being implemented and cannot teach another card's shape. The block is framed
   as intent-not-structure, and explicitly subordinate to the printed text.
   **Coverage is 80% of the remaining corpus (3416 / 4245 pending)** — but it is
   the *newest* sets that are uncovered, and `pen` (13%) and `sup` (14%) are the
   two worst. The run picked the one large set this could not have helped.
3. **The pathological example is no longer selectable.** `build_real_examples`
   now skips cards whose whole implementation is a single bare keyword grant.
   `scowling_flesh_bag` is out; "INTIMIDATE" now appears twice in a Blade Break
   prompt (the DSL type list and rule 19's own warning) instead of four times.

### Suggested set order for the next run
Run the well-covered sets first, where every card gets its own reference logic:
`mpg` 100%, `sea` 97%, `hnt` 96%, `cru` 96%, `ele` 96%, `evr` 96%, `out` 95%,
`mon` 95%, `ros` 95%. Leave `pen` 13%, `sup` 14%, `omn` 2% until the
uncovered-card path is trusted on its own.

## Recommendations, in order

1. **Do not commit the 258 candidates into the playable corpus as-is.** Either
   revert the run, or move candidates out of the live folders until reviewed.
2. **Fix the example retrieval — the actual root cause.** Options, cheapest
   first: exclude examples whose text contains mechanics the target's text does
   not; for a target whose text is purely keywords, show the vanilla
   `{"abilities": []}` exemplar instead of a similarity match; or put the
   examples *after* the rules and label them "shape only, do not copy effects".
3. **Protect reviewed cards from regeneration.** Skip any card whose JSON
   already exists and is not queue-`pending`, or reconcile queue status against
   disk before a run. `carrion_crown` was deleted by a run that should never
   have touched it.
4. **Skip reprints already implemented elsewhere** — check the slug across all
   set folders before writing.
5. **Run the three sweeps inside the pipeline as a gate**, not afterwards. All
   four mechanical defect kinds above are detectable at generation time and
   could downgrade a card to needs_review automatically.
6. **Reconsider the model.** At 6% verified and 20% mechanically defective, the
   14B implementer is producing more review work than it saves. Worth an A/B
   against `qwen3-coder:30b` on 20 cards before committing another long run.

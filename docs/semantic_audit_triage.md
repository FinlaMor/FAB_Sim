# Semantic audit triage — 2026-07-20

Hand-verification of all 23 cards flagged by `scripts/dsl_semantic_audit.py`
across the full 107-card corpus. Each verdict was reached by reading the
printed text, the card JSON, **and** the implementation of every effect it
names — the auditor sees effect *names* only, which is the source of several
false positives below.

**17 real, 6 false — 74% precision.**

Several real defects carry bugs the auditor did *not* report; those are marked
"missed by auditor" and were found by reading the JSON during triage.

## Fix status (updated 2026-07-20)

**Fixed (9 of 17) — each ships with the test the test-audit flagged as missing:**
- `leave_no_witnesses_red` — banish up-to-1 arsenal, not destroy-all
- `art_of_desire_body_red` — draw/gain gated on red banish
- `death_touch_red` — token type is a choice
- `inertia_trap_red` — new condition `ATTACK_POWER_GT_BASE` gates the token
- `spreading_plague_yellow` — `CREATE_TOKEN` count `DEFENDING_CARD_COUNT`
- `orb_weaver_spinneret_red` — equip token + stealth-filtered pump
- `cut_from_the_same_cloth_red` — `REVEAL_HAND_MARK_IF_TYPE` + dagger filter
- `overcrowded_blue` — arena-wide aura count, power on attack / defense on defend
- `chain_of_brutality_red` — `SELF_ATTACK_POWER_GTE` gate, go again, set-base-6
- `pain_in_the_backside_red` — `DAGGER_DEALS_DAMAGE` (dagger deals it, registers the hit)
- `stains_of_the_redback_red` / `_blue` — new conditional-play-cost subsystem (`cost_modifiers`)
- `10000_year_reunion_red` — alternative cost via existing `REMOVE_COUNTERS_FROM_AURAS` + `alternative_cost`
- `infiltrate_red` — `BANISH_OPP_TOP_GRANT_PLAY` + cross-player playable-from-banish in `play.py`
- `tarantula_toxin_red` — MODAL `choose`/`choose_max` range + per-mode conditions

**Reclassified as FALSE POSITIVE (verified correct against the real
implementation, regression-locked):**
- `arakni_trap_door` — `SEARCH_BANISH_FACE_DOWN` already banishes the trap and
  marks it playable-from-banish.
- `under_the_trap_door_blue` — already grants play-from-banish AND sets the
  graveyard→banish rider (`gy_to_banish_<id>`, honoured by `_to_graveyard`). My
  earlier triage wrongly called this open, misled by a stale code comment that
  said the rider "is not modeled"; the comment was wrong and is now fixed.

Both were flagged through effect-name blindness (same class as `nimby_blue`):
the auditor reads effect names, not their Python. Revised precision: 15 real,
8 false (~65%).

**All 15 real findings are now fixed** (the other 8 of the original 23 were
verified false positives — effect-name blindness). Every fix ships with the
regression test the test-audit flagged as missing.

---

## Real — wrong quantity or wrong mechanism

These produce wrong game outcomes today.

| Card | Defect |
|---|---|
| `chain_of_brutality_red` | Three bugs. Text: *"If this has 6 or more {p}, it gets go again and 'when this hits a hero, the next attack action card you play this turn has 6 **base** {p}.'"* JSON applies `MODIFY_NEXT_ATTACK +4 add` unconditionally. The 6-power condition is absent (fires always), `go again` is not granted, and **+4 additive is not the same as setting base power to 6** — the Big Bully error class again. |
| `spreading_plague_yellow` | X is hardcoded to 1. Text: *"Create **X** Bloodrot Pox tokens … where X is the number of defending cards this chain link."* |
| `inertia_trap_red` | Condition absent. Text fires only when defending *"an attack with {p} greater than its base"*; JSON fires on every defend. |
| `art_of_desire_body_red` | `DRAW 1` is unconditional; text gates it on *"whenever this banishes a **red** card"*. The *"gain 1{h}"* half is missing entirely. |
| `death_touch_red` | Token type hardcoded to `frailty`; text says *"a Frailty, Inertia, **or** Bloodrot Pox token"* — a choice. Same class as Mask of Deceit (choose vs. fixed). |
| `leave_no_witnesses_red` | **Missed by auditor.** Text: *"banish … **up to 1** card in their arsenal"*. JSON uses `DESTROY_ARSENAL`, which `destroy()`s **every** card in the arsenal. Three deviations at once: destroy≠banish, all≠up-to-1, mandatory≠optional. |
| `overcrowded_blue` | Missing `+1{d}` (only `MODIFY_ATTACK_POWER_PER_UNIQUE_AURA`). **Missed by auditor:** text reads *"when this attacks **or defends**"* but `ON_PLAY` never fires on defend, so half the clause is unreachable. |

## Real — type-restricted pump applied to any attack

A recurring class: the pump exists but is not restricted to the card type the
text names. `MODIFY_NEXT_ATTACK` already supports a `filter` param, so these
are small fixes.

| Card | Defect |
|---|---|
| `cut_from_the_same_cloth_red` | **Missed by auditor.** *"next **dagger** attack gets +4{p}"* — no filter, buffs any attack. Also missing the entire *"target opposing hero reveals their hand; if an attack reaction is revealed, mark them"* clause. |
| `orb_weaver_spinneret_red` | *"next attack **with stealth**"* — unrestricted. Also missing *"Equip a Graphene Chelicera token"* entirely. |
| `tarantula_toxin_red` | Not modal at all. *"Choose 1 or both"* — only the `+3{p}` mode exists; the *"target card defending an attack with stealth gets -3{d}"* mode is absent, and the `+3` is not dagger-restricted. |

## Real — missing clause

| Card | Defect |
|---|---|
| `stains_of_the_redback_red` | *"If the defending hero is marked, this costs {r} less to play"* — no cost reduction. This is a **cost**, so it must affect play legality, not be an effect. |
| `stains_of_the_redback_blue` | Same. |
| `under_the_trap_door_blue` | Graveyard→banish rider unmodelled; `effect_types.py` says so in a comment. |
| `infiltrate_red` | *"You may play it until the end of your next turn"* — the play-grant on the banished card is absent. |
| `arakni_trap_door` | *"If it's a trap, you may play it until the start of your next turn"* — absent. |
| `pain_in_the_backside_red` | Damage is dealt but not *by the dagger*, and *"the dagger has hit"* is not registered — so dagger-hit triggers never fire. |
| `10000_year_reunion_red` | *"You may remove three +1{p} counters … **rather than pay** its {r} cost"* is an alternative cost, entirely absent. Per project convention a cost must gate play legality, never be modelled as an ON_PLAY effect. |

---

## False positives — and why

| Card | Why it is correct |
|---|---|
| `nimby_blue` | `SEARCH_DECK` already puts the card to hand and shuffles (`effect_types.py:274`). The auditor judged from the effect *name*. |
| `pummel_red` | *"Choose 1"* is modelled as target legality: an `OR` filter accepts either a Club/Hammer weapon attack or a cost-2+ attack action, and `INJECT_TRIGGER` applies the discard rider only on the attack-action branch. Outcome-equivalent and arguably cleaner than a modal. |
| `disable_red` / `disable_blue` / `disable_yellow` | Text says *"put a card from their **arsenal** on the **bottom** of their deck"*; JSON is `PUT_ARSENAL_BOTTOM`. Correct. Superficially resembles the Boulder Drop top/bottom bug and is not. |
| `victor_goldmane_high_and_mighty` | The fail-clash retry is a Python `REPLACEMENT` in `replacement_abilities.py`, structurally invisible to a JSON-only auditor. |

## Structural limits this triage exposed

Two false-positive classes cannot be fixed by prompting, because the auditor
never sees the relevant code:

1. **Effect implementations.** It reads `SEARCH_DECK` and cannot know the
   function already shuffles. Any correctly-named effect whose behaviour
   exceeds its name will read as incomplete.
2. **Python-side replacements.** `REPLACEMENT` abilities carry their logic in
   `replacement_abilities.py`; the JSON is only a declaration.

Both argue for keeping the tool advisory. It never edits card JSON.

## Suggested fix order

1. `chain_of_brutality_red` — three bugs including a base-power mechanism error.
2. `leave_no_witnesses_red` — destroys the whole arsenal where the card banishes up to one.
3. `overcrowded_blue`, `inertia_trap_red`, `art_of_desire_body_red`, `spreading_plague_yellow` — missing conditions and halves of effects.
4. The three type-restricted pumps — `MODIFY_NEXT_ATTACK` already takes a `filter`.
5. The cost-based ones (`stains_of_the_redback_*`, `10000_year_reunion_red`) — need cost/legality work, not effects.

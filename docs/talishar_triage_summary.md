# Talishar divergence triage — candidate corpus (789 cards)

Static cross-check of every `candidate` card against the local Talishar backend
as a **reference oracle** (second opinion, not ground truth — Talishar's own
README says it may have bugs). Tooling: `scripts/talishar_reference.py --report`.

## Result

| bucket | count | meaning / action |
|---|---:|---|
| `looks-aligned` | 598 | structural cross-check found no divergence |
| `no-talishar-logic` | 180 | vanilla card, or a set newer than this Talishar build — nothing to cross-check |
| `keyword-only` | 8 | all card text is engine-handled keywords (Stealth/Dominate/Heave…); empty `abilities` is **correct** |
| `persistent-combat-effect/verify-scope` | **3** | **genuine divergence** — see below |

The first pass raised 16 flags; 13 were **heuristic false positives**, now fixed
in `_flags`:
- **keyword-only cards** (e.g. `isolate_red` = Stealth+Dominate, `rubble_raiser_red`
  = Heave 2) were flagged `empty-abilities`. But those keywords are applied
  generically by the engine from card **metadata** (`triggers.py` parses `Heave N`,
  `Dominate`, `Stealth`), so empty `abilities` is right. Now suppressed.
- **ON_HIT nested in `INJECT_TRIGGER`** (the canonical "this attack gains: *if it
  hits* …" pattern) was invisible to a check that only looked at top-level
  `ability.trigger`. ~10 false `hit-effect` flags. Now checks the whole JSON.

## The 3 genuine divergences — one root cause

All three are **persistent turn/next-turn-scoped combat effects** that our JSON
models as a **one-shot self-trigger** on the card itself:

| card | text | our JSON | why it's wrong |
|---|---|---|---|
| `buzz_bolt_blue` | "…whenever an attack hits a hero **this turn**, it deals 1 damage" | `TRIGGERED ON_HIT` on buzz_bolt | fires only when buzz_bolt itself hits, not for the turn's other attacks |
| `chilling_icevein_yellow` | "…whenever an attack deals damage to a hero **this turn**…" | `TRIGGERED ON_DEAL_DAMAGE` on the card | same: self-scoped, not turn-scoped |
| `this_rounds_on_me_blue` | "**until the start of your next turn**, attacks that target you have -1{p}" | one-shot `PLAY` power mod (also wrong type: per-aura, not flat) | doesn't persist into the opponent's turn |

(`poisoned_blade_blue`, found in the earlier candidate-verification pass, is the
same class.)

## Root cause: no turn-scoped injected-trigger construct

`INJECT_TRIGGER` (`effect_types.py:381`) appends a **one-shot** `TriggerDef` to
`state.combat.injected_triggers`, which the engine fires **and consumes** per
combat (`engine.py:1165-1176`). There is no mechanism for an injected trigger (or
attack-power modifier) that **persists across every attack for the rest of the
turn / until the start of next turn**. That is precisely what these cards need.

`SET_FLAG` with `scope: NEXT/CURRENT` registers a turn flag, but nothing reads it
on each attack to re-apply a trigger/modifier.

### Fix — LANDED (2026-08-03)

Turn-scoped attack hooks were built: `INJECT_TRIGGER` with `"scope": "TURN" |
"NEXT_TURN"` (+ `"player"`) and a new `MODIFY_ATTACKS_THIS_TURN` power modifier,
stored on `Player.turn_attack_hooks` / `next_turn_attack_hooks` and re-applied to
every attack by `engine._apply_turn_attack_effects`. See the commit and
`DSL_REFERENCE.md`. Building it also fixed two latent DSL bugs (a nested `NOT`
that was always-False; nested-`trigger` `INJECT_TRIGGER` inner effects that were
silently dropped — ~60 cards).

- **`buzz_bolt_blue`** → `done` (fused: 1 damage on every hero-hit this turn).
- **`this_rounds_on_me_blue`** → `done` (each hero draws; -1 to the opponent's
  hero attacks until your next turn).

- **`chilling_icevein_yellow`** → `done` (2026-08-03). Needed a base
  `ON_DEAL_DAMAGE` event dispatch, which existed for **no** card: added a
  `_dsl_deal_damage_listener` on the combat `'damage_dealt'` event (fires
  card-level ON_DEAL_DAMAGE + consumes injected ON_DEAL_DAMAGE triggers), plus a
  generic `PAY_OR_ELSE` effect ("pay N or else …"). This also revives the other
  4 previously-dead ON_DEAL_DAMAGE cards.

- **`poisoned_blade_blue`** → `done` (2026-08-04). Added an `INJECT_TRIGGER`
  `"scope": "CHAIN"` (Player.chain_attack_hooks, re-applied per attack link,
  cleared at chain close in `engine._close_step`) for "… this combat chain …".
  Also fixed its condition (`ATTACK_SUBTYPE_IN ["dagger"]` — Dagger is a subtype,
  the old `ATTACK_TYPE_IN` never matched).

**All 4 genuine divergences from the triage are now resolved.** The candidate
corpus cross-check is fully closed out.

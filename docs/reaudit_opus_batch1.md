# Opus re-audit of "14b-clean" candidate cards — batch 1 (2026-08-11)

Pool: `docs/semantic_audit_all_candidates.jsonl` rows[230:] where `not suspect`,
minus slugs already in `docs/semantic_audit_reaudit.jsonl`. **245 remaining**
before this batch; 14 read here.

Confirms the handoff's claim that the 14b "clean" verdict is unreliable:
**6 of 14 (43%) have at least one wrong clause**, and 2 of those are severe.

## Findings

| Card | Severity | Defect |
|---|---|---|
| `carrion_crown` + **26 more** | **high** | Fabricated INTIMIDATE ability (corpus-wide; FIXED) |
| `prismatic_lens_yellow` | **high** | "unless" modelled as AND |
| `lady_barthimont` | high | Wrong destination zone + wrong condition |
| `driving_blade_red` | med | "next attack" applies to every attack |
| `nerve_scalpel` | med | "next time" not consumed; likely wrong player |
| `path_of_same_ends_red` | low | Missing "if damage is dealt" gate |

### carrion_crown — fabricated ability → a 27-card systemic finding, FIXED
Text is only `Action - Discard an ally, destroy this: Draw a card. Go again` +
`Blade Break`. The JSON added a **`STATIC_TRIGGERED` ON_DEFEND → `INTIMIDATE`
ability the card does not have.** `teklo_base_head`'s `_comment` records the
same fabrication being found and removed there earlier, which suggested a
repeating generator failure mode rather than a one-off.

**It was.** A corpus-wide grep for cards emitting `INTIMIDATE` whose text and
keywords contain no "intimidate" found **27 cards**. Their only common feature
is **Blade Break** — the generator hallucinated an intimidate ability from Blade
Break equipment. 26 had an ability whose effects were *only* `INTIMIDATE`; those
abilities are removed, each card carrying a `_comment` recording why. The 27th
(`gloves_of_azure_waves`) had `INTIMIDATE` standing in for the card's actual
**blade break** clause and is fixed separately (below).

This is the single largest correctness win of the re-audit so far, and it is a
**whole defect class the 14b auditor rated "clean"** — strong evidence for the
handoff's argument that 38% flagged is an underestimate.

Three cards drop to `abilities: []`. `teklo_base_chest` is genuinely vanilla.
`embrace_adversity` and `overcome_adversity` have real text ("This may only
defend an attack if the attack's controller has destroyed a Might/Agility token
this turn") that the INTIMIDATE ability never modelled anyway; they now carry an
`UNIMPLEMENTED:` comment, since **defend-legality restrictions have no DSL
primitive**.

Emptying them tripped `test_card_with_functional_text_implements_something`,
which correctly asserts that a card with non-keyword text implements *something*
— the guard doing its job. Rather than paper over it, both slugs are listed in a
new explicit `KNOWN_UNIMPLEMENTED` set in `tests/test_card_json_hygiene.py` and
`xfail`, so the gap stays visible in every test run instead of being disguised
by an ability that grants a bonus keyword for text that is purely a downside.
**Removing an entry from that set is the definition of done for the primitive it
names.** The primitive needed: a per-card defend-legality restriction, enforced
in the live `play.available_actions` path (note `actions.get_defendable_cards`
is the audit-only path — the sole existing restriction,
`combat.head_equipment_only`, is attacker-side and set by Headbutt).

Secondary on carrion_crown: "Discard an ally" is a *chosen* ally; the JSON uses
`DISCARD_RANDOM`. Not fixed.

### gloves_of_azure_waves — INTIMIDATE standing in for blade break
"High Tide - If there are 2 or more blue cards in your pitch zone, this gets
+3{d} and **blade break**." The blade-break clause was emitted as `INTIMIDATE`,
and gated on `REF_PITCH_IS {ref: self, color: blue, amount: 2}` — a condition
that tests a *referenced card's pitch value*, not a count of blue cards in the
pitch zone. Condition corrected to `CARD_IN_ZONE {zone: pitch, color: blue,
count_gte: 2}`; the fabricated INTIMIDATE removed. The conditional blade-break
grant remains **UNIMPLEMENTED** — there is no `BLADE_BREAK` effect type.

### prismatic_lens_yellow — "unless" modelled as AND
Text: "At the start of your turn, **destroy this unless you remove a steam
counter from it**." The JSON runs `DESTROY_PERMANENT` **and** `REMOVE_COUNTER`
unconditionally — it destroys the card every turn *and* removes the counter.
This is the mutually-exclusive-branch class (rule 9 of the authoring prompt),
which the prompt already warns about, so the generator is still violating it.

Correct shape: choose to remove a steam counter, else destroy; and destroy
outright when there is no counter to remove.

Secondary: the activated ability's "Mechanologist item **of the same color**"
is hardcoded `"color": "yellow"`, and the nested filter uses singular
`subtype`/`class` keys that `CARD_IN_ZONE` does not read (it reads
`filter_types` / `card_class`), so the search filter is inert.

### lady_barthimont — wrong destination zone
Text: "search your deck for a specialization card, **put it face up into
arsenal**". JSON uses `PUT_REF_BOTTOM_DECK` — the opposite of the intended
effect. Also `DISCARDED_CARD_POWER_GTE` is used to test a **banished** card,
and the "whenever you play an attack action card" gate is authored as
`CARD_IN_ZONE {zone: HAND, card_type: ATTACK_ACTION}`, which asks whether an
attack action is *in hand*, not whether the played card *is* one.

### driving_blade_red — "next" not consumed
"Your **next** weapon attack this turn gains +3{p} and go again" is modelled as
a turn-long `SET_FLAG` + `STATIC` gate, so it buffs **every** weapon attack for
the rest of the turn. The +3 should use `MODIFY_NEXT_ATTACK` (verified one-shot:
`engine.py:1115-1141` consumes the queued entry on the first attack matching its
`filter`). Note `MODIFY_NEXT_ATTACK` carries power mods only — granting a
one-shot **go again** has no primitive yet, so this card needs one to be fully
correct.

### nerve_scalpel — same class, plus wrong player
"the **next time** they defend with 1 or more reaction cards this turn" — the
flag is never consumed, so the -1{d} applies to every defence that turn.
Additionally `SET_FLAG` defaults to `player: SELF`, but the penalty applies to
the **defending opponent's** cards.

### path_of_same_ends_red — missing consequent gate
"deal 1 arcane damage to them. **If damage is dealt this way**, this gets go
again." The `GAIN go_again` is unconditional, so it also fires when the arcane
damage is fully prevented.

## Judged correct
`isolate_yellow` (Stealth/Dominate are engine keywords → `abilities: []`),
`teklo_base_head` (vanilla + explanatory comment), `agile_windup_yellow`
(see note), `harness_lightning_yellow` (the `LIGHTNING_PLAYED_THIS_TURN` flag
does have setters: photon_rush_red, shock_frock, static_shock_yellow,
volzar_the_lightning_rod), `rubble_raiser_red` (Heave keyword),
`arakni_web_of_deceit`, `wounding_blow_blue` (no card data — empty text).

Two lower-confidence notes on the "correct" list:
- `agile_windup_yellow` — `Instant - Discard this: ...` is an *activated* line
  (rule 3/4), but it is authored as `ability_type: PLAY` with a `DISCARD_SELF`
  cost. Worth a second opinion on whether the engine offers this from hand.
- `arakni_web_of_deceit` — `TRANSFORM_HERO` is given `"target"`, but the effect
  reads `"mode"`; it works only because the default mode is already
  `random_agent_of_chaos`. Fragile, not currently wrong. Its `END_OF_TURN`
  transform also lacks an `IS_ACTIVE_PLAYER` gate for "your end phase".

## Cross-cutting

**The hallucinated-keyword sweep generalises.** The INTIMIDATE find took one
grep: *for each keyword-granting effect type, list cards emitting it whose
printed text and keywords never mention that keyword.* Run the same check for
DOMINATE, GO_AGAIN, OVERPOWER, STEALTH, ARCANE_BARRIER, PIERCING, etc. — this is
a param-key-sweep-grade technique (finds a whole class in one query, invisible
to per-card audit) and should be the FIRST thing the next session does. It also
belongs in the tooling as a standing check.

Running that generalised sweep now returns only **expected** hits, which is a
useful negative result: `AMP` (4) and `WARD` (16) fire because those ARE the
correct primitives for "next arcane damage +N" (CR 8.5.47) and "prevent N
damage" — text that never says the keyword. `ARCANE_BARRIER` (2:
`malign_blue`, `templar_spellbane`) is the only unexplained residue and is worth
a look. So INTIMIDATE was the one real hallucination class, not the first of
many — but the check is cheap and belongs in tooling as a regression guard.

### Duplicate slugs — silent shadowing (pre-existing, NOT fixed)
`engine/card_effects/json/` contains **two slugs implemented twice in different
set directories**, with *different* JSON in each:

- `agility` — `ako/` vs `tokens/` (different ability_type and effects)
- `tuffnut_bumbling_hulkster` — `her/` vs `sup/` (entirely different abilities)

Whichever the loader's glob reaches last wins, so the live behaviour is
arbitrary and neither file is obviously the intended one. `load_all_cards()`
does not complain. Given the loader's existing fail-loud design (unknown
effect/condition types raise), **it should raise on a duplicate slug too** —
but that change will hard-fail the game until these two are resolved, so it
needs a deliberate pass, not a drive-by fix. Resolving which implementation is
correct is per-card judgement.

Two other defect classes here are the same "one-shot vs turn-long" mistake
(`driving_blade_red`, `nerve_scalpel`). A **`CLEAR_FLAG` effect** — or a
`consume: true` option on `FLAG_SET`/`FLAG_SET`-gated statics — would give the
generator a way to express "the next time ..." for cases `MODIFY_NEXT_ATTACK`
does not cover. That is probably the single highest-leverage primitive to add
next, since "your next X this turn" is an extremely common FAB template.

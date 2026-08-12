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

### prismatic_lens_yellow — "unless" modelled as AND (FIXED)
Text: "At the start of your turn, **destroy this unless you remove a steam
counter from it**." The JSON ran `DESTROY_PERMANENT` **and** `REMOVE_COUNTER`
unconditionally — destroying the card every turn *and* spending the counter.
This is the mutually-exclusive-branch class (rule 9 of the authoring prompt),
which the prompt already warned about, so the generator was still violating it.

Fixed by extending `PAY_OR_ELSE` to take a **counter cost** (`counter_type` +
`amount`) instead of resources, since "destroy this unless you remove a X
counter" is the recurring Crank/steam pattern. Declining, or having no counter
to spend, runs `on_failure`.

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

### driving_blade_red — "next" not consumed (FIXED)
"Your **next** weapon attack this turn gains +3{p} and go again" was modelled as
a turn-long `SET_FLAG` + `STATIC` gate, so it buffed **every** weapon attack for
the rest of the turn.

Fixed, together with the missing primitive it needed. `MODIFY_NEXT_ATTACK` was
already correctly one-shot (`engine.py` consumes the queued entry on the first
attack matching its `filter`) but carries power mods only, so **`GRANT_NEXT_ATTACK`**
now queues a one-shot keyword grant on the same list. Driving Blade uses both,
weapon-filtered; the Agility token uses it for its go-again clause.

Deliberately NOT built as a self-consuming flag condition: `FLAG_SET` is
re-evaluated repeatedly during attack-power recalculation, so a condition with
side effects would fire an unpredictable number of times. Reusing the existing
consume-at-announcement queue keeps the one-shot semantics exact.

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

### Crowd cheer — four private flags, none connected (FIXED)
Chasing Tuffnut turned up a defect class of its own: "the crowd cheers you" had
**four** hand-rolled spellings across 8 cards and no shared state at all.

- `CROWD_CHEERS` (comeback_kid_red, pleiades, tuffnut, tuffnut_bumbling_hulkster)
- `CROWD_CHEERS_ACTIVE` (comeback_kid_blue)
- `THE_CROWD_CHEERS` (shining_courage_red)
- `CHEERED_THIS_TURN` (disarm_yellow, old_favorite_yellow)

Consequences: **Comeback Kid red and blue — the same card in two colours — used
different flags**, so neither could see the other's cheer. `disarm_yellow` and
`old_favorite_yellow` tested `CHEERED_THIS_TURN`, which **no card ever set**, so
those abilities could never fire. `pleiades` read a flag nothing set and hung
its Confidence token off `ON_CLASH_WIN_REVEALED`, unrelated to its actual
"whenever the crowd cheers you" text.

Meanwhile `effect_keywords.cheer()` (CR 8.5.57) was **dead code called by
nothing but its own unit test**, and the "the crowd cheers" keyword-text handler
in triggers.py appended a flag no code read.

Now one path: `CROWD_CHEER` effect → `ability_keywords.effect_crowd_cheers` →
the CR `cheer()`; an `IS_CHEERED` condition over shared state; and an `ON_CHEER`
trigger mirroring `ON_BOO` for "whenever the crowd cheers you" (every card with
that text is a hero, which is what the boo-style hero dispatch covers).
`IS_CHEERED` also accepts the legacy spellings so no cheer is lost. `boo` had
the identical split and got the same routing.

### Duplicate slugs — silent shadowing (FIXED)
`engine/card_effects/json/` contains **two slugs implemented twice in different
set directories**, with *different* JSON in each:

- `agility` — `ako/` vs `tokens/` (different ability_type and effects)
- `tuffnut_bumbling_hulkster` — `her/` vs `sup/` (entirely different abilities)

Whichever the loader's glob reached last won, so the live behaviour was
arbitrary and neither file was obviously the intended one.

Resolved by the owner: `agility` keeps `tokens/` (both were wrong; the deleted
`ako/` one at least *attempted* the go-again clause, but as a turn-long flag —
worse than omitting it). `tuffnut_bumbling_hulkster` keeps `sup/`, which was
also the better implementation on the merits (see the analysis in its
`_comment`). Note the pair was invisible to
`test_card_is_filed_under_a_set_it_was_printed_in` because the card is printed
in **both** HER146 and SUP001, so either folder passed.

**The loader now refuses duplicates.** A slug defined by more than one file is
recorded in `loader.DUPLICATE_SLUGS`, dropped from the registry and added to
`LOAD_ERRORS`, so `require_card` rejects it at game start naming both paths —
an ambiguous definition counts as no definition. It earned its keep within
minutes, catching a `driving_blade_red` duplicate created during this very
session (and `setIdentifiers` then showed the new copy was in the wrong set
folder too). A regression test asserts the real corpus stays at zero.

Two other defect classes here were the same "one-shot vs turn-long" mistake
(`driving_blade_red`, `nerve_scalpel`). `GRANT_NEXT_ATTACK` now covers the
attack-keyword case; **`nerve_scalpel` is still open**, because its "the next
time they defend" applies to the DEFENDING player's cards and there is no
equivalent one-shot queue on the defence side (it also sets its flag on the
wrong player — `SET_FLAG` defaults to SELF).

### pitch_power_gte — a zone filter, not a ref check (FIXED)
Correcting an earlier reading in this document: `pitch_power_gte` was described
as needing a `REF_POWER_GTE` primitive. It does not. Buckwild and Rough Up both
say "if there is a card with 6 or more {p} **in your pitch zone**" — a COUNT
over a zone, so it is a `power_gte` filter on `CARD_IN_ZONE` (added, alongside
`power_lte`, and accepting the legacy `pitch_power_gte` spelling). They were
authored as `REF_PITCH_IS`, which tests a *referenced card's pitch value* and
defaults to `pitch: 1`, so both really asked "is the referenced card red?".
`buckwild_yellow` also granted go again with `GRANT_SUBTYPE` — go again is a
keyword, not a subtype.

Only the two Tuffnut cards need a genuine ref-based power check, because theirs
is "pitch the top card of your deck; if **it** has 6 or more {p}".

Remaining known-unimplemented, in rough order of leverage:
- one-shot queue for "the next time they DEFEND" (`nerve_scalpel` — which also
  sets its flag on the wrong player, `SET_FLAG` defaulting to SELF; fixing only
  the player would leave it turn-long, i.e. still wrong but less visibly)
- ref-based power check + pitch-top-of-deck — finishes both Tuffnut cards
- per-card defend-legality restriction — clears the two `KNOWN_UNIMPLEMENTED`
  xfails (`embrace_adversity`, `overcome_adversity`)
- `lady_barthimont` (specialization to bottom of deck instead of face up in
  arsenal) — per-card, no primitive needed
- `prismatic_lens_yellow`'s activated ability: "Mechanologist item **of the same
  color**" is hardcoded yellow, and its nested filter uses singular
  `subtype`/`class` keys `CARD_IN_ZONE` does not read, so that filter is inert

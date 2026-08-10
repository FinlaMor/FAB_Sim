# Semantic audit — candidate cards (2026-08-10)

Clause-by-clause audit of a sample of **candidate** DSL cards against their printed
text, done by a model in a session separate from the (qwen-generated) authors —
the check `scripts/dsl_semantic_audit.py` is built for, run here directly because
the local auditor model (qwen2.5-coder) is same-family as the authors and weak.

These cards all **load and pass their generated behavioral test**, yet several are
quantitatively or semantically wrong — exactly the "wrong-but-plausible passed the
gate" class that a stronger semantic pass exists to catch.

## Fixed in this pass (verified)

| Card | Bug | Fix |
|------|-----|-----|
| `rejuvenate_blue` | Two `PLAY` GAIN-health abilities; the second added a bogus `alternative_cost` PAY_RESOURCES 0 → double-gained on fuse and **drove the controller's resources negative** | Collapsed to a single gain-1-life ability; documented the "play as instant if fused" timing as omitted |
| `emeritus_scolding_yellow` / `_red` | "Deal 3(4); if on opponent's turn **instead** 5(6)" modeled as two `PLAY` abilities that both fired → dealt 8(10) | Gated the default branch on `IS_ACTIVE_PLAYER value:true` so the two are mutually exclusive |
| `pry_yellow` | Reveal-2 vs reveal-all branches had their `IS_ACTIVE_PLAYER` values **backwards** (revealed all on your turn, 2 on the opponent's) — masked by the ignored-`value` bug | Swapped the two `value`s to match the text |
| **DSL: `IS_ACTIVE_PLAYER`** | Condition **silently ignored its `value` field** → every card using `value:false` ("on an opponent's turn") fired on the wrong turn. Affected `emeritus_scolding_red/yellow`, `pry_yellow`, `timekeepers_whim_blue` (last was already structured correctly and just needed the honoured `value`) | `condition_types.py`: honour `value` (default True) |

## Open findings (triage, not yet fixed)

Severity: **H** wrong game outcome, **M** partial/incorrect clause, **L** cosmetic/edge.

- **H `put_em_in_their_place_red`** — "they discard their hand, then draw that many
  cards." JSON: `DISCARD opponent hand_size` then `DRAW hand_size` with **no player**
  (draws for self) and evaluated **after** the discard (so `hand_size`=0 → draws
  nothing). Needs: draw for the OPPONENT, and a captured pre-discard count
  (a `DISCARDED_COUNT` marker or a combined discard-then-draw effect). Also
  `ATTACK_CLASS_IN {"class":"Hero"}` is meaningless (Hero is not a class).
- **H `talisman_of_featherfoot_yellow`** — trigger "when an attack you control gains
  exactly +1{p} during the reaction step" is unrepresentable; JSON stuffed an
  **effect type** (`MODIFY_ATTACK`) into a `conditions` list, so the trigger is
  effectively dead. Needs a real "attack-power-increased-by-N" trigger or quarantine.
- **M `spreading_flames_red`** — "+1{p} while base {p} < number of Draconic chain
  links you control" modeled as `SELF_ATTACK_POWER_GTE amount 1` (a fixed threshold
  of 1, wrong direction and not dynamic).
- **M `vigorous_engagement_red`** — "if it's defended by an **attack action card**"
  modeled as `DEFENDS_WITH_OTHER_HAND_CARD` (different condition). Also
  `ATTACK_CLASS_IN {"class":"Warrior"}` uses singular `class`; the working form is
  `{"classes":[...]}` (see `spreading_flames_red`) — likely a no-op filter.
- **M `stellar_glide_blue`** — "When this **attacks**" modeled as `ATTACK_REACTION`
  (wrong ability type / timing); the "you **may** destroy a Lightning Flow" is done
  unconditionally.
- **M `brand_with_cinderclaw_blue`** — the whole "your next attack this combat chain
  is Draconic in addition to its types" clause is **missing**; only `Go again` is
  implemented (needs a next-attack subtype-grant, cf. INJECT_TRIGGER/CHAIN scope).
- **M `gallow_end_of_the_line_yellow`** — activation cost `{r},{t}` modeled as
  `activation_cost 1 + PITCH 2` (the `{t}` tap became a pitch-2); and the instant's
  effect only `SET_FLAG WATERY_GRAVE_ACTIVE` with (apparently) nothing consuming it
  to actually suppress opponents' hit-triggers.
- **L `sedation_shot_blue`** / **L `civic_duty`** — token created "under their /
  another hero's control" but `CREATE_TOKEN` defaults to `player:"SELF"`; should pass
  `player:"OPPONENT"` (Inertia is a debuff on the hit hero; the Vigor placement is
  "another hero").
- **L `infuse_alloy_yellow`** — item filter restricted to `zone:"arsenal"` (items
  live in the items/permanents zone); and `DESTROY_PERMANENT` isn't gated on the
  `OPT` result, so declining the "may" may still destroy the item.

## Takeaway for the pipeline

Two of the three fixes were the **same failure mode** — a "choose/instead/optional"
clause modeled as an extra always-on `PLAY` ability — and one was a latent **engine
condition bug** that no single-card test would surface. A CR-grounded semantic pass
by a *different, stronger* model than the author is the highest-leverage quality
gate; the load+behavioral-test gate cannot see any of these.

# DSL card semantic-audit & fix — handoff (2026-08-11)

Where the card-quality effort stands and exactly how to continue it. Branch:
`dsl-cards-and-three-decks`.

## The situation

- ~1,015 card JSONs implemented of ~4,953 slugs (~20%). Of the 758 "candidate"
  cards (load + auto-test pass, unreviewed), a full semantic audit flagged **38%**
  as having ≥1 wrong clause — and that is an **underestimate** (see below).
- All engine changes below are verified against the full suite (~13,136 tests,
  ~8 min) and pushed.

## The two techniques that work (ranked by ROI)

### 1. Param-key sweep — HIGHEST ROI, do this first each session

Card JSON authors a param key the compiler never reads → the clause is silently
ignored, breaking **dozens of cards at once**, invisible to any per-card audit.
One grep finds them. Run:

```
python - <<'EOF'
import json, glob, re
from pathlib import Path
from collections import Counter
ROOT=Path("engine/card_effects/json")
USE=Counter(); TYPES={}
def walk(o):
    if isinstance(o,dict):
        t=o.get("type") or o.get("ability_type")
        for k in o:
            if k in ("type","ability_type","_comment","slug","abilities"): continue
            USE[k]+=1; TYPES.setdefault(k,set()).add(t)
        for v in o.values(): walk(v)
    elif isinstance(o,list):
        [walk(v) for v in o]
for p in glob.glob(str(ROOT/"**"/"*.json"),recursive=True):
    if "needs_review" in p or "_work_queue" in p: continue
    try: walk(json.loads(Path(p).read_text(encoding="utf-8")))
    except: pass
src="".join(Path("engine/card_effects/dsl"/Path(f)).read_text(encoding="utf-8")
            for f in ["effect_types.py","condition_types.py","cost_types.py","trigger_types.py","loader.py"])
read=set(re.findall(r'\.get\(\s*["\']([a-zA-Z_]+)["\']', src))
for k in sorted(USE, key=lambda k:-USE[k]):
    if k not in read and USE[k]>=4:
        print(f"{USE[k]:4d}x {k:18s} {sorted(x for x in TYPES[k] if x)[:5]}")
EOF
```

For each suspect: open the effect/condition in `engine/card_effects/dsl/*.py`,
see what key it *reads*, and grep how cards *write* it. If mismatched, fix by
reading BOTH keys (or aliasing the values). **Fix pattern:** read both keys;
add a condition/effect-level test in `tests/test_semantic_audit_batch1.py`; run
the full suite (dozens of cards flip, so a subset is not enough).

**Already fixed (8, pass 1):** CONTROLS_TOKEN_TYPE (token/token_type/token_types
+ amount), GAIN (LIFE_POINTS/HEALTH/HEALTH_POINTS/LIFE), counter/counter_type,
CARD_IN_ZONE (zone/zones + color), COMBO_CONTAINS (substring/card/card_name,
was always-true), CREATE_TOKEN (player/controller + token/token_name/token_type),
ATTACK_TYPE_IN (types/attack_type), PAY_OR_DAMAGE (resources/resource_cost/
resource). Plus earlier IS_ACTIVE_PLAYER `value`.

**Fixed in pass 2 (9)** — tests in `tests/test_semantic_audit_batch2.py`:

- **PAY_OR_DAMAGE `resource` as a NAME** — a *regression from pass 1*. Adding
  `resource` as a cost alias meant `resource: "RESOURCE_POINTS"` (a type name,
  quantity in `amount`) reached `player.resources >= "RESOURCE_POINTS"` and
  raised **TypeError mid-trigger** on 5 cards (grains_of_bloodspill, terra,
  hamstring_shot_red, heart_of_vengeance, earthlore_empowerment_yellow). Only
  numeric values are taken as the cost now, with `amount` as the fallback.
  *Lesson: when adding an alias, check the VALUES cards put under it, not just
  the key name.*
- **PAY_OR_DAMAGE `on_success`** — the "if you do, X" payoff was never run, so
  "you may pay {r}. If you do, X" cards (flex_red/blue, be_like_water_blue,
  terra, grains_of_bloodspill) did nothing. Also skips the prompt entirely when
  there is no damage to avoid AND no payoff, so the mis-modeled cards that use
  PAY_OR_DAMAGE for cost-reduction text can't drain resources for nothing.
- **ROLL `sides`/`on_success`** — die size read only as `faces`; result-consuming
  effects were dropped.
- **`_resolve_amount` expression dicts** — `{"type":"HALF","value":{"type":
  "ROLL_RESULT"}}` fell through as a dict into the arithmetic. Now resolves
  HALF / ROLL_RESULT / VALUE recursively.
- **MAY / APPLY_CONTINUOUS singular `effect`** — a lone sub-effect authored as
  `"effect": {...}` instead of the list; MAY prompted and then did nothing.
- **HAS_KEYWORD `keywords` list** — fell back to an empty keyword and was
  **always False**, killing the whole ability. Matching now normalises, so
  "blood_debt" finds the stored "BloodDebt".
- **IN_COMBAT `combat_role`** — ignored, so cards authored as ATTACKER and
  DEFENDER branches fired BOTH in every combat.
- **CARD_IN_ZONE `card_class` + `keywords`** — ignored filters (too permissive).
  `card_class` matches class, talent OR pitch color, since cards use the one
  field for all three ("Guardian", "Earth", "Blue").
- **DURING_TURN `phase`**, **ATTACK_TARGET_IS_HERO `hero_type`**,
  **CONTROLS_TOKEN_TYPE `comparison` + `opponent`** — all ignored. The last is
  the worst kind: gold_hunter_lightsail_yellow ("if you control LESS Gold than
  an opponent") fired whenever it controlled ANY Gold — the opposite of print.

Shared helpers now in `condition_types.py`: `_norm()` (fold a name for
comparison) and `_card_traits()` (classes + talents + color). **Watch out:** a
local `def _norm` inside `compile_condition` shadowed the module-level one and
broke every card at load; keep helpers at module scope.

**Checked and benign:** `duration` (16×) — every value is an end-of-turn variant
that matches the effect default. `comparison` on FLAG_SET / CARD_IN_ZONE /
DEFENDER_USED_HAND_CARD — redundant or meaningless on a boolean condition.
`from` on TRANSFORM_HERO (names the source form, unused).

**Still open:** `pitch_power_gte` (4×, on REF_PITCH_IS — the cards mean "the
referenced card has 6+ POWER" but REF_PITCH_IS tests PITCH and defaults to
`pitch: 1`, so buckwild_yellow / rough_up_yellow / tuffnut / tuffnut_bumbling_
hulkster all test the wrong thing; needs a REF_POWER_GTE primitive);
`ward_type` (4×, WARD); `card_condition` on CARD_IN_ZONE (little_big_foot_red's
"cost 3 or more" filter is ignored → counts any 2 pitch cards); FLAG_SET `count`
(flowing_stormstrike_red's "twice per turn" limit). **Re-run the sweep after each
fix** — fixing one reveals the next tier.

**Verified NOT a problem:** unknown effect/condition types are not a silent
failure class — both compilers `raise ValueError` on an unknown type and
`load_all_cards()` surfaces it, and `LOAD_ERRORS` is currently `{}`.

### 2. Opus (or a stronger-than-author model) re-audit of "clean" cards

The full audit used qwen2.5-coder:14b for cards 230-758 (the 30b OOMs on this
31 GB box even at ctx8k/19 GB, and its flip rate was only 2% — it shares the
14b's blind spots). **An Opus re-audit of the "14b-clean" cards finds ~20-30%
that are actually wrong** — and it is how BOTH systemic GAIN and CONTROLS_TOKEN
bugs were found. Pull a batch of 14b-clean cards (original jsonl `rows[230:]`,
`not suspect`) with text + JSON and read each clause vs the text. `scripts/
reaudit_14b_tail.py` runs the 30b version (low value, OOMs). Prefer doing it
yourself. ~244 14b-clean cards remain un-re-audited.

## The candidate-card fix-lane (for genuinely per-card bugs)

Common per-card defects and the correct model (see the already-fixed exemplars):
- **"instead" / "if X, instead Y"** = mutually-exclusive branches — CONDITIONAL_
  EFFECT{when/then/else} or base + condition-gated delta. NEVER a whole-ability
  gate (zeros the default) and NEVER always-on X + always-on Y (does X+Y).
  Exemplars: emeritus_scolding_red/yellow, comet_collision_red, tide_chakra_yellow.
- **"you may … if you do …"** = one MAY block (declining runs neither). Gate the
  MAY on a CONTROLS_* condition when there must be a legal target. Exemplar:
  splintering_deadwood_blue.
- **"next arcane damage +N"** = AMP N (CR 8.5.47), NOT MODIFY_ATTACK. Exemplars:
  absorb_in_aether_red, aether_flare_blue, tempest_aurora_red, blessing_of_aether_blue.
- **ability_type INSTANT** is activated-only (fires ON_ACTIVATE); a *played*
  instant-speed action uses PLAY. Exemplar: comet_collision_red.
- Invented keys `additional_effects`/`alternative_effects` are silently ignored.
- The card-authoring prompt (auto_implement_wtr.py STRUCTURAL_RULES, rules 9-13)
  now teaches all of the above so new generations avoid them.

DSL primitives added this effort: DESTROY_PERMANENT `subtype`, CONTROLS_SUBTYPE,
CONTROLS_CHAIN_LINKS (variable `attribute` — ChainLink stores talents/classes/
subtypes), plus the key fixes. `MODIFY_NEXT_ATTACK`, `DESTROY_TOKEN`, `MAY`,
`AMP` already existed. ROLL now records a turn-scoped `DIE_ROLLED_SIX` flag
whenever a die comes up 6, which is what "if you've rolled a 6 on a die this
turn" needs (it reads back across every roll in the turn, not just this one).

Per-card fixes from pass 2 (exemplars for the same defect classes):
- `mark_of_the_huntsman` — "you may destroy this AND mark them" was authored as
  two independent MAY prompts; it is ONE choice doing both.
- `reckless_charge_blue` — action points authored as a combat `keyword` instead
  of the `asset: ACTION_POINTS` (GAIN's `keyword` branch grants a combat
  keyword, silently); the DIE_ROLLED_SIX flag was set unconditionally; the draw
  was deferred to END_OF_TURN when the text resolves it immediately.
- `aether_icevein_blue` — "they discard a card unless they pay {r}{r}" is
  PAY_OR_ELSE against the OPPONENT, not PAY_OR_DAMAGE against us; the card had
  invented `pay_cost`/`damage_effect` keys that were silently ignored.

## Verification workflow (do NOT skip)

1. `python -c "from engine.card_effects.dsl.loader import load_all_cards,LOAD_ERRORS; load_all_cards(); print(LOAD_ERRORS)"` — must be `{}`.
2. Add tests to `tests/test_semantic_audit_batch2.py` (behavioral for cards,
   condition/effect-level for primitive/key fixes). Assert observable GameState,
   never internal flags. Note `GAIN` needs `asset: "LIFE_POINTS"` — there is no
   `GAIN_LIFE` effect type — and `CombatState` requires `attack_card`.
3. Full suite for any engine (effect/condition) change: `python -m pytest -q -p no:cacheprovider` (~8 min). A subset is NOT enough — key fixes flip dozens of cards.
4. Commit + push. Re-run the candidate audit (`python scripts/run_candidate_audit.py --seeds 1 --max-turns 60`) if you touched combat/zones.

## Recommended next-session order

The sweep is now largely mined out — pass 2 fixed every high-count mismatch and
the leftovers are documented above as benign or as small per-card items. The
remaining yield is in the re-audit, so:

1. **Opus re-audit of the 14b-clean cards (§2)** — **231 remain** (14 done in
   `docs/reaudit_opus_batch1.md`; read that first). This is the highest-value
   lane: batch 1 flagged 6 of 14 and turned up a **27-card fabricated-INTIMIDATE
   class** the 14b auditor rated clean. Batch 1 also names the next move —
   re-run the hallucinated-keyword grep (it generalises) and consider a
   "consume this flag after one use" primitive, since "your next X this turn"
   is a very common template that currently mis-implements as turn-long.
2. Clear the small "still open" list above (`pitch_power_gte` → REF_POWER_GTE
   primitive, `card_condition` on CARD_IN_ZONE, `ward_type`, FLAG_SET `count`).
3. Re-run the sweep once more after those; it should come back clean.
4. Then switch to bulk authoring against the set queues. The authoring prompt
   (auto_implement_wtr.py STRUCTURAL_RULES) now carries the pass-2 lessons as
   rules 14-18 — lists-are-lists, GAIN asset-vs-keyword, who-pays picks
   PAY_OR_ELSE vs PAY_OR_DAMAGE, quantities must be numbers, and "an unread
   filter key makes the condition too permissive rather than failing loudly" —
   so new generations should not reproduce these defect classes.

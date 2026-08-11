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

**Already fixed (8):** CONTROLS_TOKEN_TYPE (token/token_type/token_types +
amount), GAIN (LIFE_POINTS/HEALTH/HEALTH_POINTS/LIFE), counter/counter_type,
CARD_IN_ZONE (zone/zones + color), COMBO_CONTAINS (substring/card/card_name,
was always-true), CREATE_TOKEN (player/controller + token/token_name/token_type),
ATTACK_TYPE_IN (types/attack_type), PAY_OR_DAMAGE (resources/resource_cost/
resource). Plus earlier IS_ACTIVE_PLAYER `value`.

**Still to check (from the last sweep):** `duration` (16×, on APPLY_CONTINUOUS/
MODIFY_ATTACK/GAIN/SET_FLAG — probably benign, effects default correctly, but
confirm); `on_success` (8×, PAY_OR_DAMAGE/ROLL — a success-branch effects list
the effect doesn't consume; STRUCTURAL, not a simple alias); `card_class` (7×,
CARD_IN_ZONE/SEARCH_DECK/PLAYED_FROM_ARSENAL class filter — likely ignored);
`comparison` (6×); `from` (5×, MOVE_REF — likely redundant); `pitch_power_gte`,
`ward_type`, `combat_role`, `hero_type` (4× each). **Re-run the sweep after each
fix** — fixing one reveals the next tier.

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
subtypes), plus the 8 key fixes. `MODIFY_NEXT_ATTACK`, `DESTROY_TOKEN`, `MAY`,
`AMP` already existed.

## Verification workflow (do NOT skip)

1. `python -c "from engine.card_effects.dsl.loader import load_all_cards,LOAD_ERRORS; load_all_cards(); print(LOAD_ERRORS)"` — must be `{}`.
2. Add tests to `tests/test_semantic_audit_batch1.py` (behavioral for cards,
   condition/effect-level for primitive/key fixes). Assert observable GameState,
   never internal flags.
3. Full suite for any engine (effect/condition) change: `python -m pytest -q -p no:cacheprovider` (~8 min). A subset is NOT enough — key fixes flip dozens of cards.
4. Commit + push. Re-run the candidate audit (`python scripts/run_candidate_audit.py --seeds 1 --max-turns 60`) if you touched combat/zones.

## Recommended next-session order

1. Run the param-key sweep (§1). Fix `card_class`, `token`-adjacent, and any new
   high-count mismatches. Cheapest, highest yield.
2. Re-run the sweep; repeat until only benign metadata keys remain.
3. Opus re-audit the next ~16 14b-clean cards (§2); fix per-card bugs.
4. Consider: re-audit the whole 14b tail with Opus (or wire a stronger model)
   since 38% flagged is an underestimate.

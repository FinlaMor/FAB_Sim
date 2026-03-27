# DB-Driven Approach: Implementation Accelerator Assessment

**Subtask**: 2-2 — Evaluate DB-driven approach as implementation accelerator
**Date**: 2026-03-24

## 1. Existing Generic Effect Executors in loader.py

The `_make_effect()` function in `engine/card_effects/db/loader.py` implements **15 generic effect executors** plus a `custom` passthrough:

| # | effect_type | Parameters | Status |
|---|-------------|-----------|--------|
| 1 | `gain_life` | `{amount: N}` | ✅ Implemented |
| 2 | `lose_life` | `{amount: N}` | ✅ Implemented |
| 3 | `deal_damage` | `{amount: N, target: 'opponent'\|'self'}` | ✅ Implemented |
| 4 | `deal_arcane` | `{amount: N, target: 'opponent'\|'self'}` | ✅ Implemented |
| 5 | `draw` | `{amount: N}` | ✅ Implemented |
| 6 | `create_token` | `{token: slug, count: N}` | ✅ Implemented |
| 7 | `grant_go_again` | `{}` | ✅ Implemented |
| 8 | `intimidate` | `{}` | ✅ Implemented |
| 9 | `dominate` | `{}` | ✅ Implemented |
| 10 | `mark` | `{}` | ✅ Implemented |
| 11 | `amp` | `{amount: N}` | ✅ Implemented |
| 12 | `gain_resources` | `{amount: N}` | ✅ Implemented |
| 13 | `set_flag` | `{flag: str, scope: 'current'\|'next'}` | ✅ Implemented |
| 14 | `put_counter` | `{counter_type: str}` | ✅ Implemented |
| 15 | `power_bonus` | `{amount: N}` | ✅ Implemented |
| 16 | `custom` | — delegates to Python fn | ✅ Passthrough |

## 2. Existing Generic Condition Checkers in loader.py

The `_make_condition()` function implements **9 generic condition checkers** plus `custom` passthrough:

| # | condition_type | Parameters | Status |
|---|---------------|-----------|--------|
| 1 | `none` | — (always true) | ✅ Implemented |
| 2 | `is_attacking` | — | ✅ Implemented |
| 3 | `is_defending` | — | ✅ Implemented |
| 4 | `player_is_active` | — | ✅ Implemented |
| 5 | `health_more_than_opp` | — | ✅ Implemented |
| 6 | `coplayer_power_gte` | `{min_power: N}` | ✅ Implemented |
| 7 | `has_counter_lt` | `{type: str, max: N}` | ✅ Implemented |
| 8 | `has_counter_gte` | `{counter_type: str, min: N}` | ✅ Implemented |
| 9 | `flag_set` | `{flag: str}` | ✅ Implemented |
| 10 | `card_in_zone` | `{zone: str}` | ✅ Implemented |
| 11 | `custom` | — delegates to Python fn | ✅ Passthrough |

## 3. Schema-Defined but NOT Implemented in loader.py

The schema.sql defines additional effect types and condition types that have **no corresponding executor** in loader.py:

### Missing Effect Executors (8 defined in schema, not in loader)

| effect_type | Schema Definition | Effort to Add |
|-------------|------------------|---------------|
| `deal_physical` | `{amount: N, target}` — explicit physical damage | ~15 min (mirror deal_damage) |
| `discard` | `{amount: N, target: 'self'\|'opponent'}` | ~30 min (needs player choice logic) |
| `grant_keyword` | `{keyword: str}` — non-go-again keywords | ~20 min |
| `remove_counter` | `{counter_type: str, amount: N}` | ~15 min (mirror put_counter) |
| `banish_top_deck` | `{target, infiltrate: bool}` | ~30 min |
| `reload` | `{}` — move to arsenal if empty | ~20 min |
| `opt` | `{amount: N}` — look at top N, reorder | ~45 min (needs UI/agent interaction) |
| `charge` | `{}` — move card to hero's soul | ~15 min |

**Total to implement missing executors**: ~3 hours

### Missing Condition Checkers (13+ defined in schema, not in loader)

| condition_type | Effort |
|---------------|--------|
| `player_is_non_active` | ~5 min |
| `controller_has_card_type` | ~15 min |
| `opponent_has_supertype` | ~15 min |
| `attacking_hero_is` / `defending_hero_is` | ~10 min each |
| `reprise_check` | ~20 min |
| `crush_check` | ~15 min |
| `combo_check` | ~20 min |
| `surge_check` | ~15 min |
| `rupture_check` | ~15 min |

**Total to implement missing conditions**: ~3 hours

## 4. Current Seed Data Usage — The Gap

A critical finding: **all 148 trigger rows in seed_data.sql use `effect_type = 'custom'`**. Zero rows use the generic declarative executors. The 118 unique slugs in seed_data are essentially Python function references stored in a database wrapper — not truly declarative.

This means the DB infrastructure exists but is **not being leveraged for its primary value proposition** (data-driven effects without custom Python).

## 5. Coverage Estimate: What Percentage Could Be Declarative?

Cross-referencing the complexity tier analysis (subtask-2-1) with the available generic executors:

### Simple Tier (861 cards, 535 unique bases)

Many simple cards map directly to existing executors:
- "Deal N arcane damage" → `deal_arcane` ✅
- "Draw a card" → `draw` ✅
- "+N power when attacking" → `power_bonus` + `is_attacking` condition ✅
- "Gain N life" → `gain_life` ✅
- "Intimidate" / "Dominate" → `intimidate` / `dominate` ✅
- "Go again" (as trigger text) → `grant_go_again` ✅

**Estimated declarative coverage of Simple tier**: ~60-70% (360-375 unique bases) could be pure DB rows with existing + missing executors. The remaining 30-40% have minor wrinkles (conditional destruction, self-targeting, pitch-color checks) that need either a new condition type or custom Python.

### Medium Tier (1,493 cards, 888 unique bases)

Medium cards often combine 2-3 primitives:
- "When this attacks, create a token" → `attacking` event + `create_token` ✅
- "When this hits, draw a card" → `hit` event + `draw` ✅
- "Put a counter, then if threshold, do X" → needs compound effects (not supported)

**Estimated declarative coverage of Medium tier**: ~25-35% (220-310 unique bases) could be DB rows. The rest need compound effects (multiple effects per trigger row), zone manipulation not covered by executors, or conditional branching.

### Complex Tier (781 cards, 574 unique bases)

Complex cards almost always need custom Python:
- Player choices, replacement effects, scaling effects, tutoring, transform/transcend
- These are fundamentally imperative, not declarative

**Estimated declarative coverage of Complex tier**: ~5% (≤30 unique bases)

### Summary

| Tier | Unique Bases | Declarative DB | Custom Python | % Declarative |
|------|-------------|---------------|---------------|---------------|
| Simple | 535 | ~365 | ~170 | ~68% |
| Medium | 888 | ~265 | ~623 | ~30% |
| Complex | 574 | ~25 | ~549 | ~4% |
| **Total** | **1,997** | **~655** | **~1,342** | **~33%** |

## 6. Speedup Factor Estimate

### Time per card: DB row vs. Hand-coded Python

| Approach | Simple | Medium | Complex |
|----------|--------|--------|---------|
| Hand-coded Python | 15 min | 30 min | 60+ min |
| DB row (declarative) | 2-3 min | 5-8 min | N/A (still custom) |
| **Speedup** | **5-7x** | **4-6x** | **1x (no gain)** |

Writing a DB row is faster because:
- No Python boilerplate (function def, imports, closure variables)
- No need to wire into CARD_TRIGGERS dict
- Single INSERT statement vs. 15-30 lines of Python
- Batch-generatable from card text patterns via script

### Projected Total Effort With DB Approach

| Component | Hours |
|-----------|-------|
| Implement 8 missing effect executors | 3 |
| Implement 13 missing condition checkers | 3 |
| Write DB rows for ~655 declarative cards (avg 4 min) | 44 |
| Hand-code ~1,342 custom Python cards (original rates) | 815 |
| **Total with DB approach** | **~865 hours** |
| **Total without DB (all hand-coded, from subtask-2-1)** | **~1,152 hours** |
| **Savings** | **~287 hours (25%)** |

### Effective Speedup: ~1.33x overall

The DB approach saves ~25% of total effort. The speedup is moderate because:
1. Only 33% of cards qualify for declarative handling
2. Complex cards (which dominate effort) still need custom Python
3. The 6-hour investment in missing executors/conditions is trivial

## 7. Additional DB Benefits Beyond Raw Speed

1. **Batch generation**: A script could parse `functional_text_plain` from slug_index.json and auto-generate INSERT statements for pattern-matching simple cards (e.g., all "Deal N arcane damage" cards). This could produce ~200+ rows automatically.

2. **Non-developer contribution**: DB rows are more accessible to non-Python contributors who understand the game rules.

3. **Consistency**: Generic executors are tested once; DB rows can't introduce Python bugs.

4. **Bulk auditing**: SQL queries can verify coverage, find duplicates, spot missing cards.

5. **Runtime introspection**: Can query "what does this card do?" from the DB without parsing Python AST.

## 8. Recommendation

**Use the DB-driven approach as the primary path for Simple-tier cards, and as a supplement for Medium-tier cards.** Specifically:

1. **Immediate** (~6 hours): Implement the 8 missing effect executors and 13 missing condition checkers in loader.py
2. **Week 1** (~20 hours): Write a `generate_simple_triggers.py` script that parses slug_index.json functional_text and auto-generates DB INSERT statements for pattern-matching simple cards (~200-300 cards automatically)
3. **Ongoing**: Use DB rows for any new card whose effect matches the declarative vocabulary; use Python for everything else
4. **Migrate existing seed_data**: Convert the 148 existing `custom` rows to use generic executors where applicable (estimated ~40 rows convertible)

The DB approach is a **meaningful but not transformative** accelerator. It saves ~25% of total effort and provides important secondary benefits (batch generation, consistency, auditability). It should be used alongside hand-coded Python, not as a replacement.

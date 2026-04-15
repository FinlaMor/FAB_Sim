# Work Tracks

See also: [[Architecture Hub]] | [[Engine Overview]] | [[Card Set Status]]

Two parallel tracks. Work both simultaneously — engine gaps block card implementations, card implementations reveal engine gaps.

---

## Track 1 — Engine Rules Completeness
Goal: any legal FAB play is correctly modelled, regardless of which cards are in play.

### CR 8.5 Effect Keywords (`effect_keywords.py`)
- [ ] Audit all primitives against current CR 8.5 — confirm each matches the rules text
- [ ] need to confirm that event.x variables are used after replacement effects
- [ ] shuffle needs to update player pitch histories. they wouldn't know the order anymore
- [ ] `gets` / `gets_property` — verify continuous effect duration and cleanup
- [ ] `search` — confirm full zone search pattern (deck shuffle after)
- [ ] `opt` — confirm N look / choose any to top or bottom

### Continuous Effects (`continuous_effects.py` / `effects.py`)
- [ ] Clarify which `ContinuousEffect` class is authoritative (two exist)
- [ ] Verify stage 1-8 ordering is actually enforced in `ContinuousEffectManager`
- [ ] Replacement effects (CR 6.4) — are they wired into the damage pipeline?

### Other Engine Gaps
- [ ] Pitch ordering at end of turn — player chooses top-to-bottom order (CR 4.4.3)
- [ ] Landmark rules (CR 3.x) — verify add/remove/trigger coverage
- [ ] Ally attacks — `ATTACK_ALLY` exists, verify legality conditions
- [ ] Stack resolution — does the engine handle multiple stack entries correctly?

---

## Track 2 — Card Implementations
Goal: every card in target decks has correct effects registered.
See [[Card Set Status]] for per-set tracking.

### Immediate (block target decks)
- [ ] Victor CC deck — identify hero + key cards, implement
- [ ] Mario CC deck — identify hero + key cards, implement

### Process for each new card
1. Find card in slug_index (functional_text, keywords, types)
2. Check if text_trigger_parser handles the pattern automatically
3. If not: add to appropriate registry or card_triggers_extended.py
4. Write test in `tests/test_card_implementations.py`
5. Run `pytest tests/test_card_implementations.py`

### Templates to build
- [ ] Card implementation template (alt cost / additional cost / effect / counters format) — from Next Actions.md
- [ ] Confirm `text_trigger_parser.py` patterns cover: "When this hits, draw N", "At start of turn, do X", "When you play X, do Y"

---

## Track 3 — ML / Training (lower priority until card coverage improves)
- IQL v3 trained, needs fresh H2H eval after turn_penalty retraining
- [ ] Run v3 vs v2 H2H to confirm improvement
- [ ] Expand random deck builder once more sets implemented
- [ ] `build_winrate_deck()` stub in deck_builder.py — implement once data exists

---

## Key Files to Know
| What you're doing | File to open |
|------------------|-------------|
| Adding a card effect | `engine/card_effects/registry.py` |
| Adding a card trigger | `engine/card_effects/card_triggers_extended.py` |
| Adding a trigger pattern | `engine/card_effects/text_trigger_parser.py` |
| Fixing a keyword mechanic | `engine/card_effects/card_keywords.py` |
| Fixing a CR 8.5 primitive | `engine/effect_keywords.py` |
| Fixing game loop logic | `engine/engine.py` |
| Fixing legal action generation | `engine/actions.py` |
| Fixing state/zone bugs | `engine/state.py` |

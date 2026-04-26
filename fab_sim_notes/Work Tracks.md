# Work Tracks

See also: [[Architecture Hub]] | [[Engine Overview]] | [[Card Set Status]]

Two parallel tracks. Work both simultaneously — engine gaps block card implementations, card implementations reveal engine gaps.

---

## Track 1 — Engine Rules Completeness
Goal: any legal FAB play is correctly modelled, regardless of which cards are in play.

### CR 8.5 Effect Keywords (`effect_keywords.py`) ✅ Complete
- [x] Audit all primitives against current CR 8.5 — confirm each matches the rules text
	- [x] All emit calls updated to use `create_emit_event()` helper
	- [x] Every Event object has `type: str` — no bare dict emits remain
	- [x] `EVENTTYPES` set expanded with all event strings for variable consistency
	- [x] `ContinuousEffectManager` references removed; `effect_manager` is the sole authority
	- [x] Rules fixes applied: `clash` (CR 8.5.10 both players look), `amp` (damage type tag), `retrieve` (equip from discard not hand)
	- [x] All 262 tests in `test_effect_keywords.py` pass
- [x] Post-replacement variable audit: 24 bugs fixed across 22 functions — every function now reads `event.x` fields after `dataclasses.replace()`, never pre-replacement params
- [x] shuffle needs to update player pitch histories. they wouldn't know the order anymore
- [x] `gets` / `gets_property` — continuous effect cleanup: persistent effects with no `until_condition` now auto-register a one-shot `leaves_arena` listener that calls `remove_by_id` when the target card exits the arena; prevents leaked `ContinuousEffect` entries accumulating across the game
- [x] `search` — CR 8.5.19 compliant: post-search deck shuffle added; can_fail now reads post-replacement `event.eligible_cards`
- [x] `opt` — confirm N look / choose any to top or bottom

### Attack Activation Refactor (`play.py` / `actions.py` / `engine.py`) ✅ Complete
- [x] `ATTACK_WEAPON` and `ATTACK_ALLY` action types removed from `ActionType` enum (subsumed)
- [x] `legal_actions()` now emits `ActionType.ACTIVATE_CARD` with `is_attack_proxy=True` for both weapon and ally attacks (CR 1.6.2b, CR 11.0)
- [x] `_apply_activate()` in `play.py`: if `is_attack_proxy`, creates `layer_type='activated'` StackEntry and returns — engine resolves via existing `_combat_phase_iter` / `_attack_step` logic
- [x] `_pay_costs()` is the single authoritative cost site: AP, resources (with pitching), weapon exhaustion, ally exhaustion — no cost logic in `_apply_activate` or `_apply_play_card`
- [x] `_pay_costs` returns `True` (critical fix — `None` return caused early exit before `_apply_activate` was called)
- [x] `_ally_attack_resource_cost()` added to `play.py`; `_get_base_resource_cost()` routes weapon → `_weapon_cost()`, ally → `_ally_attack_resource_cost()`
- [x] ~300 lines of dead commented-out code removed from `engine.py` tail
- [x] 15 new tests in `tests/test_play_attack_activation.py`; all 277 tests pass
- [x] Committed (`68f3280`) and pushed to `origin/effect-redesign-with-hooks`

### Continuous Effects (`continuous_effects.py` / `effects.py`) ✅ Complete
- [x] `ContinuousEffectManager` removed from `effect_keywords.py` (done in effect_keywords audit above)
- [x] Clarify which `ContinuousEffect` class is authoritative (two exist in codebase)
- [x] Replacement effects (CR 6.4) — are they wired into the damage pipeline?
- [x] `ContinuousEffectManager` folded into `EffectManager`: `EffectManager.staging` owns the instance; `state.continuous_effect_manager` is now a `@property` returning `state.effect_manager.staging` — all 12+ call sites unchanged
- [x] `state.py` field removed; top-level `ContinuousEffectManager` import removed from `state.py`
- [x] 8 new tests in `tests/test_continuous_effects.py` (arena-exit cleanup, staging identity, add/remove round-trip); 270 tests pass

### Other Engine Gaps ✅ Complete
- [x] Pitch ordering at end of turn — player chooses top-to-bottom order (CR 4.4.3)
- [x] Landmark rules (CR 8.2.9) — `player.landmarks` SubZoneView added; `resolve_stack()` now detects `_is_landmark`, enters card into permanents (sets `permanent_subtype`); CR 8.2.9b clears all other landmark permanents to graveyard on entry; legacy `GameState.landmarks` list stub removed; 7 tests in `test_landmarks.py`
- [x] Stack resolution — LIFO + attack-entry-at-front + meld two-pass all correct; fixed `_resolve_all_triggers` bug: `order_stack` was called after every resolution, now only fires when new triggers arrive during resolution; 3 tests in `test_stack_resolution.py`
### CR 8.6 Token Keywords Audit
- [ ] token keywords are included with the create_token function of effect_keywords. confirm that all token keywords are present and have their triggers processed
### CR 8.1 Type Keywords and CR 8.2 Subtype Keywords Independence 
- [ ] these should be included in the deck constructor but there are a few functions that reference types when they really mean subtypes or vice versa. I found a few in card.py but these references could be anywhere.
## Engine.Card CardDB class update for Activation cost
- [ ] The "get" method of CardDB stops looking for activation costs as soon as it finds an instance of "{r}". This does not account for cards without an activation cost ("scabskin_leathers") or cards with multiple activations ("cutty_shark_yellow")
## Update Card/CardDB classes to set an activation/play cost for 'X' cost cards
- [ ] i assumed "X" cost cards would appear in the cost field of the slug_index, however, for cards like imposing visage the "cost" field is None and they have a "specialCost" field that is a string.
- [ ] Engine needs to be updated to look for "{x}" in the functional text to represent a variable cost for activations (like beckoning_haunt) or look at "specialCost" for cards like imposing visage.
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
## Track 2.5 - Talishar Front End
- Use the talishar front-end design to track games in a human-readable way
- [ ] Only use it for tracking card movements. Don't need to adapt the actor decision inputs if we only use it to update card locations
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

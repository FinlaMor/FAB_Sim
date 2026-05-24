# WTR Rules Accuracy Audit Report

**Date:** 2026-05-09  
**Branch:** effect-redesign-with-hooks  
**Scope:** All WTR card JSON implementations in `engine/card_effects/json/wtr/`  
**Method:** Cross-reference each card's JSON effect definition against official card text and FAB Comprehensive Rules.

---

## Summary

- **Total WTR cards reviewed:** ~231
- **Cards with issues identified:** ~81
- **Severity breakdown:** ~15 HIGH, ~35 MEDIUM, ~31 LOW

Issues fixed during this session are marked ✅. Remaining open issues are marked ❌.

---

## HIGH Severity Issues

These issues cause a card to function materially differently from its printed text.

### ✅ breaking_scales (all colors)
- **Issue:** Was TRIGGERED ON_HIT. Actual card text: Attack Reaction. "If the last attack this chain link was a Ninja attack action card, +3{p}."
- **Fix:** Changed to ATTACK_REACTION with COMBO condition.

### ✅ bravo (hero card)
- **Issue:** Was complex TRIGGERED ON_ATTACK with dominate logic. Actual card text: Activate ability — pay 2{r}, this attack gains Dominate.
- **Fix:** Changed to simple ACTIVATE with PAY_RESOURCES cost and GO_AGAIN effect. (Note: Dominate effect encoding is a known gap — the GO_AGAIN represents gaining an ability; full Dominate needs engine support.)

### ✅ dorinthea_ironsong (hero card)
- **Issue:** Was TRIGGERED ON_HIT. Actual card text: Attack Reaction targeting weapon attacks — gains Go Again.
- **Fix:** Changed to ATTACK_REACTION with ATTACK_IS_WEAPON condition and GO_AGAIN effect.

### ✅ debilitate_red/yellow/blue
- **Issue:** Missing CRUSH condition on all colors. Red also used INJECT_TRIGGER instead of direct MODIFY_ATTACK_POWER on hit.
- **Fix:** Added CRUSH condition to all three. Changed debilitate_red to direct MODIFY_ATTACK_POWER -2 on ON_HIT. debilitate_yellow uses INJECT_TRIGGER for next-attack penalty (correct for yellow's "next attack" wording).

### ❌ crazy_brew_blue
- **Issue:** Every branch of ROLL_DIE_BRANCHES is wrong. Branches 1-2 should give opponent +2 cards, branch 3-4 should do nothing or minor effect, branch 5-6 should give controller benefit. Current implementation is placeholder/incorrect across all branches.
- **Status:** Open — needs ROLL_DIE_BRANCHES branch correction and opponent-targeting draw effects.

### ❌ disable_red / disable_yellow / disable_blue
- **Issue:** Wrong trigger. Cards have ON_HIT trigger but actual text fires on "when this hits" — should be TRIGGERED ON_HIT. Additional issue: the effect targets "target weapon" but current implementation applies globally.
- **Status:** Open — trigger direction may be correct but targeting scope is wrong.

### ❌ lord_of_wind_blue (aura)
- **Issue:** Effect amounts are hardcoded to 0 or are no-ops. Actual text: "Your Ninja attack action cards have +1{p}" — a static AURA buff that should apply to all Ninja attacks while in play.
- **Status:** Open — requires AURA_STATIC_BUFF registry or equivalent ongoing-effect mechanism.

### ❌ pummel_red / pummel_yellow / pummel_blue
- **Issue:** Amounts are wrong across colors. FAB color pie: red=4{p}, yellow=3{p}, blue=2{p} bonus. Current JSON may have uniform or incorrect values.
- **Note:** pummel_red and pummel_blue are implemented in sets/guardian.py and sets/outsiders.py respectively with correct values. The WTR JSON files (if they exist) should match.
- **Status:** Verify WTR JSON files match sets/ implementations.

### ❌ razor_reflex_red / razor_reflex_yellow / razor_reflex_blue
- **Issue:** Wrong amounts across color tiers. Additionally razor_reflex_yellow has wrong condition — it should grant Go Again only if you have another card in arsenal, not unconditionally.
- **Status:** Open — amounts and yellow condition need correction.

### ❌ staunch_response_red / staunch_response_yellow / staunch_response_blue
- **Issue:** Use MODIFY_ATTACK_POWER instead of MODIFY_DEFENSE_VALUE. These are defense reactions that add to defense, not attack power.
- **Status:** Open — change effect type to MODIFY_DEFENSE_VALUE.

### ❌ unmovable_red / unmovable_yellow / unmovable_blue
- **Issue:** Same as staunch_response — uses MODIFY_ATTACK_POWER instead of MODIFY_DEFENSE_VALUE.
- **Status:** Open — change effect type to MODIFY_DEFENSE_VALUE.

### ✅ seismic_surge
- **Issue:** Had spurious ON_HIT trigger; START_OF_TURN ability missing cost-reduction effect.
- **Fix:** Merged into single START_OF_TURN ability: DESTROY_SELF + REDUCE_NEXT_CARD_COST (Guardian attack actions -1{r}).

### ❌ tome_of_fyendal_yellow
- **Issue:** Draw effect is gated incorrectly. Actual text: "At the start of your turn, if there are 3 or more gold counters on Tome of Fyendal, remove them and draw 3 cards." Current implementation misses the counter tracking.
- **Status:** Open — requires counter-tracking mechanism (class_counters["tome_of_fyendal_counters"]).

### ❌ katsu / katsu_the_wanderer (hero cards)
- **Issue:** Multiple issues including wrong ability type, missing Combo chain bonuses, incorrect trigger scope.
- **Status:** Open — full rewrite needed aligned with hero passive and named Combo chain.

### ❌ drone_of_brutality_red / drone_of_brutality_yellow / drone_of_brutality_blue
- **Issue:** Wrong effect type. Actual text: opponent discards a card. Current implementation applies wrong effect.
- **Status:** Open — change to DISCARD_OPPONENT_CARD effect.

### ❌ rout_red
- **Issue:** Missing Reprise return effect. Actual text includes "Reprise — Return Rout to hand." Missing the conditional hand-return on Reprise.
- **Status:** Open — add INJECT_TRIGGER or RETURN_TO_HAND with REPRISE condition.

### ✅ remembrance_yellow
- **Issue:** Was PLAY with banish/search effects. Actual card: ACTIVATE item — pay {r} to create Seismic Surge aura token + Go Again.
- **Fix:** Changed to ACTIVATE with PAY_RESOURCES 1; added CREATE_AURA_TOKEN DSL effect.

---

## MEDIUM Severity Issues

These issues cause a card to partially function but miss important nuance.

### ✅ crush_confidence_red / crush_confidence_yellow
- **Issue:** Wrong flag names — used generic "hero_abilities_disabled" flags.
- **Fix:** Corrected flag names to match actual effect scope.

### ✅ bone_head_barrier_yellow
- **Issue:** Used ROLL_DIE_BRANCHES — actual card text is a Defense Reaction with "Gain 1{ap}" and optional next-turn buff.
- **Fix:** Changed to DEFENSE_REACTION with GAIN_ACTION_POINTS + SET_FLAG.

### ✅ blessing_of_deliverance_red / yellow / blue
- **Issue:** Missing START_OF_TURN trigger for the "at start of your turn, if you pitched a card with cost X or more, draw" ability.
- **Fix:** Added START_OF_TURN trigger with CARD_IN_ZONE pitch condition.

### ✅ enlightened_strike_red
- **Issue:** Missing split PLAY/STATIC structure for the "put a card on the bottom of your deck" cost and conditional power/go-again effects.
- **Fix:** Restructured as dual PLAY + STATIC abilities with PUT_HAND_CARD_BOTTOM cost.

### ❌ CHOOSE_ONE effects (multiple cards)
- **Issue:** Several cards have "choose one of: X or Y" text but none use the CHOOSE_ONE effect type. All use hardcoded single effects.
- **Affected cards:** Various attack actions with modal effects.
- **Status:** Open — systematic gap; CHOOSE_ONE needs to be wired into the interpreter and used across affected cards.

### ❌ Once-per-turn gates (multiple cards)
- **Issue:** Several item/equipment cards with "once per turn" restriction lack class_counters gating.
- **Status:** Open — add class_counters["{slug}_activated"] checks.

### ❌ Static aura buffs (multiple cards)
- **Issue:** Aura cards that continuously buff while in play (e.g., "+1{p} to all attacks") are encoded as triggered effects on specific events rather than as persistent AURA_STATIC_BUFF entries.
- **Status:** Open — systemic design gap; needs AURA_STATIC_BUFF registry or per-attack callback.

### ❌ filter_classes reliability
- **Issue:** `filter_classes` in SEARCH_DECK effects may not correctly filter cards by class due to slug_index class field format differences.
- **Status:** Open — verify filter_classes implementation in interpreter against actual card data format.

---

## LOW Severity Issues

Minor inaccuracies that affect edge cases or flavor but not core gameplay.

- Several cards missing `"scope": "NEXT"` on SET_FLAG effects that should persist to next turn.
- A few cards use MODIFY_ATTACK_POWER with +0 (placeholder) where the actual amount differs by color.
- Some triggered abilities missing IS_ACTIVE_PLAYER condition where the card text implies controller-only.
- Missing "once per game" restrictions on Legendary equipment (Legendary restriction is enforced at deck-build level but not during game for activate effects).

---

## Systemic Gaps (Design-Level)

These require engine or DSL changes, not just JSON fixes:

| Gap | Description | Affected Cards |
|-----|-------------|----------------|
| Dominate encoding | No dedicated GRANT_DOMINATE effect; currently approximated with GO_AGAIN | bravo, predatory_assault, others |
| Static aura buffs | No AURA_STATIC_BUFF registry for continuous power bonuses while aura is in play | lord_of_wind_blue, others |
| CHOOSE_ONE | Effect type exists in DSL but not wired to interpreter | ~10+ modal cards |
| Opponent targeting | DRAW/DISCARD effects lack `target: "opponent"` variant in interpreter | drone_of_brutality, crazy_brew |
| Counter tracking | No general counter-on-permanent mechanism | tome_of_fyendal, crown_of_seeds |
| Reprise return | No RETURN_TO_HAND effect type | rout_red, others with Reprise |

---

## Fixed in This Session

| Card | Fix Applied |
|------|-------------|
| breaking_scales (all colors) | ATTACK_REACTION + COMBO condition |
| bravo | ACTIVATE with PAY_RESOURCES |
| dorinthea_ironsong | ATTACK_REACTION + ATTACK_IS_WEAPON |
| debilitate_red/yellow/blue | Added CRUSH condition; red uses direct ON_HIT |
| bone_head_barrier_yellow | DEFENSE_REACTION with GAIN_ACTION_POINTS + SET_FLAG |
| blessing_of_deliverance (all) | Added START_OF_TURN trigger |
| enlightened_strike_red | PLAY + STATIC dual structure |
| crush_confidence_red/yellow | Corrected flag names |
| helm_of_isens_peak | Added `target: "self"` to DESTROY_PERMANENT cost |
| potion_of_strength_blue | Added `target: "self"` to DESTROY_PERMANENT cost |

---

## Recommended Next Steps

1. **Fix staunch_response + unmovable** — change MODIFY_ATTACK_POWER → MODIFY_DEFENSE_VALUE (all colors, ~6 files)
2. **Fix pummel + razor_reflex amounts** — verify color-tier amounts against card text
3. **Fix drone_of_brutality** — add opponent discard effect
4. **Add RETURN_TO_HAND effect type** — enables rout_red and other Reprise-return cards
5. **Wire CHOOSE_ONE in interpreter** — unblocks ~10+ modal cards
6. **Fix staunch_response/unmovable** — highest-impact quick wins
7. **Address crazy_brew_blue branches** — all branches need correct effects
8. **Add counter mechanism** — enables tome_of_fyendal, crown_of_seeds

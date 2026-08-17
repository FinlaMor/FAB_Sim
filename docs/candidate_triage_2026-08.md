# Candidate-tier triage (2026-08-17)

`candidate` means the JSON compiles and is not a no-op stub, but **no generated
test ever passed**. Those cards stayed live and playable, so the corpus was
trusting 787 implementations nothing had ever checked — and the last semantic
sample of that tier found errors in 6 of 6 cards.

## What was done

`scripts/triage_candidates.py` classifies every candidate using the mechanical
defect checks from `audit_run.py` (no LLM, so 787 cards take seconds instead of
the ~23 hours a full gate run would need).

| Bucket | Count | Action |
|---|---|---|
| defective, not in any deck | 93 | **quarantined** out of the live corpus |
| defective, used by a deck | 48 | kept live, listed below for hand review |
| clean | 645 | stay live and stay `candidate` |
| json missing | 1 | queue entry with no file |

Result: corpus 1036 -> 943 cards, mechanical defect rate **15% -> 6%**, zero
load errors, and all 5 working decks plus all 15 audit decks still load.

## Policy: quarantine only on positive evidence

Only cards with a *provable* defect are quarantined. Absence of a passing test
is NOT evidence a card is wrong — the gate benchmark showed the residual
failures are AssertionErrors, i.e. genuine disagreements, not proof of breakage.
Quarantining all 645 clean candidates would remove far more working cards than
broken ones.

## Two traps this hit (both would have been silent)

1. **A vacuous safety check.** The deck-protection set was first parsed with a
   regex expecting bare slugs, but deck files list card NAMES (`1x Aurum
   Aegis`). It returned an EMPTY set, making "is this card in a deck?" false
   for everything — the guard would have passed vacuously and quarantined all
   141 defective cards, including the 48 below that working decks depend on.
   The script now resolves names through `engine.deck.load_deck` and **aborts**
   if the protection set is empty.
2. **A cosmetic quarantine.** `loader.load_all_cards()` rglobs `*.json` and
   skips only DOT-prefixed path parts, so a `_quarantine/` folder would still
   have been loaded and the cards would have stayed live. The folder is
   `.quarantine/`. Verified by card count: 1036 -> 943 = exactly the 93 moved.

## The 48 defective cards inside working decks

These are the highest-value fixes left: they are provably broken AND actually
played. They are NOT quarantined, because a missing implementation makes the
game refuse to start, which would break a deck that works today.

### Invented flags (33) — the ability can never fire

| Card | Flag |
|---|---|
| `batch/auric_shards_yellow` | `HOLO_COUNTER` |
| `batch/pound_town_blue` | `BEAT_CHEST_THIS_TURN` |
| `batch/public_bounty_yellow` | `TARGET_MARKED` |
| `batch/loan_shark_yellow` | `NO_GOLD_CREATED_OR_STOLEN_THIS_TURN` |
| `batch/comet_collision_red` | `STARFALL_FLAG` |
| `batch/tide_chakra_yellow` | `TRANSCENDED` |
| `batch/infuse_alloy_yellow` | `OPT_1_USED` |
| `batch/break_ground_red` | `PUT_CARDS_BOTTOM_FLAG` |
| `batch/scrap_prospector_blue` | `SCRAPPED_CARD` |
| `batch/hunted_or_hunter_red` | `ATTACK_REACTION_PLAYED_OR_ACTIVATED` |
| `batch/downswing_red` | `CLASH_LOSE` |
| `batch/scrap_compactor_blue` | `SCRAPPED_CARD` |
| `batch/high_roller_yellow` | `ROLL_5_OR_6` |
| `batch/bonebreaker_bellow_red` | `BEAT_CHEST` |
| `batch/whelming_gustwave_red` | `SURGING_STRIKE_LAST_ATTACK` |
| `batch/call_in_the_big_guns_red` | `NEXT_ARROW_ATTACK` |
| `batch/push_the_point_yellow` | `LAST_ATTACK_HIT` |
| `batch/wind_chakra_red` | `TRANSCEDED_THIS_TURN` |
| `batch/grow_wings_blue` | `LAST_ATTACK_WAS_DRACONIC` |
| `batch/mage_hunter_arrow_red` | `MAGE_HUNTER_ARROW_ACTIVE` |
| `batch/rising_knee_thrust_blue` | `LEG_TAP_LAST_ATTACK` |
| `batch/chromatic_refinement_blue` | `CHROMATIC_REFINEMENT_DEALT_DAMAGE` |
| `batch/glint_the_quicksilver_blue` | `REPRISE_FLAG` |
| `batch/blackout_kick_yellow` | `RISING_KNEE_THRUST_LAST_ATTACK` |
| `batch/swordmasters_path_blue` | `SHARPEN_FLAG` |
| `batch/envelop_in_darkness_red` | `RUNE_GATE_FLAG` |
| `batch/angelic_descent_yellow` | `ANGEL_ATTACK_THIS_TURN` |
| `batch/biting_blade_red` | `DEFENDED_WITH_HAND_CARD` |
| `batch/resounding_courage_yellow` | `CHARGED_THIS_TURN` |
| `batch/lumina_ascension_yellow` | `BOLTYN_SPECIALIZATION_ACTIVE` |
| `batch/vengeance_never_rests_blue` | `EDGE_OF_AUTUMN_LAST_ATTACK` |
| `batch/back_alley_breakline_yellow` | `ACTIVATED_ABILITY_OR_ACTION_CARD_EFFECT` |
| `batch/grow_claws_blue` | `LAST_ATTACK_WAS_DRACONIC` |

### Invented amounts (15) — resolves to 0, effect silently does nothing

| Card | Amount |
|---|---|
| `batch/bully_tactics_red` | `PAYMENT_AMOUNT` |
| `batch/rushing_river_blue` | `CHAIN_HIT_COUNT` |
| `batch/pry_yellow` | `ALL` |
| `batch/eradicate_yellow` | `DAMAGE_AMOUNT` |
| `batch/heavy_artillery_red` | `EVO_COUNT` |
| `batch/thistle_bloom__life_yellow` | `TOTAL_HEALTH_GAINED_THIS_TURN` |
| `batch/reel_in_blue` | `X+1` |
| `batch/doomsaying_red` | `doom` |
| `batch/urgent_delivery_yellow` | `BOOST_COUNT` |
| `batch/imposing_visage_blue` | `SEARCHED_COUNT` |
| `batch/sigil_of_solitude_red` | `gt` |
| `batch/bask_in_your_own_greatness_red` | `PAY_AMOUNT` |
| `batch/mounting_anger_red` | `DRACONIC_CHAIN_LINKS_CONTROLLED` |
| `batch/pulsewave_harpoon_red` | `BOOST_FLAG_COUNT` |
| `batch/cash_out_blue` | `destroyed_permanents_count` |

## Next

The flag families here are the same ones the dangling-flag work left open
(scrap, transcend, chakra, clash, chain-link, beat-chest) plus per-card
one-offs. Each needs a real mechanic, not another marker — which is the
missing-primitives work the gate benchmark also pointed at.

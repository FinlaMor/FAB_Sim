#!/bin/bash

echo "=== VICTOR CARDS ==="
for card in "boulder_drop_red" "command_and_conquer_red" "debilitate_red" "enlightened_strike_red" "pummel_red" "spinal_crush_red" "test_of_iron_grip_red" "test_of_strength_red" "trounce_red" "riches_of_trpal_dhani_yellow" "righteous_cleansing_yellow" "the_golden_son_yellow" "cranial_crush_blue" "debilitate_blue" "disable_blue" "headbutt_blue" "macho_grande_blue" "right_behind_you_blue" "ripple_away_blue" "thunder_quake_blue" "thunk_blue" "visit_goldmane_estate_blue" "aurum_aegis" "crown_of_dominion" "fyendals_spring_tunic" "ironfist_revelation" "miller_s_grindstone" "quickdodge_flexors" "victor_goldmane_high_and_mighty"; do
  if grep -q "\"$card\"" engine/card_effects/*.py; then
    echo "$card: FOUND"
  else
    echo "$card: MISSING"
  fi
done

echo ""
echo "=== KAYO CARDS ==="
for card in "big_bully_red" "chain_of_brutality_red" "looking_for_a_scrap_red" "mocking_blow_red" "show_of_strength_red" "sigil_of_solace_red" "sink_below_red" "snarky_prick_red" "swing_big_red" "mocking_blow_yellow" "booze_blue" "insult_to_injury_blue" "mocking_blow_blue" "nimblism_blue" "nimby_blue" "offensive_behavior_blue" "outside_interference_blue" "overcrowded_blue" "reckless_arithmetic_blue" "steal_victory_blue" "apex_bonebreaker" "savage_claw" "scabskin_leathers" "scowling_flesh_bag" "kayo_underhanded_cheat"; do
  if grep -q "\"$card\"" engine/card_effects/*.py; then
    echo "$card: FOUND"
  else
    echo "$card: MISSING"
  fi
done

echo ""
echo "=== ARAKNI CARDS ==="
for card in "art_of_desire_body_red" "cut_from_the_same_cloth_red" "death_touch_red" "frailty_trap_red" "inertia_trap_red" "infiltrate_red" "kiss_of_death_red" "lair_of_the_spider_red" "leave_no_witnesses_red" "mark_of_the_black_widow_red" "orb_weaver_spinneret_red" "pain_in_the_backside_red" "pick_up_the_point_red" "savor_bloodshed_red" "scar_tissue_red" "sink_below_red" "stains_of_the_redback_red" "tarantula_toxin_red" "to_the_point_red" "up_sticks_and_run_red" "codex_of_frailty_yellow" "codex_of_inertia_yellow" "shred_yellow" "spreading_plague_yellow" "take_up_the_mantle_yellow" "night_s_embrace_blue" "schism_of_chaos_blue" "stains_of_the_redback_blue" "under_the_trap_door_blue" "blacktek_whisperers" "flick_knives" "hunter_s_klaive" "mask_of_deceit" "arakni_marionette"; do
  if grep -q "\"$card\"" engine/card_effects/*.py; then
    echo "$card: FOUND"
  else
    echo "$card: MISSING"
  fi
done

# Missing Mechanics — Cards That Cannot Be Implemented Yet

This file tracks card mechanics that the FAB_Sim engine does not yet support.
Each section lists the mechanic, a brief description of why it's blocked, and all affected card slugs.

**Total unsupported cards: ~271** (some cards appear under multiple mechanics)

---

## Transform (69 cards)

**Description:** Transform replaces one permanent with another (e.g., an Ash token becomes an Aether Ashwing, or base equipment becomes an Evo upgrade). Requires the engine to support removing a card from play and replacing it with a different card, maintaining zone continuity and counters where applicable.

**Why blocked:** No engine support for in-place card replacement / permanent mutation. The state model has no concept of transforming one card object into another.

| Slug | Notes |
|------|-------|
| `billowing_mirage_red` | Transform ash → Aether Ashwing |
| `billowing_mirage_yellow` | Transform ash → Aether Ashwing |
| `billowing_mirage_blue` | Transform ash → Aether Ashwing |
| `blasmophet_levia_consumed` | Legendary hero transform |
| `construct_bank_breaker_yellow` | Transform wrench + Hyper Drivers → Construct |
| `construct_nitro_mechanoid_yellow` | Transform equipment + Hyper Drivers → Mechanoid |
| `dustup_red` | Create Ash then transform to Aether Ashwing |
| `dustup_yellow` | Create Ash then transform to Aether Ashwing |
| `dustup_blue` | Create Ash then transform to Aether Ashwing |
| `evo_atom_breaker_red` | Transform base chest + Hyper Drivers → Evo equipment |
| `evo_battery_pack_yellow` | Evo transform |
| `evo_beta_base_arms_blue` | Evo transform |
| `evo_beta_base_chest_blue` | Evo transform |
| `evo_beta_base_head_blue` | Evo transform |
| `evo_beta_base_legs_blue` | Evo transform |
| `evo_buzz_hive_yellow` | Evo transform |
| `evo_charging_rods_yellow` | Evo transform |
| `evo_circuit_breaker_red` | Evo transform |
| `evo_cogspitter_yellow` | Evo transform |
| `evo_command_center_yellow` | Evo transform |
| `evo_data_mine_yellow` | Evo transform |
| `evo_energy_matrix_blue` | Evo transform |
| `evo_engine_room_yellow` | Evo transform |
| `evo_face_breaker_red` | Evo transform |
| `evo_heartdrive_blue` | Evo transform |
| `evo_mach_breaker_red` | Evo transform |
| `evo_magneto_blue` | Evo transform |
| `evo_rapid_fire_blue` | Evo transform |
| `evo_recall_blue` | Evo transform |
| `evo_scatter_shot_blue` | Evo transform |
| `evo_sentry_base_arms_red` | Evo transform |
| `evo_sentry_base_chest_red` | Evo transform |
| `evo_sentry_base_head_red` | Evo transform |
| `evo_sentry_base_legs_red` | Evo transform |
| `evo_shortcircuit_blue` | Evo transform |
| `evo_smoothbore_yellow` | Evo transform |
| `evo_speedslip_blue` | Evo transform |
| `evo_steel_soul_controller_blue` | Evo transform |
| `evo_steel_soul_memory_blue` | Evo transform |
| `evo_steel_soul_processor_blue` | Evo transform |
| `evo_steel_soul_tower_blue` | Evo transform |
| `evo_tekloscope_blue` | Evo transform |
| `evo_thruster_yellow` | Evo transform |
| `evo_whizz_bang_yellow` | Evo transform |
| `evo_zip_line_yellow` | Evo transform |
| `evo_zoom_call_yellow` | Evo transform |
| `invoke_azvolai_red` | Invoke dragon transform |
| `invoke_cromai_red` | Invoke dragon transform |
| `invoke_dominia_red` | Invoke dragon transform |
| `invoke_dracona_optimai_red` | Invoke dragon transform |
| `invoke_kyloria_red` | Invoke dragon transform |
| `invoke_miragai_red` | Invoke dragon transform |
| `invoke_nekria_red` | Invoke dragon transform |
| `invoke_ouvia_red` | Invoke dragon transform |
| `invoke_suraya_yellow` | Invoke dragon transform |
| `invoke_themai_red` | Invoke dragon transform |
| `invoke_tomeltai_red` | Invoke dragon transform |
| `invoke_vynserakai_red` | Invoke dragon transform |
| `invoke_yendurai_red` | Invoke dragon transform |
| `levia_redeemed` | Hero transform |
| `ouvia` | Dragon hero with transform |
| `rake_the_embers_red` | Transform ash → Aether Ashwing |
| `rake_the_embers_yellow` | Transform ash → Aether Ashwing |
| `rake_the_embers_blue` | Transform ash → Aether Ashwing |
| `silken_form` | Transform equipment |
| `singularity_red` | Transform mechanic |
| `skittering_sands_red` | Transform ash → Aether Ashwing |
| `skittering_sands_yellow` | Transform ash → Aether Ashwing |
| `skittering_sands_blue` | Transform ash → Aether Ashwing |

---

## Clash (60 cards)

**Description:** Clash is a mechanic where heroes reveal the top card of their deck and compare pitch values. The hero with the higher pitch value wins the clash. Requires deck-top reveal, comparison logic, and winner/loser effect resolution.

**Why blocked:** No engine support for simultaneous reveal-and-compare from deck tops, clash winner tracking, or clash count per turn.

| Slug | Notes |
|------|-------|
| `big_hits_big_applause` | Clash with each opposing hero |
| `boast_blue` | Bonus based on clashes won this turn |
| `break_stature_yellow` | Can't clash while crush effect active |
| `brutus_summa_rudis` | Hero — multi-class clash deck building |
| `clash_of_agility_red` | Defend trigger → clash, winner creates Agility token |
| `clash_of_agility_yellow` | Defend trigger → clash, winner creates Agility token |
| `clash_of_agility_blue` | Defend trigger → clash, winner creates Agility token |
| `clash_of_arms_yellow` | Defend Guardian → clash |
| `clash_of_bravado_yellow` | Defend → clash, winner destroys aura |
| `clash_of_chests_yellow` | Defend Guardian → clash |
| `clash_of_heads_yellow` | Defend Guardian → clash |
| `clash_of_legs_yellow` | Defend Guardian → clash |
| `clash_of_might_red` | Attack → clash |
| `clash_of_might_yellow` | Attack → clash |
| `clash_of_might_blue` | Attack → clash |
| `clash_of_mountains_red` | Attack → clash |
| `clash_of_mountains_yellow` | Attack → clash |
| `clash_of_mountains_blue` | Attack → clash |
| `clash_of_shields_yellow` | Defend Guardian → clash |
| `clash_of_vigor_red` | Defend → clash, winner gains life |
| `clash_of_vigor_yellow` | Defend → clash, winner gains life |
| `clash_of_vigor_blue` | Defend → clash, winner gains life |
| `daily_grind_blue` | Clash-related |
| `fix_the_match_yellow` | Manipulate clash outcomes |
| `groundbreaker_crix` | Hero with clash synergy |
| `millers_grindstone` | Equipment with clash synergy |
| `no_hero_stands_alone_yellow` | Clash-related |
| `overturn_the_results_blue` | Clash result manipulation |
| `pec_perfect_red` | Clash synergy |
| `rapturous_applause_red` | Clash synergy |
| `rapturous_applause_yellow` | Clash synergy |
| `rapturous_applause_blue` | Clash synergy |
| `reckless_stampede_red` | Clash synergy |
| `stonewall_impasse` | Equipment with clash |
| `test_of_agility_red` | Clash test |
| `test_of_iron_grip_red` | Clash test |
| `test_of_might_red` | Clash test |
| `test_of_strength_red` | Clash test |
| `test_of_vigor_red` | Clash test |
| `the_golden_son_yellow` | Clash-related |
| `the_old_switcheroo_blue` | Clash manipulation |
| `thunk_red` | Clash attack |
| `thunk_yellow` | Clash attack |
| `thunk_blue` | Clash attack |
| `tough_smashup_red` | Clash attack |
| `tough_smashup_yellow` | Clash attack |
| `tough_smashup_blue` | Clash attack |
| `trounce_red` | Clash-related |
| `unexpected_backhand_red` | Clash attack |
| `unexpected_backhand_yellow` | Clash attack |
| `unexpected_backhand_blue` | Clash attack |
| `victor_goldmane` | Hero with clash |
| `victor_goldmane_high_and_mighty` | Hero with clash |
| `victor_goldmane_match_fixer` | Hero with clash |
| `vigorous_smashup_red` | Clash attack |
| `vigorous_smashup_yellow` | Clash attack |
| `vigorous_smashup_blue` | Clash attack |
| `wallop_red` | Clash attack |
| `wallop_yellow` | Clash attack |
| `wallop_blue` | Clash attack |

---

## Spectra (64 cards)

**Description:** Spectra is a token subtype (Spectral Shield) that can be activated to attack or used defensively. Spectral Shields are aura tokens with ward that can be sacrificed for various effects. Requires token activation as an attack source and Spectra-specific interactions.

**Why blocked:** No engine support for token-based attacks (Spectral Shield activation), ward on tokens, or Spectra-specific triggered abilities.

| Slug | Notes |
|------|-------|
| `aegis_archangel_of_protection` | Banish from soul, Spectra synergy |
| `arc_light_sentinel_yellow` | Spectra attack target restriction |
| `astral_etchings_red` | +1 power counters on aura with ward, Spectral Shield check |
| `astral_etchings_yellow` | +1 power counters on aura with ward, Spectral Shield check |
| `astral_etchings_blue` | +1 power counters on aura with ward, Spectral Shield check |
| `blessing_of_spirits_red` | Create 3 Spectral Shield tokens |
| `blessing_of_spirits_yellow` | Create 2 Spectral Shield tokens |
| `blessing_of_spirits_blue` | Create 1 Spectral Shield token |
| `calming_gesture` | Create Spectral Shield token |
| `enigma` | Spectral Shield cost reduction, hero ability |
| `enigma_ledger_of_ancestry` | Enigma hero variant |
| `enigma_new_moon` | Enigma hero variant |
| `figment_of_protection_yellow` | Spectral Shield creation |
| `genesis_yellow` | Spectra synergy |
| `haunting_specter_red` | Spectral attack |
| `haunting_specter_yellow` | Spectral attack |
| `haunting_specter_blue` | Spectral attack |
| `haze_bending_blue` | Spectra manipulation |
| `herald_of_protection_red` | Spectral Shield creation |
| `herald_of_protection_yellow` | Spectral Shield creation |
| `herald_of_protection_blue` | Spectral Shield creation |
| `invoke_suraya_yellow` | Spectra + transform |
| `merciful_retribution_yellow` | Spectra synergy |
| `ode_to_wrath_yellow` | Spectra synergy |
| `parable_of_humility_yellow` | Spectra synergy |
| `passing_mirage_blue` | Spectra manipulation |
| `phantasmal_haze_red` | Spectra aura |
| `phantasmal_haze_yellow` | Spectra aura |
| `phantasmal_haze_blue` | Spectra aura |
| `pierce_reality_blue` | Spectra synergy |
| `prism` | Prism hero — Spectra core |
| `prism_sculptor_of_arc_light` | Prism hero variant |
| `prismatic_shield_red` | Spectra defense |
| `prismatic_shield_yellow` | Spectra defense |
| `prismatic_shield_blue` | Spectra defense |
| `restless_coalescence_yellow` | Spectra synergy |
| `sacred_art_immortal_lunar_shrine_blue` | Spectra + Transcend |
| `shimmering_specter_red` | Spectral attack |
| `shimmering_specter_yellow` | Spectral attack |
| `shimmering_specter_blue` | Spectral attack |
| `shimmers_of_silver_blue` | Spectra creation |
| `solitary_companion_red` | Spectra synergy |
| `solitary_companion_yellow` | Spectra synergy |
| `solitary_companion_blue` | Spectra synergy |
| `spectral_manifestations_red` | Spectra creation |
| `spectral_manifestations_yellow` | Spectra creation |
| `spectral_manifestations_blue` | Spectra creation |
| `spectral_procession_red` | Spectra creation |
| `spectral_prowler_red` | Spectral attack |
| `spectral_prowler_yellow` | Spectral attack |
| `spectral_prowler_blue` | Spectral attack |
| `spectral_rider_red` | Spectral attack |
| `spectral_rider_yellow` | Spectral attack |
| `spectral_rider_blue` | Spectral attack |
| `tales_of_adventure_blue` | Spectra synergy |
| `the_librarian` | Equipment — Spectra synergy |
| `united_we_stand_yellow` | Spectra synergy |
| `waning_vengeance_red` | Spectra synergy |
| `waning_vengeance_yellow` | Spectra synergy |
| `waning_vengeance_blue` | Spectra synergy |
| `water_glow_lanterns_red` | Spectra token creation |
| `water_glow_lanterns_yellow` | Spectra token creation |
| `water_glow_lanterns_blue` | Spectra token creation |
| `wave_of_reality` | Spectra mass effect |

---

## Aim Counter (50 cards)

**Description:** Aim counters are placed on arrow cards in arsenal to grant bonus effects when attacking. Requires arsenal face-up state tracking, counter placement on arsenal cards, and conditional ability grants based on counter presence.

**Why blocked:** No engine support for counters on cards in arsenal, face-up arsenal card state, or conditional ability modification based on arsenal counter state.

| Slug | Notes |
|------|-------|
| `barbed_castaway` | Put arrow face-up in arsenal, aim counter placement |
| `barbed_undertow_red` | Aim counter grants on-hit color choice |
| `blessing_of_focus_red` | Opt then reveal top, aim counter if arrow |
| `blessing_of_focus_yellow` | Opt then reveal top, aim counter if arrow |
| `blessing_of_focus_blue` | Opt then reveal top, aim counter if arrow |
| `crows_nest` | Aim counter on arrow from deck to arsenal |
| `dead_eye_yellow` | Arrow +3 power, aim counter bonus |
| `drill_shot_red` | Aim counter grants piercing |
| `drill_shot_yellow` | Aim counter grants piercing |
| `drill_shot_blue` | Aim counter grants piercing |
| `falcon_wing_red` | Aim counter interaction |
| `falcon_wing_yellow` | Aim counter interaction |
| `falcon_wing_blue` | Aim counter interaction |
| `fletch_a_blue_tail_blue` | Put arrow in arsenal with aim counter |
| `fletch_a_red_tail_red` | Put arrow in arsenal with aim counter |
| `fletch_a_yellow_tail_yellow` | Put arrow in arsenal with aim counter |
| `flight_path` | Aim counter synergy equipment |
| `hemorrhage_bore_red` | Aim counter interaction |
| `hemorrhage_bore_yellow` | Aim counter interaction |
| `hemorrhage_bore_blue` | Aim counter interaction |
| `immobilizing_shot_red` | Aim counter interaction |
| `infecting_shot_red` | Aim counter interaction |
| `infecting_shot_yellow` | Aim counter interaction |
| `infecting_shot_blue` | Aim counter interaction |
| `judge_jury_executioner_red` | Aim counter interaction |
| `line_it_up_yellow` | Aim counter placement |
| `long_shot_red` | Aim counter interaction |
| `long_shot_yellow` | Aim counter interaction |
| `long_shot_blue` | Aim counter interaction |
| `melting_point_red` | Aim counter interaction |
| `murkmire_grapnel_red` | Aim counter interaction |
| `murkmire_grapnel_yellow` | Aim counter interaction |
| `murkmire_grapnel_blue` | Aim counter interaction |
| `murky_water_red` | Aim counter interaction |
| `point_the_tip_red` | Aim counter interaction |
| `point_the_tip_yellow` | Aim counter interaction |
| `point_the_tip_blue` | Aim counter interaction |
| `sandscour_greatbow` | Weapon — aim counter synergy |
| `sedation_shot_red` | Aim counter interaction |
| `sedation_shot_yellow` | Aim counter interaction |
| `sedation_shot_blue` | Aim counter interaction |
| `sharp_shooters` | Equipment — aim counter synergy |
| `skybound_shot_red` | Aim counter interaction |
| `skybound_shot_yellow` | Aim counter interaction |
| `skybound_shot_blue` | Aim counter interaction |
| `stone_rain_red` | Aim counter interaction |
| `target_totalizer` | Equipment — aim counter synergy |
| `withering_shot_red` | Aim counter interaction |
| `withering_shot_yellow` | Aim counter interaction |
| `withering_shot_blue` | Aim counter interaction |

---

## Contract (40 cards)

**Description:** Contract is an Assassin mechanic where a card specifies a contract condition (e.g., "banish opponents' attack action cards"). When the condition is met during the game, the contract is "completed" and a reward triggers. Requires persistent tracking of contract fulfillment across turns.

**Why blocked:** No engine support for persistent contract state tracking, contract completion detection, or contract reward resolution.

| Slug | Notes |
|------|-------|
| `already_dead_red` | Contract to banish non-action cards |
| `annihilate_the_armed_red` | Contract to banish attack action cards |
| `annihilate_the_armed_yellow` | Contract to banish attack action cards |
| `annihilate_the_armed_blue` | Contract to banish attack action cards |
| `arakni` | Hero — contract play trigger |
| `arakni_huntsman` | Hero — contract play trigger |
| `coercive_tendency_blue` | Look at top 3 of defending hero's deck |
| `cut_to_the_chase_red` | Contract attack buff + deck peek |
| `cut_to_the_chase_yellow` | Contract attack buff + deck peek |
| `cut_to_the_chase_blue` | Contract attack buff + deck peek |
| `defang_the_dragon_red` | Contract variant |
| `eradicate_yellow` | Contract variant |
| `excessive_bloodloss_red` | Contract synergy |
| `excessive_bloodloss_yellow` | Contract synergy |
| `excessive_bloodloss_blue` | Contract synergy |
| `extinguish_the_flames_red` | Contract variant |
| `fleece_the_frail_red` | Contract to banish defense reactions |
| `fleece_the_frail_yellow` | Contract to banish defense reactions |
| `fleece_the_frail_blue` | Contract to banish defense reactions |
| `hunter_or_hunted_blue` | Contract synergy |
| `leave_no_witnesses_red` | Contract variant |
| `mist_hunter_red` | Contract synergy |
| `nix_the_nimble_red` | Contract to banish instants |
| `nix_the_nimble_yellow` | Contract to banish instants |
| `nix_the_nimble_blue` | Contract to banish instants |
| `pay_day_blue` | Contract reward |
| `plunder_the_poor_red` | Contract to banish resources |
| `plunder_the_poor_yellow` | Contract to banish resources |
| `plunder_the_poor_blue` | Contract to banish resources |
| `rob_the_rich_red` | Contract to banish equipment |
| `rob_the_rich_yellow` | Contract to banish equipment |
| `rob_the_rich_blue` | Contract to banish equipment |
| `sack_the_shifty_red` | Contract variant |
| `sack_the_shifty_yellow` | Contract variant |
| `sack_the_shifty_blue` | Contract variant |
| `slay_the_scholars_red` | Contract variant |
| `slay_the_scholars_yellow` | Contract variant |
| `slay_the_scholars_blue` | Contract variant |
| `surgical_extraction_blue` | Contract synergy |
| `the_hand_that_pulls_the_strings` | Contract synergy |

---

## Transcend (26 cards)

**Description:** Transcend is a Mystic mechanic (primarily Kya/Twelve Petal). When a card with transcend resolves, if a condition is met (usually "played another blue card this turn"), the card transcends — it is put into the hero's soul instead of the graveyard, and the hero transforms or gains a permanent benefit. Requires soul zone tracking and conditional zone redirection.

**Why blocked:** No engine support for the soul zone, transcend state tracking, or conditional graveyard-to-soul redirection.

| Slug | Notes |
|------|-------|
| `a_drop_in_the_ocean_blue` | Legendary, transcend if played another blue |
| `homage_to_ancestors_blue` | Legendary, transcend if played another blue |
| `mistcloak_gully` | Legendary equipment, transcend synergy |
| `moon_chakra_red` | Damage prevention, transcend bonus |
| `moon_chakra_yellow` | Damage prevention, transcend bonus |
| `moon_chakra_blue` | Damage prevention, transcend bonus |
| `pass_over_blue` | Legendary, banish from opponent graveyard + transcend |
| `path_well_traveled_blue` | Legendary, grant go again + transcend |
| `preserve_tradition_blue` | Legendary, graveyard recursion + transcend |
| `rising_sun_setting_moon_blue` | Legendary, draw/bottom + transcend |
| `sacred_art_immortal_lunar_shrine_blue` | Sacred art + transcend |
| `sacred_art_jade_tiger_domain_blue` | Sacred art + transcend |
| `sacred_art_undercurrent_desires_blue` | Sacred art + transcend |
| `second_tenet_of_chi_moon_blue` | Chi tenet + transcend |
| `second_tenet_of_chi_tide_blue` | Chi tenet + transcend |
| `second_tenet_of_chi_wind_blue` | Chi tenet + transcend |
| `serpents_kiss_blue` | Transcend variant |
| `stir_the_pot_blue` | Transcend variant |
| `the_grain_that_tips_the_scale_blue` | Legendary + transcend |
| `tide_chakra_red` | Resource gain + transcend bonus |
| `tide_chakra_yellow` | Resource gain + transcend bonus |
| `tide_chakra_blue` | Resource gain + transcend bonus |
| `twelve_petal_kya` | Hero — transcend core |
| `wind_chakra_red` | Go again + transcend bonus |
| `wind_chakra_yellow` | Go again + transcend bonus |
| `wind_chakra_blue` | Go again + transcend bonus |

---

## Flow (19 cards)

**Description:** Flow is an elemental mechanic where a card gains a bonus if you've played a card of a specific element (Lightning, Ice, Earth) earlier in the same turn. Requires tracking which element types have been played during the current turn.

**Why blocked:** No engine support for per-turn element type tracking or Flow conditional checks.

| Slug | Notes |
|------|-------|
| `channel_galcias_cradle_blue` | Channel with Flow |
| `channel_iceloch_glaze_blue` | Channel with Flow |
| `channel_lake_frigid_blue` | Channel Ice Flow |
| `channel_lightning_valley_yellow` | Channel Lightning Flow |
| `channel_mount_heroic_red` | Channel Earth Flow |
| `channel_mount_isen_blue` | Channel Ice Flow |
| `channel_the_bleak_expanse_blue` | Channel Ice Flow |
| `channel_the_millennium_tree_red` | Channel Earth Flow |
| `channel_the_skybreaker_yellow` | Channel Lightning Flow |
| `channel_the_tranquil_domain_yellow` | Channel Flow |
| `channel_thunder_steppe_yellow` | Channel Lightning Flow |
| `crackling_red` | Lightning Flow — +1 power if Lightning played |
| `crackling_yellow` | Lightning Flow — +1 power if Lightning played |
| `harness_lightning_red` | Lightning Flow synergy |
| `harness_lightning_yellow` | Lightning Flow synergy |
| `photon_rush_red` | Flow synergy |
| `photon_rush_blue` | Flow synergy |
| `static_shock_red` | Lightning Flow synergy |
| `static_shock_yellow` | Lightning Flow synergy |

---

## Negate (12 cards)

**Description:** Negate cancels a card or ability on the stack, preventing it from resolving. Requires a stack/chain system where cards can be countered before resolution.

**Why blocked:** No engine support for stack-based card negation or counter-spell resolution.

| Slug | Notes |
|------|-------|
| `aetherize_blue` | Negate target instant with cost ≤ resource |
| `construct_nitro_mechanoid_yellow` | Negate as part of transform |
| `fabric_of_blossoms_blue` | Equip or negate self |
| `fabric_of_hope_red` | Equip or negate self |
| `fabric_of_providence_red` | Equip or negate self |
| `fabric_of_scales_blue` | Equip or negate self |
| `fabric_of_spring_yellow` | Equip or negate self |
| `null__shock_yellow` | Meld — negate target instant |
| `rewind_blue` | Negate non-attack action, return to hand |
| `semblance_blue` | Negate phantasm effects |
| `temporal_wobble_red` | Negate variant |
| `venomback_fabric_yellow` | Equip or negate self |

---

## Meld (11 cards)

**Description:** Meld cards are two-sided cards (e.g., "Arcane Seeds // Life") that can be played as either half. When played from hand, the controller chooses which side to play. Requires dual-faced card representation and side selection during play.

**Why blocked:** No engine support for dual-faced cards, side selection UI/logic, or split card resolution.

| Slug | Notes |
|------|-------|
| `arcane_seeds__life_red` | Meld — Runechant creation // Gain life |
| `burn_up__shock_red` | Meld — On-hit arcane // Arcane damage |
| `comet_storm__shock_red` | Meld — 5 arcane damage // 1 arcane damage |
| `consign_to_cosmos__shock_yellow` | Meld — Banish from graveyard // Arcane damage |
| `everbloom__life_blue` | Meld — Graveyard recursion // Gain life |
| `null__shock_yellow` | Meld — Negate instant // Arcane damage |
| `pulsing_aether__life_red` | Meld — 4 arcane damage // Gain life |
| `rampant_growth__life_yellow` | Meld — Amp X // Gain life |
| `regrowth__shock_blue` | Meld — Return attack from graveyard // Arcane damage |
| `thistle_bloom__life_yellow` | Meld — Create X Runechants // Gain life |
| `vaporize__shock_yellow` | Meld — Destroy item // Arcane damage |

---

## Material (8 cards)

**Description:** Material is a keyword on cards that go "under" another permanent, granting that permanent additional abilities (e.g., phantasm, +1 power). Requires support for cards being attached underneath other permanents.

**Why blocked:** No engine support for card-under-card attachment or material-granted ability propagation.

| Slug | Notes |
|------|-------|
| `ash` | Material — grants phantasm to parent object |
| `dust_from_stillwater_shrine_red` | Material — grants phantasm (non-Miragai) |
| `dust_from_the_chrome_caverns_red` | Material — grants phantasm (non-Cromai) |
| `dust_from_the_fertile_fields_red` | Material — grants phantasm (non-Ouvia) |
| `dust_from_the_golden_plains_red` | Material — grants phantasm (non-Themai) |
| `dust_from_the_red_desert_red` | Material — grants phantasm (non-Vynserakai) |
| `dust_from_the_shadow_crypts_red` | Material — grants phantasm (non-Nekria) |
| `galvanic_bender` | Material — grants +1 power to parent |

---

## Modular (3 cards)

**Description:** Modular equipment can be moved between equipment zones using an activated ability. Requires support for re-equipping to a different slot without destroying and re-playing.

**Why blocked:** No engine support for equipment zone transfer or dynamic equipment slot reassignment.

| Slug | Notes |
|------|-------|
| `adaptive_alpha_mold` | Modular — move to another equipment zone, Battleworn |
| `adaptive_dissolver` | Modular — move to another equipment zone, Arcane Barrier 1 |
| `adaptive_plating` | Modular — move to another equipment zone, Galvanize |

---

## Figment (3 cards)

**Description:** Figments are a special token type that exist in a dormant state and can be "awakened" to become active permanents. Requires dormant/awake state tracking for tokens.

**Why blocked:** No engine support for dormant token state or awaken mechanic.

| Slug | Notes |
|------|-------|
| `angelic_attendant_yellow` | Awaken target figment |
| `prism_advent_of_thrones` | Hero — figment awakening from soul |
| `prism_awakener_of_sol` | Hero — figment awakening from soul |

---

## Invoke (1 card)

**Description:** Invoke is a Draconic mechanic for summoning dragon allies. The Invoke cards reference specific dragon cards that must be in the deck/sideboard. Overlaps heavily with Transform mechanic.

**Why blocked:** Invoke cards are also listed under Transform. No engine support for ally summoning or sideboard access during gameplay.

| Slug | Notes |
|------|-------|
| `dragons_of_legend` | Lists all invocable dragons with stats |

---

## Summary by Priority

| Priority | Mechanic | Card Count | Complexity |
|----------|----------|------------|------------|
| High | Transform | 69 | High — permanent replacement system |
| High | Clash | 60 | High — reveal/compare/winner system |
| High | Spectra | 64 | Medium — token attack activation |
| Medium | Aim Counter | 50 | Medium — arsenal counter tracking |
| Medium | Contract | 40 | Medium — persistent condition tracking |
| Medium | Transcend | 26 | Medium — soul zone + condition |
| Low | Flow | 19 | Low — per-turn element tracking |
| Low | Negate | 12 | Medium — stack/counter system |
| Low | Meld | 11 | Medium — dual-faced card system |
| Low | Material | 8 | Low — card attachment system |
| Low | Modular | 3 | Low — equipment zone transfer |
| Low | Figment | 3 | Low — dormant token state |
| Low | Invoke | 1 | High — overlaps with Transform |

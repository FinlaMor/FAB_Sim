# DSL semantic audit — 2026-07-20

Model-generated *suspicions*, not verified defects. Each finding is a
clause the auditor could not map to an implementing effect. Confirm
against the card text and the CR before changing anything.

- cards audited: 46
- cards with at least one suspect clause: 9
- cards clean: 37
- audit errors: 0

## Suspect clauses

### Leave No Witnesses (`leave_no_witnesses_red`)

> **Contract** - You are contracted to banish opponents' red cards. Whenever you complete this contract, create a Silver token.  When this hits a hero, banish the top card of their deck and up to 1 card in their arsenal.

- **MISSING** — "You are contracted to banish opponents' red cards"
  - No JSON effect implements the contract objective of banningishing opponents' red cards
- **MISSING** — 'create a Silver token'
  - No JSON effect creates a Silver token

### Arakni, Trap-Door (`arakni_trap_door`)

> When you become this, you may search your deck for a card, banish it face-down, then shuffle. If it's a trap, you may play it until the start of your next turn.  At the beginning of your end phase, **return to the brood**.

- **MISMATCH** — 'you may play it until the start of your next turn'
  - JSON does not implement playing a banished trap card. The effect only bansishes, but does not allow playing.

### Cut from the Same Cloth (`cut_from_the_same_cloth_red`)

> Target opposing hero reveals their hand. If an attack reaction card is revealed this way, **mark** them.  Your next dagger attack this turn gets +4{p}.  **Go again**

- **MISSING** — 'Target opposing hero reveals their hand'
  - No effect in JSON implements hand revealing

### Orb-Weaver Spinneret (`orb_weaver_spinneret_red`)

> Equip a Graphene Chelicera token.  Your next attack with **stealth** this turn gets +3{p}.  **Go again**

- **MISSING** — 'Equip a Graphene Chelicera token'
  - No JSON effect for equipping a token
- **MISSING** — 'Your next attack with'
  - No JSON effect for specifying next attack with stealth

### Pain in the Backside (`pain_in_the_backside_red`)

> When this hits a hero, target dagger you control deals 1 damage to them. If damage is dealt this way, the dagger has hit.  **Go again**

- **MISMATCH** — 'target dagger you control deals 1 damage to them'
  - The JSON deals damage to opponent but doesn't specify targeting a dagger, and doesn't use the correct target type for a dagger
- **MISSING** — 'the dagger has hit'
  - No effect indicating the dagger has hit is present in the JSON

### Stains of the Redback (`stains_of_the_redback_blue`)

> If the defending hero is **marked**, this costs {r} less to play.  Target attack with **stealth** gets +1{p} and **go again**.

- **MISSING** — 'If the defending hero is **marked**, this costs {r} less to play.'
  - The JSON does not implement any cost reduction effect based on the defending hero being marked.

### Stains of the Redback (`stains_of_the_redback_red`)

> If the defending hero is **marked**, this costs {r} less to play.  Target attack with **stealth** gets +3{p} and **go again**.

- **MISSING** — 'If the defending hero is **marked**, this costs {r} less to play.'
  - The JSON does not implement any cost reduction effect based on the defending hero being marked.

### Tarantula Toxin (`tarantula_toxin_red`)

> Choose 1 or both;  * Target dagger attack gets +3{p}. * Target card defending an attack with stealth gets -3{d} this turn.

- **MISSING** — 'Target card defending an attack with stealth gets -3{d} this turn'
  - No effect in JSON for modifying defense of cards with stealth

### Under the Trap-Door (`under_the_trap_door_blue`)

> **Stealth**  **Instant** - Discard this: Banish target trap from your graveyard. If you do, you may play it this turn and if it would be put into the graveyard this turn, instead banish it.

- **MISSING** — 'if it would be put into the graveyard this turn, instead banish it'
  - JSON does not model the graveyard->banish rider effect

## Low confidence — probable clause fragments

The auditor split a conditional and flagged half of it. Kept here
rather than dropped, but check the high-confidence list first.

- `righteous_cleansing_yellow` — MISSING: 'If Righteous Cleansing deals 4 or more d'
- `blacktek_whisperers` — MISSING: 'If you do'
- `leave_no_witnesses_red` — MISSING: 'Whenever you complete this contract'
- `shred_yellow` — MISSING: 'this combat chain'
- `arakni_trap_door` — MISMATCH: "If it's a trap"
- `cut_from_the_same_cloth_red` — MISSING: 'If an attack reaction card is revealed t'
- `hunters_klaive` — MISSING: 'Attack'
- `lair_of_the_spider_red` — MISSING: 'the attacking hero'
- `orb_weaver_spinneret_red` — MISSING: '{p}'
- `pain_in_the_backside_red` — MISSING: 'If damage is dealt this way'
- `pick_up_the_point_red` — MISSING: 'When this attacks'
- `scar_tissue_red` — MISSING: 'Target dagger attack'

## Clean

`nights_embrace_blue`, `boulder_drop_red`, `command_and_conquer_red`, `righteous_cleansing_yellow`, `scowling_flesh_bag`, `blacktek_whisperers`, `crown_of_dominion`, `shred_yellow`, `macho_grande_blue`, `swing_big_red`, `thunder_quake_blue`, `arakni_black_widow`, `arakni_funnel_web`, `arakni_marionette`, `arakni_orb_weaver`, `arakni_redback`, `arakni_tarantula`, `hunters_klaive`, `kiss_of_death_red`, `lair_of_the_spider_red`, `mark_of_the_black_widow_red`, `mask_of_deceit`, `pick_up_the_point_red`, `quickdodge_flexors`, `savor_bloodshed_red`, `scar_tissue_red`, `schism_of_chaos_blue`, `take_up_the_mantle_yellow`, `to_the_point_red`, `up_sticks_and_run_red`, `apex_bonebreaker`, `aurum_aegis`, `millers_grindstone`, `ripple_away_blue`, `test_of_strength_red`, `the_golden_son_yellow`, `thunk_blue`

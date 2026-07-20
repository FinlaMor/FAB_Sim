# DSL semantic audit — 2026-07-20

Model-generated *suspicions*, not verified defects. Each finding is a
clause the auditor could not map to an implementing effect. Confirm
against the card text and the CR before changing anything.

- cards audited: 65
- cards with at least one suspect clause: 17
- cards clean: 48
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

### Victor Goldmane, High and Mighty (`victor_goldmane_high_and_mighty`)

> The first time each turn you create a Gold token from an effect you control, draw a card.  The first time each turn you would fail to win a **clash**, instead you may destroy a Gold you control. If you do, put 1 of the revealed cards on the bottom of its owner's deck, then **clash** again.

- **MISMATCH** — "If you do, put 1 of the revealed cards on the bottom of its owner's deck, then clash again."
  - The JSON replacement effect handles the 'may destroy a Gold' and 'clash again' parts but does not explicitly implement putting 1 revealed card on bottom of owner's deck. This is a semantic difference from the printed text.

### 10,000 Year Reunion (`10000_year_reunion_red`)

> You may remove three +1{p} counters from among auras you control rather than pay 10,000 Year Reunion's {r} cost.  **Ward 10**

- **MISSING** — "You may remove three +1{p} counters from among auras you control rather than pay 10,000 Year Reunion's {r} cost"
  - JSON does not implement the conditional cost reduction mechanism involving removing counters from auras

### Art of Desire: Body (`art_of_desire_body_red`)

> **Stealth**  When this hits a hero, banish the top card of their deck.  Whenever this banishes a red card, draw a card and gain 1{h}.

- **MISMATCH** — 'Whenever this banishes a red card, draw a card and gain 1{h}'
  - The JSON only implements the DRAW effect but does not specify that it only occurs when a red card is banished. The gain 1{h} part is completely missing.

### Death Touch (`death_touch_red`)

> Death Touch can't be played from hand.  When this hits a hero, create a Frailty, Inertia, or Bloodrot Pox token under their control.

- **MISSING** — "Death Touch can't be played from hand"
  - The JSON does not contain any restriction preventing the card from being played from hand
- **MISMATCH** — 'When this hits a hero, create a Frailty, Inertia, or Bloodrot Pox token under their control'
  - The JSON only creates a Frailty token, but the printed text requires choosing between Frailty, Inertia, or Bloodrot Pox tokens

### Inertia Trap (`inertia_trap_red`)

> When this defends an attack with {p} greater than its base, create an Inertia token under the attacking hero's control.

- **MISMATCH** — "When this defends an attack with {p} greater than its base, create an Inertia token under the attacking hero's control."
  - The printed text requires a condition that {p} (power) is greater than the base, but the JSON implementation lacks this conditional check. The JSON unconditionally creates a token, while the text implies the creation is dependent on the power being greater than base.

### Infiltrate (`infiltrate_red`)

> **Stealth**  When this hits a hero, banish the top card of their deck. You may play it until the end of your next turn.

- **MISSING** — 'You may play it until the end of your next turn'
  - JSON does not implement the optional playing mechanic or duration restriction

### Spreading Plague (`spreading_plague_yellow`)

> Create X Bloodrot Pox tokens under the defending hero's control, where X is the number of defending cards this chain link.

- **MISMATCH** — "Create X Bloodrot Pox tokens under the defending hero's control, where X is the number of defending cards this chain link."
  - JSON creates only 1 token regardless of the number of defending cards, while the text specifies creating X tokens where X equals the number of defending cards.

### Chain of Brutality (`chain_of_brutality_red`)

> If this has 6 or more {p}, it gets **go again** and "When this hits a hero, the next attack action card you play this turn has 6 base {p}."

- **MISSING** — 'If this has 6 or more {p}, it gets **go again** and "When this hits a hero, the next attack action card you play this turn has 6 base {p}."'
  - The condition 'If this has 6 or more {p}' and the effects 'it gets go again' and 'the next attack action card you play this turn has 6 base {p}' are not implemented in the JSON.

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
- `vigorous_windup_blue` — MISSING: 'Discard this'

## Clean

`nights_embrace_blue`, `boulder_drop_red`, `command_and_conquer_red`, `righteous_cleansing_yellow`, `scowling_flesh_bag`, `blacktek_whisperers`, `crown_of_dominion`, `shred_yellow`, `macho_grande_blue`, `swing_big_red`, `thunder_quake_blue`, `arakni_black_widow`, `arakni_funnel_web`, `arakni_marionette`, `arakni_orb_weaver`, `arakni_redback`, `arakni_tarantula`, `hunters_klaive`, `kiss_of_death_red`, `lair_of_the_spider_red`, `mark_of_the_black_widow_red`, `mask_of_deceit`, `pick_up_the_point_red`, `quickdodge_flexors`, `savor_bloodshed_red`, `scar_tissue_red`, `schism_of_chaos_blue`, `take_up_the_mantle_yellow`, `to_the_point_red`, `up_sticks_and_run_red`, `apex_bonebreaker`, `aurum_aegis`, `millers_grindstone`, `ripple_away_blue`, `test_of_strength_red`, `the_golden_son_yellow`, `thunk_blue`, `trounce_red`, `vigorous_windup_blue`, `headbutt_blue`, `test_of_iron_grip_red`, `visit_goldmane_estate_blue`, `codex_of_frailty_yellow`, `codex_of_inertia_yellow`, `flick_knives`, `frailty_trap_red`, `looking_for_a_scrap_red`, `insult_to_injury_blue`

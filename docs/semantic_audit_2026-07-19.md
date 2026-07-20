# DSL semantic audit — 2026-07-19

Model-generated *suspicions*, not verified defects. Each finding is a
clause the auditor could not map to an implementing effect. Confirm
against the card text and the CR before changing anything.

- cards audited: 40
- cards with at least one suspect clause: 14
- cards clean: 25
- audit errors: 1

## Suspect clauses

### Boulder Drop (`boulder_drop_red`)

> **Crush** - When this deals 4 or more damage to a hero, they put a card from their hand on top of their deck.

- **MISMATCH** — 'When this deals 4 or more damage to a hero, they put a card from their hand on top of their deck.'
  - The JSON puts the card at the bottom of the deck instead of on top.

### Scowling Flesh Bag (`scowling_flesh_bag`)

> When this defends, **intimidate**.  **Blade Break**

- **MISSING** — '**Blade Break**'
  - The JSON does not implement the Blade Break keyword.

### Leave No Witnesses (`leave_no_witnesses_red`)

> **Contract** - You are contracted to banish opponents' red cards. Whenever you complete this contract, create a Silver token.  When this hits a hero, banish the top card of their deck and up to 1 card in their arsenal.

- **MISSING** — "Contract - You are contracted to banish opponents' red cards."
  - The JSON does not implement the contract or its effect of banishing opponents' red cards.
- **MISSING** — 'Whenever you complete this contract, create a Silver token.'
  - The JSON does not implement creating a Silver token upon completing the contract.

### Arakni, Trap-Door (`arakni_trap_door`)

> When you become this, you may search your deck for a card, banish it face-down, then shuffle. If it's a trap, you may play it until the start of your next turn.  At the beginning of your end phase, **return to the brood**.

- **MISSING** — "If it's a trap, you may play it until the start of your next turn."
  - The JSON does not implement the conditional playing of a trap card.

### Cut from the Same Cloth (`cut_from_the_same_cloth_red`)

> Target opposing hero reveals their hand. If an attack reaction card is revealed this way, **mark** them.  Your next dagger attack this turn gets +4{p}.  **Go again**

- **MISSING** — 'Target opposing hero reveals their hand.'
  - The JSON does not include an effect for the target revealing their hand.
- **MISSING** — 'If an attack reaction card is revealed this way, mark them.'
  - The JSON does not include a condition to check for attack reaction cards or marking the hero.

### Hunter's Klaive (`hunters_klaive`)

> **Once per Turn Action** - {r}{r}: **Attack**. **Go again**  When this hits a hero, **mark** them.  **Piercing 1**

- **MISSING** — 'Piercing 1'
  - JSON does not specify Piercing effect

### Orb-Weaver Spinneret (`orb_weaver_spinneret_red`)

> Equip a Graphene Chelicera token.  Your next attack with **stealth** this turn gets +3{p}.  **Go again**

- **MISSING** — 'Equip a Graphene Chelicera token.'
  - The JSON does not implement the equipping of a token.
- **MISMATCH** — 'Your next attack with **stealth** this turn gets +3{p}.'
  - The JSON adds +3 to any next attack, not specifically to an attack with stealth.

### Pain in the Backside (`pain_in_the_backside_red`)

> When this hits a hero, target dagger you control deals 1 damage to them. If damage is dealt this way, the dagger has hit.  **Go again**

- **MISSING** — 'If damage is dealt this way, the dagger has hit'
  - The JSON does not track or indicate if the dagger has hit.

### Stains of the Redback (`stains_of_the_redback_blue`)

> If the defending hero is **marked**, this costs {r} less to play.  Target attack with **stealth** gets +1{p} and **go again**.

- **MISSING** — 'If the defending hero is marked, this costs {r} less to play.'
  - The JSON does not implement any cost reduction based on the defending hero being marked.

### Stains of the Redback (`stains_of_the_redback_red`)

> If the defending hero is **marked**, this costs {r} less to play.  Target attack with **stealth** gets +3{p} and **go again**.

- **MISSING** — 'If the defending hero is marked, this costs {r} less to play.'
  - The JSON does not implement any cost reduction based on the defending hero being marked.

### Take Up the Mantle (`take_up_the_mantle_yellow`)

> Target attack action card with **stealth** gets +2{p}. If it's attacking a **marked** hero, instead it gets +3{p} and you may banish an attack action card with **stealth** from your graveyard. If you do, the target becomes a copy of the banished card.

- **MISMATCH** — 'and you may banish an attack action card with **stealth** from your graveyard.'
  - The JSON allows copying the banished stealth attack instead of just banishing it.
- **MISMATCH** — 'If you do, the target becomes a copy of the banished card.'
  - The JSON allows copying the banished stealth attack instead of just making the target a copy.

### Tarantula Toxin (`tarantula_toxin_red`)

> Choose 1 or both;  * Target dagger attack gets +3{p}. * Target card defending an attack with stealth gets -3{d} this turn.

- **MISSING** — 'Target card defending an attack with stealth gets -3{d} this turn.'
  - The JSON does not implement the effect for a card defending an attack with stealth.

### To the Point (`to_the_point_red`)

> Target dagger attack gets +3{p}. If the defending hero is **marked**, instead it gets +4{p}.

- **MISMATCH** — 'If the defending hero is **marked**, instead it gets +4{p}.'
  - The text specifies +4{p} when marked, but JSON adds only +1{p}.

### Under the Trap-Door (`under_the_trap_door_blue`)

> **Stealth**  **Instant** - Discard this: Banish target trap from your graveyard. If you do, you may play it this turn and if it would be put into the graveyard this turn, instead banish it.

- **MISSING** — 'If it would be put into the graveyard this turn, instead banish it.'
  - The JSON does not implement the part about banishing the trap if it would go to the graveyard.

## Audit errors

- `up_sticks_and_run_red`: unparseable model output: Expecting property name enclosed in double quotes: line 16 column 7 (char 432)

## Clean

`nights_embrace_blue`, `command_and_conquer_red`, `righteous_cleansing_yellow`, `blacktek_whisperers`, `crown_of_dominion`, `shred_yellow`, `macho_grande_blue`, `swing_big_red`, `thunder_quake_blue`, `arakni_black_widow`, `arakni_funnel_web`, `arakni_marionette`, `arakni_orb_weaver`, `arakni_redback`, `arakni_tarantula`, `kiss_of_death_red`, `lair_of_the_spider_red`, `mark_of_the_black_widow_red`, `mask_of_deceit`, `pick_up_the_point_red`, `quickdodge_flexors`, `savor_bloodshed_red`, `scar_tissue_red`, `schism_of_chaos_blue`, `apex_bonebreaker`

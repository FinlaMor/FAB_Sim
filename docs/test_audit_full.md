# DSL semantic audit — 2026-07-21

Model-generated *suspicions*, not verified defects. Each finding is a
clause the auditor could not map to an implementing effect. Confirm
against the card text and the CR before changing anything.

- cards audited: 107
- cards with at least one suspect clause: 55
- cards clean: 52
- audit errors: 0

## Suspect clauses

### Night's Embrace (`nights_embrace_blue`)

> Your attacks with stealth get +1{p} this turn.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Boulder Drop (`boulder_drop_red`)

> **Crush** - When this deals 4 or more damage to a hero, they put a card from their hand on top of their deck.

- **MISSING** — 'Crush - When this deals 4 or more damage to a hero'
  - No test asserts that Boulder Drop deals at least 4 damage to a hero.

### Command and Conquer (`command_and_conquer_red`)

> Defense reaction cards can't be played this chain link. When this hits a hero, destroy all cards in their arsenal.

- **MISSING** — "Defense reaction cards can't be played this chain link."
  - No test checks that defense reaction cards are not playable in the same chain link.

### Crown of Dominion (`crown_of_dominion`)

> Your hero is Royal.  When you equip Crown of Dominion, create a Gold token.

- **MISSING** — 'Your hero is Royal.'
  - No test asserts that the hero gains the 'Royal' status.

### Leave No Witnesses (`leave_no_witnesses_red`)

> **Contract** - You are contracted to banish opponents' red cards. Whenever you complete this contract, create a Silver token.  When this hits a hero, banish the top card of their deck and up to 1 card in their arsenal.

- **MISSING** — "You are contracted to banish opponents' red cards."
  - No test checks if the card bansishes opponents' red cards.
- **MISSING** — 'Whenever you complete this contract, create a Silver token.'
  - No test checks if a Silver token is created upon completing the contract.

### Shred (`shred_yellow`)

> Target card defending an Assassin attack gets -3{d} this combat chain.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Macho Grande (`macho_grande_blue`)

> **Dominate**

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Thunder Quake (`thunder_quake_blue`)

> **Heave 3**

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Arakni, Black Widow (`arakni_black_widow`)

> **Once per Turn Attack Reaction** - Discard an Assassin card: Target Assassin attack gets +3{p}. If it has **stealth**, it gets "When this hits a hero, they banish a card from their hand."  At the beginning of your end phase, **return to the brood**.

- **MISSING** — 'At the beginning of your end phase, return to the brood.'
  - No test checks the effect at the end of the turn.

### Arakni, Funnel Web (`arakni_funnel_web`)

> **Once per Turn Attack Reaction** - Discard an Assassin card: Target Assassin attack gets +3{p}. If it has **stealth**, it gets "When this hits a hero, banish a card in their arsenal."  At the beginning of your end phase, **return to the brood**.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Arakni, Orb-Weaver (`arakni_orb_weaver`)

> Graphene Chelicerae cost you {r} less to activate.  **Once per Turn Instant** - Discard an Assassin card: Equip a Graphene Chelicera token. Your next attack with **stealth** this turn gets +3{p}.  At the beginning of your end phase, **return to the brood**.

- **MISSING** — 'Once per Turn Instant - Discard an Assassin card: Equip a Graphene Chelicera token.'
  - No test checks if the token is equipped correctly.
- **MISSING** — 'Your next attack with stealth this turn gets +3{p}.'
  - No test checks the power modification for a stealth attack.
- **MISSING** — 'At the beginning of your end phase, return to the brood.'
  - No test checks if the hero returns to the brood at the end of the turn.

### Arakni, Redback (`arakni_redback`)

> **Once per Turn Attack Reaction** - Discard an Assassin card: Target Assassin attack gets +3{p}. If it has **stealth**, it gets **go again**.  At the beginning of your end phase, **return to the brood**.

- **MISSING** — 'Once per Turn Attack Reaction'
  - No test checks the 'once per turn' restriction.
- **MISSING** — 'Target Assassin attack gets +3{p}'
  - No test checks the attack power modification.

### Arakni, Tarantula (`arakni_tarantula`)

> Whenever a dagger you own hits a hero, they lose 1{h}.  **Once per Turn Attack Reaction** - Discard an Assassin card: Target dagger attack gets +3{p}.  At the beginning of your end phase, **return to the brood**.

- **MISSING** — 'At the beginning of your end phase, **return to the brood**.'
  - No test covers the transformation at the end of turn.

### Arakni, Trap-Door (`arakni_trap_door`)

> When you become this, you may search your deck for a card, banish it face-down, then shuffle. If it's a trap, you may play it until the start of your next turn.  At the beginning of your end phase, **return to the brood**.

- **MISSING** — 'When you become this, you may search your deck for a card, banish it face-down, then shuffle.'
  - No test asserts that the player can choose not to perform the action.
- **MISSING** — 'At the beginning of your end phase, return to the brood.'
  - No test asserts that the card returns to the brood at the beginning of the end phase.

### Cut from the Same Cloth (`cut_from_the_same_cloth_red`)

> Target opposing hero reveals their hand. If an attack reaction card is revealed this way, **mark** them.  Your next dagger attack this turn gets +4{p}.  **Go again**

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Hunter's Klaive (`hunters_klaive`)

> **Once per Turn Action** - {r}{r}: **Attack**. **Go again**  When this hits a hero, **mark** them.  **Piercing 1**

- **MISSING** — 'When this hits a hero, mark them.'
  - No test asserts the marking of a hero.

### Kiss of Death (`kiss_of_death_red`)

> **Stealth**  When this hits a hero, they lose 1{h}.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Lair of the Spider (`lair_of_the_spider_red`)

> When this defends an attack with **go again**, **mark** the attacking hero.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Mark of the Black Widow (`mark_of_the_black_widow_red`)

> **Stealth**  When this hits a **marked** hero, they banish a card from their hand.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Orb-Weaver Spinneret (`orb_weaver_spinneret_red`)

> Equip a Graphene Chelicera token.  Your next attack with **stealth** this turn gets +3{p}.  **Go again**

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Pain in the Backside (`pain_in_the_backside_red`)

> When this hits a hero, target dagger you control deals 1 damage to them. If damage is dealt this way, the dagger has hit.  **Go again**

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Pick Up the Point (`pick_up_the_point_red`)

> When this attacks, you may **retrieve** a dagger from your graveyard.  **Go again**

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Savor Bloodshed (`savor_bloodshed_red`)

> Your next dagger attack this turn gets +4{p}.  The next time you hit a **marked** hero with a dagger this turn, draw a card.  **Go again**

- **MISSING** — 'Your next dagger attack this turn gets +4{p}.'
  - No test asserts an observable outcome for the attack power increase.

### Scar Tissue (`scar_tissue_red`)

> Target dagger attack gets +3{p} and "When this hits a hero, **mark** them."

- **MISSING** — 'Target dagger attack gets +3{p}'
  - No test asserts the attack power modification.
- **MISSING** — 'When this hits a hero, **mark** them.'
  - No test asserts that the target hero is marked.

### Stains of the Redback (`stains_of_the_redback_blue`)

> If the defending hero is **marked**, this costs {r} less to play.  Target attack with **stealth** gets +1{p} and **go again**.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Stains of the Redback (`stains_of_the_redback_red`)

> If the defending hero is **marked**, this costs {r} less to play.  Target attack with **stealth** gets +3{p} and **go again**.

- **MISSING** — 'If the defending hero is marked, this costs {r} less to play.'
  - No test covers the cost reduction when the defending hero is marked.

### Take Up the Mantle (`take_up_the_mantle_yellow`)

> Target attack action card with **stealth** gets +2{p}. If it's attacking a **marked** hero, instead it gets +3{p} and you may banish an attack action card with **stealth** from your graveyard. If you do, the target becomes a copy of the banished card.

- **MISSING** — 'Target attack action card with stealth gets +2{p}.'
  - No test asserts the attack power increase of +2 for a stealth attack.

### Tarantula Toxin (`tarantula_toxin_red`)

> Choose 1 or both;  * Target dagger attack gets +3{p}. * Target card defending an attack with stealth gets -3{d} this turn.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### To the Point (`to_the_point_red`)

> Target dagger attack gets +3{p}. If the defending hero is **marked**, instead it gets +4{p}.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Up Sticks and Run (`up_sticks_and_run_red`)

> You may **retrieve** a dagger from your graveyard.  Your next dagger attack this turn gets +4{p}.  **Go again**

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Ripple Away (`ripple_away_blue`)

> **Instant** - Discard this: If an action card effect would create 1 or more tokens this turn, instead it creates that many minus 1 of each of those tokens.

- **MISSING** — 'Instant - Discard this'
  - No test checks if the card is discarded when activated.

### The Golden Son (`the_golden_son_yellow`)

> **Victor Specialization**  As an additional cost to play this, you may destroy a Gold you control. If you do, this gets +3{p} and **overpower**.  When you win a **clash** revealing this, create a Gold token.

- **MISSING** — 'As an additional cost to play this, you may destroy a Gold you control.'
  - No test covers the option of not destroying a Gold.
- **MISSING** — 'If you do, this gets +3{p} and **overpower**.'
  - No test checks if the card gains +3 power or overpower when a Gold is destroyed.

### Trounce (`trounce_red`)

> When this defends, **clash** with the attacking hero. Put the revealed cards on the bottom of their owner's deck, then **clash** again.  If a hero wins both **clashes**, they create a Gold, Might, and Vigor token.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Vigorous Windup (`vigorous_windup_blue`)

> **Instant** - Discard this: Create a Vigor token.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### 10,000 Year Reunion (`10000_year_reunion_red`)

> You may remove three +1{p} counters from among auras you control rather than pay 10,000 Year Reunion's {r} cost.  **Ward 10**

- **MISSING** — "You may remove three +1{p} counters from among auras you control rather than pay 10,000 Year Reunion's {r} cost."
  - No test covers the ability to remove +1{p} counters instead of paying the cost.

### Death Touch (`death_touch_red`)

> Death Touch can't be played from hand.  When this hits a hero, create a Frailty, Inertia, or Bloodrot Pox token under their control.

- **MISSING** — "Death Touch can't be played from hand."
  - No test asserts that Death Touch cannot be played from hand.

### Frailty Trap (`frailty_trap_red`)

> When this defends an attack with **go again**, create a Frailty token under the attacking hero's control.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Inertia Trap (`inertia_trap_red`)

> When this defends an attack with {p} greater than its base, create an Inertia token under the attacking hero's control.

- **MISSING** — "create an Inertia token under the attacking hero's control."
  - No test checks if the created token is under the attacking hero's control.

### Infiltrate (`infiltrate_red`)

> **Stealth**  When this hits a hero, banish the top card of their deck. You may play it until the end of your next turn.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Looking for a Scrap (`looking_for_a_scrap_red`)

> As an additional cost to play Looking for a Scrap, you may banish a card with 1{p} from your graveyard. When you do, this gains +1{p} and **go again**.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Spreading Plague (`spreading_plague_yellow`)

> Create X Bloodrot Pox tokens under the defending hero's control, where X is the number of defending cards this chain link.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Chain of Brutality (`chain_of_brutality_red`)

> If this has 6 or more {p}, it gets **go again** and "When this hits a hero, the next attack action card you play this turn has 6 base {p}."

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Insult to Injury (`insult_to_injury_blue`)

> When this attacks a hero, if you have more {h} than them, this gets **go again**.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Reckless Arithmetic (`reckless_arithmetic_blue`)

> When this attacks, roll a 6 sided die. This gets +X{p}, where X is the number rolled.

- **MISSING** — 'When this attacks, roll a 6 sided die.'
  - No test directly asserts that a 6-sided die is rolled.

### Nimby (`nimby_blue`)

> When this attacks, you may search your deck for a Nimblism, reveal it, put it into your hand, then shuffle.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Booze! (`booze_blue`)

> **Go again**  When this enters or leaves the arena, **the crowd boos** you.  At the start of your turn, destroy this.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Mocking Blow (`mocking_blow_blue`)

> When this attacks a hero, if you have more {h} than them, **the crowd boos** you.  If you've been booed this turn, this gets +2{p}.

- **MISSING** — 'When this attacks a hero, if you have more {h} than them, the crowd boos you.'
  - No test checks if the crowd boos when attacking a hero with more health.
- **MISSING** — "If you've been booed this turn, this gets +2{p}."
  - No test checks if the card gains +2 power after being booed.

### Mocking Blow (`mocking_blow_red`)

> When this attacks a hero, if you have more {h} than them, **the crowd boos** you.  If you've been booed this turn, this gets +4{p}.

- **MISSING** — 'When this attacks a hero, if you have more {h} than them, the crowd boos you.'
  - No test checks if the crowd actually boos when attacking a hero with more health.
- **MISSING** — "If you've been booed this turn, this gets +4{p}."
  - No test checks if the card's power increases by 4 after being booed.

### Mocking Blow (`mocking_blow_yellow`)

> When this attacks a hero, if you have more {h} than them, **the crowd boos** you.  If you've been booed this turn, this gets +3{p}.

- **MISSING** — 'When this attacks a hero, if you have more {h} than them, the crowd boos you.'
  - No test checks if the crowd boos when attacking a hero with more health.
- **MISSING** — "If you've been booed this turn, this gets +3{p}."
  - No test checks if the card gains +3 power after being booed.

### Offensive Behavior (`offensive_behavior_blue`)

> If you control a Might or Vigor token, this gets +1{p}.  When this hits a hero, create a Might and a Vigor token.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Overcrowded (`overcrowded_blue`)

> **Ambush**  When this attacks or defends, it gets +1{p} +1{d} for each different name among aura tokens in the arena.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Right Behind You (`right_behind_you_blue`)

> When this defends together with another card from hand, this gets +1{d} and you may look at the top card of your deck. You may put it on the bottom.

- **MISSING** — 'you may look at the top card of your deck'
  - No assertion checks if the player can look at the top card of their deck.
- **MISSING** — 'you may put it on the bottom'
  - No assertion checks if the player can put the top card of their deck on the bottom.

### Steal Victory (`steal_victory_blue`)

> When this defends, **steal** an aura token the attacking hero controls.

- **MISSING** — 'This card has no automated test referencing its slug.'
  - no test references this card's slug

### Alpha Rampage (`alpha_rampage_red`)

> **Rhinar Specialization**  As an additional cost to play Alpha Rampage, discard a random card.  When you attack with Alpha Rampage, **intimidate**.

- **MISSING** — 'As an additional cost to play Alpha Rampage, discard a random card.'
  - No test asserts that a random card is discarded when playing the card.

### Enlightened Strike (`enlightened_strike_red`)

> As an additional cost to play Enlightened Strike, put a card from your hand on the bottom of your deck.  Choose 1; - When you attack with Enlightened Strike, draw a card. - Enlightened Strike gains +2{p}. - Enlightened Strike gains **go again**.

- **MISSING** — 'When you attack with Enlightened Strike, draw a card.'
  - No test covers drawing a card when attacking with Enlightened Strike.

## Low confidence — probable clause fragments

The auditor split a conditional and flagged half of it. Kept here
rather than dropped, but check the high-confidence list first.

- `righteous_cleansing_yellow` — MISSING: 'If Righteous Cleansing deals 4 or more d'
- `thunk_blue` — MISSING: 'When you win a clash revealing this'
- `inertia_trap_red` — MISSING: 'When this defends an attack with {p} gre'
- `cranial_crush_blue` — MISSING: 'When this deals 4 or more damage to a he'
- `disable_blue` — MISSING: 'When this deals 4 or more damage to a he'
- `spinal_crush_red` — MISSING: 'If Spinal Crush deals 4 or more damage t'

## Clean

`righteous_cleansing_yellow`, `scowling_flesh_bag`, `blacktek_whisperers`, `swing_big_red`, `arakni_marionette`, `mask_of_deceit`, `quickdodge_flexors`, `schism_of_chaos_blue`, `under_the_trap_door_blue`, `apex_bonebreaker`, `aurum_aegis`, `millers_grindstone`, `test_of_strength_red`, `thunk_blue`, `victor_goldmane_high_and_mighty`, `headbutt_blue`, `test_of_iron_grip_red`, `art_of_desire_body_red`, `visit_goldmane_estate_blue`, `codex_of_frailty_yellow`, `codex_of_inertia_yellow`, `flick_knives`, `savage_claw`, `snarky_prick_red`, `riches_of_tropal_dhani_yellow`, `big_bully_red`, `ironfist_revelation`, `kayo_underhanded_cheat`, `outside_interference_blue`, `show_of_strength_red`, `ancestral_empowerment_red`, `anothos`, `awakening_bellow_blue`, `awakening_bellow_red`, `awakening_bellow_yellow`, `barkbone_strapping`, `cranial_crush_blue`, `debilitate_blue`, `debilitate_red`, `debilitate_yellow`, `disable_blue`, `disable_red`, `disable_yellow`, `fyendals_spring_tunic`, `nimblism_blue`, `nimblism_red`, `nimblism_yellow`, `pummel_red`, `scabskin_leathers`, `sigil_of_solace_red`, `sink_below_red`, `spinal_crush_red`

# Semantic audit (candidate batch) — qwen3-coder:30b — 2026-08-10
Auditor model: `qwen3-coder:30b` (30B-A3B MoE) via Ollama. Suspicions, not verified defects.
**42% of the 40-card sample (17 cards) had at least one suspect clause** — a
measure of how much of the qwen-authored candidate corpus is wrong-but-plausible
(loads + passes its generated test, yet mis-implements a clause). The model
independently re-found bugs also caught by a hand audit (spreading_flames_red,
talisman_of_featherfoot_yellow, civic_duty, put_em_in_their_place_red,
brand_with_cinderclaw_blue) and marked the just-fixed emeritus_scolding_yellow
CLEAN.
- audited: 40 candidates
- with suspect clauses: 17

### Tripwire Trap (`tripwire_trap_red`)
> Tripwire Trap can only be played from arsenal.

When this defends, effects don't trigger when an attack hits this chain link unless the attacking hero pays {r}.
- **MISSING** — Tripwire Trap can only be played from arsenal.  
  The JSON does not specify that the card can only be played from arsenal.

### Spreading Flames (`spreading_flames_red`)
> Draconic attacks you control have +1{p} while their base {p} is less than the number of Draconic chain links you control.

**Go again**
- **MISMATCH** — Draconic attacks you control have +1{p} while their base {p} is less than the number of Draconic chain links you control.  
  JSON applies a flat +1 power modifier regardless of base power or number of chain links; printed text requires conditional modification based on base power vs. chain link count.

### Mage Master Boots (`mage_master_boots`)
> **Action** - {r}, destroy this: The next non-attack action card you play this turn gets **go again**. **Go again**
- **MISMATCH** — the next non-attack action card you play this turn gets **go again**  
  JSON sets a flag but does not implement the effect of giving 'go again' to the next non-attack action card played. The engine must handle this logic.

### Doomsaying (`doomsaying_red`)
> **Go again**

At the beginning of your end phase, put a doom counter on this, then each hero destroys X auras they control, where X is the number of doom counters on this.
- **MISMATCH** — then each hero destroys X auras they control, where X is the number of doom counters on this  
  JSON uses 'amount': 'doom' which does not correctly implement the rule that X equals the number of doom counters; it should dynamically calculate X based on current doom counter count, but JSON effect does not support dynamic calculation.

### Talisman of Featherfoot (`talisman_of_featherfoot_yellow`)
> **Go again**

When an attack you control gains exactly +1{p} from an effect during the reaction step, destroy Talisman of Featherfoot and the attack gains **go again**.
- **MISMATCH** — When an attack you control gains exactly +1{p} from an effect during the reaction step, destroy Talisman of Featherfoot  
  The JSON destroys the talisman when the attack is modified by +1, but does not check that the modification came from an effect during the reaction step.
- **MISMATCH** — and the attack gains **go again**  
  The JSON applies 'GO_AGAIN' keyword, but does not ensure that this happens only when the attack gained exactly +1{p} from an effect during the reaction step.

### Fire in the Hole (`fire_in_the_hole_red`)
> Your next arrow attack this turn gets +3{p}.

You may {u} a bow you control.

**Go again**
- **MISSING** — You may {u} a bow you control.  
  The JSON does not include any effect for unsummoning a bow.

### Blessing of Occult (`blessing_of_occult_yellow`)
> At the start of your turn, destroy Blessing of Occult then create 2 Runechant tokens.
- **MISMATCH** — At the start of your turn, destroy Blessing of Occult then create 2 Runechant tokens  
  The printed text says to destroy the card itself, but the JSON does not include a destroy effect; it only creates tokens.

### Civic Duty (`civic_duty`)
> Whenever this defends, create a Vigor token under another hero's control.

**Temper**
- **MISMATCH** — Whenever this defends, create a Vigor token under another hero's control.  
  JSON does not specify that the token is created under another hero's control, only that it is created.

### Rejuvenate (`rejuvenate_blue`)
> Gain 1{h}

If you've **fused** this turn, you may play Rejuvenate as though it were an instant.
- **MISSING** — If you've fused this turn, you may play Rejuvenate as though it were an instant  
  This is a play-timing permission that allows playing the card as an instant if fused this turn. The JSON omits this condition entirely.

### Stony Woottonhog (`stony_woottonhog_red`)
> While Stony Woottonhog is defended by less than 2 non-equipment cards, it has +1{p}.
- **MISMATCH** — While Stony Woottonhog is defended by less than 2 non-equipment cards, it has +1{p}  
  The JSON condition checks for DEFENDER_USED_HAND_CARD with amount 2 and equipment false, which does not correctly implement 'defended by less than 2 non-equipment cards'. The logic is inverted and does not match the printed text.

### Tome of the Arknight (`tome_of_the_arknight_blue`)
> Reveal the top 2 cards of your deck. If you reveal an attack action card and a non-attack action card this way, put them into your hand.

**Go again**
- **MISMATCH** — If you reveal an attack action card and a non-attack action card this way, put them into your hand.  
  The JSON uses SEARCH_DECK with conditions that require both card types to be revealed, but the effect puts the revealed cards into hand only if both conditions are met. However, the JSON's RETURN_TO_HAND targets REVEALED, which is correct, but the logic of putting them into hand is not fully aligned with the printed text's conditional phrasing.

### Grind Them Down (`grind_them_down_blue`)
> **Crush** - When this deals 4 or more damage to a hero, destroy the top card of their deck.
- **MISMATCH** — Crush - When this deals 4 or more damage to a hero, destroy the top card of their deck.  
  The JSON uses DID_NOT_HIT condition which is opposite to the printed text requiring 4 or more damage.

### Put 'Em In Their Place (`put_em_in_their_place_red`)
> **Valda Specialization**

**Crush** - When this deals 4 or more damage to a hero, they discard their hand, then they draw that many cards.
- **MISMATCH** — Crush - When this deals 4 or more damage to a hero, they discard their hand, then they draw that many cards.  
  The JSON implements ON_CRUSH but does not specify the condition of dealing 4 or more damage, and uses 'hand_size' which is not equivalent to 'that many cards' as specified in the text.

### Creep (`creep_red`)
> **Stealth**

When this attacks, the next attack with stealth you play this combat chain gets **go again**.
- **MISMATCH** — When this attacks, the next attack with stealth you play this combat chain gets **go again**.  
  JSON sets a flag but does not implement the mechanic of granting 'go again' to the next stealth attack. The engine must handle the 'go again' logic based on the flag, which is not present in the JSON.

### Brand with Cinderclaw (`brand_with_cinderclaw_blue`)
> Your next attack this combat chain is Draconic in addition to its other card types.

**Go again**
- **MISSING** — Your next attack this combat chain is Draconic in addition to its other card types.  
  The JSON does not implement the effect of making the next attack draconic.

### Pour the Mold (`pour_the_mold_blue`)
> Put a Mechanologist item with cost 0 from your hand into the arena.

If you have **boosted** this turn, put a steam counter on it.

**Go again**
- **MISSING** — Put a Mechanologist item with cost 0 from your hand into the arena.  
  The JSON uses PUT_CARDS_BOTTOM but does not specify that the card must be a Mechanologist item with cost 0.

### Gallow, End of the Line (`gallow_end_of_the_line_yellow`)
> **Action** - {r}, {t}: **Attack**

**Instant** - {t}, discard a card with watery grave: Until end of turn, effects controlled by opponents don't trigger when their attacks hit.

**Watery Grave**
- **MISMATCH** — Instant - {t}, discard a card with watery grave: Until end of turn, effects controlled by opponents don't trigger when their attacks hit.  
  The JSON sets a flag 'WATERY_GRAVE_ACTIVE' but does not implement the actual effect of preventing opponent effects from triggering when their attacks hit. This is a semantic difference.

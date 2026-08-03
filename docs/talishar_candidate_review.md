# Talishar candidate cross-check (789 candidates)

Second opinion from the local Talishar backend; not authoritative.

## Flag summary

- **looks-aligned**: 598
- **no-talishar-logic**: 180
- **keyword-only**: 8
- **persistent-combat-effect/verify-scope**: 3

## Candidates (divergences first)

### crouching_tiger  — keyword-only
text: '**Ephemeral**\n\n**Go again**'
```json
{
  "slug": "crouching_tiger",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CurrentEffectNameModifier()
$name = $effectParameter;
      break;
// DYNCombatEffectActive()
case "crouching_tiger": return true;
```

### this_rounds_on_me_blue  — persistent-combat-effect/verify-scope
text: 'Each hero draws a card.\n\nUntil the start of your next turn, attacks that target you have -1{p}.\n\n**Go again**'
```json
{
  "slug": "this_rounds_on_me_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DRAW",
          "amount": 1,
          "conditions": [
            {
              "type": "IS_ACTIVE_PLAYER"
            }
          ]
        },
        {
          "type": "DRAW",
          "amount": 1,
          "conditions": [
            {
              "type": "NOT",
              "condition": {
                "type": "IS_ACTIVE_PLAYER"
              }
            }
          ]
        },
        {
          "type": "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA",
          "mod": "subtract",
          "amount": 1,
          "conditions": [
            {
              "type": "ATTACK_TARGET_IS_HERO"
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsCombatEffectPersistent()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// EVREffectPowerModifier()
case "this_rounds_on_me_blue": return IsHeroAttackTarget() ? -1 : 0;
// EVRCombatEffectActive()
case "this_rounds_on_me_blue": return true;
// EVRPlayAbility()
Draw(1);
        Draw(2);
        if($currentPlayer != $mainPlayer) AddCurrentTurnEffect($cardID, $otherPlayer);
        else AddNextTurnEffect($cardID, $otherPlayer);
        return "";
```

### whisper_of_the_oracle_red  — keyword-only
text: '**Opt 4**\n\n**Go again**'
```json
{
  "slug": "whisper_of_the_oracle_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "OPT",
          "amount": 4
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCGenericPlayAbility()
$opt = match($cardID) { "whisper_of_the_oracle_red" => 4, "whisper_of_the_oracle_yellow" => 3, default => 2 };
      PlayerOpt($currentPlayer, $opt);
      return "";
```

### take_cover_red  — keyword-only
text: '**Reload**'
```json
{
  "slug": "take_cover_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "effects": [
        {
          "type": "RELOAD"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCRangerPlayAbility()
Reload();
        return "";
```

### isolate_yellow  — keyword-only
text: '**Stealth**\n\n**Dominate**'
```json
{
  "slug": "isolate_yellow",
  "abilities": []
}
```
Talishar:
```php
// HasDominate()
return true;
// IsDominateActive()
return true;
```

### rubble_raiser_red  — keyword-only
text: '**Heave 2**'
```json
{
  "slug": "rubble_raiser_red",
  "abilities": []
}
```
Talishar:
```php
// HeaveValue()
case "rubble_raiser_red": case "rubble_raiser_yellow": case "rubble_raiser_blue": return 2;
```

### buzz_bolt_blue  — persistent-combat-effect/verify-scope
text: '**Lightning Fusion**\n\nIf Buzz Bolt was **fused**, whenever an attack hits a hero this turn, it deals 1 damage to them.'
```json
{
  "slug": "buzz_bolt_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BUZZ_BOLT_FUSED"
        }
      ],
      "effects": [
        {
          "type": "DEAL_GENERIC",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddEffectHitTrigger()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// EffectHitEffect()
if (IsHeroAttackTarget()) DamageTrigger($defPlayer, 1, "ATTACKHIT", $cardID, $mainPlayer);
      break;
// IsCombatEffectPersistent()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// FuseAbility()
case "buzz_bolt_red": case "buzz_bolt_yellow": case "buzz_bolt_blue": AddCurrentTurnEffect($cardID, $player); break;
// HasFusion()
case "buzz_bolt_red": case "buzz_bolt_yellow": case "buzz_bolt_blue": return "LIGHTNING";
// ELECombatEffectActive()
case "buzz_bolt_red": case "buzz_bolt_yellow": case "buzz_bolt_blue": return true;
```

### nullrune_gloves  — keyword-only
text: '**Arcane Barrier 1**'
```json
{
  "slug": "nullrune_gloves",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "ARCANE_BARRIER",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ArcaneBarrierChoices()
++$barrierArray[1];
        $total += 1;
        break;
```

### chilling_icevein_yellow  — persistent-combat-effect/verify-scope
text: '**Ice Fusion**\n\nIf Chilling Icevein was **fused**, whenever an attack deals damage to a hero this turn, they discard a card unless they pay {r}.'
```json
{
  "slug": "chilling_icevein_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEAL_DAMAGE",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FUSED"
        },
        {
          "type": "CARD_IN_ZONE",
          "zone": "HERO"
        }
      ],
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "resource": "RESOURCE_POINTS",
          "amount": 1,
          "on_failure": [
            {
              "type": "DISCARD",
              "amount": 1
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
PayOrDiscard($target, 1);
        break;
// CurrentEffectDamageEffects()
if (IsHeroAttackTarget() && CardType($source) == "AA")
          AddLayer("TRIGGER", $otherPlayer, $effectID, $target);
        break;
// IsCombatEffectPersistent()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// FuseAbility()
case "chilling_icevein_red": case "chilling_icevein_yellow": case "chilling_icevein_blue": AddCurrentTurnEffect($cardID, $player); break;
// HasFusion()
case "chilling_icevein_red": case "chilling_icevein_yellow": case "chilling_icevein_blue": return "ICE";
// ELECombatEffectActive()
case "chilling_icevein_red": case "chilling_icevein_yellow": case "chilling_icevein_blue": return true;
```

### exploding_aether_blue  — keyword-only
text: '**Amp 1**\n\n**Go again**'
```json
{
  "slug": "exploding_aether_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "AMP",
          "amount": 1
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ArcaneModifierAmount()
return $effectArr[1];
// CurrentEffectArcaneModifier()
if ($currentTurnEffects[$i + 1] != $player) break;
        $modifier += $effectArr[1];
        $remove = true;
        break;
// ROSPlayAbility()
$ampAmount = match ($cardID) {
        "exploding_aether_red" => 3,
        "exploding_aether_yellow" => 2,
        "exploding_aether_blue" => 1
      };
      AddCurrentTurnEffect($cardID . "," . $ampAmount, $currentPlayer, "PLAY");
      return " Amp " . $ampAmount;
```

### isolate_red  — keyword-only
text: '**Stealth**\n\n**Dominate**'
```json
{
  "slug": "isolate_red",
  "abilities": []
}
```
Talishar:
```php
// HasDominate()
return true;
// IsDominateActive()
return true;
```

### sedation_shot_blue  — looks-aligned
text: 'If Sedation Shot has an aim counter, it has +1{p}.\n\nWhen this hits a hero, create an Inertia token under their control.'
```json
{
  "slug": "sedation_shot_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "COUNTER_GTE",
          "counter": "aim",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "target": {
        "filter": [
          {
            "type": "ATTACK_TARGET_IS_HERO"
          }
        ]
      },
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Inertia"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTEffectPowerModifier()
case "sedation_shot_red": case "sedation_shot_yellow": case "sedation_shot_blue": return 1;
// OUTCombatEffectActive()
case "sedation_shot_red": case "sedation_shot_yellow": case "sedation_shot_blue": return true;
// OUTPlayAbility()
if(HasAimCounter()) {
          AddCurrentTurnEffect($cardID, $currentPlayer);
          $rv = "Gets +1.";
        }
        return $rv;
// OUTHitEffect()
if(IsHeroAttackTarget()) PlayAura($CID_Inertia, $defPlayer, effectController: $mainPlayer);
        break;
```

### cogwerx_tinker_rings  — looks-aligned
text: 'When this defends, create a Golden Cog token.\n\n**Blade Break**'
```json
{
  "slug": "cogwerx_tinker_rings",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Golden Cog"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
PutItemIntoPlayForPlayer("golden_cog", $player);
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
```

### poisoned_blade_blue  — looks-aligned
text: 'Whenever a dagger you own hits a hero this combat chain, they lose 1{h}.\n\n**Go again**'
```json
{
  "slug": "poisoned_blade_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TYPE_IN",
          "types": [
            "dagger"
          ]
        },
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "LOSE_LIFE",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CombatChainHitEffect()
if(IsHeroAttackTarget() && (SubtypeContains($CombatChain->AttackCard()->ID(), "Dagger") || SubtypeContains($sourceID, "Dagger"))) {
        AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "EFFECTHITEFFECT", $source);
      }
      break;
// EffectHitEffect()
WriteLog("The " . CardLink($cardID, $cardID) . " drains 1 health");
      LoseHealth(1, $defPlayer);
      break;
// RemoveEffectsFromCombatChain()
$remove = 1;
        break;
// IsCombatEffectPersistent()
return true;
```

### bonds_of_memory_yellow  — looks-aligned
text: '**Stealth**\n\nWhen this hits a hero, banish the top card of their deck, then banish a card from their graveyard.\n\nWhenever this banishes a card and this has banished another card with the same name, gain 1{h}.'
```json
{
  "slug": "bonds_of_memory_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": {
            "type": "TOP_DECK",
            "controller": "opponent"
          }
        },
        {
          "type": "BANISH",
          "target": {
            "type": "GRAVEYARD",
            "controller": "opponent"
          }
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BANISH",
      "conditions": [
        {
          "type": "REF_EXISTS",
          "ref": "BANISHED_CARDS"
        },
        {
          "type": "REF_PITCH_IS",
          "ref": "BANISHED_CARDS",
          "pitch": 1
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "HEALTH_POINTS",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTHitEffect()
if (IsHeroAttackTarget()) {
        $deck = new Deck($defPlayer);
        $deck->BanishTop("Source-" . $attackCard, banishedBy: $attackCard);
        if ($discard->NumCards() > 0) MZMoveCard($mainPlayer, "THEIRDISCARD", "THEIRBANISH,GY,Source-" . $attackCard . "," . $attackCard, silent: true);
      }
      break;
```

### soul_butcher_red  — looks-aligned
text: 'If the defending hero has 1 or more cards in their soul, this gets +2{p}.\n\n**Blood Debt**'
```json
{
  "slug": "soul_butcher_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "SOUL",
          "amount": 1,
          "player": "OPPONENT"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$theirSoul = &GetSoul($defPlayer);
        $power += (count($theirSoul) > 0 ? 2 : 0);
        break;
```

### tribute_to_demolition_red  — looks-aligned
text: 'As an additional cost to play this, banish a random card from your hand.\n\nIf a card with 6 or more {p} is banished this way, this gets +2{p}.\n\n**Blood Debt**'
```json
{
  "slug": "tribute_to_demolition_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "DISCARD_RANDOM"
        }
      ],
      "conditions": [
        {
          "type": "DISCARDED_CARD_POWER_GTE",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DTDEffectPowerModifier()
case "tribute_to_demolition_red": case "tribute_to_demolition_yellow": case "tribute_to_demolition_blue": return 2;
// DTDCombatEffectActive()
case "tribute_to_demolition_red": case "tribute_to_demolition_yellow": case "tribute_to_demolition_blue": return true;
// DTDPlayAbility()
if(ModifiedPowerValue($additionalCosts, $currentPlayer, "HAND", source:$cardID) >= 6) {
        AddCurrentTurnEffect($cardID, $currentPlayer);
      }
      return "";
```

### goldwing_turbine_yellow  — looks-aligned
text: 'Your next Mechanologist attack this turn gets +2{p}.\n\nCreate a Golden Cog token.'
```json
{
  "slug": "goldwing_turbine_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2,
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "classes": [
                "Mechanologist"
              ]
            },
            {
              "type": "DURING_TURN"
            }
          ]
        },
        {
          "type": "CREATE_TOKEN",
          "token": "Golden Cog"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SEAPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      PutItemIntoPlayForPlayer("golden_cog", $currentPlayer);
      break;
```

### promise_of_plenty_red  — looks-aligned
text: "If Promise of Plenty hits, each hero who doesn't have a card in their arsenal puts the top card of their deck face down into their arsenal.\n\nIf Promise of Plenty is played from arsenal, it gains **go again**."
```json
{
  "slug": "promise_of_plenty_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "EACH_HERO_ARSENAL_FROM_ZONE_THEN_DISCARD",
          "zone": "deck",
          "amount": 1,
          "face_down": true
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PLAY_ACTIVATE_ATTACK",
      "conditions": [
        {
          "type": "PLAYED_FROM_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CRUPlayAbility()
if($from == "ARS") {
        GiveAttackGoAgain();
        $rv = "Gains go again";
      }
      return $rv;
// CRUHitEffect()
if(ArsenalEmpty($defPlayer)) TopDeckToArsenal($defPlayer);
      if(ArsenalEmpty($mainPlayer)) TopDeckToArsenal($mainPlayer);
      break;
```

### stir_the_wildwood_red  — looks-aligned
text: '**Earth Fusion**\n\nIf you have dealt arcane damage to an opposing hero this turn, Stir the Wildwood gains +2{p}.\n\nIf Stir the Wildwood was **fused**, it gains +2{p}.'
```json
{
  "slug": "stir_the_wildwood_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DEALT_ARCANE_DAMAGE_TO_OPPONENT"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FUSED"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += GetClassState($defPlayer, $CS_ArcaneDamageTaken) >= 1 ? 2 : 0;
        break;
// FuseAbility()
case "stir_the_wildwood_red": case "stir_the_wildwood_yellow": case "stir_the_wildwood_blue": AddCurrentTurnEffect($cardID, $player); break;
// HasFusion()
case "stir_the_wildwood_red": case "stir_the_wildwood_yellow": case "stir_the_wildwood_blue": return "EARTH";
// ELEEffectPowerModifier()
case "stir_the_wildwood_red": case "stir_the_wildwood_yellow": case "stir_the_wildwood_blue": return 2;
// ELECombatEffectActive()
case "stir_the_wildwood_red": case "stir_the_wildwood_yellow": case "stir_the_wildwood_blue": return true;
```

### grow_claws_yellow  — looks-aligned
text: 'If a Draconic attack was the last attack this combat chain, this gets +1{p}.\n\n**Go again**'
```json
{
  "slug": "grow_claws_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "classes": [
                "draconic"
              ]
            },
            {
              "type": "LAST_ATTACK_IN_COMBAT_CHAIN"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += isPreviousLinkDraconic() ? 1 : 0;
        break;
```

### slay_the_scholars_yellow  — looks-aligned
text: "**Contract** - You are contracted to banish opponents' 'non-attack' action cards. Whenever you complete this contract, create a Silver token.\n\nWhen this hits a hero, banish the top card of their deck."
```json
{
  "slug": "slay_the_scholars_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": {
            "type": "TOP_DECK",
            "controller": "opponent"
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNHitEffect()
if(IsHeroAttackTarget()) {
        $deck = new Deck($defPlayer);
        if($deck->Empty()) { WriteLog("The opponent deck is already... depleted."); break; }
        $deck->BanishTop(banishedBy:$cardID);
      }
      break;
// ContractType()
case "slay_the_scholars_red": case "slay_the_scholars_yellow": case "slay_the_scholars_blue": return "NAA";
// ContractCompleted()
$EffectContext = $cardID;
      PutItemIntoPlayForPlayer("silver", $player);
      break;
```

### berserk_yellow  — looks-aligned
text: 'Until end of turn, whenever you discard a random card with 6 or more {p}, banish it. If you do, reveal the top card of your deck. If it has 6 or more {p}, draw a card.\n\n**Go again**'
```json
{
  "slug": "berserk_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DISCARD",
      "conditions": [
        {
          "type": "DISCARDED_CARD_POWER_GTE",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "BANISH"
        },
        {
          "type": "REVEAL_TOP_DECK"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DISCARD",
      "conditions": [
        {
          "type": "DISCARDED_CARD_POWER_GTE",
          "amount": 6
        },
        {
          "type": "REF_PITCH_IS",
          "pitch": 6
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
$deck = new Deck($player);
        if ($deck->Reveal() && ModifiedPowerValue($deck->Top(), $player, "DECK", source: "berserk_yellow") >= 6) {
          Draw($player);
          WriteLog(CardLink($parameter, $parameter) . " drew a card");
        }
        break;
// IsCombatEffectPersistent()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// DYNPlayAbility()
case "berserk_yellow": AddCurrentTurnEffect($cardID, $currentPlayer); return "";
```

### step_between_red  — looks-aligned
text: "While this is attacking or on the stack, opponents can't play or activate instants.\n\n**Instant** - {r}, {t} your hero: This gets +1{p} and {p} damage can't be prevented this combat chain."
```json
{
  "slug": "step_between_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "OR",
          "conditions": [
            {
              "type": "IN_COMBAT",
              "source": "self"
            },
            {
              "type": "CARD_IN_ZONE",
              "zone": "stack",
              "card": "self"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT",
          "opponent": true
        }
      ]
    },
    {
      "ability_type": "INSTANT",
      "activation_cost": 1,
      "cost": [
        {
          "type": "TAP_SELF"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "WARD",
          "duration": "combat_chain"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// InstantRestricted()
return $currentPlayer == $defPlayer;
// InstantRestricted()
return $currentPlayer == $defPlayer;
// InstantRestricted()
return $currentPlayer == $defPlayer;
```

### dragonscaler_flight_path  — looks-aligned
text: "**Instant** - {r}{r}{r}, destroy this: Target Draconic attack gets **go again**. If it's a weapon or ally attack, you may attack with it an additional time this turn. This ability costs {r} less to activate for each Draconic chain link you control.\n\n**Battleworn**"
```json
{
  "slug": "dragonscaler_flight_path",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 3,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "OR",
              "conditions": [
                {
                  "type": "ATTACK_IS_WEAPON"
                },
                {
                  "type": "ATTACK_SUBTYPE_IN",
                  "subtypes": [
                    "ally"
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if(!$CombatChain->HasCurrentLink() && SearchLayersForPhase("RESOLUTIONSTEP") == -1) return true;
      $previousLink = SearchCombatChainAttacks($currentPlayer, talent:"DRACONIC") == "";
      $currentLink = !TalentContains($attackID, "DRACONIC", $currentPlayer);
      if ($previousLink && $currentLink) return true;
      return false;
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// DoesCurrentTurnEffectGrantGoAgain()
return true;
// GetLayerTarget()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "COMBATCHAINATTACKS:talent=DRACONIC&ACTIVEATTACK:talent=DRACONIC");
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a draconic attack");
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);  
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// HNTPlayAbility()
if (substr($target, 0, strlen("COMBATCHAINLINK")) == "COMBATCHAINLINK") {
        AddCurrentTurnEffect($cardID, $currentPlayer);
        $targetID = $CombatChain->AttackCard()->ID();
        $targetUID = $CombatChain->AttackCard()->OriginUniqueID();
      }
      else {
        $targetID = GetMZCard($currentPlayer, $target);
        $targetUID = GetMZUID($currentPlayer, $target);
      }
      $type = TypeContains($targetID, "W", $currentPlayer);
      $subtype = SubtypeContains($targetID, "Ally", $currentPlayer);
      if($type) {
        $character = &GetPlayerCharacter($currentPlayer);
        $charPieces = CharacterPieces();
        $charCount = count($character);
        $index = -1;
        for ($i = 0; $i < $charCount; $i += $charPieces) {
          if ($character[$i + 11] == $targetUID) { $index = $i; break; }
        }
        if ($index != -1) {
          ++$character[$index + 5];
          if($character[$index + 1] == 1) $character[$index + 1] = 2;
        }
      }
      elseif ($subtype) {
        $ally = &GetAllies($currentPlayer);
        $allyIndex = SearchAlliesForUniqueID($targetUID, $currentPlayer);
        if($allyIndex != -1) {
          $ally[$allyIndex + 1] = 2;
        }
      }
      break;
```

### smashing_performance_yellow  — looks-aligned
text: 'When this attacks draw a card, then discard a random card. If a card with 6 or more {p} is discarded this way, destroy a random item in the arena.'
```json
{
  "slug": "smashing_performance_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "DISCARD_RANDOM"
        },
        {
          "type": "DESTROY_REF",
          "conditions": [
            {
              "type": "DISCARDED_CARD_POWER_GTE",
              "amount": 6
            },
            {
              "type": "REF_EXISTS",
              "ref": "ITEM"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVOPlayAbility()
Draw($currentPlayer);
      $card = DiscardRandom();
      if (ModifiedPowerValue($card, $currentPlayer, "HAND", source: "smashing_performance_yellow") >= 6) {
        $items = SearchMultizone($currentPlayer, "THEIRITEMS&MYITEMS");
        if ($items != "") {
          $items = explode(",", $items);
          $destroyedItem = $items[GetRandom(0, count($items) - 1)];
          $destroyedItemID = GetMZCard($currentPlayer, $destroyedItem);
          WriteLog(CardLink("smashing_performance_yellow", "smashing_performance_yellow") . " destroys " . CardLink($destroyedItemID, $destroyedItemID) . ".");
          MZDestroy($currentPlayer, $destroyedItem, $currentPlayer);
        }
      }
      return "";
```

### sack_the_shifty_red  — looks-aligned
text: "**Contract** - You are contracted to banish opponents' cards with base **go again**. Whenever you complete this contract, create a Silver token.\n\nWhen this hits a hero, banish the top card of their deck."
```json
{
  "slug": "sack_the_shifty_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": {
            "type": "TOP_CARD",
            "controller": "opponent"
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNHitEffect()
if(IsHeroAttackTarget()) {
        $deck = new Deck($defPlayer);
        if($deck->Empty()) { WriteLog("The opponent deck is already... depleted."); break; }
        $deck->BanishTop(banishedBy:$cardID);
      }
      break;
// ContractType()
case "sack_the_shifty_red": case "sack_the_shifty_yellow": case "sack_the_shifty_blue": return "GOAGAIN";
// ContractCompleted()
$EffectContext = $cardID;
      PutItemIntoPlayForPlayer("silver", $player);
      break;
```

### fools_gold_yellow  — looks-aligned
text: 'When this is discarded, create a Gold token.'
```json
{
  "slug": "fools_gold_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DISCARD",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "GOLD"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
PutItemIntoPlayForPlayer("gold", $player, effectController:$player, isToken:true);
        break;
// AddGraveyard()
if(str_contains($from, "HAND")) {
        AddLayer("TRIGGER", $player, $cardID);
      }
```

### tripwire_trap_red  — looks-aligned
text: "Tripwire Trap can only be played from arsenal.\n\nWhen this defends, effects don't trigger when an attack hits this chain link unless the attacking hero pays {r}."
```json
{
  "slug": "tripwire_trap_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "amount": 1,
          "target": "attacker"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return $from != "ARS";
// ProcessTrigger()
AddDecisionQueue("YESNO", $mainPlayer, "if_you_want_to_pay_1_to_allow_hit_effects_this_chain_link", 1, 1);
        AddDecisionQueue("NOPASS", $mainPlayer, $parameter, 1);
        AddDecisionQueue("PAYRESOURCES", $mainPlayer, "1", 1);
        AddDecisionQueue("ELSE", $mainPlayer, "-");
        AddDecisionQueue("TRIPWIRETRAP", $mainPlayer, "-", 1);
        break;
// OnDefenseReactionResolveEffects()
AddLayer("TRIGGER", $defPlayer, $cardID);
      break;
// CRUCombatEffectActive()
case "tripwire_trap_red": return true;
```

### soul_cleaver_yellow  — looks-aligned
text: 'If the defending hero has 1 or more cards in their soul, this gets **go again**.\n\n**Blood Debt**'
```json
{
  "slug": "soul_cleaver_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "SOUL",
          "amount": 1,
          "comparison": "gte"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DTDPlayAbility()
$theirSoul = &GetSoul($otherPlayer);
      if(count($theirSoul) > 0) GiveAttackGoAgain();
      return "";
```

### convulsions_from_the_bellows_of_hell_red  — looks-aligned
text: 'As an additional cost to play Convulsions from the Bellows of Hell, banish 3 random cards from your graveyard.\n\nIf a card with 6 or more {p} is banished this way, the next attack action card you play this turn gains +3{p} and **dominate**.\n\n**Go again**'
```json
{
  "slug": "convulsions_from_the_bellows_of_hell_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "BANISH_NAMED_GRAVEYARD_OPTIONAL",
          "amount": 3
        }
      ],
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ],
      "conditions": [
        {
          "type": "OR",
          "conditions": [
            {
              "type": "NOT",
              "condition": {
                "type": "REF_EXISTS",
                "ref": "banished_high_power_card"
              }
            },
            {
              "type": "AND",
              "conditions": [
                {
                  "type": "REF_EXISTS",
                  "ref": "banished_high_power_card"
                },
                {
                  "type": "MODIFY_ATTACK",
                  "mod": "add",
                  "amount": 3
                },
                {
                  "type": "DOMINATE"
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return (new Discard($player))->NumCards() < 3;
// DoesEffectGrantsDominate()
return true;
// PayAdditionalCosts()
if (RandomBanish3GY($cardID) > 0) AddCurrentTurnEffect($cardID, $currentPlayer);
      break;
// MONEffectPowerModifier()
case "convulsions_from_the_bellows_of_hell_red": return 3;
// MONCombatEffectActive()
case "convulsions_from_the_bellows_of_hell_red": case "convulsions_from_the_bellows_of_hell_yellow": case "convulsions_from_the_bellows_of_hell_blue": return CardType($attackID) == "AA";
```

### humble_blue  — looks-aligned
text: 'When this hits a hero, they lose all hero card abilities until the end of their next turn.'
```json
{
  "slug": "humble_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "HERO_ABILITIES_DISABLED",
          "duration": "END_OF_TURN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTHitEffect()
if(IsHeroAttackTarget())
        {
          AddCurrentTurnEffect($cardID, $defPlayer);
          AddNextTurnEffect($cardID, $defPlayer);
          $char = &GetPlayerCharacter($defPlayer);
          $char[1] = 3;
        }
        break;
```

### emerging_dominance_red  — looks-aligned
text: 'At the beginning of your action phase, destroy Emerging Dominance then the next Guardian attack action card you play this turn gains +3{p} and **dominate**.'
```json
{
  "slug": "emerging_dominance_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_REF",
          "target": "self"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        },
        {
          "type": "PLAYED_FROM_ARSENAL",
          "card_type": "ACTION",
          "card_class": "Guardian"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        },
        {
          "type": "DOMINATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraBeginningActionPhaseAbilities()
AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", "DESTROY", $auras[$i + 6]);
        break;
// DoesEffectGrantsDominate()
return true;
// ProcessTrigger()
AddCurrentTurnEffect($parameter, $player);
        DestroyAuraUniqueID($player, $uniqueID);
        break;
// CRUEffectPowerModifier()
case "emerging_dominance_red": return 3;
// CRUCombatEffectActive()
case "emerging_dominance_red": case "emerging_dominance_yellow": case "emerging_dominance_blue": return CardType($attackID) == "AA" && ClassContains($attackID, "GUARDIAN", $mainPlayer);
```

### clash_of_might_blue  — looks-aligned
text: 'When this defends, **clash** with the attacking hero. The winner creates a Might token.'
```json
{
  "slug": "clash_of_might_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "CLASH",
          "target": {
            "filter": [
              {
                "type": "ATTACK_CLASS_IN",
                "classes": [
                  "hero"
                ]
              }
            ]
          },
          "on_win": [
            {
              "type": "CREATE_TOKEN",
              "token_type": "Might"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
Clash($parameter, effectController: $player);
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
// WonClashAbility()
PlayAura("might", $playerID);
        break;
```

### vaporize__shock_yellow  — looks-aligned
text: "**Meld**\n\nDestroy an aura permanent with cost X or less and/or up to X aura tokens, where X is the total arcane damage you've dealt to opposing heroes this turn.\n\n//\n\nDeal 1 arcane damage to any target."
```json
{
  "slug": "vaporize__shock_yellow",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zones": [
                  "aura"
                ]
              },
              {
                "type": "COUNTER_GTE",
                "asset": "ARCANIC_DAMAGE_DEALT",
                "amount": 0
              }
            ]
          }
        },
        {
          "type": "DESTROY_TOKEN",
          "amount": {
            "type": "COUNTER_GTE",
            "asset": "ARCANIC_DAMAGE_DEALT",
            "amount": 0
          }
        }
      ]
    },
    {
      "ability_type": "INSTANT",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CardClass()
if(function_exists("GetClassState")) {
        if (IsMeldInstantName(GetClassState($currentPlayer, $CS_AdditionalCosts))) return "NONE";
      }
      return "RUNEBLADE";
// CardTalent()
if(function_exists("GetClassState") && $from == "-") {
        if(IsMeldLeftSideName(GetClassState($currentPlayer, $CS_AdditionalCosts))) return "NONE";
        return "LIGHTNING";        
      }
      return "LIGHTNING";
// ProcessMeld()
$arcaneDamageDealt = GetClassState($player, $CS_ArcaneDamageDealt);
      AddDecisionQueue("MULTIZONEINDICES", $player, "THEIRAURAS:minCost=0;maxCost=" . $arcaneDamageDealt . "&MYAURAS:minCost=0;maxCost=" . $arcaneDamageDealt, 1);
      AddDecisionQueue("SETDQCONTEXT", $player, "Choose an aura with cost $arcaneDamageDealt or less to destroy, or pass (tokens are chosen next)", 1);
      AddDecisionQueue("MAYCHOOSEMULTIZONE", $player, "<-", 1);
      AddDecisionQueue("MZDESTROY", $player, "-", 1);
      for($i=0; $i<$arcaneDamageDealt; ++$i) {
        AddDecisionQueue("MULTIZONEINDICES", $player, "THEIRAURAS:type=T&MYAURAS:type=T");
        AddDecisionQueue("SETDQCONTEXT", $player, "Choose a token aura to destroy, or pass", 1);
        AddDecisionQueue("MAYCHOOSEMULTIZONE", $player, "<-", 1);
        AddDecisionQueue("MZDESTROY", $player, "-", 1);
      }
      break;
// ActionsThatDoArcaneDamage()
$meldState = GetClassState($playerID, $CS_AdditionalCosts);
      return ($meldState == "Both" || $meldState == "Shock");
```

### flex_blue  — looks-aligned
text: 'When you attack or defend with Flex, you may pay {r}{r}. If you do, it gains +2{p}.'
```json
{
  "slug": "flex_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "resource_cost": 2,
          "on_success": [
            {
              "type": "MODIFY_ATTACK",
              "mod": "add",
              "amount": 2
            }
          ]
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "resource_cost": 2,
          "on_success": [
            {
              "type": "MODIFY_ATTACK",
              "mod": "add",
              "amount": 2
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
ChooseToPay($player, $parameter, "0,2");
        AddDecisionQueue("PASSPARAMETER", $player, $target, 1);
        AddDecisionQueue("COMBATCHAINPOWERMODIFIER", $player, "2", 1);
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
// UPREffectPowerModifier()
case "flex_red": case "flex_yellow": case "flex_blue": return 2;
// UPRCombatEffectActive()
case "flex_red": case "flex_yellow": case "flex_blue": return true;
// UPRTalentPlayAbility()
$hand = &GetHand($currentPlayer);
        $resources = &GetResources($currentPlayer);
        if (count($hand) > 0 || $resources[0] >= 2)
        {
          AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose if you want to pay to buff " . CardLink($cardID, $cardID), 1);
          AddDecisionQueue("BUTTONINPUT", $currentPlayer, "0,2", 0, 1);
          AddDecisionQueue("PAYRESOURCES", $currentPlayer, "<-", 1);
        }
        else {
          AddDecisionQueue("PASSPARAMETER", $currentPlayer, "0");
        }
        AddDecisionQueue("LESSTHANPASS", $currentPlayer, "1", 1);
        AddDecisionQueue("ADDCURRENTTURNEFFECT", $currentPlayer, $cardID, 1);
        return "";
```

### little_big_foot_red  — looks-aligned
text: 'If there are two or more cards with cost 3 or more in your pitch zone, this gets +6{p}.'
```json
{
  "slug": "little_big_foot_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "pitch",
          "amount": 2,
          "comparison": "gte",
          "card_condition": {
            "type": "COST_GTE",
            "amount": 3
          }
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 6
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += SearchCount(SearchPitch($mainPlayer, minCost: 3)) >= 2 ? 6 : 0;
        break;
```

### ray_of_hope_yellow  — looks-aligned
text: "Attacks you control have +1{p} while attacking a Shadow hero this turn.\n\nIf you have less {h} than an opposing Shadow hero, put Ray of Hope into your hero's soul."
```json
{
  "slug": "ray_of_hope_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "classes": [
            "shadow"
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "conditions": [
        {
          "type": "HEALTH_LT_OPP",
          "opponent_subtypes": [
            "shadow"
          ]
        }
      ],
      "effects": [
        {
          "type": "PUT_SELF_BOTTOM_DECK"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// GoesWhereAfterResolving()
$theirChar = &GetPlayerCharacter($otherPlayer);
      return PlayerHasLessHealth($player) && TalentContains($theirChar[0], "SHADOW") ? "SOUL" : "GY";
// IsCombatEffectPersistent()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// MONEffectPowerModifier()
case "ray_of_hope_yellow": return 1;
// MONCombatEffectActive()
case "ray_of_hope_yellow": $theirChar = GetPlayerCharacter($defPlayer); return TalentContains($theirChar[0], "SHADOW");
// MONTalentPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### new_horizon  — looks-aligned
text: 'If you have a face up card in your arsenal, you have an additional arsenal zone.\n\nWhen this is destroyed, destroy all cards in your arsenal.\n\n**Blade Break**'
```json
{
  "slug": "new_horizon",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEATH",
      "effects": [
        {
          "type": "DESTROY_REF",
          "ref": "arsenal"
        }
      ]
    },
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CharacterDestroyEffect()
WriteLog(Cardlink($cardID, $cardID) . " destroys your arsenal");
      DestroyArsenal($player, effectController: $player);
      break;
```

### grow_wings_yellow  — looks-aligned
text: 'If a Draconic attack was the last attack this combat chain, this gets **go again**.'
```json
{
  "slug": "grow_wings_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "classes": [
            "draconic"
          ]
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
return isPreviousLinkDraconic();
```

### harness_lightning_red  — looks-aligned
text: "**Lightning Flow** - If you've played a Lightning card this turn, deal 3 arcane damage to target hero."
```json
{
  "slug": "harness_lightning_red",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LIGHTNING_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AURPlayAbility()
if (GetClassState($mainPlayer, $CS_NumLightningPlayed) > 0) {
        DealArcane(3, 0, "PLAYCARD", $cardID);
      }
      return "";
```

### pound_town_blue  — looks-aligned
text: "**Beat Chest**\n\nWhen this attacks, if you've **beaten chest** this turn, create a Might token."
```json
{
  "slug": "pound_town_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BEAT_CHEST_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Might"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HVYPlayAbility()
if (SearchCurrentTurnEffects("BEATCHEST", $currentPlayer)) PlayAura("might", $currentPlayer);
      return "";
```

### current_funnel_blue  — looks-aligned
text: 'When this attacks, if the last action card you played this turn was Lightning, this and the next action card you play this turn get **go again**.'
```json
{
  "slug": "current_funnel_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LIGHTNING_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        },
        {
          "type": "SET_FLAG",
          "flag": "CURRENT_FUNNEL_GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PLAY_ACTIVATE_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CURRENT_FUNNEL_GO_AGAIN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
//the last action in numActions is going to be the current chain link
      //so we want the second to last
      $actionsPlayed = explode(",", GetClassState($mainPlayer, $CS_ActionsPlayed) ?? "");
      $numActions = count($actionsPlayed);
      return $numActions > 1 && TalentContains($actionsPlayed[$numActions-2], "LIGHTNING", $mainPlayer);
// ROSPlayAbility()
$actionsPlayed = explode(",", GetClassState($currentPlayer, $CS_ActionsPlayed) ?? "");
      $numActions = count($actionsPlayed);
      if (count($actionsPlayed) > 1 && TalentContains($actionsPlayed[$numActions-2], "LIGHTNING", $currentPlayer)) {
        AddCurrentTurnEffect($cardID, $currentPlayer);
      }
      return "";
```

### longdraw_half_glove  — looks-aligned
text: '**Instant** - Destroy this, put 2 cards from your hand and/or arsenal on the bottom of your deck: Your next arrow attack this turn gets +4{p}.\n\n**Battleworn**'
```json
{
  "slug": "longdraw_half_glove",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "PUT_HAND_CARD_BOTTOM",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4,
          "conditions": [
            {
              "type": "ATTACK_SUBTYPE_IN",
              "subtypes": [
                "arrow"
              ]
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return count($myHand) + count($myArsenal) < 2;
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex, true);
      break;
// PayAdditionalCosts()
$myHand = &GetHand($currentPlayer);
      $myArsenal = &GetArsenal($currentPlayer);
      if(count($myHand) + count($myArsenal) < 2) {
        WriteLog("No card in hand/arsenal to pay the cost of " . CardLink($cardID, $cardID) . ". Reverting the gamestate.", highlight:true);
        RevertGamestate();
      }
      MZMoveCard($currentPlayer, "MYHAND&MYARS", "MYBOTDECK", silent: true);
      MZMoveCard($currentPlayer, "MYHAND&MYARS", "MYBOTDECK", silent: true);
      break;
// MSTPlayAbility()
AddCurrentTurnEffectNextAttack($cardID, $currentPlayer);
      return "";
```

### public_bounty_yellow  — looks-aligned
text: '**Mark** target opposing hero.\n\nThe next time you attack a **marked** hero this turn, the attack gets +2{p}.\n\n**Go again**'
```json
{
  "slug": "public_bounty_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MARK",
          "target": "opponent"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "TARGET_MARKED"
        },
        {
          "type": "DURING_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HNTPlayAbility()
AddCurrentTurnEffect("$cardID-UNSET", $currentPlayer);
      MarkHero($otherPlayer);
      break;
```

### static_shock_yellow  — looks-aligned
text: "**Lightning Flow** - When this hits a hero, if you've played a Lightning card this turn, deal 1 arcane damage to them."
```json
{
  "slug": "static_shock_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LIGHTNING_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AURHitEffect()
if (GetClassState($mainPlayer, $CS_NumLightningPlayed) > 0) {
      DealArcane(1, 1, "PLAYCARD", $cardID, false, $mainPlayer);
```

### spark_spray_yellow  — looks-aligned
text: 'When this is defended by 1 or more cards, you may pay {r}. If you do, this gets +1{p}.'
```json
{
  "slug": "spark_spray_yellow",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "DEFENDS_WITH_OTHER_HAND_CARD",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "MAY",
          "cost": [
            {
              "type": "PAY_LIFE",
              "amount": 1
            }
          ],
          "effects": [
            {
              "type": "MODIFY_ATTACK",
              "mod": "add",
              "amount": 1
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
AddDecisionQueue("YESNO", $player, "if_you_want_to_pay_1_to_buff_".CardLink($parameter, $parameter), 0, 1);
        AddDecisionQueue("NOPASS", $player, "-", 1);
        AddDecisionQueue("PASSPARAMETER", $player, 1, 1);
        AddDecisionQueue("PAYRESOURCES", $player, "<-", 1);
        AddDecisionQueue("ADDCURRENTTURNEFFECT", $mainPlayer, $parameter, 1);
        break;
// OnDefenseReactionResolveEffects()
AddLayer("TRIGGER", $mainPlayer, $combatChain[0]);
      break;
// OnBlockResolveEffects()
$numBlocking = 0;
        for ($i = $combatChainPieces; $i < $combatChainCount; $i += $combatChainPieces) {
          if ($combatChain[$i+1] == $defPlayer) $numBlocking += 1;
        }
        if ($numBlocking > 0) {
          AddLayer("TRIGGER", $mainPlayer, $combatChain[0]);
        }
        break;
```

### open_the_flood_gates_red  — looks-aligned
text: 'Deal 3 arcane damage to target hero.\n\n**Surge** - If this deals more than 3 damage, draw 2 cards.'
```json
{
  "slug": "open_the_flood_gates_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CLASH_WIN_REVEALED",
      "conditions": [
        {
          "type": "SURGE"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayRequiresTarget()
return 0;
// ActionsThatDoArcaneDamage()
return true;
// ProcessSurge()
WriteLog(CardLink($cardID, $cardID) . " draws 2 cards");
      Draw($player, num:2);
      break;
// ROSPlayAbility()
case "open_the_flood_gates_blue"://open the floodgates
```

### blinding_beam_yellow  — looks-aligned
text: 'Blinding Beam cost {r} less to play if it targets a Shadow Card.\n\nTarget attacking or defending attack action card gets -2{p}.'
```json
{
  "slug": "blinding_beam_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "PAY_LIFE",
          "amount": 1
        }
      ],
      "conditions": [
        {
          "type": "ATTACK_HAS_KEYWORD",
          "keyword": "SHADOW"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "subtract",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return !$CombatChain->HasCurrentLink();
// SelfCostModifier()
return TalentContains($combatChain[$layers[3]], "SHADOW") ? -1 : 0;
// GetLayerTarget()
AddDecisionQueue("FINDINDICES", $currentPlayer, "CCAA");
      AddDecisionQueue("CHOOSECOMBATCHAIN", $currentPlayer, "<-", 1);
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// MONTalentPlayAbility()
switch ($cardID) {
// MONTalentPlayAbility()
$amount = -2;
          break;
```

### grow_wings_red  — looks-aligned
text: 'If a Draconic attack was the last attack this combat chain, this gets **go again**.'
```json
{
  "slug": "grow_wings_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "classes": [
            "draconic"
          ]
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
return isPreviousLinkDraconic();
```

### push_forward_red  — looks-aligned
text: 'Your next weapon attack this turn gains +3{p}.\n\nIf you have attacked with a weapon this turn, your next attack this turn gains **dominate**.\n\n**Go again**'
```json
{
  "slug": "push_forward_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "ATTACK_IS_WEAPON"
            }
          ]
        },
        {
          "type": "DOMINATE",
          "conditions": [
            {
              "type": "ATTACK_IS_WEAPON"
            }
          ]
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CRUPlayAbility()
AddCurrentTurnEffect($cardID . "-1", $mainPlayer);
      if(GetClassState($currentPlayer, $CS_AttacksWithWeapon) > 0) {
        AddCurrentTurnEffect($cardID . "-2", $mainPlayer);
        $rv = "Gives your attack dominate because you've attacked with a weapon";
      }
      return $rv;
```

### dead_threads  — looks-aligned
text: '**Instant** - {t}: Gain {r}. Activate this only if an ally has been put into your graveyard this turn.\n\n**Blade Break**'
```json
{
  "slug": "dead_threads",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ALLY_PUT_IN_GRAVEYARD_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return CheckTapped("MYCHAR-$index", $currentPlayer) || GetClassState($currentPlayer, $CS_NumAllyPutInGraveyard) == 0;
// EquipPayAdditionalCosts()
Tap("MYCHAR-$cardIndex", $currentPlayer);
      break;
// SEAPlayAbility()
GainResources($currentPlayer, 1);
      break;
```

### system_failure_yellow  — looks-aligned
text: 'Remove all steam counters from target equipment, item, or weapon. If 2 or more steam counters are removed this way, deal 2 damage to its controler.'
```json
{
  "slug": "system_failure_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "REMOVE_COUNTERS",
          "counter": "steam",
          "conditions": [
            {
              "type": "COUNTER_GTE",
              "counter": "steam",
              "amount": 2
            }
          ]
        },
        {
          "type": "DEAL_GENERIC",
          "amount": 2,
          "conditions": [
            {
              "type": "COUNTER_GTE",
              "counter": "steam",
              "amount": 2
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVOPlayAbility()
AddDecisionQueue("MULTIZONEINDICES", $mainPlayer, "THEIRITEMS:hasSteamCounter=true&THEIRCHAR:hasSteamCounter=true&MYITEMS:hasSteamCounter=true&MYCHAR:hasSteamCounter=true");
      AddDecisionQueue("SETDQCONTEXT", $mainPlayer, "Choose an equipment, item, or weapon. Remove all steam counters from it.");
      AddDecisionQueue("CHOOSEMULTIZONE", $mainPlayer, "<-", 1);
      AddDecisionQueue("MZREMOVEALLCOUNTERS", $currentPlayer, "-", 1);
      AddDecisionQueue("SYSTEMFAILURE", $currentPlayer, "<-", 1);
      return "";
```

### out_muscle_blue  — looks-aligned
text: "While Out Muscle isn't defended by a card with equal or greater {p}, it has **go again**."
```json
{
  "slug": "out_muscle_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "NOT",
          "condition": {
            "type": "DEFENDS_WITH_OTHER_HAND_CARD",
            "conditions": [
              {
                "type": "SELF_ATTACK_POWER_GTE",
                "amount": 4
              }
            ]
          }
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
return SearchHighestAttackDefended() < CachedTotalPower();
```

### loan_shark_yellow  — looks-aligned
text: "**Go again**\n\nWhen this enters the arena, create 2 Gold tokens.\n\nAt the beginning of your end phase, if you haven't created or stolen a Gold this turn, destroy this, then lose 2{h} unless you discard a card."
```json
{
  "slug": "loan_shark_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Gold",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "NO_GOLD_CREATED_OR_STOLEN_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_SELF"
        },
        {
          "type": "LOSE_LIFE",
          "amount": 2
        }
      ],
      "additional_cost": [
        {
          "type": "DISCARD_CARD"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraBeginEndPhaseTriggers()
if(GetClassState($mainPlayer, $CS_NumGoldCreated) <= 0) {
          AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", "-", $auras[$i + 6]);
        }
        break;
// ProcessTrigger()
DestroyAuraUniqueID($player, $uniqueID);
        WriteLog("Resolving " . CardLink($parameter, $parameter) . " ability");
        AddDecisionQueue("MULTIZONEINDICES", $player, "MYHAND");
        AddDecisionQueue("SETDQCONTEXT", $player, CardLink($parameter, $parameter) . ": choose a card to discard (or pass and lose 2 health)");
        AddDecisionQueue("MAYCHOOSEMULTIZONE", $player, "<-", 1);
        AddDecisionQueue("MZREMOVE", $player, "-", 1);
        AddDecisionQueue("ADDDISCARD", $player, "HAND", 1);
        AddDecisionQueue("NOTEQUALPASS", $player, "PASS");
        AddDecisionQueue("PASSPARAMETER", $player, "2", 1);
        AddDecisionQueue("OP", $mainPlayer, "PLAYERLOSEHEALTH", 1);
        break;
// SEAPlayAbility()
PutItemIntoPlayForPlayer("gold", $currentPlayer, number: 2, effectController: $currentPlayer);
      break;
    // Gravy cards
```

### spreading_flames_red  — looks-aligned
text: 'Draconic attacks you control have +1{p} while their base {p} is less than the number of Draconic chain links you control.\n\n**Go again**'
```json
{
  "slug": "spreading_flames_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "classes": [
            "draconic"
          ]
        },
        {
          "type": "ATTACK_CONTROLLED_BY_YOU"
        },
        {
          "type": "SELF_ATTACK_POWER_GTE",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// RemoveEffectsFromCombatChain()
$remove = 1;
        break;
// IsCombatEffectPersistent()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// UPRNinjaPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
// UPREffectPowerModifier()
case "spreading_flames_red": return 1;
// UPRCombatEffectActive()
case "spreading_flames_red": return TalentContains($attackID, "DRACONIC", $mainPlayer) && PowerValue($attackID, $mainPlayer, "CC") < NumDraconicChainLinks();
```

### force_of_nature_blue  — looks-aligned
text: '**Briar Specialization**\n\n**Earth Fusion**\n\nWhenever an attack action card you control hits this turn, if its {p} is greater than its base {p}, draw a card.\n\nIf Force of Nature was fused, your next attack this turn gains +1{p}.\n\n**Go again**'
```json
{
  "slug": "force_of_nature_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_POWER_GT_BASE"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FORCE_OF_NATURE_FUSED"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// FuseAbility()
case "force_of_nature_blue": AddCurrentTurnEffect($cardID, $player); break;
// HasFusion()
case "force_of_nature_blue": return "EARTH";
// ELERunebladePlayAbility()
AddCurrentTurnEffect($cardID . "-HIT", $currentPlayer);
        return "";
// ELEEffectPowerModifier()
case "force_of_nature_blue": return 1;
// ELECombatEffectActive()
case "force_of_nature_blue": return true;
```

### buckle_blue  — looks-aligned
text: 'Your next Guardian attack this turn gains +1{p}, **dominate**, and "When this hits a hero, destroy an equipment they control with a -1{d} counter on it."\n\n**Go again**'
```json
{
  "slug": "buckle_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "DOMINATE"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "classes": [
            "Guardian"
          ]
        },
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "opponent_equipment",
          "conditions": [
            {
              "type": "COUNTER_GTE",
              "counter": "-1",
              "amount": 1
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesEffectGrantsDominate()
return true;
// AddEffectHitTrigger()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// EffectHitEffect()
if(IsHeroAttackTarget()) Mangle();
      break;
// DYNEffectPowerModifier()
case "buckle_blue": return 1;
// DYNCombatEffectActive()
case "buckle_blue": return ClassContains($attackID, "GUARDIAN", $mainPlayer);
// DYNPlayAbility()
case "buckle_blue": AddCurrentTurnEffect($cardID, $currentPlayer); return "";
```

### herald_of_ravages_blue  — looks-aligned
text: "When this hits, put it into your hero's soul and deal 1 arcane damage to target hero.\n\n**Phantasm**"
```json
{
  "slug": "herald_of_ravages_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "PUT_SELF_BOTTOM_DECK"
        },
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MONIllusionistHitEffect()
DealArcane(1, 0, "PLAYCARD", $cardID, false, $mainPlayer);
        if (DoesAttackHaveGoAgain()) GiveAttackGoAgain();
        $combatChainState[$CCS_GoesWhereAfterLinkResolves] = "-"; 
        AddSoul($attackCard, $mainPlayer, "CC");
        break;
```

### mark_of_the_huntsman  — looks-aligned
text: '**Once per Turn Action** - {r}{r}: **Attack**. **Go again**\n\nWhen this hits a hero, you may choose to destroy this and **mark** them.\n\nIf this is attacking a **marked** hero, this gets +1{p}.'
```json
{
  "slug": "mark_of_the_huntsman",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 2,
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "MAY",
          "effect": {
            "type": "DESTROY_PERMANENT",
            "target": "self"
          }
        },
        {
          "type": "MAY",
          "effect": {
            "type": "MARK",
            "target": "ATTACK_TARGET"
          }
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "MARKED"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerValue()
if (!IsHeroAttackTarget() || $from != "CC") return $basePower;
        else return CheckMarked($defPlayer) ? $basePower+1 : $basePower;
// AddOnHitTrigger()
if (IsHeroAttackTarget() || $targetPlayer != "-") {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $cardID, $targetPlayer, "ONHITEFFECT", $uniqueID);
        return true;
      }
      break;
// ReverseID()
return "GEM007";
// ReverseArt()
case "mark_of_the_huntsman": return "mark_of_the_huntsman_r";
// HNTHitEffect()
AddDecisionQueue("YESNO", $mainPlayer, "if you want to destroy " . CardLink($cardID, $cardID) . " and mark the opponent", 0, 1);
      AddDecisionQueue("NOPASS", $mainPlayer, "-", 1);
      AddDecisionQueue("HUNTSMANMARK", $mainPlayer, $uniqueID);
      break;
```

### man_overboard_yellow  — looks-aligned
text: 'When this attacks, you may discard an ally. If you do, this gets +1{p} and **go again**.'
```json
{
  "slug": "man_overboard_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "OPT",
          "amount": 1
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesCurrentTurnEffectGrantGoAgain()
return true;
```

### rushing_river_blue  — looks-aligned
text: '**Combo** - If Torrent of Tempo was the last attack this combat chain, Rushing River gains +1{p}, **go again**, and "If Rushing River hits, draw X cards then put X cards from your hand on top of your deck in any order, where X is the number of attacks that have hit this combat chain."'
```json
{
  "slug": "rushing_river_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "COMBO_CONTAINS",
          "card": "torrent_of_tempo"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_HIT",
          "effects": [
            {
              "type": "DRAW",
              "amount": "CHAIN_HIT_COUNT"
            },
            {
              "type": "REORDER_REF",
              "ref": "HAND",
              "amount": "CHAIN_HIT_COUNT"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Torrent of Tempo") return true;
        break;
// AddOnHitTrigger()
if (ComboActive($cardID)) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "ONHITEFFECT");
        return true;
      }
      break;
// PowerModifier()
$power += (ComboActive() ? 1 : 0);
        break;
// DoesAttackHaveGoAgain()
return ComboActive($attackID);
// CRUHitEffect()
if(ComboActive()) {
        $num = NumAttacksHit()+1;
        for($i = 0; $i < $num; ++$i) {
          Draw($mainPlayer);
          AddDecisionQueue("FINDINDICES", $mainPlayer, "HAND");
          AddDecisionQueue("CHOOSEHAND", $mainPlayer, "<-", 1);
          AddDecisionQueue("MULTIREMOVEHAND", $mainPlayer, "-", 1);
          AddDecisionQueue("MULTIADDTOPDECK", $mainPlayer, "-", 1);
        }
      }
      break;
```

### cogwerx_dovetail_red  — looks-aligned
text: 'When this hits a hero, {u} all cogs you control.\n\n**Thrice per Turn Instant** - {t} a cog you control: This gets +1{p} or **go again**.'
```json
{
  "slug": "cogwerx_dovetail_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "cog",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "INSTANT",
      "activation_cost": 0,
      "cost": [
        {
          "type": "TAP_SELF"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ],
      "max_uses": 3
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if ($player != $mainPlayer) return true;
      if ($from != "PLAY" && $from != "COMBATCHAINATTACKS") return false;
      if (GetUntapped($player, "MYITEMS", "subtype=Cog") == "") return true;
      if ($from == "PLAY" && $combatChain[11] >= 3) return true;
      if ($from == "COMBATCHAINATTACKS" && $chainLinks[$index][9] >= 3) return true;
      return false;
// CombatChainPayAdditionalCosts()
$inds = GetUntapped($currentPlayer, "MYITEMS", "subtype=Cog");
      if($inds != "") {//Tap(explode(",", $inds)[0], $currentPlayer);
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, $inds);
        AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("MZTAP", $currentPlayer, "<-", 1);
      }
      if ($from == "PLAY") ++$combatChain[$i + 11];
      else ++$chainLinks[$i][9];
      break;
// SEAPlayAbility()
if ($from == "PLAY") {
        AddDecisionQueue("BUTTONINPUTNOPASS", $currentPlayer, "+1 Power,Go Again");
        AddDecisionQueue("SPECIFICCARD", $currentPlayer, "COGCONTROL-".$cardID, 1);
      }
      elseif ($from == "COMBATCHAINATTACKS") WriteLog("For now activating " . CardLink($cardID, $cardID) . " on a previous chain link will have no effect");
      return "";
// SEAHitEffect()
WriteLog(CardLink($cardID, $cardID) . " untap all the cogs Player " . $mainPlayer . " control.");
      AddDecisionQueue("UNTAPALL", $mainPlayer, "MYITEMS:subtype=Cog", 1);
      break;
```

### soul_cleaver_blue  — looks-aligned
text: 'If the defending hero has 1 or more cards in their soul, this gets **go again**.\n\n**Blood Debt**'
```json
{
  "slug": "soul_cleaver_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BLOOD_DEBT_FLAG"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DTDPlayAbility()
$theirSoul = &GetSoul($otherPlayer);
      if(count($theirSoul) > 0) GiveAttackGoAgain();
      return "";
```

### ragamuffins_hat  — looks-aligned
text: "**Instant** - Destroy Ragamuffin's Hat: Draw a card then put a card from your hand on the top or bottom of your deck. Activate this ability only if you have 1 card in hand."
```json
{
  "slug": "ragamuffins_hat",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "HAND",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "PUT_HAND_CARD_BOTTOM"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return count($myHand) != 1;
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// ELEAbilityType()
case "ragamuffins_hat": case "runaways": return "I";
// ELETalentPlayAbility()
$deck = new Deck($currentPlayer);
        SetClassState($currentPlayer, $CS_CardsInDeckBeforeOpt, $deck->RemainingCards());
        Draw($currentPlayer);
        AddDecisionQueue("FINDINDICES", $currentPlayer, "HAND");
        AddDecisionQueue("CHOOSEHAND", $currentPlayer, "<-", 1);
        AddDecisionQueue("MULTIREMOVEHAND", $currentPlayer, "-", 1);
        AddDecisionQueue("OPT", $currentPlayer, "<-");
        return "";
```

### mage_master_boots  — looks-aligned
text: '**Action** - {r}, destroy this: The next non-attack action card you play this turn gets **go again**. **Go again**'
```json
{
  "slug": "mage_master_boots",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "MAGE_MASTER_BOOTS_FLAG"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// ARCGenericPlayAbility()
SetClassState($currentPlayer, $CS_NextNAACardGoAgain, 1);
      AddCurrentTurnEffect($cardID, $currentPlayer); 
      return "";
// ARCAbilityCost()
case "mage_master_boots": return 1;
// ARCAbilityType()
case "bracers_of_belief": case "mage_master_boots": return "A";
// ARCAbilityHasGoAgain()
case "bracers_of_belief": case "mage_master_boots": return true;
```

### bite_red  — looks-aligned
text: '**Stealth**\n\nWhen this attacks a hero, you may have target dagger you control deal 1 damage to them. If damage is dealt this way, the dagger has hit. Destroy the dagger.'
```json
{
  "slug": "bite_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "MAY",
          "effects": [
            {
              "type": "DAGGER_DEALS_DAMAGE",
              "amount": 1
            },
            {
              "type": "DESTROY_REF",
              "target": "DAGGER"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
ThrowWeapon("Dagger", $parameter, target:$target);
        break;
// DecisionQueueStaticEffect()
$targetParts = explode("-", $target);
          $targetLoc = $targetParts[0];
          $targetInd = $targetParts[1];
          if ($targetLoc == "MYCHAR") {
            $targetInd = GetMZUID($player, $target);
          }
          AddLayer("TRIGGER", $player, $params[0], "$targetLoc,$targetInd");
          break;
// HNTPlayAbility()
if (IsHeroAttackTarget())
      {
        AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYCHAR:subtype=Dagger&COMBATCHAINATTACKS:subtype=Dagger;type=AA");
        AddDecisionQueue("REMOVEINDICESIFACTIVECHAINLINK", $currentPlayer, "<-", 1);
        AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);
        AddDecisionQueue("ADDTRIGGER", $currentPlayer, $cardID, 1);
      }
      break;
```

### force_sight_red  — looks-aligned
text: 'The next attack action card you play this turn gains +3{p}.\n\nIf Force Sight is played from arsenal, **opt 2**.\n\n**Go again**'
```json
{
  "slug": "force_sight_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "PLAYED_FROM_ARSENAL",
              "value": false
            }
          ]
        },
        {
          "type": "OPT",
          "amount": 2,
          "conditions": [
            {
              "type": "PLAYED_FROM_ARSENAL",
              "value": true
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCGenericPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      if($from == "ARS") {
        PlayerOpt($currentPlayer, 2);
        $rv = "Was played from arsenal and lets you Opt 2";
      }
      return $rv;
// ARCEffectPowerModifier()
case "force_sight_red": return 3;
// ARCCombatEffectActive()
case "force_sight_red": case "force_sight_yellow": case "force_sight_blue": return CardType($attackID) == "AA";
```

### companion_of_the_claw_yellow  — looks-aligned
text: "When this attacks, if you've pitched a blue card this turn, create a Crouching Tiger in your hand.\n\n**Go again**"
```json
{
  "slug": "companion_of_the_claw_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "PITCHED_BLUE_CARD"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token": "Crouching Tiger",
          "zone": "HAND"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTPlayAbility()
if (SearchPitchForColor($currentPlayer, 3) > 0) AddPlayerHand("crouching_tiger", $currentPlayer, $cardID, created:true);
      return "";
```

### phantasmal_haze_red  — looks-aligned
text: '**Phantasm**\n\nWhen Phantasmal Haze is destroyed, create a Spectral Shield token.'
```json
{
  "slug": "phantasmal_haze_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEATH",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token": "Spectral Shield"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AttackDestroyed()
PlayAura("spectral_shield", $mainPlayer);
      break;
```

### double_trouble_yellow  — looks-aligned
text: '**Stealth**\n\nIf you\'ve played or activated 2 or more attack reactions this chain link, this gets +2{p} and "When this hits a hero, banish the top 2 cards of their deck."'
```json
{
  "slug": "double_trouble_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "CHAIN_HIT_COUNT_GTE",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddOnHitTrigger()
if (IsHeroAttackTarget() && NumAttackReactionsPlayed() > 1) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "ONHITEFFECT");
        return true;
      }
      break;
// PowerModifier()
$power += NumAttackReactionsPlayed() > 1 ? 2 : 0;
        break;
// MSTHitEffect()
$deck->BanishTop("Source-" . $attackCard, banishedBy: $attackCard);
      $deck->BanishTop("Source-" . $attackCard, banishedBy: $attackCard);
      break;
```

### cogwerx_base_arms  — looks-aligned
text: "When this is equipped, put a steam counter on it.\n\n**Once per Turn Instant** - {r}, remove a steam counter from this: Your next Mechanologist attack this turn gets +1{p}. Activate this ability only if you've **boosted** this turn."
```json
{
  "slug": "cogwerx_base_arms",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_EQUIP",
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter_type": "steam",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "per_turn": 1,
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BOOSTED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "target": {
            "filter": [
              {
                "type": "ATTACK_CLASS_IN",
                "classes": [
                  "mechanologist"
                ]
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return $character[$index + 2] == 0 || GetClassState($player, $CS_NumBoosted) == 0;
// EquipPayAdditionalCosts()
$character[$cardIndex + 2] = 0;
      break;
// EquipmentsUsingSteamCounter()
return true;
// EVOPlayAbility()
AddCurrentTurnEffectNextAttack($cardID, $mainPlayer);
      return "";
```

### destructive_deliberation_yellow  — looks-aligned
text: 'When this hits a hero, create a Ponder token.'
```json
{
  "slug": "destructive_deliberation_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Ponder"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTHitEffect()
PlayAura("ponder", $mainPlayer);//Ponder
        break;
```

### vela_flash_yellow  — looks-aligned
text: "**Lightning Fusion**\n\nIf Vela Flash was **fused**, you may play your next 'non-attack' action card this turn as though it were an instant."
```json
{
  "slug": "vela_flash_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "VELA_FLASH_FUSION_ACTIVE"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_PLAY_ACTIVATE_ATTACK",
            "conditions": [
              {
                "type": "NOT",
                "condition": {
                  "type": "ATTACK_SUBTYPE_IN",
                  "subtypes": [
                    "Attack"
                  ]
                }
              }
            ],
            "effects": [
              {
                "type": "ACTIVATE",
                "activation_cost": 0
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// FuseAbility()
case "vela_flash_red": case "vela_flash_yellow": case "vela_flash_blue": SetClassState($player, $CS_NextNAAInstant, 1); break;
// HasFusion()
case "vela_flash_red": case "vela_flash_yellow": case "vela_flash_blue": return "LIGHTNING";
```

### invigorating_light_blue  — looks-aligned
text: "When you play Invigorating Light, if there are no cards in your hero's soul, put it into your hero's soul when the combat chain closes."
```json
{
  "slug": "invigorating_light_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PLAY",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "SOUL",
          "amount": 0
        }
      ],
      "effects": [
        {
          "type": "MOVE_REF",
          "target": "self",
          "destination": "SOUL"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// GoesWhereAfterResolving()
return $from == "CHAINCLOSING" && SearchCurrentTurnEffects($cardID, $mainPlayer) ? "SOUL" : "GY";
// MONTalentPlayAbility()
if(count(GetSoul($currentPlayer)) == 0) AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### fyendals_fighting_spirit_red  — looks-aligned
text: 'When this attacks or defends, if you have less {h} than an opposing hero, gain 1{h}.'
```json
{
  "slug": "fyendals_fighting_spirit_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "HEALTH_LT_OPP"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "LIFE",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "HEALTH_LT_OPP"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "LIFE",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
if (PlayerHasLessHealth($player)) GainHealth(1, $player);
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
// UPRTalentPlayAbility()
if(PlayerHasLessHealth($currentPlayer)) { GainHealth(1, $currentPlayer); }
        return "";
```

### peace_of_mind_blue  — looks-aligned
text: 'The next time you would be dealt {p} damage, prevent 2 of that damage.\n\nCreate a Ponder token.'
```json
{
  "slug": "peace_of_mind_blue",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "PAY_LIFE",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Ponder"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CurrentTurnEffectDamagePreventionAmount()
if ($type == "COMBAT") {
        return 2;
      }
      break;
// CurrentEffectDamagePrevention()
if ($type == "COMBAT") {
        if ($preventable) $preventedDamage += 2;
        RemoveCurrentTurnEffect($index);
      }
      break;
// OUTPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        PlayAura("ponder", $currentPlayer);
        return "Prevents some of the next combat damage you take this turn.";
```

### blessing_of_qi_red  — looks-aligned
text: 'At the start of your turn, destroy this, then create a Crouching Tiger in your banished zone. It gains +3{p} and you may play it this turn.'
```json
{
  "slug": "blessing_of_qi_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "effects": [
        {
          "type": "DESTROY_REF",
          "target": "self"
        },
        {
          "type": "CREATE_TOKEN",
          "token": "Crouching Tiger",
          "zone": "BANISHED",
          "effects": [
            {
              "type": "MODIFY_ATTACK",
              "mod": "add",
              "amount": 3
            },
            {
              "type": "SET_FLAG",
              "flag": "PLAYABLE_THIS_TURN"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
if ($auras[$i] == "blessing_of_qi_red") $amount = 3;
        else $amount = ($auras[$i] == "blessing_of_qi_yellow") ? 2 : 1;
        $index = BanishCardForPlayer("crouching_tiger", $mainPlayer, "-", "TT", $mainPlayer, created:true);
        $banish = new Banish($mainPlayer);
        AddDecisionQueue("PASSPARAMETER", $mainPlayer, $banish->Card($index)->UniqueID());
        AddDecisionQueue("ADDLIMITEDCURRENTEFFECT", $mainPlayer, $auras[$i] . ",BANISH");
        DestroyAuraUniqueID($mainPlayer, $auras[$i + 6]);
        break;
// DYNEffectPowerModifier()
case "blessing_of_qi_red": return 3;
// DYNCombatEffectActive()
case "blessing_of_qi_red": case "blessing_of_qi_yellow": case "blessing_of_qi_blue": return CardNameContains($attackID, "Crouching Tiger", $mainPlayer);
```

### pry_yellow  — looks-aligned
text: 'Target hero reveals 2 cards from their hand. If Pry is played during an opponents turn, instead they reveal all cards in their hand.\n\nYou may choose a card revealed this way. If you do, that hero puts it on the bottom of their deck then draws a card.'
```json
{
  "slug": "pry_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "REVEAL_HAND_MARK_IF_TYPE",
          "amount": 2,
          "conditions": [
            {
              "type": "IS_ACTIVE_PLAYER",
              "value": false
            }
          ]
        },
        {
          "type": "REVEAL_HAND_MARK_IF_TYPE",
          "amount": "ALL",
          "conditions": [
            {
              "type": "IS_ACTIVE_PLAYER",
              "value": true
            }
          ]
        },
        {
          "type": "OPT",
          "amount": 1,
          "conditions": [
            {
              "type": "REF_EXISTS",
              "ref": "REVEALED_CARDS"
            }
          ]
        },
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": 1,
          "conditions": [
            {
              "type": "REF_EXISTS",
              "ref": "SELECTED_CARD"
            }
          ]
        },
        {
          "type": "DRAW",
          "amount": 1,
          "conditions": [
            {
              "type": "REF_EXISTS",
              "ref": "SELECTED_CARD"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVRPlayAbility()
if($mainPlayer != $currentPlayer) $numReveal = count(GetHand($otherPlayer));
        else $numReveal = match($cardID) { "pry_red" => 3, "pry_yellow" => 2, default => 1 };
        AddDecisionQueue("PASSPARAMETER", $mainPlayer, $numReveal);
        AddDecisionQueue("SETDQVAR", $currentPlayer, "0");
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose target hero");
        AddDecisionQueue("BUTTONINPUT", $currentPlayer, "Target_Opponent,Target_Yourself");
        AddDecisionQueue("PLAYERTARGETEDABILITY", $currentPlayer, "PRY", 1);
        return "";
```

### eradicate_yellow  — looks-aligned
text: "**Contract** - You are contracted to banish opponents' yellow cards. Whenever you complete this contract, create a Silver token.\n\nWhen this hits a hero, banish the top X cards of their deck, where X is the damage dealt by Eradicate."
```json
{
  "slug": "eradicate_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "amount": "DAMAGE_AMOUNT"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNHitEffect()
if(IsHeroAttackTarget()) {
        $deck = new Deck($defPlayer);
        if($deck->Empty()) { WriteLog("The opponent deck is already... depleted."); break; }
        if($deck->RemainingCards() < $combatChainState[$CCS_DamageDealt]) $deck->BanishTop(banishedBy:$cardID, amount:$deck->RemainingCards());
        else $deck->BanishTop(banishedBy:$cardID, amount:$combatChainState[$CCS_DamageDealt]);
      }
      break;
// ContractType()
case "eradicate_yellow": return "YELLOWPITCH";
// ContractCompleted()
$EffectContext = $cardID;
      PutItemIntoPlayForPlayer("silver", $player);
      break;
```

### charge_of_the_light_brigade_blue  — looks-aligned
text: 'The next attack you **charge** to play this turn gets +1{p}.\n\n**Go again**'
```json
{
  "slug": "charge_of_the_light_brigade_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "CHARGED_ATTACK"
            }
          ]
        },
        {
          "type": "SET_FLAG",
          "flag": "CHARGED_ATTACK"
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DTDEffectPowerModifier()
case "charge_of_the_light_brigade_blue": return 1;
// DTDCombatEffectActive()
case "charge_of_the_light_brigade_red": case "charge_of_the_light_brigade_yellow": case "charge_of_the_light_brigade_blue": return $combatChainState[$CCS_AttackNumCharged] > 0;//Charge of the Light Brigade
// DTDPlayAbility()
case "charge_of_the_light_brigade_red": case "charge_of_the_light_brigade_yellow": case "charge_of_the_light_brigade_blue"://Charge of the Light Brigade
```

### stir_the_wildwood_blue  — looks-aligned
text: '**Earth Fusion**\n\nIf you have dealt arcane damage to an opposing hero this turn, Stir the Wildwood gains +2{p}.\n\nIf Stir the Wildwood was **fused**, it gains +2{p}.'
```json
{
  "slug": "stir_the_wildwood_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DEALT_ARCANE_DAMAGE_TO_OPPONENT"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FUSED"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += GetClassState($defPlayer, $CS_ArcaneDamageTaken) >= 1 ? 2 : 0;
        break;
// FuseAbility()
case "stir_the_wildwood_red": case "stir_the_wildwood_yellow": case "stir_the_wildwood_blue": AddCurrentTurnEffect($cardID, $player); break;
// HasFusion()
case "stir_the_wildwood_red": case "stir_the_wildwood_yellow": case "stir_the_wildwood_blue": return "EARTH";
// ELEEffectPowerModifier()
case "stir_the_wildwood_red": case "stir_the_wildwood_yellow": case "stir_the_wildwood_blue": return 2;
// ELECombatEffectActive()
case "stir_the_wildwood_red": case "stir_the_wildwood_yellow": case "stir_the_wildwood_blue": return true;
```

### krakens_aethervein  — looks-aligned
text: '**Once per Turn Instant** - {r}{r}{r}: Deal 1 arcane damage to target opposing hero. Draw a card for each arcane damage dealt this way.'
```json
{
  "slug": "krakens_aethervein",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 3,
      "per_turn": 1,
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        },
        {
          "type": "DRAW",
          "amount": "DEAL_ARCANE_AMOUNT"
        }
      ],
      "target": {
        "filter": [
          {
            "type": "ATTACK_TARGET_IS_HERO",
            "opponent": true
          }
        ]
      }
    }
  ]
}
```
Talishar:
```php
// EVRAbilityCost()
case "krakens_aethervein": return 3;
// EVRAbilityType()
case "krakens_aethervein": return "I";
// EVRPlayAbility()
DealArcane(1, 1, "ABILITY", $cardID);
        AddDecisionQueue("SPECIFICCARD", $currentPlayer, "KRAKENAETHERVEIN");
        return "";
```

### ironsong_response_blue  — looks-aligned
text: '**Reprise** - If the defending hero has defended with a card from their hand this chain link, target weapon attack gains +1{p}.'
```json
{
  "slug": "ironsong_response_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "DEFENDS_WITH_OTHER_HAND_CARD"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ],
      "target": {
        "filter": [
          {
            "type": "ATTACK_SUBTYPE_IN",
            "subtypes": [
              "weapon"
            ]
          }
        ]
      }
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if (!$CombatChain->HasCurrentLink()) return true;
      if (!RepriseActive()) return false;
      return !TypeContains($attackID, "W", $mainPlayer);
// ReactionRequirementsMet()
case "stroke_of_foresight_red": case "stroke_of_foresight_yellow": case "stroke_of_foresight_blue": return TypeContains($combatChain[0], "W", $mainPlayer);
// WTREffectPowerModifier()
case "ironsong_response_blue": return 1;
// WTRCombatEffectActive()
case "ironsong_response_red": case "ironsong_response_yellow": case "ironsong_response_blue": return true;
// WTRPlayAbility()
if (!str_contains($target, "COMBATCHAINATTACKS") && $repriseActive) AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### arcane_seeds__life_red  — looks-aligned
text: '**Meld**\n\nCreate a Runechant token. Create a Runechant token.\n\n**Go again**\n\n//\n\nGain 1{h}'
```json
{
  "slug": "arcane_seeds__life_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        },
        {
          "type": "GAIN",
          "asset": "LIFE_POINTS",
          "amount": 1
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CardClass()
if(function_exists("GetClassState")) {
        if (IsMeldInstantName(GetClassState($currentPlayer, $CS_AdditionalCosts))) return "NONE";
      }
      return "RUNEBLADE";
// CardTalent()
if(function_exists("GetClassState") && $from == "-") {
        if(IsMeldLeftSideName(GetClassState($currentPlayer, $CS_AdditionalCosts))) return "NONE";
        return "EARTH";
      }
      return "EARTH";
// ProcessMeld()
PlayAura("runechant", $player);
      PlayAura("runechant", $player);
      break;
```

### art_of_the_dragon_blood_red  — looks-aligned
text: 'When this attacks, if it is Draconic, it gets **go again** and the next 3 Draconic cards you play this turn cost {r} less to play.'
```json
{
  "slug": "art_of_the_dragon_blood_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "Draconic"
        }
      ],
      "effects": [
        {
          "type": "GO_AGAIN"
        },
        {
          "type": "SET_FLAG",
          "flag": "DRACONIC_ATTACK_GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DRACONIC_ATTACK_GO_AGAIN"
        },
        {
          "type": "DURING_TURN"
        },
        {
          "type": "HAS_KEYWORD",
          "keyword": "Draconic"
        }
      ],
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "amount": -1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CurrentTurnEffectUses()
return 3;
// DoesAttackHaveGoAgain()
$attackUniqueID = $CombatChain->AttackCard()->UniqueID();
      return SearchCurrentTurnEffects("art_of_the_dragon_blood_red-$attackUniqueID", $mainPlayer);
// HNTPlayAbility()
$uniqueID = $CombatChain->AttackCard()->UniqueID();
      if(TalentContains($cardID, "DRACONIC", $currentPlayer)) {
        AddCurrentTurnEffect("$cardID-$uniqueID", $currentPlayer);
      }
      break;
```

### drawn_to_the_dark_dimension_blue  — looks-aligned
text: 'Drawn to the Dark Dimension costs {r} less to play for each Runechant you control.\n\nDraw a card.'
```json
{
  "slug": "drawn_to_the_dark_dimension_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "PAY_LIFE",
          "amount": "RUNECHANTS_CONTROLLED"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SelfCostModifier()
return -1 * NumRunechants($currentPlayer);
// ARCRunebladePlayAbility()
case "drawn_to_the_dark_dimension_red": case "drawn_to_the_dark_dimension_yellow": case "drawn_to_the_dark_dimension_blue": Draw($currentPlayer); return "";
```

### towering_titan_blue  — looks-aligned
text: 'At the beginning of your action phase, destroy Towering Titan then the next Guardian attack action card you play this turn gains +8{p}.'
```json
{
  "slug": "towering_titan_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_REF",
          "target": "self"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        },
        {
          "type": "CARD_IN_ZONE",
          "zones": [
            "arsenal"
          ],
          "card_type": "ACTION",
          "classes": [
            "Guardian"
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 8
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraBeginningActionPhaseAbilities()
AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", "DESTROY", $auras[$i + 6]);
        break;
// ProcessTrigger()
AddCurrentTurnEffect($parameter, $player);
        DestroyAuraUniqueID($player, $uniqueID);
        break;
// CRUEffectPowerModifier()
case "towering_titan_blue": return 8;
// CRUCombatEffectActive()
case "towering_titan_red": case "towering_titan_yellow": case "towering_titan_blue": return CardType($attackID) == "AA" && ClassContains($attackID, "GUARDIAN", $mainPlayer);
```

### tide_chakra_yellow  — looks-aligned
text: "Target Assassin or Mystic attack action card gets +2{p}. If you've **transcended** this turn, instead it gets +4{p}."
```json
{
  "slug": "tide_chakra_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ],
      "target": {
        "filter": [
          {
            "type": "ATTACK_CLASS_IN",
            "classes": [
              "assassin",
              "mystic"
            ]
          }
        ]
      },
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "TRANSCENDED"
        }
      ],
      "additional_effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if (!$CombatChain->HasCurrentLink()) return true;
      if (CardType($attackID) == "AA" && (ClassContains($attackID, "ASSASSIN", $player) || TalentContains($attackID, "MYSTIC", $player))) return false;
      return true;
// MSTPlayAbility()
if (GetClassState($currentPlayer, $CS_Transcended) <= 0) AddCurrentTurnEffect($cardID . "-1", $currentPlayer);
      else AddCurrentTurnEffect($cardID . "-2", $currentPlayer);
      return "";
```

### sheltered_cove  — looks-aligned
text: '**Instant** - {r}{r}{r}, destroy this: The next time you would be dealt damage this turn, prevent 2 of that damage'
```json
{
  "slug": "sheltered_cove",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 3,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "SHIELDED",
          "duration": "TURN"
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SHIELDED",
          "negate": true
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// CurrentTurnEffectDamagePreventionAmount()
return 2;
// CurrentEffectDamagePrevention()
if ($preventable) $preventedDamage += 2;
      RemoveCurrentTurnEffect($index);
      break;
// HVYPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### splintering_deadwood_blue  — looks-aligned
text: 'When this attacks or hits, you may destroy an aura you control. If you do, create a Runechant token.'
```json
{
  "slug": "splintering_deadwood_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "OPT",
          "amount": 1
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "OPT",
          "amount": 1
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ROSPlayAbility()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYAURAS");
      AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("MZDESTROY", $currentPlayer, "-", 1);
      AddDecisionQueue("PLAYAURA", $currentPlayer, "runechant", 1);
      return "";
// ROSHitEffect()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYAURAS");
      AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("MZDESTROY", $currentPlayer, "-", 1);
      AddDecisionQueue("PLAYAURA", $currentPlayer, "runechant", 1);
      break;
```

### entwine_lightning_blue  — looks-aligned
text: '**Lightning Fusion**\n\nIf Entwine Lightning was **fused**, it gains **go again**.'
```json
{
  "slug": "entwine_lightning_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FUSION"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// FuseAbility()
case "entwine_lightning_red": case "entwine_lightning_yellow": case "entwine_lightning_blue": GiveAttackGoAgain(); break;
// HasFusion()
case "entwine_lightning_red": case "entwine_lightning_yellow": case "entwine_lightning_blue": return "LIGHTNING";
```

### infuse_alloy_yellow  — looks-aligned
text: '**Galvanize** - When this defends, you may destroy an item you control. If you do, this gets +2{d}.'
```json
{
  "slug": "infuse_alloy_yellow",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "effects": [
        {
          "type": "OPT",
          "amount": 1
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zones": [
                  "arsenal"
                ],
                "subtypes": [
                  "Item"
                ]
              }
            ]
          }
        },
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "amount": 2,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "OPT_1_USED"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
case "steel_street_hoons_blue": //Galvanize
```

### thistle_bloom__life_yellow  — looks-aligned
text: "**Meld**\n\nCreate X Runechant tokens, where X is the total {h} you've gained this turn.\n\n//\n\nGain 1{h}"
```json
{
  "slug": "thistle_bloom__life_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant",
          "amount": "TOTAL_HEALTH_GAINED_THIS_TURN"
        },
        {
          "type": "GAIN",
          "asset": "HEALTH_POINTS",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CardClass()
if(function_exists("GetClassState")) {
        if (IsMeldInstantName(GetClassState($currentPlayer, $CS_AdditionalCosts))) return "NONE";
      }
      return "RUNEBLADE";
// CardTalent()
if(function_exists("GetClassState") && $from == "-") {
        if(IsMeldLeftSideName(GetClassState($currentPlayer, $CS_AdditionalCosts))) return "NONE";
        return "EARTH";
      }
      return "EARTH";
// ProcessMeld()
PlayAura("runechant", $player, GetClassState($player, $CS_HealthGained));
      break;
```

### aether_flare_blue  — looks-aligned
text: 'Deal 1 arcane damage to target opposing hero.\n\nThe next card you play this turn with an effect that deals arcane damage, instead deals that much arcane damage plus X, where X is the damage dealt by Aether Flare.'
```json
{
  "slug": "aether_flare_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        },
        {
          "type": "SET_FLAG",
          "flag": "AETHER_FLARE_DEALT"
        }
      ],
      "target": {
        "filter": [
          {
            "type": "CARD_IN_ZONE",
            "zones": [
              "opponent"
            ]
          }
        ]
      }
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "AETHER_FLARE_DEALT"
        },
        {
          "type": "AND",
          "conditions": [
            {
              "type": "IS_ACTIVE_PLAYER"
            },
            {
              "type": "OR",
              "conditions": [
                {
                  "type": "ATTACK_HAS_KEYWORD",
                  "keyword": "DEAL_ARCANE"
                },
                {
                  "type": "ATTACK_HAS_KEYWORD",
                  "keyword": "DEAL_GENERIC"
                }
              ]
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": "AETHER_FLARE_DAMAGE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EffectArcaneBonus()
return intval($modifier);
// ARCWizardPlayAbility()
DealArcane(ArcaneDamage($cardID), 1, "PLAYCARD", $cardID, resolvedTarget: $target);
      AddDecisionQueue("BUFFARCANE", $currentPlayer, $cardID, 1);
      return "";
// PlayRequiresTarget()
return 1;
// ArcaneModifierAmount()
return $effectArr[1];
// ActionsThatDoArcaneDamage()
return true;
```

### barraging_big_horn_blue  — looks-aligned
text: 'As an additional cost to play Barraging Big Horn, discard a random card.\n\nWhile Barraging Big Horn is defended by less than 2 non-equipment cards, it has **go again**.'
```json
{
  "slug": "barraging_big_horn_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "DISCARD_RANDOM"
        }
      ],
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ],
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_CONTROLLED_BY_YOU"
            },
            {
              "type": "DEFENDER_USED_HAND_CARD",
              "amount": {
                "type": "LT",
                "value": 2
              },
              "filter": [
                {
                  "type": "NOT",
                  "condition": {
                    "type": "HAS_SUBTYPE",
                    "subtypes": [
                      "Equipment"
                    ]
                  }
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
if (NumCardsNonEquipBlocking() < 2) return true;
```

### slay_the_scholars_red  — looks-aligned
text: "**Contract** - You are contracted to banish opponents' 'non-attack' action cards. Whenever you complete this contract, create a Silver token.\n\nWhen this hits a hero, banish the top card of their deck."
```json
{
  "slug": "slay_the_scholars_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": {
            "type": "TOP_CARD",
            "controller": "opponent"
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNHitEffect()
if(IsHeroAttackTarget()) {
        $deck = new Deck($defPlayer);
        if($deck->Empty()) { WriteLog("The opponent deck is already... depleted."); break; }
        $deck->BanishTop(banishedBy:$cardID);
      }
      break;
// ContractType()
case "slay_the_scholars_red": case "slay_the_scholars_yellow": case "slay_the_scholars_blue": return "NAA";
// ContractCompleted()
$EffectContext = $cardID;
      PutItemIntoPlayForPlayer("silver", $player);
      break;
```

### bonds_of_ancestry_red  — looks-aligned
text: '**Combo** - If a card with Gustwave in its name was the last attack this combat chain, this costs {r}{r} less to play, and has **go again** and "When this attacks, you may banish a card with **combo** from your graveyard. If you do, search your deck for a card with the same name, banish it, then shuffle. You may play it this combat chain."'
```json
{
  "slug": "bonds_of_ancestry_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "PAY_LIFE",
          "amount": 2
        }
      ],
      "conditions": [
        {
          "type": "COMBO_CONTAINS",
          "card_name": "Gustwave"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 2
        },
        {
          "type": "GO_AGAIN"
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_ATTACK",
          "effects": [
            {
              "type": "BANISH_REF",
              "target": {
                "filter": [
                  {
                    "type": "CARD_IN_ZONE",
                    "zone": "GRAVEYARD"
                  },
                  {
                    "type": "HAS_KEYWORD",
                    "keyword": "COMBO"
                  }
                ]
              }
            },
            {
              "type": "SEARCH_DECK",
              "target": {
                "filter": [
                  {
                    "type": "SAME_NAME",
                    "card_name": "Gustwave"
                  }
                ]
              },
              "action": "BANISH",
              "then": [
                {
                  "type": "SHUFFLE_DECK"
                }
              ]
            },
            {
              "type": "PLAY_ACTIVATE_ATTACK",
              "target": {
                "filter": [
                  {
                    "type": "SAME_NAME",
                    "card_name": "Gustwave"
                  }
                ]
              }
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if (str_contains($lastAttackName, "Gustwave")) return true;
        break;
// ProcessAttackTrigger()
GiveAttackGoAgain();
      AddDecisionQueue("MULTIZONEINDICES", $player, "MYDISCARD:comboOnly=true");
      AddDecisionQueue("SETDQCONTEXT", $player, "Choose a card with Combo to banish from your graveyard");
      AddDecisionQueue("MAYCHOOSEMULTIZONE", $player, "<-", 1);
      AddDecisionQueue("MZBANISH", $player, "GY,-," . $player, 1);
      AddDecisionQueue("MZREMOVE", $player, "-", 1);
      AddDecisionQueue("PREPENDLASTRESULT", $player, "isSameName=", 1);
      AddDecisionQueue("SETDQVAR", $player, "search", 1);
      AddDecisionQueue("PASSPARAMETER", $player, "Search", 1);
      AddDecisionQueue("MAYSEARCHDECK", $player, "-,MYBANISH,false,TCC", 1);
      break;
// SelfCostModifier()
return ComboActive($cardID) ? -2 : 0;
// OUTPlayAbility()
if(ComboActive())
        {
          AddLayer("TRIGGER", $currentPlayer, $cardID, "-", "ATTACKTRIGGER");
        }
        return "";
```

### reel_in_blue  — looks-aligned
text: 'Look at the top X+1 cards of your deck. Choose up to 4 traps, reveal them, put them into your hand, then shuffle.\n\n**Reload**'
```json
{
  "slug": "reel_in_blue",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "REVEAL_CARD_COST_GTE",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "LOOK_AT",
          "amount": "X+1"
        },
        {
          "type": "SEARCH_DECK",
          "amount": 4,
          "filter": [
            {
              "type": "CARD_IN_ZONE",
              "zones": [
                "deck"
              ],
              "subtypes": [
                "trap"
              ]
            }
          ]
        },
        {
          "type": "REVEAL_TOP_DECK",
          "amount": "X+1"
        },
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": "X+1"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DynamicCost()
return "0,1,2,3,4,5,6,7,8,9,10,11,12";
// HVYPlayAbility()
AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Here are the top " . ($resourcesPaid + 1) . " cards of your deck.", 1);
      AddDecisionQueue("FINDINDICES", $currentPlayer, "DECKTOPXINDICES," . ($resourcesPaid + 1));
      AddDecisionQueue("DECKCARDS", $currentPlayer, "<-", 1);
      AddDecisionQueue("LOOKTOPDECK", $currentPlayer, "-", 1);
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, CardLink($cardID, $cardID) . " shows the top cards of your deck are", 1);
      AddDecisionQueue("MULTISHOWCARDSDECK", $currentPlayer, "<-", 1);
      AddDecisionQueue("FINDINDICES", $currentPlayer, "DECKTOPXINDICES," . ($resourcesPaid + 1));
      AddDecisionQueue("DECKCARDS", $currentPlayer, "<-", 1);
      AddDecisionQueue("TOPDECKCHOOSE", $currentPlayer, 4 . ",Trap", 1);
      AddDecisionQueue("MULTICHOOSEDECK", $currentPlayer, "<-", 1);
      AddDecisionQueue("MULTIREMOVEDECK", $currentPlayer, "-", 1);
      AddDecisionQueue("MULTIADDHAND", $currentPlayer, "-", 1);
      AddDecisionQueue("REVEALCARDS", $currentPlayer, "-", 1);
      AddDecisionQueue("SHUFFLEDECK", $currentPlayer, "-", 1);
      AddDecisionQueue("ELSE", $currentPlayer, "-");
      AddDecisionQueue("SHUFFLEDECK", $currentPlayer, "-", 1);
      Reload();
      return "";
```

### break_ground_red  — looks-aligned
text: 'When you attack with Break Ground, you may put a card from your arsenal on the bottom of your deck. If you do, draw a card.'
```json
{
  "slug": "break_ground_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": 1,
          "zone": "arsenal"
        },
        {
          "type": "DRAW",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "PUT_CARDS_BOTTOM_FLAG"
            }
          ]
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "PUT_CARDS_BOTTOM_FLAG"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ELETalentPlayAbility()
MZMoveCard($currentPlayer, "MYARS", "MYBOTDECK", may:true, silent:true);
        AddDecisionQueue("DRAW", $currentPlayer, "-", 1);
        return "";
```

### knife_through_butter_blue  — looks-aligned
text: 'Your next dagger attack this turn gets +2{p}.\n\nWhenever you attack a **marked** hero this turn, the attack gets **go again**.\n\n**Go again**'
```json
{
  "slug": "knife_through_butter_blue",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2,
          "conditions": [
            {
              "type": "ATTACK_TYPE_IN",
              "types": [
                "dagger"
              ]
            }
          ]
        },
        {
          "type": "GO_AGAIN",
          "conditions": [
            {
              "type": "ATTACK_TARGET_IS_HERO",
              "conditions": [
                {
                  "type": "OPPONENT_IS_MARKED"
                }
              ]
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HNTPlayAbility()
AddCurrentTurnEffect($cardID."-BUFF", $currentPlayer);
      AddCurrentTurnEffect($cardID."-GOAGAIN", $currentPlayer);
      break;
```

### goblet_of_bloodrun_wine_blue  — looks-aligned
text: 'Create an Agility and a Vigor token.\n\n**Go again**'
```json
{
  "slug": "goblet_of_bloodrun_wine_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "subtype": "Agility"
        },
        {
          "type": "CREATE_TOKEN",
          "subtype": "Vigor"
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HVYPlayAbility()
PlayAura("agility", $currentPlayer);
      PlayAura("vigor", $currentPlayer);
      return "";
```

### condemn_to_slaughter_yellow  — looks-aligned
text: 'Your next Runeblade attack this turn gets +2{p}.\n\nYou may destroy an aura you control. If you do, each opponent destroys an aura permanent they control.\n\n**Go again**'
```json
{
  "slug": "condemn_to_slaughter_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2,
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "classes": [
                "runeblade"
              ]
            },
            {
              "type": "DURING_TURN"
            }
          ]
        },
        {
          "type": "MAY_DESTROY_SILVERS_TO_EQUIP",
          "target": {
            "filter": [
              {
                "type": "CONTROLS_TOKEN_TYPE",
                "token_types": [
                  "aura"
                ]
              }
            ]
          },
          "effects": [
            {
              "type": "DESTROY_TOKEN",
              "target": {
                "filter": [
                  {
                    "type": "CONTROLS_TOKEN_TYPE",
                    "token_types": [
                      "aura"
                    ]
                  }
                ]
              }
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ROSPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);

      AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYAURAS");
      AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("MZDESTROY", $currentPlayer, "-", 1);
      AddDecisionQueue("MULTIZONEINDICES", $otherPlayer, "MYAURAS", 1);
      AddDecisionQueue("CHOOSEMULTIZONE", $otherPlayer, "<-", 1);
      AddDecisionQueue("MZDESTROY", $otherPlayer, "-", 1);
      return "";
```

### gigawatt_blue  — looks-aligned
text: 'Your next Mechanologist attack this turn gets +2{p}.\n\n**Go again**'
```json
{
  "slug": "gigawatt_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2,
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "classes": [
                "mechanologist"
              ]
            },
            {
              "type": "DURING_TURN"
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVOPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### ornate_tessen  — looks-aligned
text: '**Instant** - {r}, destroy Ornate Tessen: Put a card from your hand on the bottom of your deck. If you do, draw a card.'
```json
{
  "slug": "ornate_tessen",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "PAY_RESOURCES",
          "amount": 1
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "PUT_HAND_CARD_BOTTOM"
        },
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// DYNAbilityCost()
case "ornate_tessen": return 1;
// DYNAbilityType()
case "ornate_tessen": return "I";
// DYNPlayAbility()
BottomDeck($currentPlayer, false, shouldDraw:true);
      return "";
```

### hamstring_shot_red  — looks-aligned
text: 'If Hamstring Shot hits a hero, their first attack during their next turn costs an additional {r}.'
```json
{
  "slug": "hamstring_shot_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "START_OF_TURN",
            "conditions": [
              {
                "type": "REF_PITCH_IS",
                "ref": "ATTACKER",
                "pitch": 1
              }
            ],
            "effects": [
              {
                "type": "PAY_OR_DAMAGE",
                "target": "ATTACKER",
                "resource": "RESOURCE_POINTS",
                "amount": 1,
                "damage": 1
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CurrentEffectCostModifiers()
$resolvedType = GetResolvedAbilityType($cardID, $from);
          if (($cardType == "AA" || $resolvedType == "AA") && ($resolvedType == "AA" || $resolvedType == "")) {
            $costModifier += 1;
            $remove = true;
          }
          break;
// ARCRangerHitEffect()
if(IsHeroAttackTarget()) AddNextTurnEffect($cardID, $defPlayer);
        break;
```

### pass_over_blue  — looks-aligned
text: "**Legendary**\n\nBanish target card from an opposing hero's graveyard.\n\nIf you've played another blue card this turn, **transcend**."
```json
{
  "slug": "pass_over_blue",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "BANISH_FROM_GRAVEYARD",
          "target": "opponent"
        }
      ],
      "effects": [
        {
          "type": "TRANSFORM_HERO",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "HAND",
              "color": "blue"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// GoesWhereAfterResolving()
if (GetClassState($currentPlayer, $CS_NumBluePlayed) > 1) return "-";
        else return "THEIRDISCARD";
// GoesWhereAfterResolving()
if (GetClassState($currentPlayer, $CS_NumBluePlayed) > 1) return "-";
      else return "GY";
// IsPlayRestricted()
return count($otherPlayerDiscard) <= 0;
// GetLayerTarget()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "THEIRDISCARD");
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose target card");
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// MSTPlayAbility()
$params = explode("-", $target);
      $index = SearchdiscardForUniqueID($params[1], $otherPlayer);
      if ($index != -1) {
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, "THEIRDISCARD-" . $index, 1);
        AddDecisionQueue("MZADDZONE", $currentPlayer, "THEIRBANISH,GY,-,$cardID,$currentPlayer", 1);
        AddDecisionQueue("MZREMOVE", $currentPlayer, "-", 1);
      }
      if (GetClassState($currentPlayer, $CS_NumBluePlayed) > 1) AddDecisionQueue("TRANSCEND", $currentPlayer, "MST097_inner_chi_blue," . $from);
      return "";
```

### grains_of_bloodspill  — looks-aligned
text: 'Whenever a weapon attack you control hits, you may pay {r}. If you do, create a Vigor token. \n\n**Temper**'
```json
{
  "slug": "grains_of_bloodspill",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "SOURCE_IS_ATTACK",
          "source": "self"
        },
        {
          "type": "ATTACK_IS_WEAPON"
        }
      ],
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "resource": "RESOURCE_POINTS",
          "amount": 1,
          "on_success": [
            {
              "type": "CREATE_TOKEN",
              "token_type": "Vigor"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessMainCharacterHitEffect()
$hand = &GetHand($player);
      $resources = &GetResources($player);
      if (TypeContains($combatChain[0], "W", $mainPlayer) && (Count($hand) > 0 || $resources[0] > 0)) {
        AddDecisionQueue("YESNO", $player, "if you want to pay 1 to create a " . CardLink("vigor", "vigor"), 0, 1);
        AddDecisionQueue("NOPASS", $player, "-", 1);
        AddDecisionQueue("PASSPARAMETER", $player, "1", 1);
        AddDecisionQueue("PAYRESOURCES", $player, "<-", 1);
        AddDecisionQueue("WRITELOG", $player, CardLink($cardID, $cardID) . " created a " . CardLink("vigor", "vigor") . " token ", 1);
        AddDecisionQueue("PASSPARAMETER", $player, "vigor", 1);
        AddDecisionQueue("PUTPLAY", $player, "-", 1);
        AddDecisionQueue("LOGSTATS", $player, $cardID.",EQUIP,PASSIVE", 1);
      }
      break;
// MainCharacterHitTrigger()
if (TypeContains($attackID, "W", $mainPlayer) && IsCharacterActive($mainPlayer, $i)) {
          AddLayer("TRIGGER", $mainPlayer, $characterID, $damageSource, "MAINCHARHITEFFECT");
        }
        break;
```

### urgent_delivery_yellow  — looks-aligned
text: "When this hits, you may put a Mechanologist item from your hand into the arena with cost less than or equal to the number of times you've **boosted** this combat chain."
```json
{
  "slug": "urgent_delivery_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "OPT",
          "amount": 1
        },
        {
          "type": "PUT_CARDS_BOTTOM",
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zones": [
                  "hand"
                ]
              },
              {
                "type": "SUBTYPE_IN",
                "subtypes": [
                  "Item"
                ]
              },
              {
                "type": "CLASS_IN",
                "classes": [
                  "Mechanologist"
                ]
              },
              {
                "type": "COST_LTE",
                "amount": "BOOST_COUNT"
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNHitEffect()
MZMoveCard($mainPlayer, "MYHAND:subtype=Item;class=MECHANOLOGIST;maxCost=" . $combatChainState[$CCS_NumBoosted], "MYITEMS", may:true);
      break;
```

### dustup_blue  — looks-aligned
text: 'When Dustup hits, create an Ash token, then **transform** up to 1 ash you control into an Aether Ashwing.'
```json
{
  "slug": "dustup_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Ash"
        },
        {
          "type": "TRANSFORM_HERO",
          "from": "Ash",
          "to": "Aether Ashwing",
          "max_count": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// UPRIllusionistHitEffect()
PutPermanentIntoPlay($mainPlayer, "ash");
        Transform($mainPlayer, "Ash", "aether_ashwing", true);
        break;
```

### earthlore_surge_yellow  — looks-aligned
text: 'The next attack action card you play this turn gains +4{p}.\n\n**Go again**'
```json
{
  "slug": "earthlore_surge_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4,
          "conditions": [
            {
              "type": "DURING_TURN"
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ELEEffectPowerModifier()
case "earthlore_surge_yellow": return 4;
// ELECombatEffectActive()
case "earthlore_surge_red": case "earthlore_surge_yellow": case "earthlore_surge_blue": return CardType($attackID) == "AA";
// ELETalentPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### ram_raider_yellow  — looks-aligned
text: 'As an additional cost to play this, banish a random card from your hand. If a card with 6 or more {p} is banished this way, this gets **go again**.\n\n**Blood Debt**'
```json
{
  "slug": "ram_raider_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "DISCARD_RANDOM"
        }
      ],
      "effects": [
        {
          "type": "GO_AGAIN",
          "conditions": [
            {
              "type": "DISCARDED_CARD_POWER_GTE",
              "amount": 6
            }
          ]
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "BLOOD_DEBT"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DTDPlayAbility()
if(ModifiedPowerValue($additionalCosts, $currentPlayer, "HAND", source:$cardID) >= 6) GiveAttackGoAgain();
      return "";
```

### scrap_prospector_blue  — looks-aligned
text: '**Scrap**\n\nWhen this attacks, if it scrapped a card, gain {r}.'
```json
{
  "slug": "scrap_prospector_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SCRAPPED_CARD"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVOPlayAbility()
if (DelimStringContains($additionalCosts, "SCRAP", true)) GainResources($currentPlayer, 1);
      return "";
```

### persuasive_prognosis_blue  — looks-aligned
text: '**Stealth**\n\nWhen this hits a hero, banish the top card of their deck. Then look at their hand and banish a card with the same color as the banished card.\n\nWhenever this banishes an action card, gain 1{h}.'
```json
{
  "slug": "persuasive_prognosis_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": {
            "type": "TOP_DECK",
            "controller": "opponent"
          }
        },
        {
          "type": "LOOK_AT",
          "target": {
            "type": "HAND",
            "controller": "opponent"
          }
        },
        {
          "type": "BANISH",
          "target": {
            "type": "HAND",
            "controller": "opponent",
            "filter": [
              {
                "type": "SAME_COLOR_AS",
                "reference": "BANISHED_TOP_DECK"
              }
            ]
          }
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BANISH",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zones": [
            "BANISHED"
          ],
          "filter": [
            {
              "type": "SUBTYPE_IN",
              "subtypes": [
                "Action"
              ]
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "HEALTH_POINTS",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTHitEffect()
if (IsHeroAttackTarget()) {
        LookAtHand($defPlayer);
        $pitchValue = PitchValue($deck->Top());
        $deck->BanishTop("Source-" . $attackCard, banishedBy: $attackCard);
        AddDecisionQueue("MULTIZONEINDICES", $mainPlayer, "THEIRHAND:pitch=" . $pitchValue);
        AddDecisionQueue("SETDQCONTEXT", $mainPlayer, "Choose which card you want your opponent to banish", 1);
        AddDecisionQueue("CHOOSEMULTIZONE", $mainPlayer, "<-", 1);
        AddDecisionQueue("MZBANISH", $mainPlayer, "HAND,Source-" . $attackCard . "," . $attackCard, 1);
        AddDecisionQueue("MZREMOVE", $mainPlayer, "-", 1);
      }
      break;
```

### consuming_volition_blue  — looks-aligned
text: 'If you\'ve dealt arcane damage this turn, this gets "When this hits a hero, they discard a card."'
```json
{
  "slug": "consuming_volition_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DEALT_ARCANE_DAMAGE_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "DISCARD",
          "target": "opponent"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CRUHitEffect()
if(IsHeroAttackTarget() && GetClassState($defPlayer, $CS_ArcaneDamageTaken)) PummelHit();
      break;
```

### hunted_or_hunter_red  — looks-aligned
text: 'When this defends and the attacking hero has played or activated an attack reaction this chain link, they lose 1{h}.'
```json
{
  "slug": "hunted_or_hunter_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "classes": [
            "assassin"
          ]
        },
        {
          "type": "FLAG_SET",
          "flag": "ATTACK_REACTION_PLAYED_OR_ACTIVATED"
        }
      ],
      "effects": [
        {
          "type": "LOSE_LIFE",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
WriteLog("👹 The Hunter has become the hunted");
        LoseHealth(1, $mainPlayer);
        break;
// OnDefenseReactionResolveEffects()
if (NumAttackReactionsPlayed() > 0) AddLayer("TRIGGER", $defPlayer, $cardID);
      break;
```

### rising_solartide_red  — looks-aligned
text: "If Rising Solartide hits, put it into your hero's soul."
```json
{
  "slug": "rising_solartide_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "PUT_SELF_BOTTOM_DECK"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MONTalentHitEffect()
case "rising_solartide_blue": $combatChainState[$CCS_GoesWhereAfterLinkResolves] = "SOUL"; break;
```

### nock_the_deathwhistle_blue  — looks-aligned
text: '**Azalea Specialization**\n\nSearch your deck for an arrow card, reveal it, then shuffle your deck and put it on top of your deck.\n\n**Reload**\n\n**Go again**'
```json
{
  "slug": "nock_the_deathwhistle_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SEARCH_DECK",
          "filter": {
            "type": "CARD_IN_ZONE",
            "zones": [
              "deck"
            ],
            "subtypes": [
              "arrow"
            ]
          },
          "amount": 1,
          "reveal": true,
          "put_on_top": true
        },
        {
          "type": "RELOAD"
        },
        {
          "type": "GO_AGAIN"
        }
      ],
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_types": [
            "Azalea"
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCRangerPlayAbility()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYDECK:subtype=Arrow");
        AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("MZREMOVE", $currentPlayer, "-", 1);
        AddDecisionQueue("SHUFFLEDECK", $currentPlayer, "-");
        AddDecisionQueue("REVEALCARDS", $currentPlayer, "-", 1);
        AddDecisionQueue("MULTIADDTOPDECK", $currentPlayer, "-", 1);
        Reload();
        return "";
```

### steadfast_blue  — looks-aligned
text: 'Prevent the next 4 damage that would be dealt to your hero this turn by a source of your choice.'
```json
{
  "slug": "steadfast_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "STEADFAST_ACTIVE",
          "duration": "END_OF_TURN"
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_DAMAGE",
            "conditions": [
              {
                "type": "FLAG_SET",
                "flag": "STEADFAST_ACTIVE"
              },
              {
                "type": "DURING_TURN"
              },
              {
                "type": "ATTACKER_CONTROLLED_BY_YOU"
              },
              {
                "type": "CHAIN_HIT_COUNT_GTE",
                "amount": 4
              }
            ],
            "effects": [
              {
                "type": "PREVENT_DAMAGE",
                "amount": 4
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CurrentTurnEffectUses()
return 4;
// CurrentTurnEffectDamagePreventionAmount()
return $source == $currentTurnEffects[$index + 2] && $preventable ? $currentTurnEffects[$index + 3] : 0;
// CurrentEffectDamagePrevention()
if ($source == $currentTurnEffects[$index + 2]) {
        if ($preventable) {
          $origDamage = $damage;
          $preventedDamage += $currentTurnEffects[$index + 3];
          if ($preventedDamage > $damage) $preventedDamage = $damage;
          $currentTurnEffects[$index + 3] -= $origDamage;
        }
        if ($currentTurnEffects[$index + 3] <= 0) $remove = true;
        $multiAttack = match($source) {
          "explosive_growth_red", "explosive_growth_yellow", "explosive_growth_blue", "art_of_the_dragon_fire_red" => true,
          "vexing_malice_red", "vexing_malice_yellow", "vexing_malice_blue", "reckless_stampede_red" => true,
          "runic_fellingsong_red", "runic_fellingsong_yellow", "runic_fellingsong_blue" => true,
          "arcanic_shockwave_red", "arcanic_shockwave_yellow", "arcanic_shockwave_blue" => true,
          "arcanic_crackle_red", "arcanic_crackle_yellow", "arcanic_crackle_blue" => true,
          default => false,
        };
        if (SubtypeContains($source, "Dagger")) $multiAttack = true;
        if (TypeContains($source, "AA") && !$multiAttack) $remove = true; //To be removed when coded with Unique ID instead of cardID name as $source
        if ($source == "spectral_shield" || $source == "runechant" || $source == "aether_ashwing") $remove = true; //To be removed when coded with Unique ID instead of cardID name as $source
        if ($remove) RemoveCurrentTurnEffect($index);
      }
      break;
// EVRPlayAbility()
AddDecisionQueue("FINDINDICES", $currentPlayer, "DAMAGEPREVENTIONTARGET");
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a damage source for " . CardLink($cardID, $cardID));
        AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);
        AddDecisionQueue("MZOP", $currentPlayer, "GETCARDID", "-", 1);
        AddDecisionQueue("PREPENDLASTRESULT", $currentPlayer, "{$cardID}!{$from}!", 1);
        AddDecisionQueue("ADDCURRENTTURNEFFECT", $currentPlayer, "<-", 1);
        return "";
```

### send_packing_yellow  — looks-aligned
text: "When this attacks a hero, banish a card from their arsenal. When the chain link resolves, if this didn't hit, return the banished card to its owner's hand."
```json
{
  "slug": "send_packing_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "BANISH",
          "target": {
            "zone": "arsenal",
            "controller": "opponent"
          }
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CRUSH",
      "conditions": [
        {
          "type": "DID_NOT_HIT"
        }
      ],
      "effects": [
        {
          "type": "RETURN_TO_HAND",
          "target": {
            "zone": "banish",
            "controller": "opponent"
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// NonHitEffects()
RemoveCurrentTurnEffect($i);
          $banish = new Banish($defPlayer);
          $banishedCard = $banish->FirstCardWithModifier($cardID);
          if ($banishedCard == null) break;
          $banishIndex = $banishedCard->Index();
          if ($banishIndex > -1) AddPlayerHand($banish->Remove($banishIndex), $defPlayer, "BANISH");
          break;
// HVYHitEffect()
$CurrentTurnEffects->RemoveEffectByID($cardID);
      break;
// HVYPlayAbility()
if (IsHeroAttackTarget()) {
        AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "THEIRARS");
        AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("MZBANISH", $currentPlayer, "CC," . $cardID, 1);
        AddDecisionQueue("MZREMOVE", $currentPlayer, "-", 1);
        AddDecisionQueue("ADDCURRENTTURNEFFECT", $currentPlayer, $cardID, 1);
      } else {
        WriteLog("<span style='color:red;'>No arsenal is banished because it does not attack a hero.</span>");
      }
      return "";
```

### lightning_press_yellow  — looks-aligned
text: 'Target attack action card with cost 1 or less gains +2{p}.'
```json
{
  "slug": "lightning_press_yellow",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ],
      "target": {
        "filter": [
          {
            "type": "ATTACK_COST_LTE",
            "amount": 1
          }
        ]
      }
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
$targets = TargetAttackActionCard(maxCost:1);
      return count($targets) == 0;
// ReactionRequirementsMet()
case "lightning_press_red": case "lightning_press_yellow": case "lightning_press_blue": return CardType($combatChain[0]) == "AA" && CardCost($combatChain[0]) <= 1;
// GetLayerTarget()
$targets = TargetAttackActionCard(maxCost:1);
      $targets = implode(",", $targets);
      AddDecisionQueue("PASSPARAMETER", $currentPlayer, $targets);
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a target for ". CardLink($cardID));
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "<-", 1);
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// ELEEffectPowerModifier()
case "lightning_press_yellow": return 2;
// ELECombatEffectActive()
return CardType($attackID) == "AA" && CardCost($attackID) <= 1;
// ELETalentPlayAbility()
$amount = match($cardID) { "lightning_press_yellow" => 2, "lightning_press_blue" => 1, default => 3 };
        $targetParts = explode("-", $target, 2);
        $index = $targetParts[1];
        if ($targetParts[0] == "COMBATCHAINLINK" && $CombatChain->HasCurrentLink() && $index != -1) {
          if ($index == 0 && $combatChainState[$CCS_GoesWhereAfterLinkResolves] == "-") {
            WriteLog(CardLink($cardID, $cardID) . " layer fails as the target is no longer valid.");
            return "";
          }
          CombatChainPowerModifier($index, $amount);
          AddCurrentTurnEffect($cardID."-VISUAL", $currentPlayer);//For Visual Effect only
        }
        elseif ($targetParts[0] == "PASTCHAINLINK") {
          // targeting a past chain link, do nothing for now
        }
        //only add current turn effect if there's no target (ie. played in layer step)
        elseif (IsLayerStep()) AddCurrentTurnEffect($cardID, $currentPlayer);
        else return "FAILED"; // This shouldn't ever be reached, leave it here just in case
        return "";
```

### scrap_compactor_blue  — looks-aligned
text: '**Scrap**\n\nWhen this attacks, if it **scrapped** a card, you may play your next Evo this turn as though it were an instant.'
```json
{
  "slug": "scrap_compactor_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SCRAPPED_CARD"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "PLAY_EVO_AS_INSTANT",
          "value": true
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVOPlayAbility()
if (DelimStringContains($additionalCosts, "SCRAP", true)) AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### silver_palms  — looks-aligned
text: "At the start of each other hero's turn, if they have less {h} than you, they may draw a card. If they do, you create a Silver token.\n\n**Blade Break**"
```json
{
  "slug": "silver_palms",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "OR",
          "conditions": [
            {
              "type": "AND",
              "conditions": [
                {
                  "type": "NOT",
                  "condition": {
                    "type": "IS_ACTIVE_PLAYER"
                  }
                },
                {
                  "type": "HEALTH_LT_OPP"
                }
              ]
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "CREATE_TOKEN",
          "token": "Silver"
        }
      ]
    },
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DefCharacterStartTurnAbilities()
if (PlayerHasLessHealth($mainPlayer)) {
          AddDecisionQueue("CHARREADYORPASS", $defPlayer, $i);
          AddDecisionQueue("YESNO", $mainPlayer, "if_you_want_to_draw_a_card_and_give_your_opponent_a_".CardLink("silver","silver").".", 1);
          AddDecisionQueue("NOPASS", $mainPlayer, "-", 1);
          AddDecisionQueue("DRAW", $mainPlayer, "-", 1);
          AddDecisionQueue("PASSPARAMETER", $defPlayer, "silver", 1);
          AddDecisionQueue("PUTPLAY", $defPlayer, "0", 1);
        }
        break;
```

### spire_sniping_red  — looks-aligned
text: 'When Spire Sniping is put or turned face up in arsenal, look at the top 2 cards of your deck, then put them back in any order.'
```json
{
  "slug": "spire_sniping_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "effects": [
        {
          "type": "LOOK_AT",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddArsenal()
SpireSnipingAbility($player);
        break;
// ArsenalTurnFaceUpAbility()
SpireSnipingAbility($player);
      break;
```

### infectious_host_blue  — looks-aligned
text: 'When this attacks a hero, if you control a Frailty token, create a Frailty token under their control, then repeat for Inertia and Bloodrot Pox.'
```json
{
  "slug": "infectious_host_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Frailty"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Frailty",
          "controller": "opponent"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Inertia",
          "controller": "opponent"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Bloodrot Pox",
          "controller": "opponent"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTPlayAbility()
if(SearchAuras($CID_Frailty, $currentPlayer)) PlayAura($CID_Frailty, $defPlayer, effectController: $currentPlayer);
        if(SearchAuras($CID_BloodRotPox, $currentPlayer)) PlayAura($CID_BloodRotPox, $defPlayer, effectController: $currentPlayer);
        if(SearchAuras($CID_Inertia, $currentPlayer)) PlayAura($CID_Inertia, $defPlayer, effectController: $currentPlayer);
        return "";
```

### imposing_visage_blue  — looks-aligned
text: 'Search your deck for an aura card with cost X or less, put it into the arena, then shuffle your deck.\n\n**Go again**'
```json
{
  "slug": "imposing_visage_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SEARCH_DECK",
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zones": [
                  "deck"
                ],
                "subtypes": [
                  "Aura"
                ],
                "cost": {
                  "type": "LTE",
                  "amount": "X"
                }
              }
            ]
          },
          "destination": "arena"
        },
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": "SEARCHED_COUNT",
          "zone": "deck"
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CardCost()
return 3;
// DynamicCost()
return "3,4,5,6,7,8,9,10,11,12,13,14,15";
// EVRPlayAbility()
AddDecisionQueue("FINDINDICES", $currentPlayer, "DECKAURAMAXCOST," . ($resourcesPaid-CardCost($cardID)), 1);
        AddDecisionQueue("MAYCHOOSEDECK", $currentPlayer, "<-", 1);
        AddDecisionQueue("PUTPLAY", $currentPlayer, "-", 1);
        AddDecisionQueue("SHUFFLEDECK", $currentPlayer, "-");
        return "";
```

### trade_in_yellow  — looks-aligned
text: 'When this attacks, you may discard a card. If you do, draw a card.\n\nIf this was played from arsenal, it gains **go again**.'
```json
{
  "slug": "trade_in_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "DISCARD",
          "amount": 1
        },
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "PLAYED_FROM_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// UPRTalentPlayAbility()
if($from == "ARS") GiveAttackGoAgain();
        AddDecisionQueue("FINDINDICES", $currentPlayer, "HAND");
        AddDecisionQueue("MAYCHOOSEHAND", $currentPlayer, "<-", 1);
        AddDecisionQueue("REMOVEMYHAND", $currentPlayer, "-", 1);
        AddDecisionQueue("DISCARDCARD", $currentPlayer, "HAND-".$currentPlayer, 1);
        AddDecisionQueue("DRAW", $currentPlayer, "-", 1);
        return "";
```

### burly_bones_blue  — looks-aligned
text: 'When this attacks, you may discard a card or destroy the top card of your deck. If that card has watery grave, this gets **overpower**.'
```json
{
  "slug": "burly_bones_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "DISCARD_RANDOM"
        },
        {
          "type": "DESTROY_REF",
          "target": {
            "type": "TOP_CARD_OF_DECK"
          }
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "pitch": "watery_grave"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "OVERPOWER"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SEAPlayAbility()
$hand = &GetHand($currentPlayer);
      $handCount = count($hand);
      $deck = &GetDeck($currentPlayer);
      $deckCount = count($deck);
      $context = "Choose a card to discard from your hand or destroy from the top of your deck (or pass)";
      if ($handCount == 0 && $deckCount == 0) break;
      if ($handCount == 0) {
        $context = "Choose a card to destroy from the top of your deck (or pass)";
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, "MYDECK-0", 1);
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, $context, 1);
      } 
      else {
        AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYHAND", 1);
        if($deckCount > 0) {
          AddDecisionQueue("APPENDLASTRESULT", $currentPlayer, ",MYDECK-0", 1);
        }
        else $context = "Choose a card to discard from your hand (or pass)";
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, $context, 1);
      }
      AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SETDQVAR", $currentPlayer, "0", 1);
      AddDecisionQueue("MZADDZONE", $currentPlayer, "MYDISCARD,{0}", 1);
      AddDecisionQueue("MZSETDQVAR", $currentPlayer, "0", 1);
      AddDecisionQueue("WRITELOG", $currentPlayer, "Card chosen: <0>", 1);
      AddDecisionQueue("MZREMOVE", $currentPlayer, "-", 1);
      AddDecisionQueue("ALLCARDWATERYGRAVEORPASS", $currentPlayer, "<-", 1);
      AddDecisionQueue("PASSPARAMETER", $currentPlayer, $cardID, 1);
      AddDecisionQueue("ADDCURRENTTURNEFFECT", $currentPlayer, $cardID, 1);
      break;
```

### tiger_stripe_shuko  — looks-aligned
text: 'The second attack action card with 2 or less base {p} you play each turn has +1{p} and "Damage that would be dealt by this can\'t be prevented."\n\n**Blade Break**'
```json
{
  "slug": "tiger_stripe_shuko",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "DURING_TURN"
            },
            {
              "type": "PLAYED_FROM_ARSENAL"
            },
            {
              "type": "ATTACK_ACTION"
            },
            {
              "type": "BASE_POWER_LTE",
              "amount": 2
            },
            {
              "type": "COMBO_CONTAINS",
              "amount": 2,
              "card": "tiger_stripe_shuko"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "WARD"
        }
      ]
    },
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CharacterPlayCardAbilities()
if (GetClassState($currentPlayer, $CS_NumLess3PowAAPlayed) == 2 && PowerValue($cardID, $currentPlayer, "CC") <= 2) {
          AddCurrentTurnEffect($characterID, $currentPlayer);
          $CharacterCard->SetUsed();
          LogPlayCardStats($currentPlayer, "tiger_stripe_shuko", "EQUIP", "PASSIVE");
        }
        break;
// UPREffectPowerModifier()
case "tiger_stripe_shuko": return 1;
// UPRCombatEffectActive()
case "tiger_stripe_shuko": return true;
```

### clash_of_agility_blue  — looks-aligned
text: 'When this defends, **clash** with the attacking hero. The winner creates an Agility token.'
```json
{
  "slug": "clash_of_agility_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "CLASH",
          "target": {
            "filter": [
              {
                "type": "ATTACK_CLASS_IN",
                "classes": [
                  "hero"
                ]
              }
            ]
          }
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Agility"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
Clash($parameter, effectController: $player);
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
// WonClashAbility()
PlayAura("agility", $playerID);
        break;
```

### spring_a_leak_blue  — looks-aligned
text: '**Boost**\n\nWhen this hits a hero, remove all steam counters from an equipment, item, or weapon they control.'
```json
{
  "slug": "spring_a_leak_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "REMOVE_COUNTERS",
          "target": {
            "filter": [
              {
                "type": "CONTROLS_TOKEN_TYPE",
                "token_types": [
                  "steam"
                ]
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVOHitEffect()
AddDecisionQueue("MULTIZONEINDICES", $mainPlayer, "THEIRITEMS:hasSteamCounter=true&THEIRCHAR:hasSteamCounter=true");
      AddDecisionQueue("SETDQCONTEXT", $mainPlayer, "Choose an equipment, item, or weapon. Remove all steam counters from it.");
      AddDecisionQueue("CHOOSEMULTIZONE", $mainPlayer, "<-", 1);
      AddDecisionQueue("MZREMOVEALLCOUNTERS", $mainPlayer, "-", 1);
      break;
```

### shield_bash_blue  — looks-aligned
text: 'If a Guardian off-hand with 1 or more {d} is defending this chain link, deal 1 damage to the attacking hero unless they discard a card.'
```json
{
  "slug": "shield_bash_blue",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "classes": [
                "Guardian"
              ]
            },
            {
              "type": "ATTACK_SUBTYPE_IN",
              "subtypes": [
                "off-hand"
              ]
            },
            {
              "type": "ATTACK_PITCH_POWER_GTE",
              "amount": 1
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "amount": 1,
          "cost": [
            {
              "type": "DISCARD_CARD"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNPlayAbility()
if(SearchCombatChainLink($currentPlayer, subtype:"Off-Hand", class:"GUARDIAN") != "") {
        AddDecisionQueue("MULTIZONEINDICES", $otherPlayer, "MYHAND", 1);
        AddDecisionQueue("MAYCHOOSEMULTIZONE", $otherPlayer, "<-", 1);
        AddDecisionQueue("MZDISCARD", $otherPlayer, "HAND,".$currentPlayer, 1);
        AddDecisionQueue("MZREMOVE", $otherPlayer, "-", 1);
        AddDecisionQueue("ELSE", $otherPlayer, "-");
        AddDecisionQueue("TAKEDAMAGE", $otherPlayer, "1-".$cardID, 1);
      }
      return "";
```

### talisman_of_featherfoot_yellow  — looks-aligned
text: '**Go again**\n\nWhen an attack you control gains exactly +1{p} from an effect during the reaction step, destroy Talisman of Featherfoot and the attack gains **go again**.'
```json
{
  "slug": "talisman_of_featherfoot_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ACTIVATE",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_CONTROLLED_BY_YOU"
            },
            {
              "type": "MODIFY_ATTACK",
              "mod": "add",
              "amount": 1
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVRAbilityCost()
case "talisman_of_featherfoot_yellow": return 0;
// EVRAbilityType()
case "talisman_of_featherfoot_yellow": return "AR";
// EVRPlayAbility()
if($from == "PLAY"){
          DestroyItemForPlayer($currentPlayer, GetClassState($currentPlayer, $CS_PlayIndex));
          GiveAttackGoAgain();
        }
        return "Partially manual card: Activate the instant ability if you met the criteria";
```

### fletch_a_red_tail_red  — looks-aligned
text: 'Your next arrow attack this turn gains +4{p}.\n\nIf it has an aim counter, it gains "Red cards have -1{d} while defending this."\n\n**Go again**'
```json
{
  "slug": "fletch_a_red_tail_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4,
          "conditions": [
            {
              "type": "DURING_TURN"
            }
          ]
        },
        {
          "type": "APPLY_CONTINUOUS",
          "effects": [
            {
              "type": "MODIFY_DEFENSE_VALUE",
              "amount": -1,
              "conditions": [
                {
                  "type": "CARD_IN_ZONE",
                  "zones": [
                    "hand"
                  ],
                  "subtypes": [
                    "red"
                  ]
                }
              ]
            }
          ],
          "conditions": [
            {
              "type": "COUNTER_GTE",
              "counter": "aim",
              "amount": 1
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EffectHasBlockModifier()
return true;
// CurrentEffectBlockModifiers()
$blockModifier += (PitchValue($blockCardID) == 1 && HasAimCounter() ? -1 : 0);
          break;
// OUTEffectPowerModifier()
case "fletch_a_red_tail_red": return 4;
// OUTCombatEffectActive()
case "fletch_a_red_tail_red": case "fletch_a_yellow_tail_yellow": case "fletch_a_blue_tail_blue": return CardSubType($attackID) == "Arrow";
// OUTPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        AddCurrentTurnEffect($cardID, $defPlayer);
        return "";
```

### amulet_of_lightning_blue  — looks-aligned
text: '**Go again**\n\n**Instant** - Destroy Amulet of Lightning: Target action card gains **go again**. Activate this ability only if you have Lightning **fused** this turn.'
```json
{
  "slug": "amulet_of_lightning_blue",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LIGHTNING_FUSED"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return $from == "PLAY" && GetClassState($player, $CS_NumFusedLightning) == 0;
// CurrentEffectGrantsNonAttackActionGoAgain()
$hasGoAgain = true;
          $remove = true;
          break;
// DoesCurrentTurnEffectGrantGoAgain()
return true;
// PayItemAbilityAdditionalCosts()
DestroyItemForPlayer($currentPlayer, $index);
      break;
// ReactionRequirementsMet()
case "amulet_of_lightning_blue": return GetClassState($currentPlayer, $CS_NumFusedLightning) > 0;
// ELEAbilityType()
if($from == "PLAY") return "I";
        else return "A";
// ELECombatEffectActive()
case "amulet_of_lightning_blue": $cardType = CardType($attackID); return $cardType == "AA" || $cardType == "A";
// ELETalentPlayAbility()
if($from == "PLAY") {
          if(count($combatChain) > 0) GiveAttackGoAgain();
          else AddCurrentTurnEffect($cardID, $currentPlayer);
        }
        return "";
```

### burn_them_all_red  — looks-aligned
text: '**Go again**\n\nOnce per turn, when a dragon you control attacks, it deals 1 arcane damage to each opposing hero.\n\nAt the beginning of your end phase, put a raze counter on Burn Them All then destroy it unless you banish red card from your graveyard for each raze counter on it.'
```json
{
  "slug": "burn_them_all_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "classes": [
            "dragon"
          ]
        },
        {
          "type": "CONTROLS_ATTACK_ACTION"
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1,
          "target": {
            "type": "OPPONENT_HERO"
          }
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "RAZE",
          "amount": 1
        },
        {
          "type": "DESTROY_REF",
          "target": "self",
          "conditions": [
            {
              "type": "NOT",
              "condition": {
                "type": "BANISH_TRAP_FROM_GRAVEYARD_PLAYABLE",
                "color": "red",
                "amount": "RAZE_COUNTERS"
              }
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraNumUses()
return 1;
// AuraBeginEndPhaseAbilities()
$toBanish = ++$auras[$i + 2];
        $discardReds = SearchCount(SearchDiscard($mainPlayer, pitch: 1));
        if ($toBanish <= $discardReds) {
          for ($j = $toBanish; $j > 0; --$j) {
            MZMoveCard($mainPlayer, "MYDISCARD:pitch=1", "MYBANISH,GY,-", may: true, isSubsequent: $j < $toBanish);
          }
          AddDecisionQueue("ELSE", $mainPlayer, "-");
          AddDecisionQueue("PASSPARAMETER", $mainPlayer, "MYAURAS-" . $i, 1);
          AddDecisionQueue("MZDESTROY", $mainPlayer, "-", 1);
        } else {
          DestroyAura($mainPlayer, $i);
        }
        break;
// AuraAttackAbilities()
if ($auras[$i + 5] > 0 && DelimStringContains(CardSubType($attackID), "Dragon")) {
          --$auras[$i + 5];
          AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", $attackID, $auras[$i + 6]);
        }
        break;
// ProcessTrigger()
DealArcane(1, 1, "STATIC", $combatChain[0], false, $mainPlayer);
        break;
```

### chokeslam_yellow  — looks-aligned
text: "**Crush** - When this deals 4 or more damage to a hero, attack action cards they control can't gain {p} during their next action phase."
```json
{
  "slug": "chokeslam_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CRUSH",
      "conditions": [
        {
          "type": "DID_NOT_HIT",
          "amount": 4
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "CRUSH_FLAG"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CRUSH_FLAG"
        }
      ],
      "effects": [
        {
          "type": "RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessCrushEffect()
AddNextTurnEffect("chokeslam_red", $defPlayer);
        break;
```

### test_of_agility_red  — looks-aligned
text: 'When this defends, **clash** with the attacking hero. The winner creates an Agility token.'
```json
{
  "slug": "test_of_agility_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "CLASH",
          "target": {
            "filter": [
              {
                "type": "ATTACK_CLASS_IN",
                "classes": [
                  "hero"
                ]
              }
            ]
          }
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Agility"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
Clash($parameter, effectController: $player);
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
// WonClashAbility()
PlayAura("agility", $playerID);
        break;
```

### sloggism_blue  — looks-aligned
text: 'The next attack action card with cost 2 or greater you play this turn gains +4{p}.\n\n**Go again**'
```json
{
  "slug": "sloggism_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "APPLY_CONTINUOUS",
          "duration": "END_OF_TURN",
          "effects": [
            {
              "type": "MODIFY_ATTACK",
              "mod": "add",
              "amount": 4,
              "conditions": [
                {
                  "type": "CARD_IN_ZONE",
                  "zone": "HAND",
                  "conditions": [
                    {
                      "type": "ATTACK_COST_GTE",
                      "amount": 2
                    }
                  ]
                }
              ]
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// WTREffectPowerModifier()
case "sloggism_blue": return 4;
// WTRCombatEffectActive()
case "sloggism_red": case "sloggism_yellow": case "sloggism_blue": return CardType($attackID) == "AA" && CardCost($attackID) >= 2;
// WTRPlayAbility()
AddCurrentTurnEffect($cardID, $mainPlayer);
        return "";
```

### reapers_call_blue  — looks-aligned
text: '**Stealth**\n\n**Instant** - Discard this: **Mark** target opposing hero.'
```json
{
  "slug": "reapers_call_blue",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "MARK"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// GetAbilityNames()
return GetEasyAbilityNames($cardID, $index, $from, $allNames);
// IsPlayRestricted()
$abilityNames = GetAbilityNames($cardID, $index, $from);
      if ($abilityNames == "Ability" && $from != "HAND") return true;
      return false;
// GoesOnCombatChain()
return $phase == "B" && count($layers) == 0 || GetResolvedAbilityType($cardID, $from) == "AA";
// ProcessAbility()
MarkHero($otherPlayer);
      break;
```

### vexing_malice_red  — looks-aligned
text: 'Deal 2 arcane damage to target hero.'
```json
{
  "slug": "vexing_malice_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 2
        }
      ],
      "target": {
        "filter": [
          {
            "type": "CARD_IN_ZONE",
            "zones": [
              "hero"
            ]
          }
        ]
      }
    }
  ]
}
```
Talishar:
```php
// ProcessAttackTrigger()
DealArcane(2, 0, "PLAYCARD", $cardID);
      break;
// MONRunebladePlayAbility()
AddLayer("TRIGGER", $currentPlayer, $cardID, "-", "ATTACKTRIGGER", $CombatChain->AttackCard()->UniqueID());
        return "";
```

### runaways  — looks-aligned
text: '**Instant** - Destroy Runaways: Prevent the next 1 damage that would be dealt to your hero this turn. Activate this ability only if your hero has been dealt damage this turn.'
```json
{
  "slug": "runaways",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "WARD",
          "amount": 1
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "HERO_TAKEN_DAMAGE_THIS_TURN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return !HasTakenDamage($player);
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// CurrentTurnEffectDamagePreventionAmount()
return 1;
// CurrentEffectDamagePrevention()
if ($preventable) $preventedDamage += 1;
      RemoveCurrentTurnEffect($index);
      break;
// ELEAbilityType()
case "ragamuffins_hat": case "runaways": return "I";
// ELETalentPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### smashing_good_time_blue  — looks-aligned
text: 'The next time an attack action card hits a hero this turn, you may destroy an item they control with cost 2 or less.\n\nIf Smashing Good Time is played from arsenal, the next attack action card you play this turn gains +1{p}.\n\n**Go again**'
```json
{
  "slug": "smashing_good_time_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "classes": [
            "Generic"
          ]
        },
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "MAY_DESTROY_SILVERS_TO_EQUIP",
          "cost": 2
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "conditions": [
        {
          "type": "PLAYED_FROM_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVRPlayAbility()
$rv = "Makes your next attack action that hits destroy an item";
        AddCurrentTurnEffect($cardID . "-1", $currentPlayer);
        if($from == "ARS") AddCurrentTurnEffect($cardID . "-2", $currentPlayer);
        return "";
```

### sigil_of_shelter_blue  — looks-aligned
text: 'The next time you would be dealt damage this turn, prevent 1 of that damage.'
```json
{
  "slug": "sigil_of_shelter_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_HIT",
            "conditions": [
              {
                "type": "DURING_TURN"
              }
            ],
            "effects": [
              {
                "type": "PAY_OR_DAMAGE",
                "amount": 1
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CurrentTurnEffectDamagePreventionAmount()
return 1;
// CurrentEffectDamagePrevention()
if ($preventable) {
        $preventedDamage += 1;
      }
      RemoveCurrentTurnEffect($index);
      break;
// TERPlayAbility()
AddCurrentTurnEffect($cardID, 1);
      AddCurrentTurnEffect($cardID, 2); // I think because of the way this effect is evaluated, both players need to "know" about it in order for it to work properly. See rain_razors_yellow.
      return "";
```

### lead_with_speed_yellow  — looks-aligned
text: 'Your next Brute or Warrior attack this turn gets +2{p}.\n\nCreate an Agility token.\n\n**Go again**'
```json
{
  "slug": "lead_with_speed_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2,
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "classes": [
                "brute",
                "warrior"
              ]
            },
            {
              "type": "DURING_TURN"
            }
          ]
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Agility"
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HVYPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      PlayAura("agility", $currentPlayer); 
      return "";
```

### sigil_of_solitude_red  — looks-aligned
text: 'At the start of your turn, if you control another Illusionist aura, destroy this.\n\n**Ward 4**'
```json
{
  "slug": "sigil_of_solitude_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_types": [
            "Illusionist"
          ],
          "amount": "gt",
          "value": 1
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
$AurasArray = explode(",", SearchAura($mainPlayer, class: "ILLUSIONIST"));
        if (count($AurasArray) > 1) DestroyAuraUniqueID($mainPlayer, $auras[$i + 6]);
        break;
```

### levels_of_enlightenment_blue  — looks-aligned
text: "When this attacks, choose 1 for each blue card you've pitched this turn;\n- Draw a card.\n- This gets +2{p}.\n- This gets **go again**."
```json
{
  "slug": "levels_of_enlightenment_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "OPT",
          "amount": 1
        }
      ],
      "choose": 1,
      "modes": [
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTPlayAbility()
$modalities = "Draw_a_card,Buff_Power,Go_again";
      $numChoices = SearchPitchForColor($currentPlayer, 3);
      if ($numChoices >= 3) {
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, $modalities);
        AddDecisionQueue("MODAL", $currentPlayer, "LEVELSOFENLIGHTENMENT", 1);
        AddDecisionQueue("SHOWMODES", $currentPlayer, $cardID, 1);
      } elseif ($numChoices < 3 && $numChoices > 0) {
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose " . $numChoices . " modes");
        AddDecisionQueue("MULTICHOOSETEXT", $currentPlayer, $numChoices . "-" . $modalities . "-" . $numChoices);
        AddDecisionQueue("MODAL", $currentPlayer, "LEVELSOFENLIGHTENMENT", 1);
        AddDecisionQueue("SHOWMODES", $currentPlayer, $cardID, 1);
      }
      return "";
```

### fire_in_the_hole_red  — looks-aligned
text: 'Your next arrow attack this turn gets +3{p}.\n\nYou may {u} a bow you control.\n\n**Go again**'
```json
{
  "slug": "fire_in_the_hole_red",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "PAY_LIFE",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SEAPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      $inds = GetTapped($currentPlayer, "MYCHAR", "subtype=Bow");
      if(empty($inds)) break;
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "You may untap a bow you control");
      //technically should be a MAYCHOOSEMULTIZONE but for playerMacro we make it so it skips the step if there is 1 choice
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, $inds);
      AddDecisionQueue("MZTAP", $currentPlayer, "0", 1);
      break;
```

### high_roller_yellow  — looks-aligned
text: '**Intimidate**\n\nIf you have rolled a 5 or 6 on a die this turn, instead **intimidate** twice.\n\n**Go again**'
```json
{
  "slug": "high_roller_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ROLL_5_OR_6"
        }
      ],
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVRPlayAbility()
$rv = "Intimidates";
        Intimidate();
        $targetHigh = match($cardID) { "high_roller_red" => 4, "high_roller_yellow" => 5, default => 6 };
        if(GetClassState($currentPlayer, $CS_HighestRoll) >= $targetHigh) Intimidate();
        return "";
```

### bonebreaker_bellow_red  — looks-aligned
text: "**Beat Chest**\n\nYour next Brute attack this turn gains +3{p}. If you've **beaten chest** this turn, instead it gains +5{p}.\n\n**Go again**"
```json
{
  "slug": "bonebreaker_bellow_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "BEAT_CHEST"
            }
          ]
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 5,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "BEAT_CHEST"
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HVYPlayAbility()
$amount = 3;
      if (SearchCurrentTurnEffects("BEATCHEST", $currentPlayer)) $amount += 2;
      AddCurrentTurnEffect($cardID . "," . $amount, $currentPlayer);
      return "";
```

### bask_in_your_own_greatness_red  — looks-aligned
text: 'When this attacks, you may pay up to {r}{r}{r}. Create that many Might tokens.'
```json
{
  "slug": "bask_in_your_own_greatness_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "CREATE_MIGHT_PER_GOLD",
          "amount": "PAY_AMOUNT"
        }
      ],
      "additional_cost": [
        {
          "type": "PAY_RESOURCES",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessAttackTrigger()
AddDecisionQueue("SETDQCONTEXT", $player, "Choose a number of resources to pay");
      AddDecisionQueue("CHOOSENUMBER", $player, "0,1,2,3", 1);
      AddDecisionQueue("PAYRESOURCES", $player, "<-", 1);
      AddDecisionQueue("SPECIFICCARD", $player, "BASK,$cardID", 1);
      break;
// SUPPlayAbility()
AddLayer("TRIGGER", $currentPlayer, $cardID, additionalCosts:"ATTACKTRIGGER");
      break;
```

### blow_for_a_blow_red  — looks-aligned
text: 'When this is played, if you have less {h} than an opposing hero, it gets **go again**.\n\nWhen this hits, deal 1 damage to any target.'
```json
{
  "slug": "blow_for_a_blow_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN",
          "conditions": [
            {
              "type": "HEALTH_LT_OPP"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "DEAL_GENERIC",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CardPlayTrigger()
AddLayer("TRIGGER", $mainPlayer, $cardID);
        break;
// ProcessTrigger()
if(PlayerHasLessHealth($mainPlayer)) {
          WriteLog(CardLink($parameter, $parameter) . " gains Go Again!");
          GiveAttackGoAgain();
        }
        break;
// SEAHitEffect()
AddDecisionQueue("MULTIZONEINDICES", $mainPlayer, "MYCHAR:type=C&THEIRCHAR:type=C&MYALLY&THEIRALLY", 1);
      AddDecisionQueue("SETDQCONTEXT", $mainPlayer, "Choose a target to deal 1 damage");
      AddDecisionQueue("CHOOSEMULTIZONE", $mainPlayer, "<-", 1);
      AddDecisionQueue("MZDAMAGE", $mainPlayer, "1,DAMAGE," . $cardID, 1);
      break;
```

### barbed_castaway  — looks-aligned
text: '**Once per Turn Instant** - {r}: You may put an arrow card from your hand face up into your arsenal.\n\n**Once per Turn Instant** - {r}: You may turn a face down arrow in your arsenal face up. If you do, put an aim counter on it.'
```json
{
  "slug": "barbed_castaway",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "per_turn": 1,
      "effects": [
        {
          "type": "SEARCH_DECK",
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zones": [
                  "hand"
                ],
                "subtypes": [
                  "Arrow"
                ]
              }
            ]
          },
          "destination": "arsenal",
          "face_up": true
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "per_turn": 1,
      "effects": [
        {
          "type": "FLIP_REF",
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zones": [
                  "arsenal"
                ],
                "subtypes": [
                  "Arrow"
                ],
                "conditions": [
                  {
                    "type": "NOT",
                    "condition": {
                      "type": "REF_PITCH_IS",
                      "pitch": "face_up"
                    }
                  }
                ]
              }
            ]
          },
          "face_up": true
        },
        {
          "type": "PUT_COUNTER",
          "counter": "aim",
          "amount": 1,
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zones": [
                  "arsenal"
                ],
                "subtypes": [
                  "Arrow"
                ],
                "conditions": [
                  {
                    "type": "REF_PITCH_IS",
                    "pitch": "face_up"
                  }
                ]
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DefCharacterStartTurnAbilities()
AddCurrentTurnEffect("barbed_castaway-Load", $defPlayer);
        AddCurrentTurnEffect("barbed_castaway-Aim", $defPlayer);
        break;
// AdministrativeEffect()
return true;
```

### smack_of_reality_red  — looks-aligned
text: '**Tower** - If this has 13 or more {p}, it gets "When this hits a hero, destroy all aura tokens they control."'
```json
{
  "slug": "smack_of_reality_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "SELF_ATTACK_POWER_GTE",
          "amount": 13
        }
      ],
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zones": [
                  "aura_tokens"
                ]
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddTowerEffectTrigger()
AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "TOWEREFFECT");
      break;
// ProcessTowerEffect()
MZDestroy($mainPlayer, SearchMultizone($mainPlayer, "THEIRAURAS:type=T"), $mainPlayer);
```

### sweeping_blow_blue  — looks-aligned
text: 'When you attack with Sweeping Blow, create an Ash token.\n\n**Go again**'
```json
{
  "slug": "sweeping_blow_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Ash"
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// UPRIllusionistPlayAbility()
PutPermanentIntoPlay($currentPlayer, "ash");
        return "";
```

### gold_hunter_lightsail_yellow  — looks-aligned
text: 'When this attacks, if you control less Gold than an opponent, this gets **go again**.'
```json
{
  "slug": "gold_hunter_lightsail_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Gold",
          "comparison": "lt",
          "opponent": true
        }
      ],
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SEAPlayAbility()
$myNumGold = CountItem("gold", $currentPlayer);
      $theirNumGold = CountItem("gold", $otherPlayer);
      if ($myNumGold < $theirNumGold) {
        GiveAttackGoAgain();
      }
      break;
```

### loot_the_hold_blue  — looks-aligned
text: 'Your next Pirate ally attack this turn gets "When this hits a hero, they discard a card. If they do, create a Gold token."\n\n**Go again**'
```json
{
  "slug": "loot_the_hold_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "classes": [
            "pirate"
          ]
        },
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_HIT",
            "target": {
              "filter": [
                {
                  "type": "CARD_IN_ZONE",
                  "zones": [
                    "hero"
                  ]
                }
              ]
            },
            "effects": [
              {
                "type": "DISCARD",
                "amount": 1
              },
              {
                "type": "CREATE_TOKEN",
                "token_type": "Gold"
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddEffectHitTrigger()
if (IsHeroAttackTarget()) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $parameter, $cardID, "EFFECTHITEFFECT");
        return true;
      }
      return false;
// EffectHitEffect()
$hand = GetHand($defPlayer);
      if (count($hand) > 0) PutItemIntoPlayForPlayer("gold", $mainPlayer, effectController:$mainPlayer, isToken:true);
      PummelHit();
      break;
// AGBPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        break;
```

### misfire_dampener  — looks-aligned
text: "**Instant** - Destroy this: Prevent the next 1 arcane damage that would be dealt to you this turn. If you've **boosted** this turn, instead prevent the next 2.\n\n**Blade Break**"
```json
{
  "slug": "misfire_dampener",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "MISFIRE_DAMPENER_PREVENT_ARCANE",
          "amount": 1
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BOOSTED_THIS_TURN"
        }
      ],
      "additional_effects": [
        {
          "type": "SET_FLAG",
          "flag": "MISFIRE_DAMPENER_PREVENT_ARCANE",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// CurrentTurnEffectDamagePreventionAmount()
return $type == "ARCANE" ? intval($effects[1]) : 0;
// CurrentEffectDamagePrevention()
if ($preventable) {
        $preventedDamage += intval($effects[1]);
        RemoveCurrentTurnEffect($index);
        break;
      }
      break;
// HNTPlayAbility()
if(GetClassState($currentPlayer, $CS_NumBoosted) >= 1) AddCurrentTurnEffect($cardID."-2", $currentPlayer);
      else AddCurrentTurnEffect($cardID."-1", $currentPlayer);
      break;
```

### herald_of_protection_red  — looks-aligned
text: 'When this hits, put it into your soul and create a Spectral Shield token.\n\n**Phantasm**'
```json
{
  "slug": "herald_of_protection_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "PUT_SELF_BOTTOM_DECK"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Spectral Shield"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MONIllusionistHitEffect()
if (DoesAttackHaveGoAgain()) GiveAttackGoAgain();
        $combatChainState[$CCS_GoesWhereAfterLinkResolves] = "-"; 
        AddSoul($attackCard, $mainPlayer, "CC");
        PlayAura("spectral_shield", $mainPlayer);
        break;
```

### burly_bones_red  — looks-aligned
text: 'When this attacks, you may discard a card or destroy the top card of your deck. If that card has watery grave, this gets **overpower**.'
```json
{
  "slug": "burly_bones_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "DISCARD_RANDOM"
        },
        {
          "type": "DESTROY_REF",
          "target": {
            "type": "TOP_CARD_OF_DECK"
          }
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "pitch": "watery_grave"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "OVERPOWER"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SEAPlayAbility()
$hand = &GetHand($currentPlayer);
      $handCount = count($hand);
      $deck = &GetDeck($currentPlayer);
      $deckCount = count($deck);
      $context = "Choose a card to discard from your hand or destroy from the top of your deck (or pass)";
      if ($handCount == 0 && $deckCount == 0) break;
      if ($handCount == 0) {
        $context = "Choose a card to destroy from the top of your deck (or pass)";
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, "MYDECK-0", 1);
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, $context, 1);
      } 
      else {
        AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYHAND", 1);
        if($deckCount > 0) {
          AddDecisionQueue("APPENDLASTRESULT", $currentPlayer, ",MYDECK-0", 1);
        }
        else $context = "Choose a card to discard from your hand (or pass)";
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, $context, 1);
      }
      AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SETDQVAR", $currentPlayer, "0", 1);
      AddDecisionQueue("MZADDZONE", $currentPlayer, "MYDISCARD,{0}", 1);
      AddDecisionQueue("MZSETDQVAR", $currentPlayer, "0", 1);
      AddDecisionQueue("WRITELOG", $currentPlayer, "Card chosen: <0>", 1);
      AddDecisionQueue("MZREMOVE", $currentPlayer, "-", 1);
      AddDecisionQueue("ALLCARDWATERYGRAVEORPASS", $currentPlayer, "<-", 1);
      AddDecisionQueue("PASSPARAMETER", $currentPlayer, $cardID, 1);
      AddDecisionQueue("ADDCURRENTTURNEFFECT", $currentPlayer, $cardID, 1);
      break;
```

### strong_yield_blue  — looks-aligned
text: '**Go again**\n\nAt the beginning of your action phase, destroy this, then your next attack this turn gets +1{p}.'
```json
{
  "slug": "strong_yield_blue",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "duration": "turn"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraBeginningActionPhaseAbilities()
AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", "DESTROY", $auras[$i + 6]);
        break;
// ProcessTrigger()
DestroyAuraUniqueID($player, $uniqueID);
        AddCurrentTurnEffect($parameter, $player, "PLAY");
        break;
```

### predatory_assault_blue  — looks-aligned
text: 'If you have discarded a card with 6 or more {p} this turn, Predatory Assault gains **dominate**.'
```json
{
  "slug": "predatory_assault_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "DISCARDED_CARD_POWER_GTE",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "DOMINATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesEffectGrantsDominate()
return true;
// CRUCombatEffectActive()
case "predatory_assault_red": case "predatory_assault_yellow": case "predatory_assault_blue": return true;
// CRUPlayAbility()
if(GetClassState($currentPlayer, $CS_Num6PowDisc) > 0) {
        AddCurrentTurnEffect($cardID, $currentPlayer);
        $rv = "Gains Dominate.";
      }
      return $rv;
```

### dawnblade_resplendent  — looks-aligned
text: '**Once per Turn Action** - {r}: **Attack**\n\nThe second time you attack with this each turn, it gets +1{p} until end of turn.'
```json
{
  "slug": "dawnblade_resplendent",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "per_turn": 1,
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "CHAIN_HIT_COUNT_GTE",
              "amount": 2
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += GetClassState($mainPlayer, $CS_AttacksWithWeapon) >= 1 ? 1 : 0;
        break;
// IsCardBanned()
return false;
// DVRAbilityType()
case "dawnblade_resplendent": return "AA";
// DVRAbilityCost()
case "dawnblade_resplendent": return 1;
```

### blessing_of_occult_yellow  — looks-aligned
text: 'At the start of your turn, destroy Blessing of Occult then create 2 Runechant tokens.'
```json
{
  "slug": "blessing_of_occult_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "amount": 2,
          "token_type": "Runechant"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
if ($auras[$i] == "blessing_of_occult_red") $amount = 3;
        else $amount = ($auras[$i] == "blessing_of_occult_yellow") ? 2 : 1;
        PlayAura("runechant", $mainPlayer, $amount, true);
        DestroyAuraUniqueID($mainPlayer, $auras[$i + 6]);
        break;
```

### fuel_injector_blue  — looks-aligned
text: "**Instant** - Put this on the bottom of its owner's deck: Gain {r}"
```json
{
  "slug": "fuel_injector_blue",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "PUT_HAND_CARD_BOTTOM"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PayItemAbilityAdditionalCosts()
if (substr($items[$index + 9], 0, 5) != "THEIR") {
        $deck = new Deck($currentPlayer);
      } else {
        $deck = new Deck($otherPlayer);
      }
      RemoveItem($currentPlayer, $index);
      $deck->AddBottom($cardID, from: "PLAY");
      break;
// EVOPlayAbility()
if ($from == "PLAY") GainResources($currentPlayer, 1);
      return "";
```

### foreboding_bolt_yellow  — looks-aligned
text: 'Deal 2 damage to target hero.\n\n**Opt 1**'
```json
{
  "slug": "foreboding_bolt_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_GENERIC",
          "amount": 2,
          "target": "hero"
        },
        {
          "type": "OPT",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayRequiresTarget()
return 0;
// ActionsThatDoArcaneDamage()
return true;
// CRUPlayAbility()
DealArcane(ArcaneDamage($cardID), 0, "PLAYCARD", $cardID, resolvedTarget: $target);
      PlayerOpt($currentPlayer, 1);
      return "";
```

### scrub_the_deck_blue  — looks-aligned
text: "Destroy the top card of target hero's deck. If it's yellow, create a Gold token.\n\n**Go again**"
```json
{
  "slug": "scrub_the_deck_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DESTROY_REF",
          "target": {
            "type": "TOP_CARD",
            "controller": "opponent"
          }
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Gold",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "DECK",
              "controller": "opponent",
              "color": "yellow"
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// GetLayerTarget()
$context = "Choose whose deck to scrub";
      AddDecisionQueue("PASSPARAMETER", $currentPlayer, "MYCHAR-0,THEIRCHAR-0");
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, $context, 1);
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);
      break;
// SEAPlayAbility()
$targetPlayer = str_contains($target, "MY") ? $currentPlayer : $otherPlayer;
      $topCard = GetDeck($targetPlayer)[0];
      DestroyTopCard($targetPlayer);
      AddDecisionQueue("PASSPARAMETER", $currentPlayer, $topCard);
      AddDecisionQueue("ALLCARDCOLORORPASS", $currentPlayer, "2", 1);
      AddDecisionQueue("PASSPARAMETER", $currentPlayer, "gold", 1);
      AddDecisionQueue("PUTPLAY", $currentPlayer, "0", 1);
      break;
```

### sack_the_shifty_blue  — looks-aligned
text: "**Contract** - You are contracted to banish opponents' cards with base **go again**. Whenever you complete this contract, create a Silver token.\n\nWhen this hits a hero, banish the top card of their deck."
```json
{
  "slug": "sack_the_shifty_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": "OPPONENT_DECK_TOP"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNHitEffect()
if(IsHeroAttackTarget()) {
        $deck = new Deck($defPlayer);
        if($deck->Empty()) { WriteLog("The opponent deck is already... depleted."); break; }
        $deck->BanishTop(banishedBy:$cardID);
      }
      break;
// ContractType()
case "sack_the_shifty_red": case "sack_the_shifty_yellow": case "sack_the_shifty_blue": return "GOAGAIN";
// ContractCompleted()
$EffectContext = $cardID;
      PutItemIntoPlayForPlayer("silver", $player);
      break;
```

### bite_blue  — looks-aligned
text: '**Stealth**\n\nWhen this attacks a hero, you may have target dagger you control deal 1 damage to them. If damage is dealt this way, the dagger has hit. Destroy the dagger.'
```json
{
  "slug": "bite_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "OPT",
          "amount": 1
        },
        {
          "type": "DAGGER_DEALS_DAMAGE",
          "amount": 1
        },
        {
          "type": "DESTROY_REF",
          "target": "DAGGER"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
ThrowWeapon("Dagger", $parameter, target:$target);
        break;
// DecisionQueueStaticEffect()
$targetParts = explode("-", $target);
          $targetLoc = $targetParts[0];
          $targetInd = $targetParts[1];
          if ($targetLoc == "MYCHAR") {
            $targetInd = GetMZUID($player, $target);
          }
          AddLayer("TRIGGER", $player, $params[0], "$targetLoc,$targetInd");
          break;
// HNTPlayAbility()
if (IsHeroAttackTarget())
      {
        AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYCHAR:subtype=Dagger&COMBATCHAINATTACKS:subtype=Dagger;type=AA");
        AddDecisionQueue("REMOVEINDICESIFACTIVECHAINLINK", $currentPlayer, "<-", 1);
        AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);
        AddDecisionQueue("ADDTRIGGER", $currentPlayer, $cardID, 1);
      }
      break;
```

### mounting_anger_red  — looks-aligned
text: 'When Mounting Anger hits, you may banish an attack action card from your hand with cost less than the number of Draconic chain links you control. If you do, it gains +1{p} and you may play it this turn.\n\n**Go again**'
```json
{
  "slug": "mounting_anger_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "BANISH",
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zone": "HAND"
              },
              {
                "type": "ATTACK_TYPE_IN",
                "types": [
                  "Attack"
                ]
              },
              {
                "type": "ATTACK_COST_LTE",
                "amount": "DRACONIC_CHAIN_LINKS_CONTROLLED"
              }
            ]
          }
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zone": "BANISHED"
              },
              {
                "type": "ATTACK_TYPE_IN",
                "types": [
                  "Attack"
                ]
              }
            ]
          }
        },
        {
          "type": "SET_FLAG",
          "flag": "CAN_PLAY_BANISHED_ATTACK",
          "value": true,
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zone": "BANISHED"
              },
              {
                "type": "ATTACK_TYPE_IN",
                "types": [
                  "Attack"
                ]
              }
            ]
          }
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
$numDraconicLinks = NumDraconicChainLinks();
        MZMoveCard($mainPlayer, "MYHAND:type=AA;maxCost=" . ($numDraconicLinks > 0 ? $numDraconicLinks - 1 : -2), "MYBANISH,HAND,TT", may: true);
        AddDecisionQueue("PASSPARAMETER", $mainPlayer, "MYBANISH", 1);
        AddDecisionQueue("MZOP", $mainPlayer, "LASTMZINDEX", 1);
        AddDecisionQueue("MZOP", $mainPlayer, "GETUNIQUEID", 1);
        AddDecisionQueue("ADDLIMITEDCURRENTEFFECT", $mainPlayer, $parameter . ",HIT", 1);
        break;
// UPRNinjaHitEffect()
AddLayer("TRIGGER", $mainPlayer, $cardID);
        break;
// UPREffectPowerModifier()
case "mounting_anger_red": case "mounting_anger_yellow": case "mounting_anger_blue": return 1;
// UPRCombatEffectActive()
case "mounting_anger_red": case "mounting_anger_yellow": case "mounting_anger_blue": return true;
```

### golden_tipple_blue  — looks-aligned
text: 'When this attacks, you may discard a yellow card. If you do, draw a card and create a Gold token.\n\n**Go again**'
```json
{
  "slug": "golden_tipple_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "DISCARD",
          "color": "yellow"
        },
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Gold"
        }
      ],
      "conditions": [
        {
          "type": "DISCARDED_CARD_POWER_GTE",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SEAPlayAbility()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYHAND:pitch=2");
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Discard a card to " . CardLink($cardID) . " (or pass)", 1);
      AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("MZREMOVE", $currentPlayer, "<-", 1);
      AddDecisionQueue("DISCARDCARD", $currentPlayer, "HAND-$cardID", 1);
      AddDecisionQueue("ALLCARDCOLORORPASS", $currentPlayer, "2", 1);
      AddDecisionQueue("DRAW", $currentPlayer, $cardID, 1);
      AddDecisionQueue("PASSPARAMETER", $currentPlayer, "gold", 1);
      AddDecisionQueue("PUTPLAY", $currentPlayer, "0", 1);
      break;
```

### pleiades  — looks-aligned
text: '**Instant** - {t}, remove a suspense counter from an aura you control: You may put a suspense counter on an aura of suspense you control.\n\nWhenever the crowd cheers you, create a Confidence token.'
```json
{
  "slug": "pleiades",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "PAY_LIFE",
          "amount": 1
        },
        {
          "type": "REMOVE_COUNTERS",
          "target": "self",
          "counter_type": "suspense",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "MAY",
          "effects": [
            {
              "type": "PUT_COUNTER",
              "target": "self",
              "counter_type": "suspense",
              "amount": 1
            }
          ]
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CLASH_WIN_REVEALED",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CROWD_CHEERS"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Confidence"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if (CheckTapped("MYCHAR-$index", $currentPlayer)) return true;
      //check that there's an aura with a suspense counter
      if (count(GetSuspenseAuras($currentPlayer, true)) == 0) return true;
      return false;
// ProcessTrigger()
PlayAura("confidence", $player, isToken:true, effectController:$player, effectSource:$parameter);
        break;
// EquipPayAdditionalCosts()
Tap("MYCHAR-$cardIndex", $currentPlayer);
      $suspAuras = implode(",", GetSuspenseAuras($currentPlayer, true));
      AddDecisionQueue("PASSPARAMETER", $currentPlayer, $suspAuras);
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose an aura to remove a suspense counter from", 1);
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SUSPENSE", $currentPlayer, "REMOVE", 1);
      break;
// SUPPlayAbility()
$suspAuras = GetSuspenseAuras($currentPlayer);
      if (count($suspAuras) > 0) {
        $suspAuras = implode(",", GetSuspenseAuras($currentPlayer));
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, $suspAuras);
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose an aura to add a suspense counter to (or pass)", 1);
        AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("SUSPENSE", $currentPlayer, "ADD", 1);
      }
      break;
// Cheer()
AddLayer("TRIGGER", $player, $char[0]);
          break;
```

### cut_to_the_chase_yellow  — looks-aligned
text: "Target Assassin attack action card with **contract** gains +2{p}.\n\nLook at the top card of the defending hero's deck. You may put it on the bottom."
```json
{
  "slug": "cut_to_the_chase_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        },
        {
          "type": "LOOK_AT",
          "target": "defending_hero_deck_top"
        },
        {
          "type": "MAY",
          "effects": [
            {
              "type": "PUT_CARDS_BOTTOM",
              "target": "defending_hero_deck_top"
            }
          ]
        }
      ],
      "target": {
        "filter": [
          {
            "type": "ATTACK_CLASS_IN",
            "classes": [
              "assassin"
            ]
          },
          {
            "type": "HAS_KEYWORD",
            "keywords": [
              "contract"
            ]
          }
        ]
      }
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return !$CombatChain->HasCurrentLink() || !ClassContains($attackID, "ASSASSIN", $mainPlayer) || ContractType($attackID) == "";
// ReactionRequirementsMet()
case "cut_to_the_chase_red": case "cut_to_the_chase_yellow": case "cut_to_the_chase_blue": return ClassContains($combatChain[0], "ASSASSIN", $mainPlayer) && CardType($combatChain[0]) == "AA" && ContractType($combatChain[0]) != "";
// DYNEffectPowerModifier()
case "cut_to_the_chase_yellow": return 2;
// DYNCombatEffectActive()
case "cut_to_the_chase_red": case "cut_to_the_chase_yellow": case "cut_to_the_chase_blue": return true;
// DYNPlayAbility()
$otherPlayer = ($currentPlayer == 1 ? 2 : 1);
      AddDecisionQueue("DECKCARDS", $otherPlayer, "0", 1);
      AddDecisionQueue("SETDQVAR", $currentPlayer, "0", 1);
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose if you want sink <0>", 1);
      AddDecisionQueue("YESNO", $currentPlayer, "if_you_want_to_sink_the_opponent's_card", 1);
      AddDecisionQueue("NOPASS", $currentPlayer, "-", 1);
      AddDecisionQueue("FINDINDICES", $otherPlayer, "TOPDECK", 1);
      AddDecisionQueue("MULTIREMOVEDECK", $otherPlayer, "<-", 1);
      AddDecisionQueue("ADDBOTDECK", $otherPlayer, "-", 1);
      AddDecisionQueue("ELSE", $currentPlayer, "-");
      AddDecisionQueue("WRITELOG", $currentPlayer, "Left the card on top", 1);
      AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### shaden_scream_yellow  — looks-aligned
text: 'As an additional cost to play this, banish a random card from hand.\n\nYour next Brute or Shadow attack this turn gets +4{p}.\n\n**Go again**'
```json
{
  "slug": "shaden_scream_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "DISCARD_RANDOM"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4,
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "classes": [
                "brute",
                "shadow"
              ]
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DTDEffectPowerModifier()
case "shaden_scream_yellow": return 4;
// DTDCombatEffectActive()
case "shaden_scream_red": case "shaden_scream_yellow": case "shaden_scream_blue": return ClassContains($attackID, "BRUTE", $mainPlayer) || TalentContains($attackID, "SHADOW", $mainPlayer);
// DTDPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### absorb_in_aether_red  — looks-aligned
text: 'The next card you play this turn with an effect that deals arcane damage, instead deals that much arcane damage plus 2.'
```json
{
  "slug": "absorb_in_aether_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_PLAY",
            "conditions": [
              {
                "type": "DURING_TURN"
              },
              {
                "type": "HAS_KEYWORD",
                "keyword": "DEAL_ARCANE"
              }
            ],
            "effects": [
              {
                "type": "MODIFY_ATTACK",
                "mod": "add",
                "amount": 2
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EffectArcaneBonus()
return 2;
// ARCWizardPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
// ArcaneModifierAmount()
return 2;
```

### earths_embrace_blue  — looks-aligned
text: "**Go again**\n\nAt the beginning of your end phase, create an Embodiment of Earth token. Then, if you haven't banished an Earth card this turn, destroy this."
```json
{
  "slug": "earths_embrace_blue",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token": "Embodiment of Earth"
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": "self",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "BANISHED_EARTH_CARD"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraBeginEndPhaseTriggers()
AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", "-", $auras[$i + 6]);
        break;
// ProcessTrigger()
PlayAura("embodiment_of_earth", $player);
        if(GetClassState($player, $CS_NumEarthBanished) == 0) DestroyAuraUniqueID($player, $uniqueID);
        break;
```

### flex_red  — looks-aligned
text: 'When you attack or defend with Flex, you may pay {r}{r}. If you do, it gains +2{p}.'
```json
{
  "slug": "flex_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "resource_cost": 2,
          "on_success": [
            {
              "type": "MODIFY_ATTACK",
              "mod": "add",
              "amount": 2
            }
          ]
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "resource_cost": 2,
          "on_success": [
            {
              "type": "MODIFY_ATTACK",
              "mod": "add",
              "amount": 2
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
ChooseToPay($player, $parameter, "0,2");
        AddDecisionQueue("PASSPARAMETER", $player, $target, 1);
        AddDecisionQueue("COMBATCHAINPOWERMODIFIER", $player, "2", 1);
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
// UPREffectPowerModifier()
case "flex_red": case "flex_yellow": case "flex_blue": return 2;
// UPRCombatEffectActive()
case "flex_red": case "flex_yellow": case "flex_blue": return true;
// UPRTalentPlayAbility()
$hand = &GetHand($currentPlayer);
        $resources = &GetResources($currentPlayer);
        if (count($hand) > 0 || $resources[0] >= 2)
        {
          AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose if you want to pay to buff " . CardLink($cardID, $cardID), 1);
          AddDecisionQueue("BUTTONINPUT", $currentPlayer, "0,2", 0, 1);
          AddDecisionQueue("PAYRESOURCES", $currentPlayer, "<-", 1);
        }
        else {
          AddDecisionQueue("PASSPARAMETER", $currentPlayer, "0");
        }
        AddDecisionQueue("LESSTHANPASS", $currentPlayer, "1", 1);
        AddDecisionQueue("ADDCURRENTTURNEFFECT", $currentPlayer, $cardID, 1);
        return "";
```

### hydraulic_press_blue  — looks-aligned
text: '**Scrap**\n\nWhen this attacks, if it scrapped a card, this gets **overpower**.'
```json
{
  "slug": "hydraulic_press_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "Scrap"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "OVERPOWER"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsOverpowerActive()
return SearchCurrentTurnEffects($combatChain[0], $mainPlayer);
// EVOPlayAbility()
if (DelimStringContains($additionalCosts, "SCRAP", true)) AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### civic_duty  — looks-aligned
text: "Whenever this defends, create a Vigor token under another hero's control.\n\n**Temper**"
```json
{
  "slug": "civic_duty",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
PlayAura("vigor", $otherPlayer, effectController:$player);
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
```

### overcome_adversity  — looks-aligned
text: "This may only defend an attack if the attack's controller has destroyed an Agility token this turn.\n\n**Blade Break**"
```json
{
  "slug": "overcome_adversity",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "AGILITY_TOKEN_DESTROYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsBlockRestricted()
return GetClassState($mainPlayer, $CS_NumAgilityDestroyed) == 0;
```

### sting_of_sorcery_blue  — looks-aligned
text: '**Go again**\n\nAttack action cards you control gain "When you attack with this, deal 1 arcane damage to target hero."\n\nAt the beginning of your end phase, destroy Sting of Sorcery.'
```json
{
  "slug": "sting_of_sorcery_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_ATTACK",
          "effects": [
            {
              "type": "DEAL_ARCANE",
              "amount": 1
            }
          ],
          "target": {
            "filter": [
              {
                "type": "CONTROLS_ATTACK_ACTION"
              }
            ]
          }
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraEndTurnAbilities()
$remove = true;
        break;
// AuraAttackAbilities()
if ($attackType == "AA") {
          AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", $attackID, $auras[$i + 6]);
        }
        break;
// ProcessTrigger()
if(count($combatChain) > 0) DealArcane(1, 0, "PLAYCARD", $combatChain[0]);
        break;
```

### point_of_engagement_yellow  — looks-aligned
text: 'Your next dagger attack this turn gets +2{p}.\n\nUntil end of turn, your attacks get +1{p} while attacking a **marked** hero.\n\n**Go again**'
```json
{
  "slug": "point_of_engagement_yellow",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2,
          "conditions": [
            {
              "type": "ATTACK_TYPE_IN",
              "types": [
                "dagger"
              ]
            },
            {
              "type": "DURING_TURN"
            }
          ]
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "ATTACK_TARGET_IS_HERO",
              "conditions": [
                {
                  "type": "OPPONENT_IS_MARKED"
                }
              ]
            },
            {
              "type": "DURING_TURN"
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HNTPlayAbility()
AddCurrentTurnEffect($cardID."-NEXTDAGGER", $currentPlayer);
      AddCurrentTurnEffect($cardID."-MARKEDBUFF", $currentPlayer);
      break;
```

### blistering_blade_red  — looks-aligned
text: 'Target dagger attack gets +2{p}. If you control 2 or more Draconic chain links, instead it gets +3{p}.'
```json
{
  "slug": "blistering_blade_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ],
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "draconic_chain_link",
          "amount": 2
        }
      ],
      "additional_effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if (!$CombatChain->HasCurrentLink()) return true;
      if (SearchCombatChainAttacks($currentPlayer, subtype:"Dagger") != "") return false;
      if (SubtypeContains($CombatChain->CurrentAttack(), "Dagger", $currentPlayer)) return false;
      return true;
// GetLayerTarget()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "COMBATCHAINATTACKS:subtype=Dagger&ACTIVEATTACK:subtype=Dagger");
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a dagger attack");
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);  
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// HNTPlayAbility()
if (SubtypeContains($CombatChain->AttackCard()->ID(), "Dagger", $currentPlayer)) AddCurrentTurnEffect($cardID, $currentPlayer);
      break;
```

### embrace_adversity  — looks-aligned
text: "This may only defend an attack if the attack's controller has destroyed a Might token this turn.\n\n**Blade Break**"
```json
{
  "slug": "embrace_adversity",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "MIGHT_TOKEN_DESTROYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsBlockRestricted()
return GetClassState($mainPlayer, $CS_NumMightDestroyed) == 0;
```

### read_the_glide_path_red  — looks-aligned
text: 'Your next arrow attack this turn gains +3{p}.\n\n**Opt 1**\n\n**Go again**'
```json
{
  "slug": "read_the_glide_path_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "DURING_TURN"
            },
            {
              "type": "ATTACK_TYPE_IN",
              "types": [
                "arrow"
              ]
            }
          ]
        },
        {
          "type": "OPT",
          "amount": 1
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVREffectPowerModifier()
case "read_the_glide_path_red": return 3;
// EVRCombatEffectActive()
case "read_the_glide_path_red": case "read_the_glide_path_yellow": case "read_the_glide_path_blue": return CardSubType($attackID) == "Arrow";
// EVRPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        Opt($cardID, 1);
        return "";
```

### sanctuary_of_aria  — looks-aligned
text: '**Instant** - {r}{r}: Prevent the next 1 damage that would be dealt to you this turn by a source of your choice. Destroy this at the beginning of the end phase.'
```json
{
  "slug": "sanctuary_of_aria",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "activation_cost": 2,
      "effects": [
        {
          "type": "WARD",
          "amount": 1
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": "self",
          "trigger": "START_OF_TURN_IN_GRAVEYARD"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CardSubType()
case "sanctuary_of_aria"://Technically false, but helps with Rosetta Limited
// CurrentTurnEffectDamagePreventionAmount()
if ($source == $currentTurnEffects[$index + 2]) {
        return $damage;
      }
      break;
// CurrentEffectDamagePrevention()
if ($source == $currentTurnEffects[$index + 2]) {
        if ($preventable) {
          $preventedDamage += $currentTurnEffects[$index + 3];
          $currentTurnEffects[$index + 3] -= $damage;
        }
        if ($currentTurnEffects[$index + 3] <= 0) RemoveCurrentTurnEffect($index);
      }
      break;
// GetLayerTarget()
if($from != "HAND"){
        AddDecisionQueue("FINDINDICES", $currentPlayer, "DAMAGEPREVENTIONTARGET");
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a damage source for " . CardLink($cardID, $cardID));
        AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);  
        AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      }
      break;
// ROSPlayAbility()
if($from != "MANUAL") { //"MANUAL" is used for the ability to put this macro into play
        $params = explode("-", $target);
        if(str_contains($params[0], "AURAS")) {
          $index = SearchAurasForUniqueID($params[1], $otherPlayer);
          $target = "THEIRAURAS-" . $index;
        }
        if(GetMZCard($currentPlayer, $target) == "MELD"){
          $target = $params[0] . "-" . ($params[1]+2);
        }
        if($target != "-") AddCurrentTurnEffect($cardID, $currentPlayer, $from, GetMZCard($currentPlayer, $target));
        if(!SearchCurrentTurnEffects($cardID . "-1", $currentPlayer)) AddCurrentTurnEffect($cardID . "-1", $currentPlayer);  
      }
      return "";
```

### fiddlers_green_red  — looks-aligned
text: 'When this is put into your graveyard from anywhere, gain 3{h}.'
```json
{
  "slug": "fiddlers_green_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "effects": [
        {
          "type": "GAIN",
          "asset": "HEALTH_POINTS",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
$healthGain = match ($parameter) {
          "fiddlers_green_red" => 3,
          "fiddlers_green_yellow" => 2,
          "fiddlers_green_blue" => 1,
        };
        GainHealth($healthGain, $player);
        break;
// AddGraveyard()
if ($cardController == "" || $player == $cardController) // only if it goes to *your* graveyard
        AddLayer("TRIGGER", $player, $cardID);
      break;
```

### test_of_vigor_red  — looks-aligned
text: 'When this defends, **clash** with the attacking hero. The winner creates a Vigor token.'
```json
{
  "slug": "test_of_vigor_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "CLASH",
          "target": {
            "filter": [
              {
                "type": "ATTACK_CLASS_IN",
                "classes": [
                  "hero"
                ]
              }
            ]
          }
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
Clash($parameter, effectController: $player);
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
// WonClashAbility()
PlayAura("vigor", $playerID);
        break;
```

### qi_unleashed_blue  — looks-aligned
text: '**Combo** - If Crouching Tiger was the last attack this combat chain, this gets +4{p}.'
```json
{
  "slug": "qi_unleashed_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "COMBO_CONTAINS",
          "card": "Crouching Tiger"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Crouching Tiger") return true;
        break;
// PowerModifier()
$power += (ComboActive() ? 4 : 0);
        break;
```

### overswing_blue  — looks-aligned
text: 'The next Guardian attack action card you play this turn gets +1{p}.\n\n**Go again**\n\n**Heave 2**'
```json
{
  "slug": "overswing_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "OVERSWING_FLAG"
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "OVERSWING_FLAG"
        },
        {
          "type": "AND",
          "conditions": [
            {
              "type": "IS_ACTIVE_PLAYER"
            },
            {
              "type": "ATTACK_CLASS_IN",
              "classes": [
                "Guardian"
              ]
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HeaveValue()
case "overswing_red": case "overswing_yellow": case "overswing_blue": return 2;
// MPGPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### bigger_than_big_yellow  — looks-aligned
text: 'At the start of your turn, destroy this, then your next Guardian attack this turn gets +4{p} and "When this attacks a hero, you may **wager** a Might token with them."'
```json
{
  "slug": "bigger_than_big_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4,
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Guardian"
            }
          ]
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_ATTACK",
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Guardian"
            }
          ],
          "effects": [
            {
              "type": "WAGER",
              "token": "Might"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
AddCurrentTurnEffect($auras[$i] . "-BUFF", $mainPlayer, "PLAY");
        DestroyAuraUniqueID($mainPlayer, $auras[$i + 6]);
        break;
// ProcessWager()
PlayAura("might", $wonWager, $amount);
        break;
// ResolveWagers()
if (!$chainClosed) {
              $triggerCardID = $currentTurnEffects[$i];
              AddLayer("TRIGGER", $mainPlayer, $triggerCardID, $wonWager, "WAGER");
            }
            RemoveCurrentTurnEffect($i);
            break;
```

### shadow_of_ursur_blue  — looks-aligned
text: 'You may play Shadow of Ursur from your banished zone.\n\nAs an additional cost to play Shadow of Ursur, you may banish a card with blood debt from your hand. If you do, Shadow of Ursur gains **go again**.\n\n**Blood Debt**'
```json
{
  "slug": "shadow_of_ursur_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "BANISH_FROM_GRAVEYARD",
          "conditions": [
            {
              "type": "HAS_KEYWORD",
              "keyword": "BloodDebt"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayableFromBanish()
return true;
// PayAdditionalCosts()
MZMoveCard($currentPlayer, "MYHAND:bloodDebtOnly=true", "MYBANISH,HAND,-", may: true);
      AddDecisionQueue("OP", $currentPlayer, "GIVEATTACKGOAGAIN", 1);
      break;
```

### sky_fire_lanterns_blue  — looks-aligned
text: "Reveal the top card of your deck. If it's blue, create a Runechant token.\n\n**Go again**"
```json
{
  "slug": "sky_fire_lanterns_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "REVEAL_TOP_DECK"
        },
        {
          "type": "CREATE_TOKEN",
          "conditions": [
            {
              "type": "REF_PITCH_IS",
              "pitch": "blue"
            }
          ],
          "token": "Runechant"
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNPlayAbility()
$deck = new Deck($currentPlayer);
      if($deck->Reveal(1)) if(ColorContains($deck->Top(), PitchValue($cardID), $currentPlayer)) PlayAura("runechant", $currentPlayer, 1, true);
      return "";
```

### smelting_of_the_old_ones_red  — looks-aligned
text: '**Crush** - When this deals 4 or more damage to a Guardian hero, destroy all equipment they control with -1{d} counters.\n\n**Heave 2**'
```json
{
  "slug": "smelting_of_the_old_ones_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CRUSH",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "class": "Guardian"
        },
        {
          "type": "ATTACK_POWER_GT_BASE",
          "amount": 4
        }
      ],
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "target": "equipment",
          "conditions": [
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "equipment"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddCrushEffectTrigger()
$defChar = GetPlayerCharacter($defPlayer);
      if (ClassContains($defChar[0], "GUARDIAN", $defPlayer)) {
        AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "CRUSHEFFECT");
      }
      break;
// HeaveValue()
case "blinding_of_the_old_ones_red": case "smelting_of_the_old_ones_red": case "disenchantment_of_the_old_ones_red": return 2;
// ProcessCrushEffect()
MZDestroy($mainPlayer, SearchMultizone($mainPlayer, "THEIRCHAR:type=E;hasNegCounters=true"), $mainPlayer); 
        break;
```

### war_machine_red  — looks-aligned
text: 'If you have 1 or more Evos equipped, this gets "When this hits a hero, destroy all cards in their arsenal,""\n\n- 2 or more, this costs {r}{r}{r} less to play,\n- 3 or more, this gets **overpower**,\n- 4 or more, this gets +3{p}.'
```json
{
  "slug": "war_machine_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Evo"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "target": "arsenal"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Evo",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Evo",
          "amount": 3
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "OVERPOWER"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Evo",
          "amount": 4
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddOnHitTrigger()
if (IsHeroAttackTarget() && EvoUpgradeAmount($mainPlayer) >= 1) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "ONHITEFFECT");
        return true;
      }
      break;
// PowerModifier()
$power += EvoUpgradeAmount($mainPlayer) >= 4 ? 3 : 0;
        break;
// IsOverpowerActive()
return EvoUpgradeAmount($mainPlayer) >= 3;
// SelfCostModifier()
return EvoUpgradeAmount($currentPlayer) >= 2 ? -3 : 0;
// EVOHitEffect()
if (IsHeroAttackTarget() && EvoUpgradeAmount($mainPlayer) >= 1) DestroyArsenal($defPlayer, effectController: $mainPlayer);
      break;
```

### blessing_of_aether_blue  — looks-aligned
text: 'At the start of your turn, destroy Blessing of Aether then if the next card you play this turn has an arcane damage effect, instead it deals that much arcane damage plus 1.'
```json
{
  "slug": "blessing_of_aether_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_PLAY",
            "conditions": [
              {
                "type": "HAS_KEYWORD",
                "keyword": "DEAL_ARCANE"
              }
            ],
            "effects": [
              {
                "type": "MODIFY_EFFECT",
                "effect_type": "DEAL_ARCANE",
                "mod": "add",
                "amount": 1
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
case "power_stance_blue": // These can stack, so we don't care if the effect is already in play. See: Ancestral Harmony for comparison.
// EffectArcaneBonus()
return 1;
// ClearNextCardArcaneBuffs()
if ($currentTurnEffects[$i + 2] == -1) {
            if (!IsStaticType(CardType($playedCard), $from, $playedCard) && GetResolvedAbilityType($playedCard, $from) != "I") $remove = 1;
          }
          break;
// ArcaneModifierAmount()
return 1;
```

### deep_recesses_of_existence_blue  — looks-aligned
text: '**Rune Gate**\n\nWhen the combat chain closes, you may banish this face-down. If you do, for each hero who has lost {h} this turn, banish a card from their graveyard.\n\n**Blood Debt**'
```json
{
  "slug": "deep_recesses_of_existence_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_COMBAT_CLOSE",
      "effects": [
        {
          "type": "BANISH",
          "target": "self",
          "face_down": true
        },
        {
          "type": "BANISH_REF",
          "ref": "OPPONENTS_WITH_LOST_LIFE",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CombatChainClosedTriggers()
// Do you want to banish this card face-down, and banish a card from each player who lost life this turn?
          AddDecisionQueue("YESNO", $mainPlayer, "do_you_want_to_banish_".CardLink("deep_recesses_of_existence_blue", "deep_recesses_of_existence_blue")."?");
          // This will exit early if No
          AddDecisionQueue("NOPASS", $mainPlayer, "-");
          Await($mainPlayer, "deep_recesses_of_existence_blue", i:$i, j:$j, final:true);
          break;
```

### swell_tidings_red  — looks-aligned
text: 'Deal 5 arcane damage to target hero.\n\n**Surge** - If this deals more than 5 damage, create a Ponder token.'
```json
{
  "slug": "swell_tidings_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 5
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Ponder",
          "conditions": [
            {
              "type": "SURGE"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayRequiresTarget()
return 0;
// ActionsThatDoArcaneDamage()
return true;
// ProcessSurge()
PlayAura("ponder", $player);
      WriteLog(CardLink($cardID, $cardID) . " created a " . CardLink("ponder", "ponder") . " token");
      break;
// DYNPlayAbility()
case "sap_red": case "sap_yellow": case "sap_blue": DealArcane(ArcaneDamage($cardID), 0, "PLAYCARD", $cardID, resolvedTarget: $target); return "";
```

### earthlore_empowerment_red  — looks-aligned
text: 'At the start of your turn, destroy this, then the next Guardian attack action card you play this turn costs {r} less to play and gets +5{p}.'
```json
{
  "slug": "earthlore_empowerment_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_PLAY",
            "conditions": [
              {
                "type": "CARD_IN_ZONE",
                "zone": "arsenal",
                "card_type": "ACTION",
                "classes": [
                  "Guardian"
                ]
              }
            ],
            "effects": [
              {
                "type": "PAY_OR_DAMAGE",
                "amount": 1
              },
              {
                "type": "MODIFY_ATTACK",
                "mod": "add",
                "amount": 5
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
case "power_stance_blue": // These can stack, so we don't care if the effect is already in play. See: Ancestral Harmony for comparison.
// CurrentEffectCostModifiers()
if (ClassContains($cardID, "GUARDIAN", $currentPlayer) && $cardType == "AA") $costModifier -= 1;
          break;
```

### battalion_barque_red  — looks-aligned
text: 'High Tide - If there are 2 or more blue cards in your pitch zone, this gets +2{p}.'
```json
{
  "slug": "battalion_barque_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "pitch",
          "amount": 2,
          "color": "blue"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += 2;
          break;
```

### wither_blue  — looks-aligned
text: '**Stealth**\n\nWhen this hits a hero, create a Frailty token under their control.'
```json
{
  "slug": "wither_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Frailty"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTHitEffect()
if(IsHeroAttackTarget()) PlayAura($CID_Frailty, $defPlayer, effectController: $mainPlayer);
        break;
```

### polarity_reversal_script_red  — looks-aligned
text: '**Crank**\n\nThis enters the arena with a steam counter. At the start of your turn, destroy this unless you remove a steam counter from it.\n\nAction cards get -1{d} while defending your Mechanologist attack action cards.'
```json
{
  "slug": "polarity_reversal_script_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "steam",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "cost": [
        {
          "type": "REMOVE_COUNTERS",
          "counter": "steam",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "subtract",
          "amount": 1,
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Mechanologist"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ItemStartTurnAbility()
if ($mainItems[$index + 1] > 0 && GetItemGemState($mainPlayer, $mainItems[$index], $index) == 0) --$mainItems[$index + 1];
      elseif($mainItems[$index + 1] > 0) {
        AddDecisionQueue("YESNO", $mainPlayer, "if you want to remove a Steam Counter and keep " . CardLink($mainItems[$index], $mainItems[$index]) . " and keep it in play?");
        AddDecisionQueue("REMOVECOUNTERITEMORDESTROYUID", $mainPlayer, $mainItems[$index + 4]);
      }
      else DestroyItemForPlayer($mainPlayer, $index);
      break;
// ItemBlockModifier()
$type = CardType($cardID);
        $typeEvo = "";
        if (substr($cardID, -5) == "equip") {
          $typeEvo = CardType(substr($cardID,0, strlen($cardID) - 6));
        }
        $attackID = $CombatChain->AttackCard()->ID();
        if ((DelimStringContains($type, "A") || $type == "AA" || $typeEvo == "A") && CardType($attackID) == "AA" && ClassContains($attackID, "MECHANOLOGIST", $mainPlayer)) --$blockModifier;
        break;
```

### whelming_gustwave_red  — looks-aligned
text: '**Combo** - If Surging Strike was the last attack this combat chain, Whelming Gustwave gains +1{p}, **go again**, and "If this hits, draw a card."'
```json
{
  "slug": "whelming_gustwave_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SURGING_STRIKE_LAST_ATTACK"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Surging Strike") return true;
        break;
// AddOnHitTrigger()
if (ComboActive($cardID)) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "ONHITEFFECT");
        return true;
      }
      break;
// PowerModifier()
$power += (ComboActive() ? 1 : 0);
        break;
// DoesAttackHaveGoAgain()
return ComboActive($attackID);
// WTRHitEffect()
Draw($mainPlayer);
        break;
```

### honing_hood  — looks-aligned
text: '**Instant** - Destroy Honing Hood: Return all cards in your arsenal to your hand, then put a card from your hand face down into your arsenal.'
```json
{
  "slug": "honing_hood",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "RETURN_DR_FROM_GRAVEYARD"
        },
        {
          "type": "PUT_HAND_CARD_BOTTOM"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// ELERangerPlayAbility()
$arsenal = &GetArsenal($currentPlayer);
        $arsenalCount = count($arsenal);
        $arsenalPieces = ArsenalPieces();
        for($i=0; $i < $arsenalCount; $i+=$arsenalPieces) {
          AddPlayerHand($arsenal[$i], $currentPlayer, "ARS");
        }
        $arsenal = [];
        MZMoveCard($currentPlayer, "MYHAND", "MYARS,HAND,DOWN", silent:true);
        return "";
// ELEAbilityType()
case "honing_hood": return "I";
```

### pledge_fealty_red  — looks-aligned
text: 'Create a Fealty token.'
```json
{
  "slug": "pledge_fealty_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Fealty"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HNTPlayAbility()
PlayAura("fealty", $currentPlayer);
      break;
```

### blood_of_the_dracai_red  — looks-aligned
text: '**Legendary**\n\nWhen you pitch Blood of the Dracai, the next 3 Draconic cards you play this turn cost {r} less.'
```json
{
  "slug": "blood_of_the_dracai_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PITCH",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "ref": "blood_of_the_dracai_red"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "DRACONIC_COST_REDUCTION",
          "duration": "END_OF_TURN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DRACONIC_COST_REDUCTION"
        },
        {
          "type": "CARD_IN_ZONE",
          "zone": "HAND",
          "class_in": [
            "Draconic"
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA",
          "mod": "subtract",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CurrentTurnEffectUses()
return 3;
// PitchAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      break;
// CurrentEffectCostModifiers()
if (TalentContains($cardID, "DRACONIC", $currentPlayer) && $from != "PLAY" && $from != "EQUIP") {
            $costModifier -= 1;
            --$currentTurnEffects[$i + 3];
            if ($currentTurnEffects[$i + 3] <= 0) $remove = true;
          }
          break;
```

### parched_terrain_red  — looks-aligned
text: "Heroes can't gain {h}.\n\nAt the beginning of your end phase, put a sand counter on this, then destroy it unless you banish a red card from your graveyard for each sand counter on it."
```json
{
  "slug": "parched_terrain_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "PARCHED_TERRAIN_AURA"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "HEROES_CANT_GAIN_LIFE"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "PARCHED_TERRAIN_AURA"
        }
      ],
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "sand",
          "amount": 1
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": "self",
          "conditions": [
            {
              "type": "NOT",
              "condition": {
                "type": "BANISH_NAMED_GRAVEYARD_OPTIONAL",
                "color": "red",
                "amount": {
                  "type": "COUNTER_GTE",
                  "counter": "sand"
                }
              }
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraBeginEndPhaseTriggers()
AddLayer("TRIGGER", $mainPlayer, $auras[$i], "parched_terrain_red-1", uniqueID: $auras[$i + 6]);
        break;
```

### entwine_earth_yellow  — looks-aligned
text: '**Earth Fusion**\n\nIf Entwine Earth was **fused**, it gains +2{p}.'
```json
{
  "slug": "entwine_earth_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FUSED_FLAG"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// FuseAbility()
$index = GetClassState($player, $CS_PlayCCIndex);
        $CombatChain->Card($index)->ModifyPower(2);
        break;
// HasFusion()
case "entwine_earth_red": case "entwine_earth_yellow": case "entwine_earth_blue": return "EARTH";
```

### seismic_shelter_blue  — looks-aligned
text: '**Go again**\n\nAttack action cards you control get +X{d} while defending, where X is the number of Seismic Surge tokens you control.\n\nAt the start of your turn, destroy this.'
```json
{
  "slug": "seismic_shelter_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": "X",
          "conditions": [
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "Seismic Surge"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
DestroyAuraUniqueID($mainPlayer, $auras[$i + 6]);
        break;
// AuraBlockModifier()
if ($cardType == "AA") $blockModifier += CountAura("seismic_surge", $defPlayer);
        break;
```

### graven_justaucorpse  — looks-aligned
text: '**Instant** - Destroy this: Discard a card. Gain {r} equal to its pitch value.\n\n**Battleworn**'
```json
{
  "slug": "graven_justaucorpse",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "DISCARD_RANDOM"
        },
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": "pitch_value"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// AGBPlayAbility()
PummelHit($currentPlayer);
        AddDecisionQueue("GAINRESOURCESLASTRESULT", $currentPlayer, "<-", 1);
        break;
```

### goldwing_turbine_blue  — looks-aligned
text: 'Your next Mechanologist attack this turn gets +1{p}.\n\nCreate a Golden Cog token.'
```json
{
  "slug": "goldwing_turbine_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "DURING_TURN",
              "player": "self"
            },
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Mechanologist"
            }
          ]
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Golden Cog"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SEAPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      PutItemIntoPlayForPlayer("golden_cog", $currentPlayer);
      break;
```

### last_ditch_effort_blue  — looks-aligned
text: 'When you play Last Ditch Effort, if you have no cards in your deck, it gains +4{p} and **go again**.'
```json
{
  "slug": "last_ditch_effort_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "conditions": [
        {
          "type": "DECK_EMPTY"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
$deck = new Deck($mainPlayer);
      return $deck->Empty();
// WTREffectPowerModifier()
case "last_ditch_effort_blue": return 4;
// WTRCombatEffectActive()
case "last_ditch_effort_blue": return true;
// WTRPlayAbility()
if(count(GetDeck($currentPlayer)) == 0) {
          GiveAttackGoAgain();
          AddCurrentTurnEffect($cardID, $currentPlayer);
          $rv = "Gains go again and +4";
        }
        return $rv;
```

### invoke_azvolai_red  — looks-aligned
text: '**Transform** target ash you control into Azvolai. **Go again**'
```json
{
  "slug": "invoke_azvolai_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "TRANSFORM_HERO",
          "target": "Ash"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return SearchCount(SearchPermanents($player, "", "Ash")) < 1;
// GetLayerTarget()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYPERM:subtype=Ash");
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose an Ash to transform");
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// UPRIllusionistPlayAbility()
case "invoke_azvolai_red": return Transform($currentPlayer, "Ash", "azvolai", target:$target);
```

### call_in_the_big_guns_red  — looks-aligned
text: 'Your next arrow attack this turn gets +3{p}.\n\nYou may put an arrow from your hand face-up into your arsenal.\n\n**Go again**'
```json
{
  "slug": "call_in_the_big_guns_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "NEXT_ARROW_ATTACK"
            }
          ]
        },
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "PUT_ARROW_IN_ARSENAL"
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SEAPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      LoadArrow($currentPlayer);
      break;
      //other cards
```

### primeval_bellow_red  — looks-aligned
text: 'As an additional cost to play Primeval Bellow, discard a random card.\n\nYour next Brute attack this turn gains +5{p}.\n\n**Go again**'
```json
{
  "slug": "primeval_bellow_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "DISCARD_RANDOM"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 5,
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Brute"
            },
            {
              "type": "DURING_TURN"
            }
          ]
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// WTREffectPowerModifier()
case "primeval_bellow_red": return 5;
// WTRCombatEffectActive()
case "primeval_bellow_red": case "primeval_bellow_yellow": case "primeval_bellow_blue": return ClassContains($attackID, "BRUTE", $mainPlayer);
// WTRPlayAbility()
AddCurrentTurnEffect($cardID, $mainPlayer);
        return "";
      //Guardian
```

### push_the_point_yellow  — looks-aligned
text: 'If the last attack on this combat chain hit, Push the Point gains +2{p}.'
```json
{
  "slug": "push_the_point_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LAST_ATTACK_HIT"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$idx = count($chainLinkSummary) - ChainLinkSummaryPieces();
        if (isset($chainLinkSummary[$idx]) && $chainLinkSummary[$idx] > 0) $power += 2;
        break;
```

### dread_triptych_blue  — looks-aligned
text: "When you attack with Dread Triptych, if you've played a 'non-attack' action card this turn, create a Runechant token.\n\nWhen you attack with Dread Triptych, if you've dealt arcane damage this turn, create a Runechant token.\n\nIf Dread Triptych hits, create a Runechant token."
```json
{
  "slug": "dread_triptych_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "NON_ATTACK_ACTION_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ARCANEDAMAGE_DEALT_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
if (GetClassState($player, $CS_NumNonAttackCards) > 0) PlayAura("runechant", $player);
        if (GetClassState($player, $CS_ArcaneDamageDealt) > 0) PlayAura("runechant", $player);
        break;
// CRUPlayAbility()
AddLayer("TRIGGER", $currentPlayer, $cardID);
      return "";
// CRUHitEffect()
PlayAura("runechant", $mainPlayer);
      break;
```

### writhing_beast_hulk_red  — looks-aligned
text: 'As an additional cost to play Writhing Beast Hulk, banish 3 random cards from your graveyard.\n\nIf a card with 6 or more {p} is banished this way, Writhing Beast Hulk gains **dominate**.\n\n**Blood Debt**'
```json
{
  "slug": "writhing_beast_hulk_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "BANISH_NAMED_GRAVEYARD_OPTIONAL",
          "amount": 3
        }
      ],
      "effects": [
        {
          "type": "DOMINATE",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "BLOOD_DEBT_FLAG"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "BLOOD_DEBT_FLAG"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return (new Discard($player))->NumCards() < 3;
// DoesEffectGrantsDominate()
return true;
// PayAdditionalCosts()
if (RandomBanish3GY($cardID) > 0) AddCurrentTurnEffect($cardID, $currentPlayer);
      break;
// MONCombatEffectActive()
case "writhing_beast_hulk_red": case "writhing_beast_hulk_yellow": case "writhing_beast_hulk_blue": return true;
```

### pulsewave_harpoon_red  — looks-aligned
text: "When this attacks a hero, they reveal X cards from their hand, where X is the number of times you've **boosted** this combat chain. Choose an action card with {d} less than or equal to X, then add it to this chain link as a defending card.\n\n**Boost**"
```json
{
  "slug": "pulsewave_harpoon_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BOOST_FLAG"
        }
      ],
      "effects": [
        {
          "type": "REVEAL_HAND_MARK_IF_TYPE",
          "amount": "BOOST_FLAG_COUNT",
          "card_type": "ACTION"
        },
        {
          "type": "SELECT_FROM_REF",
          "ref": "REVEALED_CARDS",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "REVEALED_CARDS"
            },
            {
              "type": "ATTACK_COST_LTE",
              "amount": "BOOST_FLAG_COUNT"
            }
          ],
          "effects": [
            {
              "type": "MOVE_REF",
              "from": "REVEALED_CARDS",
              "to": "DEFENDING_CARDS"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNPlayAbility()
$numBoosted = $combatChainState[$CCS_NumBoosted];
      $otherPlayer = ($currentPlayer == 1 ? 2 : 1);
      $otherPlayerHand = GetHand($otherPlayer);
      if(IsHeroAttackTarget() && $numBoosted > 0 && count($otherPlayerHand) > 0)
      {
        $numToReveal = min($numBoosted, count($otherPlayerHand));
        AddDecisionQueue("PASSPARAMETER", $otherPlayer, $numBoosted, 1);
        AddDecisionQueue("SETDQVAR", $currentPlayer, "0");
        AddDecisionQueue("FINDINDICES", $otherPlayer, "HAND");
        AddDecisionQueue("APPENDLASTRESULT", $otherPlayer, "-{0}", 1);
        AddDecisionQueue("PREPENDLASTRESULT", $otherPlayer, "{0}-", 1);
        AddDecisionQueue("SETDQCONTEXT", $otherPlayer, "Select exactly $numToReveal card(s) from your hand to reveal", 1);
        AddDecisionQueue("MULTICHOOSEHAND", $otherPlayer, "<-", 1);
        AddDecisionQueue("IMPLODELASTRESULT", $otherPlayer, ",", 1);
        AddDecisionQueue("SETDQVAR", $currentPlayer, "1");
        AddDecisionQueue("REVEALHANDCARDS", $otherPlayer, "<-", 1);
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, "{1}", 1);
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a revealed action card with $numBoosted or less defense to add as a defending card", 1);
        AddDecisionQueue("SPECIFICCARD", $otherPlayer, "PULSEWAVEHARPOONFILTER", 1);
        AddDecisionQueue("CHOOSETHEIRHAND", $currentPlayer, "<-", 1);
        AddDecisionQueue("MULTIREMOVEHAND", $otherPlayer, "-", 1);
        AddDecisionQueue("ADDCARDTOCHAINASDEFENDINGCARD", $otherPlayer, "HAND", 1);
      }
      return "";
```

### flex_claws_yellow  — looks-aligned
text: 'When this hits, create a Crouching Tiger in your banished zone. You may play it this turn.\n\n**Go again**'
```json
{
  "slug": "flex_claws_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Crouching Tiger",
          "zone": "banished"
        },
        {
          "type": "BANISH_OPP_TOP_GRANT_PLAY",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNHitEffect()
case "flex_claws_red": case "flex_claws_yellow": case "flex_claws_blue": BanishCardForPlayer("crouching_tiger", $mainPlayer, "-", "TT", $mainPlayer, created:true); break;
```

### metex_red  — looks-aligned
text: '**Boost**\n\nWhen this hits, you may put an item with cost 0 or 1 from your hand into the arena.'
```json
{
  "slug": "metex_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": 1,
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "hand",
              "cost": 0
            }
          ]
        },
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": 1,
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "hand",
              "cost": 1
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVOHitEffect()
MZMoveCard($mainPlayer, "MYHAND:subtype=Item;maxCost=1", "", may: true);
      AddDecisionQueue("PUTPLAY", $mainPlayer, "0", 1);
      break;
```

### evo_speedslip_blue  — looks-aligned
text: 'If you have a base legs equipped, **transform** it into this, then equip this.\n\nWhen this is equipped, the next attack action card you play this turn gets **boost**.\n\n**Arcane Barrier 1**'
```json
{
  "slug": "evo_speedslip_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_EQUIP",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "EVO_SPEEDSLIP_EQUIPPED"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "EVO_SPEEDSLIP_EQUIPPED"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "IS_ACTIVE_PLAYER"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "ARCANE_BARRIER",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EvoTransformAbility()
AddCurrentTurnEffectNextAttack("evo_speedslip_blue", $player);
      break;
// ArcaneBarrierChoices()
++$barrierArray[1];
        $total += 1;
        break;
```

### wide_blue_yonder_blue  — looks-aligned
text: "Target attack gets +1{p} for each blue card you've pitched this turn."
```json
{
  "slug": "wide_blue_yonder_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "BLUE_PITCHED_THIS_TURN"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CurrentEffectBlockModifiers()
$blockModifier += SearchPitchForColor($mainPlayer, 3);
          break;
// MSTPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### mulch_blue  — looks-aligned
text: '**Earth Fusion**\n\nIf Mulch was **fused**, it gains "If this hits a hero, put a card from their arsenal on the bottom of their deck."'
```json
{
  "slug": "mulch_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FUSED"
        }
      ],
      "effects": [
        {
          "type": "PUT_CARDS_BOTTOM",
          "target": "opponent_arsenal",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddEffectHitTrigger()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// EffectHitEffect()
if (IsHeroAttackTarget()) {
        AddDecisionQueue("MULTIZONEINDICES", $mainPlayer, "THEIRARS", 1);
        AddDecisionQueue("SETDQCONTEXT", $mainPlayer, "Choose which card you want to put on the bottom of the deck", 1);
        AddDecisionQueue("CHOOSEMULTIZONE", $mainPlayer, "<-", 1);
        AddDecisionQueue("MZADDZONE", $mainPlayer, "THEIRBOTDECK", 1);
        AddDecisionQueue("MZREMOVE", $mainPlayer, "-", 1);
      }
      break;
// FuseAbility()
case "mulch_red": case "mulch_yellow": case "mulch_blue": AddCurrentTurnEffect($cardID, $player); break;
// HasFusion()
case "mulch_red": case "mulch_yellow": case "mulch_blue": return "EARTH";
// ELECombatEffectActive()
case "mulch_red": case "mulch_yellow": case "mulch_blue": return true;
```

### run_through_yellow  — looks-aligned
text: 'Target sword attack gains **go again**.\n\nYour next sword attack this turn gets +2{p}.'
```json
{
  "slug": "run_through_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "ATTACK_SUBTYPE_IN",
          "subtype": "Sword"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "DURING_TURN"
        },
        {
          "type": "ATTACK_SUBTYPE_IN",
          "subtype": "Sword"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ReactionRequirementsMet()
case "blade_flash_blue": return CardSubtype($combatChain[0]) == "Sword";
```

### tempest_aurora_red  — looks-aligned
text: 'The next card you play this turn with cost 2 or less and an arcane damage effect, instead deals that much arcane damage plus 1.\n\n**Go again**'
```json
{
  "slug": "tempest_aurora_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "APPLY_CONTINUOUS",
          "conditions": [
            {
              "type": "DURING_TURN"
            },
            {
              "type": "AND",
              "conditions": [
                {
                  "type": "CARD_IN_ZONE",
                  "zone": "HAND",
                  "cost_lte": 2,
                  "effects": [
                    {
                      "type": "DEAL_ARCANE",
                      "amount": 1
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EffectArcaneBonus()
return 1;
// AssignArcaneBonus()
if (CardCost($layers[$layerIndex]) > 2) $skip = true;
          break;
// ArcaneModifierAmount()
return 1;
// DYNPlayAbility()
case "tempest_aurora_red": case "tempest_aurora_yellow": case "tempest_aurora_blue": AddCurrentTurnEffect($cardID, $currentPlayer); return "";
```

### construct_nitro_mechanoid_yellow  — looks-aligned
text: "**Transform** target Mechanologist head, chest, arms, legs, weapon and 3 Hyper Drivers you control into Nitro Mechanoid. If you don't, **negate** this.\n\n**Go again**"
```json
{
  "slug": "construct_nitro_mechanoid_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "TRANSFORM_HERO",
          "target": "Mechanologist",
          "parts": [
            "head",
            "chest",
            "arms",
            "legs",
            "weapon",
            "3 Hyper Drivers"
          ],
          "transform_to": "Nitro Mechanoid"
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// GoesWhereAfterResolving()
if (SearchItemsForCard("nitro_mechanoida", $currentPlayer) != "") return "-";
        break;
```

### codex_of_bloodrot_yellow  — looks-aligned
text: "Each hero puts a card from their hand face-down into their arsenal.\n\nCreate a Ponder token under your control and a Bloodrot Pox token under each opponent's control.\n\n**Go again**"
```json
{
  "slug": "codex_of_bloodrot_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "EACH_HERO_ARSENAL_FROM_ZONE_THEN_DISCARD",
          "zone": "hand",
          "amount": 1
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Ponder",
          "controller": "self"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Bloodrot Pox",
          "controller": "opponent"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTPlayAbility()
$otherPlayer = ($currentPlayer == 1 ? 2 : 1);
        if(!ArsenalFull($currentPlayer))
        {
          MZMoveCard($currentPlayer, "MYHAND", "MYARS,HAND,DOWN", silent:true);
        }
        if(!ArsenalFull($otherPlayer))
        {
          MZMoveCard($otherPlayer, "MYHAND", "MYARS,HAND,DOWN", silent:true);
        }
        PlayAura("ponder", $currentPlayer);//Ponder
        PlayAura($CID_BloodRotPox, $otherPlayer, effectController: $currentPlayer);
        return "";
```

### wind_chakra_red  — looks-aligned
text: "The next Crouching Tiger you play this turn gets +3{p}. If you've **transcended** this turn, instead it gets +5{p}.\n\n**Go again**"
```json
{
  "slug": "wind_chakra_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "TRANSCEDED_THIS_TURN"
            }
          ]
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 5
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTPlayAbility()
if (GetClassState($currentPlayer, $CS_Transcended) <= 0) AddCurrentTurnEffect($cardID . "-1", $currentPlayer);
      else AddCurrentTurnEffect($cardID . "-2", $currentPlayer);
      return "";
```

### performance_bonus_red  — looks-aligned
text: 'When this hits, create a Gold token.\nIf this was played from arsenal, it gets **Go again**.'
```json
{
  "slug": "performance_bonus_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Gold"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PLAY_ACTIVATE_ATTACK",
      "conditions": [
        {
          "type": "PLAYED_FROM_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HVYHitEffect()
PutItemIntoPlayForPlayer("gold", $mainPlayer, effectController: $mainPlayer);
      return "";
// HVYPlayAbility()
if ($from == "ARS") GiveAttackGoAgain();
      return "";
```

### grow_wings_blue  — looks-aligned
text: 'If a Draconic attack was the last attack this combat chain, this gets **go again**.'
```json
{
  "slug": "grow_wings_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LAST_ATTACK_WAS_DRACONIC"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
return isPreviousLinkDraconic();
```

### evo_zip_line_yellow  — looks-aligned
text: 'If you have a base legs equipped, **transform** it into this, then equip this.\n\nWhen this is equipped, up to 1 target attack gets **go again**.'
```json
{
  "slug": "evo_zip_line_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_EQUIP",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EvoTransformAbility()
if ($CombatChain->HasCurrentLink() || IsLayerStep()) {
        AddDecisionQueue("YESNO", $player, "if you want to give the current attack go again");
        AddDecisionQueue("NOPASS", $player, "-");
        AddDecisionQueue("GIVEACTIONGOAGAIN", $player, "AA", 1);
      }
      break;
```

### over_loop_yellow  — looks-aligned
text: "**Boost**\n\nWhen this hits, put it on the bottom of its owner's deck."
```json
{
  "slug": "over_loop_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "PUT_SELF_BOTTOM_DECK"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCMechanologistHitEffect()
if(substr($from, 0, 5) != "THEIR") $combatChainState[$CCS_GoesWhereAfterLinkResolves] = "BOTDECK";
      else $combatChainState[$CCS_GoesWhereAfterLinkResolves] = "THEIRBOTDECK";
      break;
```

### flat_trackers  — looks-aligned
text: 'Action - Destroy this: Create an Agility token. **Go again**\n\n**Blade Break**'
```json
{
  "slug": "flat_trackers",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Agility"
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// HVYPlayAbility()
PlayAura("agility", $currentPlayer); 
      return "";
```

### looking_for_a_scrap_blue  — looks-aligned
text: 'As an additional cost to play Looking for a Scrap, you may banish a card with 1{p} from your graveyard. When you do, this gains +1{p} and **go again**.'
```json
{
  "slug": "looking_for_a_scrap_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "BANISH_FROM_GRAVEYARD",
          "pitch_power": 1
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PayAdditionalCosts()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYDISCARD:maxAttack=1;minAttack=1");
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a card to banish", 1);
      AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("MZBANISH", $currentPlayer, "GY,-," . $currentPlayer . ",1", 1);
      AddDecisionQueue("MZREMOVE", $currentPlayer, "-", 1);
      AddDecisionQueue("APPENDCLASSSTATE", $currentPlayer, $CS_AdditionalCosts . "-BANISH1ATTACK", 1);
      break;
// OUTEffectPowerModifier()
case "looking_for_a_scrap_red": case "looking_for_a_scrap_yellow": case "looking_for_a_scrap_blue": return 1;
// OUTCombatEffectActive()
case "looking_for_a_scrap_red": case "looking_for_a_scrap_yellow": case "looking_for_a_scrap_blue": return true;
// OUTPlayAbility()
if(DelimStringContains($additionalCosts, "BANISH1ATTACK"))
        {
          AddCurrentTurnEffect($cardID, $currentPlayer);
          GiveAttackGoAgain();
        }
        return "";
```

### flex_claws_red  — looks-aligned
text: 'When this hits, create a Crouching Tiger in your banished zone. You may play it this turn.\n\n**Go again**'
```json
{
  "slug": "flex_claws_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Crouching Tiger",
          "zone": "BANISHED"
        },
        {
          "type": "BANISH_OPP_TOP_GRANT_PLAY",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNHitEffect()
case "flex_claws_red": case "flex_claws_yellow": case "flex_claws_blue": BanishCardForPlayer("crouching_tiger", $mainPlayer, "-", "TT", $mainPlayer, created:true); break;
```

### flourish_blue  — looks-aligned
text: 'The next time an attack would gain {p} this turn, instead it gains that much plus 2.\n\n**Go again**'
```json
{
  "slug": "flourish_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2,
          "conditions": [
            {
              "type": "DURING_TURN"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// TERPlayAbility()
AddCurrentTurnEffect("flourish_blue-INACTIVE", $currentPlayer);
      return "";
```

### pathing_helix_yellow  — looks-aligned
text: 'If Pathing Helix hits and you have no cards in your arsenal, you may put a card from your hand face down into your arsenal.'
```json
{
  "slug": "pathing_helix_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "arsenal",
          "amount": 0
        }
      ],
      "effects": [
        {
          "type": "SEARCH_DECK",
          "amount": 1,
          "destination": "arsenal",
          "face_down": true
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CRUHitEffect()
if(!ArsenalEmpty($mainPlayer)) return "There is already a card in your arsenal, so you cannot put an arrow in your arsenal";
      MZMoveCard($mainPlayer, "MYHAND", "MYARS,HAND,DOWN", may:true);
      break;
```

### crash_and_bash_blue  — looks-aligned
text: 'When this defends, you may reveal a card with **crush** from your hand. If you do, create a Seismic Surge token.'
```json
{
  "slug": "crash_and_bash_blue",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "effects": [
        {
          "type": "REVEAL_TOP_DECK",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "CRUSH_REVEALED"
            }
          ]
        },
        {
          "type": "CREATE_TOKEN",
          "token_name": "Seismic Surge",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "CRUSH_REVEALED"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
if (CanRevealCards($player)) {
          AddDecisionQueue("SETDQCONTEXT", $player, "Choose a card with crush to reveal", 1);
          AddDecisionQueue("MULTIZONEINDICES", $player, "MYHAND:hasCrush=true");
          AddDecisionQueue("MAYCHOOSEMULTIZONE", $player, "<-", 1);
          AddDecisionQueue("MZOP", $player, "GETCARDID", 1);
          AddDecisionQueue("REVEALCARDS", $player, "-", 1);
          AddDecisionQueue("PLAYAURA", $player, "seismic_surge", 1);
        }
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
```

### first_tenet_of_chi_moon_blue  — looks-aligned
text: 'Your next blue attack this turn gets "When this attacks, draw a card."\n\n**Go again**'
```json
{
  "slug": "first_tenet_of_chi_moon_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        },
        {
          "type": "ATTACK_CLASS_IN",
          "classes": [
            "Blue"
          ]
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_ATTACK",
          "effects": [
            {
              "type": "DRAW",
              "amount": 1
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessAttackTrigger()
Draw($player);
      break;
// OnAttackEffects()
if (ColorContains($cardID, 3, $mainPlayer)) {
            AddLayer("TRIGGER", $mainPlayer, $currentTurnEffects[$i], additionalCosts:"ATTACKTRIGGER");
            $remove = true;
          }
          break;
// MSTPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### earthlore_empowerment_yellow  — looks-aligned
text: 'At the start of your turn, destroy this, then the next Guardian attack action card you play this turn costs {r} less to play and gets +4{p}.'
```json
{
  "slug": "earthlore_empowerment_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_PLAY",
            "conditions": [
              {
                "type": "ATTACK_CLASS_IN",
                "classes": [
                  "Guardian"
                ]
              }
            ],
            "effects": [
              {
                "type": "PAY_OR_DAMAGE",
                "resource": "RESOURCE_POINTS",
                "amount": 1
              },
              {
                "type": "MODIFY_ATTACK",
                "mod": "add",
                "amount": 4
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
case "power_stance_blue": // These can stack, so we don't care if the effect is already in play. See: Ancestral Harmony for comparison.
// CurrentEffectCostModifiers()
if (ClassContains($cardID, "GUARDIAN", $currentPlayer) && $cardType == "AA") $costModifier -= 1;
          break;
```

### vantage_point_red  — looks-aligned
text: "If you've played or created an aura this turn, this gets **overpower**."
```json
{
  "slug": "vantage_point_red",
  "abilities": [
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_PLAY",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "AURA_PLAYED_OR_CREATED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "OVERPOWER"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsOverpowerActive()
return GetClassState($mainPlayer, $CS_NumAuras) > 0;
```

### rising_knee_thrust_blue  — looks-aligned
text: '**Combo** - If Leg Tap was the last attack this combat chain, Rising Knee Thrust gains +2{p} and **go again**.'
```json
{
  "slug": "rising_knee_thrust_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LEG_TAP_LAST_ATTACK"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Leg Tap") return true;
        break;
// PowerModifier()
$power += (ComboActive() ? 2 : 0);
        break;
// DoesAttackHaveGoAgain()
return ComboActive($attackID);
```

### assembly_module_blue  — looks-aligned
text: '**Crank**\n\nThis enters the arena with a stream counter. At the start of your turn, destroy this unless you remove a steam counter from it.\n\n**Action** - {t}: Search your deck for a Hyper Driver, put it into the arena, then shuffle.'
```json
{
  "slug": "assembly_module_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ASSEMBLY_MODULE_STREAM_COUNTER"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "REMOVE_COUNTER",
          "counter": "STREAM"
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "effects": [
        {
          "type": "SEARCH_DECK",
          "card_type": "HYPER_DRIVER",
          "put_into": "arena"
        },
        {
          "type": "REORDER_REF",
          "ref": "deck"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PayItemAbilityAdditionalCosts()
Tap("MYITEMS-" . $index, $currentPlayer);
      break;
// ItemStartTurnAbility()
if ($mainItems[$index + 1] > 0 && GetItemGemState($mainPlayer, $mainItems[$index], $index) == 0) --$mainItems[$index + 1];
      elseif($mainItems[$index + 1] > 0) {
        AddDecisionQueue("YESNO", $mainPlayer, "if you want to remove a Steam Counter and keep " . CardLink($mainItems[$index], $mainItems[$index]) . " and keep it in play?");
        AddDecisionQueue("REMOVECOUNTERITEMORDESTROYUID", $mainPlayer, $mainItems[$index + 4]);
      }
      else DestroyItemForPlayer($mainPlayer, $index);
      break;
```

### become_the_arknight_blue  — looks-aligned
text: '**Viserai Specialization**\n\nYou may discard an action card. If you discard an attack action card this way, search your deck for a Runeblade non-attack action card, reveal it, and put it into your hand. If you discard a non-attack action card this way, search your deck for a Runeblade attack action card, reveal it, and put it into your hand. Shuffle. **Go again**'
```json
{
  "slug": "become_the_arknight_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "OPT",
          "amount": 1
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCRunebladePlayAbility()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYHAND:type=A&MYHAND:type=AA");
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a card to discard", 1);
        AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("MZREMOVE", $currentPlayer, "-", 1);
        AddDecisionQueue("SHUFFLEDECK", $currentPlayer, "-");
        AddDecisionQueue("DISCARDCARD", $currentPlayer, "HAND-".$currentPlayer, 1);
        AddDecisionQueue("SPECIFICCARD", $currentPlayer, "BECOMETHEARKNIGHT", 1);
        return "";
```

### scrap_hopper_blue  — looks-aligned
text: '**Scrap**\n\nWhen this attacks, if it **scrapped** a card, create a Quicken token.'
```json
{
  "slug": "scrap_hopper_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SCRAPPED_CARD"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Quicken"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVOPlayAbility()
if (DelimStringContains($additionalCosts, "SCRAP", true)) PlayAura("quicken", $currentPlayer);
      return "";
```

### tricorn_of_saltwater_death  — looks-aligned
text: 'When this defends, you may discard a card with watery grave. If you do, draw a card.\n\n**Blade Break**'
```json
{
  "slug": "tricorn_of_saltwater_death",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "effects": [
        {
          "type": "DISCARD",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "hand",
              "keyword": "WATERY_GRAVE"
            }
          ]
        },
        {
          "type": "DRAW",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "hand",
              "keyword": "WATERY_GRAVE"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
if (SearchHand($player, hasWateryGrave: true) != "") {
            AddDecisionQueue("FINDINDICES", $player, "HANDWATERYGRAVE,-,NOPASS");
            AddDecisionQueue("SETDQCONTEXT", $player, "Choose a card with watery grave to discard");
            AddDecisionQueue("MAYCHOOSEHAND", $player, "<-", 1);
            AddDecisionQueue("MULTIREMOVEHAND", $player, "-", 1);
            AddDecisionQueue("DISCARDCARD", $player, "HAND-" . $player, 1);
            AddDecisionQueue("DRAW", $player, "-", 1);
        }
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
```

### death_touch_yellow  — looks-aligned
text: "Death Touch can't be played from hand.\n\nWhen this hits a hero, create a Frailty, Inertia, or Bloodrot Pox token under their control."
```json
{
  "slug": "death_touch_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Frailty"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Inertia"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Bloodrot Pox"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return $from == "HAND";
// OUTHitEffect()
if(IsHeroAttackTarget())
        {
          AddDecisionQueue("CHOOSECARD", $mainPlayer, $CID_BloodRotPox . "," . $CID_Frailty . "," . $CID_Inertia);
          AddDecisionQueue("PUTPLAY", $defPlayer, $mainPlayer, 1);
        }
        break;
```

### glint_the_quicksilver_blue  — looks-aligned
text: 'Target weapon attack gets **go again**.\n\n**Reprise** - If the defending hero has defended with a card from their hand this chain link, draw a card.'
```json
{
  "slug": "glint_the_quicksilver_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "REPRISE_FLAG"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ReactionRequirementsMet()
case "stroke_of_foresight_red": case "stroke_of_foresight_yellow": case "stroke_of_foresight_blue": return TypeContains($combatChain[0], "W", $mainPlayer);
```

### blackout_kick_yellow  — looks-aligned
text: '**Combo** - If Rising Knee Thrust was the last attack this combat chain, Blackout Kick gains +3{p}.'
```json
{
  "slug": "blackout_kick_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "RISING_KNEE_THRUST_LAST_ATTACK"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Rising Knee Thrust") return true;
        break;
// PowerModifier()
$power += (ComboActive() ? 3 : 0);
        break;
```

### scrap_prospector_yellow  — looks-aligned
text: '**Scrap**\n\nWhen this attacks, if it scrapped a card, gain {r}.'
```json
{
  "slug": "scrap_prospector_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SCRAPPED_CARD"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVOPlayAbility()
if (DelimStringContains($additionalCosts, "SCRAP", true)) GainResources($currentPlayer, 1);
      return "";
```

### clash_of_might_yellow  — looks-aligned
text: 'When this defends, **clash** with the attacking hero. The winner creates a Might token.'
```json
{
  "slug": "clash_of_might_yellow",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "CLASH",
          "target": "attacker"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Might"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
Clash($parameter, effectController: $player);
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
// WonClashAbility()
PlayAura("might", $playerID);
        break;
```

### coronet_peak  — looks-aligned
text: '**Action** - {r}{r}{r}: Target hero discards a card unless they pay {r}.\n\n**Blade Break**'
```json
{
  "slug": "coronet_peak",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 3,
      "effects": [
        {
          "type": "BANISH",
          "target": "opponent",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
$options = "THEIRCHAR-0";
      if (!ShouldAutotargetOpponent($currentPlayer)) $options = "MYCHAR-0,$options";
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a hero make pay or discard");
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, $options, 1);
      AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// UPRAbilityCost()
case "coronet_peak": return 3;
// UPRAbilityType()
case "coronet_peak": return "A";
// UPRTalentPlayAbility()
$targ = (str_contains($target, "THEIRCHAR")) ? "Target_Opponent" : "Target_Yourself";
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, $targ);
        AddDecisionQueue("PLAYERTARGETEDABILITY", $currentPlayer, "CORONETPEAK", 1);
        return "";
```

### scurv_stowaway  — looks-aligned
text: '**Action** - {t}, destroy a Gold you control: Create a Goldkiss Rum token. **Go again**\n\nWhenever you activate a Goldkiss Rum, gain {r}.'
```json
{
  "slug": "scurv_stowaway",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "controlled",
          "asset": "GOLD"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token": "Goldkiss Rum"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ACTIVATE",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Goldkiss Rum"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if (CheckTapped("MYCHAR-$index", $currentPlayer)) return true;
      return CountItemByName("Gold", $currentPlayer) == 0;
// ProcessTrigger()
GainResources($player, 1);
        break;
// EquipPayAdditionalCosts()
QueueDestroyGold($currentPlayer, isMandatory:true, showContext:true, itemFallback:false, subsequent:0);
      Tap("MYCHAR-$cardIndex", $currentPlayer);
      break;
// SEAPlayAbility()
PutItemIntoPlayForPlayer("goldkiss_rum", $currentPlayer);
      break;
    // Marlynn cards
```

### hard_knuckle  — looks-aligned
text: 'When you play an attack action card, you may destroy this. If you do, the attack gets +1{p}.'
```json
{
  "slug": "hard_knuckle",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PLAY_ACTIVATE_ATTACK",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
$index = FindCharacterIndex($mainPlayer, "hard_knuckle");
        AddDecisionQueue("YESNO", $mainPlayer, "to_destroy_".Cardlink($parameter, $parameter));
        AddDecisionQueue("NOPASS", $mainPlayer, "-");
        AddDecisionQueue("PASSPARAMETER", $mainPlayer, $index, 1);
        AddDecisionQueue("DESTROYCHARACTER", $mainPlayer, "-", 1);
        AddDecisionQueue("ADDCURRENTTURNEFFECT", $mainPlayer, "hard_knuckle", 1);
        break;
// MainCharacterPlayCardAbilities()
$abilityType = GetResolvedAbilityType($cardID, $from);
        if (CardType($cardID) == "AA" && $abilityType != "I" && IsCharacterActive($mainPlayer, $i)) {
          AddLayer("TRIGGER", $currentPlayer, $characterID, $cardID);
        }
        break;
```

### victor_goldmane  — looks-aligned
text: "The first time each turn you create a Gold token from an effect you control, draw a card.\n\nThe first time each turn you would fail to win a **clash**, instead you may destroy a Gold you control. If you do, put 1 of the revealed cards on the bottom of its owner's deck, then **clash** again."
```json
{
  "slug": "victor_goldmane",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_GOLD_CREATED",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FIRST_GOLD_CREATED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CLASH_WIN_REVEALED",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FIRST_CLASH_FAIL_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "token_type": "Gold"
        },
        {
          "type": "PUT_SELF_BOTTOM_DECK",
          "amount": 1
        },
        {
          "type": "CLASH"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
WriteLog("Player $player drew a card from Victor");
        Draw($player);
        break;
// CharacterStartTurnAbility()
if (!SearchCurrentTurnEffects($cardID . "-1", $mainPlayer) && $character[1] < 3) AddCurrentTurnEffect($cardID . "-1", $mainPlayer);
      break;
// DefCharacterStartTurnAbilities()
if (!SearchCurrentTurnEffects($character[$i] . "-1", $defPlayer) && $character[1] < 3) AddCurrentTurnEffect($character[$i] . "-1", $defPlayer);
        break;
```

### panel_beater_yellow  — looks-aligned
text: '**Boost**\n\nThis gets +X{p}, where X is the number of equipment defending it.'
```json
{
  "slug": "panel_beater_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += NumEquipBlock();
        break;
```

### rejuvenate_blue  — looks-aligned
text: "Gain 1{h}\n\nIf you've **fused** this turn, you may play Rejuvenate as though it were an instant."
```json
{
  "slug": "rejuvenate_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "asset": "HEALTH",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FUSED_THIS_TURN"
        }
      ],
      "alternative_cost": [
        {
          "type": "PAY_RESOURCES",
          "amount": 0
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "HEALTH",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CanPlayAsInstant()
if (PlayerHasFused($currentPlayer)) return true;
      break;
// ELETalentPlayAbility()
case "rejuvenate_blue": GainHealth(1, $currentPlayer); return "";
```

### over_the_top_red  — looks-aligned
text: 'If this has {p} greater than its base, it gets **overpower**.'
```json
{
  "slug": "over_the_top_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "SELF_ATTACK_POWER_GTE",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "OVERPOWER"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsOverpowerActive()
return HasIncreasedAttack();
```

### strength_of_four_seasons_blue  — looks-aligned
text: 'If there are 4 or more Earth cards in your banished zone, this gets +4{p}.'
```json
{
  "slug": "strength_of_four_seasons_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "BANISHED",
          "amount": 4,
          "card_class": "Earth"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += SearchCount(SearchMultiZone($mainPlayer, "MYBANISH:talent=EARTH")) >= 4 ? 4 : 0;
        break;
```

### lord_sutcliffe  — looks-aligned
text: "While Sutcliffe is face down in arsenal, at the start of your turn, you may turn him face up.\n\nWhile Sutcliffe is face up in arsenal, whenever you play a 'non-attack' action card, deal 1 arcane damage to each hero and put a lesson counter on Sutcliffe for each damage dealt this way. Then if there are 3 or more lesson counters on him, banish him, search your deck for a **specialization** card, put it face up into arsenal, and shuffle."
```json
{
  "slug": "lord_sutcliffe",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FACE_DOWN_IN_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "START_OF_TURN",
            "effects": [
              {
                "type": "MAY",
                "effects": [
                  {
                    "type": "FLIP_REF",
                    "target": "self"
                  }
                ]
              }
            ]
          }
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FACE_UP_IN_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_PLAY",
            "conditions": [
              {
                "type": "NOT",
                "condition": {
                  "type": "ATTACK_CLASS_IN",
                  "classes": [
                    "Attack"
                  ]
                }
              }
            ],
            "effects": [
              {
                "type": "DEAL_ARCANE",
                "amount": 1,
                "target": "each_hero"
              },
              {
                "type": "PUT_COUNTER",
                "counter": "lesson",
                "amount": 1,
                "target": "self"
              },
              {
                "type": "MAY",
                "conditions": [
                  {
                    "type": "COUNTER_GTE",
                    "counter": "lesson",
                    "amount": 3
                  }
                ],
                "effects": [
                  {
                    "type": "BANISH_REF",
                    "target": "self"
                  },
                  {
                    "type": "SEARCH_DECK",
                    "conditions": [
                      {
                        "type": "HAS_KEYWORD",
                        "keyword": "specialization"
                      }
                    ],
                    "effects": [
                      {
                        "type": "PUT_REF_BOTTOM",
                        "target": "arsenal"
                      }
                    ]
                  },
                  {
                    "type": "SHUFFLE_DECK"
                  }
                ]
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// BlockValue()
$block = 3;
        break;
// IsAltCard()
return true;
// ArsenalStartTurnAbilities()
if ($arsenal[$i + 1] == "DOWN") {
          AddDecisionQueue("YESNO", $mainPlayer, "if_you_want_to_turn_".CardLink($arsenal[$i], $arsenal[$i])."_face_up");
          AddDecisionQueue("NOPASS", $mainPlayer, "-");
          AddDecisionQueue("TURNARSENALFACEUP", $mainPlayer, $i, 1);
        }
        break;
// ArsenalPlayCardAbilities()
if ($arsenal[$i + 1] == "UP" && DelimStringContains($cardType, "A")) LordSutcliffeAbility($currentPlayer, $i);
        break;
// GenerateFunction()
$setID = "MON407";
          break;
// GenerateKeywordFunction()
$setID = "MON407";
          break;
```

### spellblade_strike_blue  — looks-aligned
text: 'Create a Runechant token.'
```json
{
  "slug": "spellblade_strike_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCRunebladePlayAbility()
case "spellblade_strike_red": case "spellblade_strike_yellow": case "spellblade_strike_blue": PlayAura("runechant", $currentPlayer); return "";
```

### en_garde_red  — looks-aligned
text: 'Your next weapon attack this turn gains +3{p}.\n\n**Go again**'
```json
{
  "slug": "en_garde_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "DURING_TURN",
              "player": "self"
            },
            {
              "type": "ATTACK_IS_WEAPON"
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DVRPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
// DVREffectPowerModifier()
case "en_garde_red": return 3;
// DVRCombatEffectActive()
case "en_garde_red": return TypeContains($attackID, "W", $mainPlayer);
```

### singe_yellow  — looks-aligned
text: 'Deal 1 arcane damage to target hero and up to 2 target allies they control.'
```json
{
  "slug": "singe_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1,
          "target": "hero"
        },
        {
          "type": "DEAL_ARCANE",
          "amount": 1,
          "target": "ally",
          "max_targets": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayRequiresTarget()
return 1;
// ActionsThatDoArcaneDamage()
return true;
// UPRWizardPlayAbility()
$maxAllies = match($cardID) { "singe_red" => 3, "singe_yellow" => 2, default => 1 };
        $otherPlayer = ($currentPlayer == 1 ? 2 : 1);
        $allies = &GetAllies($otherPlayer);
        $alliesCount = count($allies);
        if($alliesCount < $maxAllies) $maxAllies = $alliesCount;
        $damage = ArcaneDamage($cardID) + ConsumeArcaneBonus($currentPlayer);
        DealArcane($damage, 1, "PLAYCARD", $cardID, false, $currentPlayer, false, false, resolvedTarget: $target);
        for($i=1; $i<$maxAllies; ++$i) DealArcane($damage, 5, "PLAYCARD", $cardID, false, $currentPlayer, true, true);
        DealArcane($damage, 5, "PLAYCARD", $cardID, false, $currentPlayer, true, false);
        return "";
```

### blessing_of_focus_red  — looks-aligned
text: "At the start of your turn, destroy Blessing of Focus then **opt 3** and reveal the top card of your deck. If it's an arrow, put it face up into your arsenal with an aim counter."
```json
{
  "slug": "blessing_of_focus_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "OPT",
          "amount": 3
        },
        {
          "type": "REVEAL_TOP_DECK",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "deck",
              "card_type": "arrow"
            }
          ],
          "effects": [
            {
              "type": "PUT_ARSENAL_BOTTOM",
              "card_type": "arrow",
              "face_up": true
            },
            {
              "type": "PUT_COUNTER",
              "counter_type": "aim"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
if ($auras[$i] == "blessing_of_focus_red") $amount = 3;
        else $amount = ($auras[$i] == "blessing_of_focus_yellow") ? 2 : 1;
        DestroyAuraUniqueID($mainPlayer, $auras[$i + 6]);
        PlayerOpt($mainPlayer, $amount);
        AddDecisionQueue("SPECIFICCARD", $mainPlayer, "BLESSINGOFFOCUS", 1);
        break;
```

### draw_swords_red  — looks-aligned
text: 'Your next Warrior attack this turn gets +3{p}.\n\nDraw a card.\n\n**Go again**'
```json
{
  "slug": "draw_swords_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "DURING_TURN",
              "player": "self"
            },
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Warrior"
            }
          ]
        },
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HVYPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      Draw($currentPlayer);
      return "";
```

### stonewall_confidence_yellow  — looks-aligned
text: '**Go again**\n\nCards you control with cost 3 or more get +3{d} while defending.\n\nAt the beginning of your action phase, destroy this.'
```json
{
  "slug": "stonewall_confidence_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_ATTACK_ACTION",
          "cost_gte": 3
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraBeginningActionPhaseAbilities()
AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", "DESTROY", $auras[$i + 6]);
        break;
// AuraBlockModifier()
if (CardCost($cardID, $from) >= 3) $blockModifier += 3;
        break;
// ProcessTrigger()
// sigils are destroyed at the start of the action phase
```

### envelop_in_darkness_red  — looks-aligned
text: 'Create a Runechant token.\n\nThe next attack action card you **rune gate** this turn gets +3{p}.\n\n**Go again**'
```json
{
  "slug": "envelop_in_darkness_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "RUNE_GATE_FLAG"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DTDEffectPowerModifier()
case "envelop_in_darkness_red": return 3;
// DTDCombatEffectActive()
case "envelop_in_darkness_red": case "envelop_in_darkness_yellow": case "envelop_in_darkness_blue": return $combatChainState[$CCS_WasRuneGate] == 1;
// DTDPlayAbility()
PlayAura("runechant", $currentPlayer);
      AddCurrentTurnEffectNextAttack($cardID, $currentPlayer);
      return "";
```

### blossoming_spellblade_red  — looks-aligned
text: '**Earth and Lightning Fusion**\n\nIf Blossoming Spellblade was fused, it gains "Whenever this deals damage to an opposing hero, you may banish a \'non-attack\' action card from your graveyard. If you do, you may play it this turn as though it were an instant and if it would be put into your graveyard this turn, instead banish it."\n\nWhen you attack with Blossoming Spellblade, if it was **fused**, deal 1 arcane damage to target hero.'
```json
{
  "slug": "blossoming_spellblade_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEAL_DAMAGE",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FUSED_FLAG"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": "GRAVEYARD",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "GRAVEYARD",
              "conditions": [
                {
                  "type": "NOT",
                  "condition": {
                    "type": "HAS_KEYWORD",
                    "keyword": "Attack"
                  }
                }
              ]
            }
          ]
        },
        {
          "type": "BANISH_TRAP_FROM_GRAVEYARD_PLAYABLE",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "BANISHED_CARD_FLAG"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FUSED_FLAG"
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// GoesWhereEffectsModifier()
if (($from == "BANISH" || $from == "MELD") && SearchCurrentTurnEffectsForUniqueID($cardID) != -1) {
          RemoveCurrentTurnEffect($i);
          return "BANISH";
        }
        break;
// CurrentEffectDamageEffects()
if ($source == "blossoming_spellblade_red" && (IsHeroAttackTarget() || $type != "COMBAT"))
          MZMoveCard($target == 1 ? 2 : 1, "MYDISCARD:type=A", "MYBANISH,GY,blossoming_spellblade_red", may: true);
        break;
// HasFusion()
case "blossoming_spellblade_red": return "EARTH,LIGHTNING";
// ELERunebladePlayAbility()
if(DelimStringContains($additionalCosts, "EARTH") && DelimStringContains($additionalCosts, "LIGHTNING")) {
          AddCurrentTurnEffect($cardID, $currentPlayer);
          DealArcane(1, 0, "PLAYCARD", $cardID, false);
        }
        return "";
// ELECombatEffectActive()
case "blossoming_spellblade_red": return true;
```

### scar_for_a_scar_blue  — looks-aligned
text: 'When this is played, if you have less {h} than an opposing hero, it gets **go again**.'
```json
{
  "slug": "scar_for_a_scar_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "conditions": [
        {
          "type": "HEALTH_LT_OPP"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CardPlayTrigger()
AddLayer("TRIGGER", $mainPlayer, $cardID);
        break;
// ProcessTrigger()
if(PlayerHasLessHealth($mainPlayer)) {
          WriteLog(CardLink($parameter, $parameter) . " gains Go Again!");
          GiveAttackGoAgain();
        }
        break;
```

### shadow_of_blasmophet_red  — looks-aligned
text: 'Draw a card then discard a random card. If a card with 6 or more {p} is discarded this way, search your deck for a card with **blood debt**, banish it, then shuffle your deck.\n\n**Blood Debt**'
```json
{
  "slug": "shadow_of_blasmophet_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "DISCARD_RANDOM"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DISCARD",
      "conditions": [
        {
          "type": "DISCARDED_CARD_POWER_GTE",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "SEARCH_DECK",
          "conditions": [
            {
              "type": "HAS_KEYWORD",
              "keyword": "BloodDebt"
            }
          ],
          "target": "single",
          "effects": [
            {
              "type": "BANISH"
            },
            {
              "type": "SHUFFLE_DECK"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MONBrutePlayAbility()
Draw($currentPlayer);
        $card = DiscardRandom();
        if(ModifiedPowerValue($card, $currentPlayer, "HAND", source:$cardID) >= 6) {
          MZMoveCard($currentPlayer, "MYDECK:bloodDebtOnly=true", "MYBANISH,DECK,-", may:true);
          AddDecisionQueue("SHUFFLEDECK", $currentPlayer, "-");
        }
        return "";
```

### flamescale_furnace  — looks-aligned
text: "**Once per Turn Instant** - {r}: Gain {r} for each red card in your pitch zone. Activate this ability only if you've played a red card this turn.\n\n**Temper**"
```json
{
  "slug": "flamescale_furnace",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "RED_CARD_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": "pitch_red_count"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return GetClassState($player, $CS_NumRedPlayed) == 0;
// UPRAbilityCost()
case "flamescale_furnace": return 1;
// UPRAbilityType()
case "flamescale_furnace": return "I";
// UPRTalentPlayAbility()
$pitch = &GetPitch($currentPlayer);
        $numRed = 0;
        $pitchCount = count($pitch);
        $pitchPieces = PitchPieces();
        for($i=0; $i<$pitchCount; $i+=$pitchPieces) if(PitchValue($pitch[$i]) == 1) ++$numRed;
        GainResources($currentPlayer, $numRed);
        return "";
```

### rising_power_yellow  — looks-aligned
text: "If you've drawn a card this turn, this gets +1{p}."
```json
{
  "slug": "rising_power_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DRAWN_CARD_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += GetClassState($mainPlayer, $CS_NumCardsDrawn) >= 1 ? 1 : 0;
        break;
```

### lay_to_rest_blue  — looks-aligned
text: 'When this attacks a Shadow hero, it gets +1{p}.\n\nWhen this hits a hero, you may turn a card in their banished zone face-down.'
```json
{
  "slug": "lay_to_rest_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "class": "Shadow"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "BANISH_REF",
          "target": "opponent_banished",
          "face_down": true
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DTDEffectPowerModifier()
case "lay_to_rest_red": case "lay_to_rest_yellow": case "lay_to_rest_blue": return 1;
// DTDCombatEffectActive()
case "lay_to_rest_red": case "lay_to_rest_yellow": case "lay_to_rest_blue": return true;
// DTDPlayAbility()
case "lay_to_rest_red": case "lay_to_rest_yellow": case "lay_to_rest_blue"://Lay to Rest
// DTDHitEffect()
if(IsHeroAttackTarget())
      {
        AddDecisionQueue("MULTIZONEINDICES", $mainPlayer, "THEIRBANISH");
        AddDecisionQueue("MAYCHOOSEMULTIZONE", $mainPlayer, "<-", 1);
        AddDecisionQueue("MZOP", $mainPlayer, "TURNBANISHFACEDOWN", 1);
      }
      break;
```

### evo_steel_soul_controller_blue  — looks-aligned
text: 'If you have base arms equipped, **transform** it into this, then equip this.\n\nWhen this **transforms** from or into an Evo with a different name, you may put an attack action card with 6{p} from your graveyard into your deck fifth from the top. If that Evo is a hero, instead this triggers twice.\n\n**Temper**'
```json
{
  "slug": "evo_steel_soul_controller_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BECOME",
      "conditions": [
        {
          "type": "OR",
          "conditions": [
            {
              "type": "AND",
              "conditions": [
                {
                  "type": "FLAG_SET",
                  "flag": "TRANSFORM_FROM_EVO"
                },
                {
                  "type": "NOT",
                  "condition": {
                    "type": "FLAG_SET",
                    "flag": "SAME_NAME_EVO"
                  }
                }
              ]
            },
            {
              "type": "AND",
              "conditions": [
                {
                  "type": "FLAG_SET",
                  "flag": "TRANSFORM_TO_EVO"
                },
                {
                  "type": "NOT",
                  "condition": {
                    "type": "FLAG_SET",
                    "flag": "SAME_NAME_EVO"
                  }
                }
              ]
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": 1,
          "target": "GRAVEYARD",
          "conditions": [
            {
              "type": "NOT",
              "condition": {
                "type": "FLAG_SET",
                "flag": "EVO_IS_HERO"
              }
            }
          ]
        },
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": 1,
          "target": "GRAVEYARD",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "EVO_IS_HERO"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "TEMPER"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
MZMoveCard($player, "MYDISCARD:type=AA;maxAttack=6;minAttack=6", "MYTOPDECK-4", true, logText: "🦾".CardLink("$parameter") . " card chosen: <0>");
        break;
// EvoTransformAbility()
if (SubtypeContains($fromCardID, "Evo", $player) && CardName($fromCardID) != CardName($toCardID)) {
        AddLayer("TRIGGER", $player, "evo_steel_soul_controller_blue");
      }
      break;
```

### briar  — looks-aligned
text: "**Essence of Earth and Lightning**\n\nThe first time an attack action card you control deals damage to an opposing hero, create an Embodiment of Earth token.\n\nWhenever you play your second 'non-attack' action card each turn, create an Embodiment of Lightning token."
```json
{
  "slug": "briar",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "SOURCE_IS_ATTACK",
          "source": "self"
        },
        {
          "type": "FLAG_SET",
          "flag": "FIRST_ATTACK_DAMAGE_DEALT"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Embodiment of Earth"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PLAY_ACTIVATE_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SECOND_NON_ATTACK_PLAYED"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Embodiment of Lightning"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
if ($additionalCosts == "DAMAGE") PlayAura("embodiment_of_earth", $player);
        else PlayAura("embodiment_of_lightning", $player);
        break;
// MainCharacterHitTrigger()
if (IsHeroAttackTarget() && $isAA && $mainCharacter[$i + 1] == 2) {
          // Is this code ever reached?
          $mainCharacter[$i + 1] = 1;
          AddLayer("TRIGGER", $mainPlayer, $characterID, $damageSource, "DAMAGE");
        }
        break;
// MainCharacterPlayCardAbilities()
if (DelimStringContains(CardType($cardID), "A") && GetClassState($currentPlayer, $CS_NumNonAttackCards) == 2 && $from != "PLAY") {
          AddLayer("TRIGGER", $currentPlayer, $characterID);
        }
        break;
// isCardLegalinHero()
$heroTalent[] = "LIGHTNING"; $heroTalent[] = "EARTH"; break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
```

### grim_feast_red  — looks-aligned
text: 'You may play this from your banished zone. If you do, it costs {r}{r} less to play.\n\nGain 3{h}\n\n**Blood Debt**'
```json
{
  "slug": "grim_feast_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "PAY_LIFE",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "HEALTH",
          "amount": 3
        },
        {
          "type": "SET_FLAG",
          "flag": "BLOOD_DEBT_FLAG"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayableFromBanish()
return true;
// SelfCostModifier()
return $from == "BANISH" ? -2 : 0;
// DTDPlayAbility()
case "grim_feast_red": GainHealth(3, $currentPlayer); return "";
```

### demolition_protocol_red  — looks-aligned
text: '**Evo Upgrade** - When this attacks a hero, remove all steam counters from up to X equipment, items, and/or weapons they control, where X is the number of Evos you have equipped.'
```json
{
  "slug": "demolition_protocol_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "EvoUpgrade"
        }
      ],
      "effects": [
        {
          "type": "REMOVE_COUNTERS",
          "counter_type": "steam",
          "target": "opponent",
          "amount": "X"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVOPlayAbility()
$evoUpgradeMain = EvoUpgradeAmount($mainPlayer);
      if (IsHeroAttackTarget() && $evoUpgradeMain > 0) {
        $evoUpgradeCurr = EvoUpgradeAmount($currentPlayer);
        AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "THEIRITEMS:hasSteamCounter=true&THEIRCHAR:hasSteamCounter=true");
        AddDecisionQueue("PREPENDLASTRESULT", $currentPlayer, "MAXCOUNT-" . $evoUpgradeMain . ",MINCOUNT-0,", 1);
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose up to " . $evoUpgradeCurr . " card" . ($evoUpgradeMain > 1 ? "s" : "") . " to remove all steam counters from.", 1);
        AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("MZREMOVEALLCOUNTERS", $currentPlayer, "<-");
      }
      return "";
```

### lead_with_power_red  — looks-aligned
text: 'Your next Brute or Guardian attack this turn gets +3{p}.\n\nCreate a Might token.\n\n**Go again**'
```json
{
  "slug": "lead_with_power_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "DURING_TURN",
              "player": "self"
            },
            {
              "type": "ATTACK_CLASS_IN",
              "classes": [
                "Brute",
                "Guardian"
              ]
            }
          ]
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Might"
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HVYPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      PlayAura("might", $currentPlayer); 
      return "";
```

### warriors_valor_yellow  — looks-aligned
text: 'Your next weapon attack this turn gets +2{p} and "When this hits, it gets **go again**."\n\n**Go again**'
```json
{
  "slug": "warriors_valor_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "DURING_TURN"
        },
        {
          "type": "ATTACK_TYPE_IN",
          "values": [
            "WEAPON"
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_HIT",
          "effects": [
            {
              "type": "GAIN",
              "keyword": "GO_AGAIN"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddEffectHitTrigger()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// EffectHitEffect()
GiveAttackGoAgain();
      break;
// WTREffectPowerModifier()
case "warriors_valor_yellow": return 2;
// WTRCombatEffectActive()
case "warriors_valor_red": case "warriors_valor_yellow": case "warriors_valor_blue": return TypeContains($attackID, "W", $mainPlayer);
// WTRPlayAbility()
AddCurrentTurnEffect($cardID, $mainPlayer);
        return "";
```

### invoke_nekria_red  — looks-aligned
text: '**Transform** target ash you control into Nekria. **Go again**'
```json
{
  "slug": "invoke_nekria_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "TRANSFORM_HERO",
          "target": "ash",
          "transform_to": "nekria"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return SearchCount(SearchPermanents($player, "", "Ash")) < 1;
// GetLayerTarget()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYPERM:subtype=Ash");
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose an Ash to transform");
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// UPRIllusionistPlayAbility()
case "invoke_nekria_red": return Transform($currentPlayer, "Ash", "nekria", target:$target);
```

### breakneck_battery_red  — looks-aligned
text: 'As an additional cost to play Breakneck Battery, discard a random card.\n\nIf the discarded card has 6 or more {p}, Breakneck Battery gains **go again**.'
```json
{
  "slug": "breakneck_battery_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "DISCARD_RANDOM"
        }
      ],
      "conditions": [
        {
          "type": "DISCARDED_CARD_POWER_GTE",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// WTRPlayAbility()
if(ModifiedPowerValue($additionalCosts, $currentPlayer, "HAND", source:$cardID) >= 6) {
          GiveAttackGoAgain();
          $rv = "Discarded a 6 power card and gains go again.";
        }
        return $rv;
```

### smash_instinct_red  — looks-aligned
text: 'When this attacks, **intimidate**.'
```json
{
  "slug": "smash_instinct_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// WTRPlayAbility()
Intimidate();
        return "";
```

### angelic_descent_yellow  — looks-aligned
text: 'Target attack action card with Herald in its name gets **go again**.\n\nYour next angel attack this turn gets +2{p}.'
```json
{
  "slug": "angelic_descent_yellow",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "ANGEL_ATTACK_THIS_TURN"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return !$CombatChain->HasCurrentLink() || !str_contains(NameOverride($attackID, $mainPlayer), "Herald");
// DTDEffectPowerModifier()
case "angelic_descent_yellow": return 2;
// DTDCombatEffectActive()
case "angelic_descent_red": case "angelic_descent_yellow": case "angelic_descent_blue": return SubtypeContains($attackID, "Angel", $mainPlayer);
// DTDPlayAbility()
GiveAttackGoAgain();
      AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### stony_woottonhog_red  — looks-aligned
text: 'While Stony Woottonhog is defended by less than 2 non-equipment cards, it has +1{p}.'
```json
{
  "slug": "stony_woottonhog_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "DURING_TURN",
              "player": "self"
            },
            {
              "type": "DEFENDER_USED_HAND_CARD",
              "amount": 2,
              "equipment": false
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += NumCardsNonEquipBlocking() < 2 ? 1 : 0;
        break;
```

### shock_striker_red  — looks-aligned
text: '**Once per Turn Instant** - {r}{r}: Shock Striker gains "If Shock Striker hits a hero, deal 1 damage to them."'
```json
{
  "slug": "shock_striker_red",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 2,
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_HIT",
            "conditions": [
              {
                "type": "ATTACK_TARGET_IS_HERO"
              }
            ],
            "effects": [
              {
                "type": "DEAL_GENERIC",
                "amount": 1
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return SearchCurrentTurnEffects($cardID, $player);
// AddEffectHitTrigger()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// EffectHitEffect()
if (IsHeroAttackTarget()) DamageTrigger($defPlayer, 1, "ATTACKHIT", $cardID, $mainPlayer);
      break;
// ELEAbilityCost()
case "shock_striker_red": case "shock_striker_yellow": case "shock_striker_blue": return 2;
// ELEAbilityType()
if($from == "PLAY" || $from == "COMBATCHAINATTACKS") return "I";
        else return "AA";
// ELECombatEffectActive()
case "shock_striker_red": case "shock_striker_yellow": case "shock_striker_blue": return true;
// ELETalentPlayAbility()
if($from == "PLAY") AddCurrentTurnEffect($cardID, $currentPlayer, "");
        return "";
```

### emeritus_scolding_red  — looks-aligned
text: 'Deal 4 arcane damage to target hero. If Emeritus Scolding is played during an opponents turn, instead deal 6 arcane damage to them.'
```json
{
  "slug": "emeritus_scolding_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER",
          "value": false
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 6
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 4
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayRequiresTarget()
return 0;
// ActionsThatDoArcaneDamage()
return true;
// EVRPlayAbility()
$oppTurn = $currentPlayer != $mainPlayer;
        $damage = match($cardID) {
          "emeritus_scolding_red" => $oppTurn ? 6 : 4,
          "emeritus_scolding_yellow" => $oppTurn ? 5 : 3,
          default => $oppTurn ? 4 : 2,
        };
        DealArcane($damage, 0, "PLAYCARD", $cardID, resolvedTarget: $target);
        return "";
```

### biting_blade_red  — looks-aligned
text: 'Target weapon attack gains +3{p}.\n\n**Reprise** - If the defending hero has defended with a card from their hand this chain link, weapons you control gain +1{p} until end of turn'
```json
{
  "slug": "biting_blade_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DEFENDED_WITH_HAND_CARD"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "duration": "end_of_turn"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if (!$CombatChain->HasCurrentLink()) return true;
      if (SearchCombatChainAttacks($mainPlayer, type:"W") != "") return false;
      if (TypeContains($attackID, "W", $mainPlayer)) return false;
      return true;
// MainCharacterPowerModifiers()
$modifier += 1;
          $powerModifiers[] = $mainCharacterEffects[$i + 1];
          $powerModifiers[] = 1;
          break;
// ReactionRequirementsMet()
case "stroke_of_foresight_red": case "stroke_of_foresight_yellow": case "stroke_of_foresight_blue": return TypeContains($combatChain[0], "W", $mainPlayer);
// GetLayerTarget()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "COMBATCHAINATTACKS:type=W&ACTIVEATTACK:type=W");
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a weapon attack");
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);  
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// WTREffectPowerModifier()
case "biting_blade_red": return 3;
// WTRCombatEffectActive()
case "biting_blade_red": case "biting_blade_yellow": case "biting_blade_blue": return true;
// WTRPlayAbility()
if(RepriseActive()) { ApplyEffectToEachWeapon($cardID); $rv = "Gives weapons you control +1 for the rest of the turn"; }
        if (!str_contains($target, "COMBATCHAINATTACKS")) AddCurrentTurnEffect($cardID, $currentPlayer);
        return $rv;
```

### clash_of_vigor_yellow  — looks-aligned
text: 'When this defends, **clash** with the attacking hero. The winner creates a Vigor token.'
```json
{
  "slug": "clash_of_vigor_yellow",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "CLASH",
          "target": "attacker"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
Clash($parameter, effectController: $player);
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
// WonClashAbility()
PlayAura("vigor", $playerID);
        break;
```

### beckoning_mistblade  — looks-aligned
text: '**Once per Turn Action** - {r}{r}: **Attack**. **Go again**\n\nWhen this hits, your next blue attack this turn gets +1{p} and **go again**.'
```json
{
  "slug": "beckoning_mistblade",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 2,
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Assassin"
            },
            {
              "type": "ATTACK_SUBTYPE_IN",
              "subtype": "Dagger"
            }
          ]
        },
        {
          "type": "GO_AGAIN",
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Assassin"
            },
            {
              "type": "ATTACK_SUBTYPE_IN",
              "subtype": "Dagger"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesCurrentTurnEffectGrantGoAgain()
return true;
// MSTHitEffect()
AddCurrentTurnEffectNextAttack($cardID, $mainPlayer);
      break;
```

### vigor_rush_blue  — looks-aligned
text: "If you have played a 'non-attack' action card this turn, Vigor Rush gains **go again**."
```json
{
  "slug": "vigor_rush_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "NON_ATTACK_ACTION_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
return GetClassState($mainPlayer, $CS_NumNonAttackCards) > 0;
```

### cash_out_blue  — looks-aligned
text: 'As an additional cost to play Cash Out, you may destroy any number of weapons, equipment and/or non-token items you control.\n\nCreate a Silver token for each permanent destroyed this way.\n\n**Go again**'
```json
{
  "slug": "cash_out_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "controlled",
          "conditions": [
            {
              "type": "OR",
              "conditions": [
                {
                  "type": "CARD_IN_ZONE",
                  "zone": "arsenal",
                  "subtype": "Weapon"
                },
                {
                  "type": "CARD_IN_ZONE",
                  "zone": "arsenal",
                  "subtype": "Equipment"
                },
                {
                  "type": "CARD_IN_ZONE",
                  "zone": "arsenal",
                  "subtype": "Item",
                  "not": {
                    "type": "TOKEN"
                  }
                }
              ]
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Silver",
          "amount": "destroyed_permanents_count"
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PayAdditionalCosts()
AddDecisionQueue("PASSPARAMETER", $currentPlayer, "0");
      AddDecisionQueue("SETDQVAR", $currentPlayer, "0");
      AddDecisionQueue("FINDINDICES", $currentPlayer, "CASHOUT");
      AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("MZDESTROY", $currentPlayer, "-", 1);
      AddDecisionQueue("PASSPARAMETER", $currentPlayer, 1, 1);
      AddDecisionQueue("SETCLASSSTATE", $currentPlayer, $CS_AdditionalCosts, 1);
      AddDecisionQueue("SPECIFICCARD", $currentPlayer, "CASHOUTCONTINUE", 1);
      break;
// EVRPlayAbility()
PutItemIntoPlayForPlayer("silver", $currentPlayer, 0, intval($additionalCosts));
        return "";
```

### minds_desire_red  — looks-aligned
text: '**Stealth**\n\nWhen this hits a hero, banish the top card of their deck.\n\nWhenever this banishes a non-attack action card, gain 1{h}.'
```json
{
  "slug": "minds_desire_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": "OPPONENT_TOP_DECK"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BANISH",
      "conditions": [
        {
          "type": "NOT",
          "condition": {
            "type": "ATTACK_SUBTYPE_IN",
            "subtype": "Attack"
          }
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "HEALTH",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTHitEffect()
if (IsHeroAttackTarget()) {
        $deck->BanishTop("Source-" . $attackCard, banishedBy: $attackCard);
      }
      break;
```

### promise_of_plenty_blue  — looks-aligned
text: "If Promise of Plenty hits, each hero who doesn't have a card in their arsenal puts the top card of their deck face down into their arsenal.\n\nIf Promise of Plenty is played from arsenal, it gains **go again**."
```json
{
  "slug": "promise_of_plenty_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "EACH_HERO_ARSENAL_FROM_ZONE_THEN_DISCARD",
          "zone": "deck",
          "amount": 1,
          "condition": {
            "type": "NOT",
            "condition": {
              "type": "CARD_IN_ZONE",
              "zone": "arsenal",
              "amount": 1
            }
          }
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "conditions": [
        {
          "type": "PLAYED_FROM_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CRUPlayAbility()
if($from == "ARS") {
        GiveAttackGoAgain();
        $rv = "Gains go again";
      }
      return $rv;
// CRUHitEffect()
if(ArsenalEmpty($defPlayer)) TopDeckToArsenal($defPlayer);
      if(ArsenalEmpty($mainPlayer)) TopDeckToArsenal($mainPlayer);
      break;
```

### frontline_scout_yellow  — looks-aligned
text: "You may look at the defending hero's hand.\n\nIf Frontline Scout is played from arsenal, it gains **go again**."
```json
{
  "slug": "frontline_scout_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "LOOK_AT",
          "target": "defending_hero_hand"
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "conditions": [
        {
          "type": "PLAYED_FROM_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MONGenericPlayAbility()
$otherPlayer = ($currentPlayer == 1 ? 2 : 1);
        AddDecisionQueue("FINDINDICES", $otherPlayer, "HAND");
        AddDecisionQueue("REVEALHANDCARDS", $otherPlayer, "-", 1);
        if($from == "ARS") GiveAttackGoAgain();
        return "";
```

### celestial_reprimand_yellow  — looks-aligned
text: 'Target card defending an attack with Herald in its name gets -2{p} this combat chain.'
```json
{
  "slug": "celestial_reprimand_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "target": "opponent",
          "amount": -2,
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "defending",
              "card_name": "Herald"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return count($combatChain) < CombatChainPieces() * 2 || !str_contains(NameOverride($attackID, $mainPlayer), "Herald");
// GetLayerTarget()
AddDecisionQueue("FINDINDICES", $currentPlayer, "CCDEFLESSX,999");
      AddDecisionQueue("CHOOSECOMBATCHAIN", $currentPlayer, "<-", 1);
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// DTDPlayAbility()
$amount = match($cardID) { "celestial_reprimand_red" => -3, "celestial_reprimand_yellow" => -2, default => -1 };
      if($target != "-") $CombatChain->Card(intval($target))->ModifyPower($amount);
      return "";
```

### aether_ironweave  — looks-aligned
text: "**Action** - Destroy Aether Ironweave: Gain {r}{r}. Activate this ability only if you have played an attack action card and a 'non-attack' action card this turn. **Go again**\n\n**Battleworn**"
```json
{
  "slug": "aether_ironweave",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ATTACK_ACTION_PLAYED_THIS_TURN"
        },
        {
          "type": "FLAG_SET",
          "flag": "NON_ATTACK_ACTION_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 2
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return GetClassState($player, $CS_NumAttackCards) == 0 || GetClassState($player, $CS_NumNonAttackCards) == 0;
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// MONRunebladePlayAbility()
GainResources($currentPlayer, 2);
        return "";
// MONAbilityType()
case "aether_ironweave": return "A";
// MONAbilityHasGoAgain()
case "aether_ironweave": return true;
```

### plume_of_evergrowth  — looks-aligned
text: '**Instant** - {r}{r}{r}, destroy Plume of Evergrowth: Return target Earth action card or Earth instant card from your graveyard to your hand.'
```json
{
  "slug": "plume_of_evergrowth",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 3,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "RETURN_TO_HAND",
          "target": "CARD",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "GRAVEYARD",
              "card_type": "ACTION",
              "card_class": "Earth"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
$found = CombineSearches(SearchDiscard($player, "AA", talent: "EARTH"), SearchDiscard($player, "A", talent: "EARTH"));
      $found = CombineSearches(SearchDiscard($player, "I", talent: "EARTH"), $found);
      return $found == "";
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// PayAdditionalCosts()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYDISCARD:type=I;talent=EARTH&MYDISCARD:type=A;talent=EARTH&MYDISCARD:type=AA;talent=EARTH");
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose {{element|Earth|" . GetElementColorCode("EARTH") . "}} action card or {{element|Earth|" . GetElementColorCode("EARTH") . "}} instant card");
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// ELEAbilityCost()
case "plume_of_evergrowth": return 3;
// ELEAbilityType()
case "plume_of_evergrowth": return "I";
// ELETalentPlayAbility()
$params = explode("-", $target);
        $index = SearchdiscardForUniqueID($params[1], $currentPlayer);
        if ($index != -1) {
          AddDecisionQueue("PASSPARAMETER", $currentPlayer, "MYDISCARD-" . $index, 1);
          AddDecisionQueue("MZADDZONE", $currentPlayer, "MYHAND", 1);
          AddDecisionQueue("MZREMOVE", $currentPlayer, "-", 1);
        } else {
          WriteLog(CardLink($cardID, $cardID) . " layer fails as there are no remaining targets for the targeted effect.");
          return "";
        }
        return "";
```

### fang_strike  — looks-aligned
text: '**Ephemeral**\n\nTarget attack action card gets +1{p}.'
```json
{
  "slug": "fang_strike",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return !$CombatChain->HasCurrentLink() || CardType($attackID) != "AA";
// MSTPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### searing_gaze_red  — looks-aligned
text: 'Target dagger attack gets +2{p}. If you control 2 or more Draconic chain links, it gets "When this hits a hero, **mark** them."'
```json
{
  "slug": "searing_gaze_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Draconic",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "MARK"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if (!$CombatChain->HasCurrentLink()) return true;
      if (!SubtypeContains($CombatChain->CurrentAttack(), "Dagger", $currentPlayer)) return true;
      return false;
// AddEffectHitTrigger()
if (IsHeroAttackTarget() && NumDraconicChainLinks() > 1) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $parameter, $cardID, "EFFECTHITEFFECT");
        return true;
      }
      return false;
// EffectHitEffect()
MarkHero($defPlayer);
      break;
// HNTPlayAbility()
if (SubtypeContains($CombatChain->AttackCard()->ID(), "Dagger", $currentPlayer)) AddCurrentTurnEffect($cardID, $currentPlayer);
      break;
```

### vigorous_engagement_yellow  — looks-aligned
text: "Target Warrior attack gets +2{p}. If it's defended by an attack action card, create a Vigor token."
```json
{
  "slug": "vigorous_engagement_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor",
          "conditions": [
            {
              "type": "DURING_TURN",
              "condition": "DEFENDED_BY_ATTACK_ACTION_CARD"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return !$CombatChain->HasCurrentLink() || !ClassContains($attackID, "WARRIOR", $mainPlayer);
// HVYPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      if (NumAttacksBlocking() > 0) PlayAura("vigor", $currentPlayer); 
      return "";
```

### deathly_duet_yellow  — looks-aligned
text: "When Deathly Duet attacks, if an attack action card was pitched to play it, it gains +2{p}. If a 'non-attack' action card was pitched to play it, create 2 Runechant tokens."
```json
{
  "slug": "deathly_duet_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "ref": "ATTACK_ACTION"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "ref": "NON_ATTACK_ACTION"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNEffectPowerModifier()
case "deathly_duet_red": case "deathly_duet_yellow": case "deathly_duet_blue": return 2;
// DYNCombatEffectActive()
case "deathly_duet_red": case "deathly_duet_yellow": case "deathly_duet_blue": return true;
// DYNPlayAbility()
if(SearchCardList($additionalCosts, $currentPlayer, "AA") != "") AddCurrentTurnEffect($cardID, $currentPlayer);
      if(SearchCardList($additionalCosts, $currentPlayer, "A") != "") PlayAura("runechant", $currentPlayer, 2, true);
      return "";
```

### arakni_web_of_deceit  — looks-aligned
text: 'Your attacks with **stealth** that are attacking a **marked** hero get +1{p} and "When this hits, this gets **go again**."\n\nAt the beginning of your end phase, if an opponent is **marked**, you become a random Agent of Chaos.'
```json
{
  "slug": "arakni_web_of_deceit",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "ATTACK_HAS_KEYWORD",
          "keyword": "STEALTH"
        },
        {
          "type": "OPPONENT_IS_MARKED"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_HAS_KEYWORD",
          "keyword": "STEALTH"
        },
        {
          "type": "OPPONENT_IS_MARKED"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "conditions": [
        {
          "type": "OPPONENT_IS_MARKED"
        }
      ],
      "effects": [
        {
          "type": "TRANSFORM_HERO",
          "target": "RANDOM_AGENT_OF_CHAOS"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessMainCharacterHitEffect()
GiveAttackGoAgain();
      break;
// MainCharacterBeginEndPhaseAbilities()
if (CheckMarked($defPlayer) && $mainCharacter[$i + 1] < 3) ChaosTransform($characterID, $mainPlayer);
        break;
// MainCharacterHitTrigger()
if ($mainCharacter[$i+1] < 3) {
          if (IsHeroAttackTarget() && CheckMarked($defPlayer) && HasStealth($attackID) && ($cardID == "-" || $cardID == $attackID) && !$flicked) {
            AddLayer("TRIGGER", $mainPlayer, $characterID, $damageSource, "MAINCHARHITEFFECT");
          }
        }
        break;
// MainCharacterPowerModifiers()
if (HasStealth($CombatChain->CurrentAttack()) && CheckMarked($otherPlayer) && IsHeroAttackTarget()) {
          $modifier += 1;
          $powerModifiers[] = $characterID;
          $powerModifiers[] = 1;
        }
        break;
```

### prismatic_lens_yellow  — looks-aligned
text: '**Crank**\n\nThis enters the arena with a steam counter. At the start of your turn, destroy this unless you remove a steam counter from it.\n\n**Once per Turn Instant** - 0: Reveal the top card of your deck. Put a Mechanologist item of the same color from your banished zone on top of your deck.'
```json
{
  "slug": "prismatic_lens_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "steam",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "REMOVE_COUNTER",
          "counter": "steam",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "effects": [
        {
          "type": "REVEAL_TOP_DECK"
        },
        {
          "type": "SEARCH_BANISH_FACE_DOWN",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "banished",
              "subtype": "Item",
              "class": "Mechanologist",
              "color": "yellow"
            }
          ],
          "effects": [
            {
              "type": "PUT_TOP_DECK",
              "target": "searched_card"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if ($from == "PLAY") return $myItems[$index + 2] != 2; else return false;
// PayItemAbilityAdditionalCosts()
if ($from == "PLAY") {
        $items[$index + 2] = 1;
      }
      break;
// ItemStartTurnAbility()
if ($mainItems[$index + 1] > 0 && GetItemGemState($mainPlayer, $mainItems[$index], $index) == 0) --$mainItems[$index + 1];
      elseif($mainItems[$index + 1] > 0) {
        AddDecisionQueue("YESNO", $mainPlayer, "if you want to remove a Steam Counter and keep " . CardLink($mainItems[$index], $mainItems[$index]) . " and keep it in play?");
        AddDecisionQueue("REMOVECOUNTERITEMORDESTROYUID", $mainPlayer, $mainItems[$index + 4]);
      }
      else DestroyItemForPlayer($mainPlayer, $index);
      break;
// EVOPlayAbility()
if ($from == "PLAY") {
        $deck = new Deck($currentPlayer);
        $deck->Reveal();
        $pitchValue = PitchValue($deck->Top());
        MZMoveCard($currentPlayer, ("MYBANISH:class=MECHANOLOGIST;subtype=Item;pitch=" . $pitchValue), "MYTOPDECK", may: false, isReveal: true);
      }
      break;
```

### sigil_of_sanctuary_blue  — looks-aligned
text: '**Arcane Shelter 1**\n\nWhen this leaves the arena, create an Embodiment of Earth token.'
```json
{
  "slug": "sigil_of_sanctuary_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_LEAVE_PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Embodiment of Earth"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraLeavesPlay()
WriteLog(CardLink($cardID, $cardID) . " created an " . CardLink("embodiment_of_earth", "embodiment_of_earth"));
      PlayAura("embodiment_of_earth", $player);
      break;
```

### phantasmal_symbiosis_yellow  — looks-aligned
text: 'When this attacks, name a card.  Cards with that name are Illusionist until end of turn.\n\n**Phantasm**'
```json
{
  "slug": "phantasmal_symbiosis_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "PHANTASMAL_SYMBIOSIS_ACTIVE",
          "params": {
            "card_name": "NAMED_CARD"
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNPlayAbility()
AddDecisionQueue("INPUTCARDNAME", $currentPlayer, "-");
      AddDecisionQueue("SETDQVAR", $currentPlayer, "0");
      AddDecisionQueue("WRITELOG", $currentPlayer, "📣<b>{0}</b> was chosen");
      AddDecisionQueue("ADDCURRENTTURNEFFECT", $currentPlayer, "phantasmal_symbiosis_yellow-{0}");
      AddDecisionQueue("ADDCURRENTTURNEFFECT", $otherPlayer, "phantasmal_symbiosis_yellow-{0}");
      return "";
```

### agile_windup_yellow  — looks-aligned
text: '**Instant** - Discard this: Create an Agility token.'
```json
{
  "slug": "agile_windup_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "cost": [
        {
          "type": "DISCARD_SELF"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Agility"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CardCost()
if (GetResolvedAbilityType($cardID, "HAND") == "I" && $from == "HAND") return 0;
      return 3;
// GetAbilityNames()
return GetEasyAbilityNames($cardID, $index, $from, $allNames);
// GoesOnCombatChain()
return $phase == "B" && count($layers) == 0 || GetResolvedAbilityType($cardID, $from) == "AA";
// ProcessAbility()
PlayAura("agility", $player, isToken:true, effectController:$player, effectSource:$parameter);
      break;
```

### lady_barthimont  — looks-aligned
text: 'While Barthimont is face down in arsenal, at the start of your turn, you may turn her face up.\n\nWhile Barthimont is face up in arsenal, whenever you play an attack action card, banish the top card of your deck. If the banished card has 6 or more {p}, the attack gains **dominate** and put a lesson counter on Barthimont. Then if there are 2 or more lesson counters on her, banish her, search your deck for a **specialization** card, put it face up into arsenal, and shuffle.'
```json
{
  "slug": "lady_barthimont",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BARTHIMONT_FACE_DOWN"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "START_OF_TURN",
            "effects": [
              {
                "type": "MAY",
                "effects": [
                  {
                    "type": "FLIP_REF",
                    "ref": "lady_barthimont",
                    "face_up": true
                  }
                ]
              }
            ]
          }
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BARTHIMONT_FACE_UP"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_PLAY",
            "conditions": [
              {
                "type": "CARD_IN_ZONE",
                "zone": "HAND",
                "card_type": "ATTACK_ACTION"
              }
            ],
            "effects": [
              {
                "type": "BANISH",
                "target": "TOP_DECK"
              },
              {
                "type": "CONDITIONAL",
                "condition": {
                  "type": "DISCARDED_CARD_POWER_GTE",
                  "amount": 6
                },
                "effects": [
                  {
                    "type": "DOMINATE"
                  },
                  {
                    "type": "PUT_COUNTER",
                    "counter_type": "LESSON",
                    "amount": 1
                  },
                  {
                    "type": "CONDITIONAL",
                    "condition": {
                      "type": "COUNTER_GTE",
                      "counter_type": "LESSON",
                      "amount": 2
                    },
                    "effects": [
                      {
                        "type": "BANISH_REF",
                        "ref": "lady_barthimont"
                      },
                      {
                        "type": "SEARCH_DECK",
                        "conditions": [
                          {
                            "type": "CARD_SUBTYPE_IN",
                            "subtype": "SPECIALIZATION"
                          }
                        ],
                        "effects": [
                          {
                            "type": "PUT_REF_BOTTOM_DECK",
                            "ref": "searched_card"
                          }
                        ]
                      },
                      {
                        "type": "SHUFFLE_DECK"
                      }
                    ]
                  }
                ]
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// BlockValue()
$block = 3;
        break;
// DoesEffectGrantsDominate()
return true;
// IsAltCard()
return true;
// ArsenalStartTurnAbilities()
if ($arsenal[$i + 1] == "DOWN") {
          AddDecisionQueue("YESNO", $mainPlayer, "if_you_want_to_turn_".CardLink($arsenal[$i], $arsenal[$i])."_face_up");
          AddDecisionQueue("NOPASS", $mainPlayer, "-");
          AddDecisionQueue("TURNARSENALFACEUP", $mainPlayer, $i, 1);
        }
        break;
// ArsenalAttackAbilities()
if (CardType($attackID) == "AA" && $arsenal[$i + 1] == "UP") LadyBarthimontAbility($mainPlayer, $i);
        break;
// GenerateFunction()
$setID = "MON406";
          break;
// GenerateKeywordFunction()
$setID = "MON406";
          break;
// MONCombatEffectActive()
case "lady_barthimont": return true;
```

### driving_blade_red  — looks-aligned
text: 'Your next weapon attack this turn gains +3{p} and **go again**.\n\n**Go again**'
```json
{
  "slug": "driving_blade_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "DRIVING_BLADE_ACTIVE"
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DRIVING_BLADE_ACTIVE"
        },
        {
          "type": "IN_COMBAT"
        },
        {
          "type": "ATTACK_IS_WEAPON"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesCurrentTurnEffectGrantGoAgain()
return true;
// WTREffectPowerModifier()
case "driving_blade_red": return 3;
// WTRCombatEffectActive()
case "driving_blade_red": case "driving_blade_yellow": case "driving_blade_blue": return TypeContains($attackID, "W", $mainPlayer);
// WTRPlayAbility()
AddCurrentTurnEffect($cardID, $mainPlayer);
        return "";
```

### infecting_shot_blue  — looks-aligned
text: 'If Infecting Shot has an aim counter, it has +1{p}.\n\nWhen this hits a hero, create a Bloodrot Pox token under their control.'
```json
{
  "slug": "infecting_shot_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "COUNTER_GTE",
          "counter": "aim",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token": "Bloodrot Pox",
          "controller": "opponent"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTEffectPowerModifier()
case "infecting_shot_red": case "infecting_shot_yellow": case "infecting_shot_blue": return 1;
// OUTCombatEffectActive()
case "infecting_shot_red": case "infecting_shot_yellow": case "infecting_shot_blue": return true;
// OUTPlayAbility()
if(HasAimCounter()) {
          AddCurrentTurnEffect($cardID, $currentPlayer);
        }
        return "";
// OUTHitEffect()
if(IsHeroAttackTarget()) PlayAura($CID_BloodRotPox, $defPlayer, effectController: $mainPlayer);
        break;
```

### light_up_the_leaves_red  — looks-aligned
text: 'Deal 6 arcane damage to any target.\n\n**Instant** - Discard this and an Earth card: Prevent the next 6 arcane damage target source would deal this turn.'
```json
{
  "slug": "light_up_the_leaves_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 6
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DISCARD_SELF"
        },
        {
          "type": "DISCARD_CARD",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "HAND",
              "subtypes": [
                "Earth"
              ]
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "LIGHT_UP_THE_LEAVES_ACTIVE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CardCost()
if (GetResolvedAbilityType($cardID, "HAND") == "I" && $from == "HAND") return 0;
      return 3;
// GetAbilityNames()
if ($allNames) return "Ability,Action";
      $names = ["-", "-"];
      //can it ability?
      if ($from == "HAND" && SearchCount(SearchHand($currentPlayer, talent:"EARTH")) > 0 && !$instantRestricted) $names[0] = "Ability";
      else return "-,Action";
      //can it be played?
      if (CanPlayNAA($cardID, $from, $index)) $names[1] = "Action";

      if ($names[1] == "-") return $names[0];
      return implode(",", $names);
// CurrentTurnEffectUses()
return 6;
// ProcessAbility()
AddCurrentTurnEffect($parameter, $player, uniqueID:$target);
      break;
// CanPlayAsInstant()
return $from == "HAND" && SearchCount(SearchHand($currentPlayer, talent: "EARTH")) > 1;
// CurrentTurnEffectDamagePreventionAmount()
if ($source == $currentTurnEffects[$index + 2] && $type == "ARCANE") {
        return $damage;
      }
      break;
// CurrentEffectDamagePrevention()
if ($source == $currentTurnEffects[$index + 2]) {
        $remove = false;
        if ($preventable && $type == "ARCANE") {
          $preventedDamage += $currentTurnEffects[$index + 3];
          $currentTurnEffects[$index + 3] -= $damage;
        }
        else $remove = true;
        if ($currentTurnEffects[$index + 3] <= 0) $remove = true;
        $multiPing = match($source) {
          "comet_storm__shock_red" => true,
          default => false,
        };
        if (!IsStaticType(CardType($source)) && !$multiPing) $remove = true;
        elseif ($source == "spectral_shield" || $source == "runechant" || $source == "aether_ashwing") $remove = true;
      }
      if ($remove) RemoveCurrentTurnEffect($index);
      break;
// AddPrePitchDecisionQueue()
QueueArcaneAbilityOrActionChoice($cardID, $index, $from);
      // discarding an extra earth card
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose an {{element|Earth|" . GetElementColorCode("EARTH") . "}} Card to discard", 1);
      AddDecisionQueue("FINDINDICES", $currentPlayer, "HANDTALENT,EARTH,NOPASS", 1);
      AddDecisionQueue("REVERTGAMESTATEIFNULL", $currentPlayer, "You don't have any earth cards in hand to discard!", 1);
      AddDecisionQueue("CHOOSEHAND", $currentPlayer, "<-", 1);
      AddDecisionQueue("MULTIREMOVEHAND", $currentPlayer, "-", 1);
      AddDecisionQueue("DISCARDCARD", $currentPlayer, "HAND-" . $currentPlayer, 1);
      // targetting a source
      AddDecisionQueue("FINDINDICES", $currentPlayer, "DAMAGEPREVENTIONTARGET", 1);
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a damage source for " . CardLink($cardID, $cardID), 1);
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);
      AddDecisionQueue("MZOP", $currentPlayer, "GETCARDID", 1);
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);

      AddDecisionQueue("CONVERTLAYERTOABILITY", $currentPlayer, $cardID, 1);
      break;
// ActionsThatDoArcaneDamage()
return true;
// SUPPlayAbility()
DealArcane(ArcaneDamage($cardID), 2, "PLAYCARD", $cardID, resolvedTarget: $target);
      break;
```

### resounding_courage_yellow  — looks-aligned
text: "Target Light Warrior attack gets +2{p}.\n\nIf you've **charged** this turn, create a Courage token."
```json
{
  "slug": "resounding_courage_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CHARGED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Courage"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return !$CombatChain->HasCurrentLink() || !ClassContains($attackID, "WARRIOR", $mainPlayer) || !TalentContains($attackID, "LIGHT", $mainPlayer);
// DTDEffectPowerModifier()
case "resounding_courage_yellow": return 2;
// DTDCombatEffectActive()
case "resounding_courage_red": case "resounding_courage_yellow": case "resounding_courage_blue": return true;//Resounding Courage
// DTDPlayAbility()
case "resounding_courage_red": case "resounding_courage_yellow": case "resounding_courage_blue"://Resounding Courage
```

### tome_of_the_arknight_blue  — looks-aligned
text: 'Reveal the top 2 cards of your deck. If you reveal an attack action card and a non-attack action card this way, put them into your hand.\n\n**Go again**'
```json
{
  "slug": "tome_of_the_arknight_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "REVEAL_TOP_DECK",
          "amount": 2
        },
        {
          "type": "SEARCH_DECK",
          "conditions": [
            {
              "type": "AND",
              "conditions": [
                {
                  "type": "CARD_IN_ZONE",
                  "zone": "REVEALED",
                  "card_type": "ATTACK_ACTION"
                },
                {
                  "type": "CARD_IN_ZONE",
                  "zone": "REVEALED",
                  "card_type": "NON_ATTACK_ACTION"
                }
              ]
            }
          ],
          "effects": [
            {
              "type": "PUT_SELF_BOTTOM_DECK"
            },
            {
              "type": "RETURN_TO_HAND",
              "target": "REVEALED"
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCRunebladePlayAbility()
$deck = new Deck($currentPlayer);
        $deck->Reveal(2);
        $cards = explode(",", $deck->Top(amount:2));
        $type1 = CardType($cards[0]);
        $type2 = CardType($cards[1]);
        if((DelimStringContains($type1, "AA") && DelimStringContains($type2, "A")) || (DelimStringContains($type2, "AA") && DelimStringContains($type1, "A"))) {
          $deck->Top(remove:true, amount:2);
          AddPlayerHand($cards[0], $currentPlayer, "HAND");
          AddPlayerHand($cards[1], $currentPlayer, "HAND");
        }
        return "";
```

### harness_lightning_yellow  — looks-aligned
text: "**Lightning Flow** - If you've played a Lightning card this turn, deal 2 arcane damage to target hero."
```json
{
  "slug": "harness_lightning_yellow",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LIGHTNING_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AURPlayAbility()
if (GetClassState($mainPlayer, $CS_NumLightningPlayed) > 0) {
        DealArcane(2, 0, "PLAYCARD", $cardID);
      }
      return "";
```

### nerve_scalpel  — looks-aligned
text: '**Once per Turn Action** - {r}{r}: **Attack**. **Go again**\n\n**Piercing 1**\n\nWhen this hits a hero, the next time they defend with 1 or more reaction cards this turn, those cards have -1{d} while defending.'
```json
{
  "slug": "nerve_scalpel",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 2,
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "NERVE_SCALPEL_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "NERVE_SCALPEL_ACTIVE"
        },
        {
          "type": "DEFENDS_WITH_OTHER_HAND_CARD"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "subtract",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HasPiercing()
return true;
// AddOnHitTrigger()
if (IsHeroAttackTarget() || $targetPlayer != "-") {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $cardID, $targetPlayer, "ONHITEFFECT", $uniqueID);
        return true;
      }
      break;
// OnDefenseReactionResolveEffects()
$count = ModifyBlockForType("DR", -1); //AR is handled in OnBlockResolveEffects
          $remove = $count > 0;
          break;
// OnBlockResolveEffects()
$count = ModifyBlockForType("AR", 0); //DR could not possibly be blocking at this time, see OnDefenseReactionResolveEffects
          $remove = $count > 0;
          break;
// OnBlockEffects()
if ($cardType == "AR") $chainCard->ModifyDefense(-1);
          break;
// EffectHasBlockModifier()
return true;
// ReverseID()
return "OUT006";
// ReverseArt()
case "nerve_scalpel": return "nerve_scalpel_r";
// OUTAbilityCost()
case "nerve_scalpel": case "nerve_scalpel_r": return 2;
// OUTAbilityType()
case "nerve_scalpel": case "nerve_scalpel_r": return "AA";
// OUTHitEffect()
AddCurrentTurnEffect($cardID, $defPlayer);
        break;
```

### lumina_ascension_yellow  — looks-aligned
text: '**Boltyn Specialization**\n\nUntil end of turn, weapons you control gain +1{p} and "If this hits, reveal the top card of your deck. If it\'s a Light card, put it into your hero\'s soul and gain 1{h}, otherwise put it on the bottom of your deck."\n\nIf you\'ve **charged** this turn, you may attack an additional time with each weapon you control.\n\n**Go again**'
```json
{
  "slug": "lumina_ascension_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BOLTYN_SPECIALIZATION_ACTIVE"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "target": "WEAPONS_CONTROLLED_BY_YOU"
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "TRIGGERED",
            "trigger": "ON_HIT",
            "effects": [
              {
                "type": "REVEAL_TOP_DECK",
                "amount": 1
              },
              {
                "type": "CONDITIONAL",
                "conditions": [
                  {
                    "type": "CARD_IN_ZONE",
                    "zone": "DECK",
                    "card_type": "LIGHT"
                  }
                ],
                "effects": [
                  {
                    "type": "PUT_SELF_BOTTOM_DECK",
                    "target": "REVEALED_CARD"
                  },
                  {
                    "type": "GAIN_LIFE",
                    "amount": 1
                  }
                ]
              },
              {
                "type": "CONDITIONAL",
                "conditions": [
                  {
                    "type": "NOT",
                    "condition": {
                      "type": "CARD_IN_ZONE",
                      "zone": "DECK",
                      "card_type": "LIGHT"
                    }
                  }
                ],
                "effects": [
                  {
                    "type": "PUT_CARD_BOTTOM",
                    "target": "REVEALED_CARD"
                  }
                ]
              }
            ]
          }
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CHARGED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GO_AGAIN",
          "target": "WEAPONS_CONTROLLED_BY_YOU"
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddEffectHitTrigger()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// EffectHitEffect()
$deck = new Deck($mainPlayer);
      if (!$deck->Reveal()) return;
      $top = $deck->Top(remove: true);
      if (TalentContains($top, "LIGHT", $mainPlayer)) {
        AddSoul($top, $mainPlayer, "DECK");
        GainHealth(1, $mainPlayer);
      } else $deck->AddBottom($top, "DECK");
      break;
// IsCombatEffectPersistent()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// MONEffectPowerModifier()
case "lumina_ascension_yellow": return 1;
// MONCombatEffectActive()
case "lumina_ascension_yellow": return TypeContains($attackID, "W", $mainPlayer);
// MONWarriorPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        $character = &GetPlayerCharacter($currentPlayer);
        if(GetClassState($currentPlayer, $CS_NumCharged) > 0) {
          $charCount = count($character);
          $charPieces = CharacterPieces();
          for($i=0; $i<$charCount; $i+=$charPieces) {
            if(CardType($character[$i]) == "W" && $character[$i+1] != 0) { $character[$i+1] = 2; ++$character[$i+5]; }
          }
        }
        return "";
```

### riptide  — looks-aligned
text: 'Whenever you play a card from hand, you may put a card from hand face down into your arsenal.\n\nWhenever a trap you control triggers, deal 1 damage to the attacking hero.'
```json
{
  "slug": "riptide",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PLAY_ACTIVATE_ATTACK",
      "effects": [
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": 1,
          "zone": "HAND",
          "face_down": true,
          "destination": "ARSenal"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_TRAP_TRIGGER",
      "effects": [
        {
          "type": "DEAL_GENERIC",
          "amount": 1,
          "target": "ATTACKER"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
if ($additionalCosts == "DAMAGE") {
          $defHero = new CharacterCard(0, $defPlayer);
          SetDamageSourceUID($defHero->UniqueID());
          DamageTrigger($mainPlayer, 1, "DAMAGE", $parameter, $defPlayer);
        }
        else SuperReload();
        break;
// MainCharacterPlayCardAbilities()
if ($from == "HAND" && GetResolvedAbilityName($cardID, "HAND") != "Ability") {
          AddLayer("TRIGGER", $currentPlayer, $characterID, $cardID);
        }
        break;
// DecisionQueueStaticEffect()
if (SubtypeContains($Layer->Parameter(), "Trap", $player)) {
              AddLayer("TRIGGER", $player, $Hero->CardID(), "-", "DAMAGE");
              ++$i; // needed due to reindexing
            }
            break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
```

### panel_beater_blue  — looks-aligned
text: '**Boost**\n\nThis gets +X{p}, where X is the number of equipment defending it.'
```json
{
  "slug": "panel_beater_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += NumEquipBlock();
        break;
```

### aether_icevein_blue  — looks-aligned
text: '**Ice Fusion**\n\nDeal 3 arcane damage to any target. If Aether Icevein was **fused** and deals damage to a hero, they discard a card unless they pay {r}{r}.'
```json
{
  "slug": "aether_icevein_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 3
        },
        {
          "type": "PAY_OR_DAMAGE",
          "pay_cost": {
            "type": "PAY_RESOURCES",
            "amount": 2
          },
          "damage_effect": {
            "type": "DEAL_GENERIC",
            "amount": 1
          },
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "FUSED"
            },
            {
              "type": "ATTACK_TARGET_IS_HERO"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayRequiresTarget()
return 2;
// ActionsThatDoArcaneDamage()
return true;
// HasFusion()
case "aether_icevein_red": case "aether_icevein_yellow": case "aether_icevein_blue": return "ICE";
// UPRWizardPlayAbility()
$damage = match($cardID) { "aether_icevein_red" => 5, "aether_icevein_yellow" => 4, default => 3 };
        if (DelimStringContains($additionalCosts, "ICE")) $source = "$cardID|FUSED";
        else $source = $cardID;
        DealArcane($damage, 2, "PLAYCARD", $source, false, $currentPlayer, false, false, !DelimStringContains($additionalCosts, "ICE"), resolvedTarget: $target);
        return "";
```

### art_of_the_dragon_scale_red  — looks-aligned
text: 'When this attacks, if it is Draconic, it gets "When this hits a hero, put a -1{d} counter on an equipment they control. Then if it has 0{d}, destroy it."'
```json
{
  "slug": "art_of_the_dragon_scale_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "Draconic"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger": "ON_HIT",
            "conditions": [
              {
                "type": "ATTACK_TARGET_IS_HERO"
              }
            ],
            "effects": [
              {
                "type": "PUT_COUNTER",
                "counter": "DEFENSE",
                "mod": "subtract",
                "amount": 1,
                "target": "equipment"
              },
              {
                "type": "CONDITIONAL",
                "condition": {
                  "type": "COUNTER_GTE",
                  "counter": "DEFENSE",
                  "amount": 0
                },
                "effects": [
                  {
                    "type": "DESTROY_REF",
                    "target": "equipment"
                  }
                ]
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddOnHitTrigger()
if (IsHeroAttackTarget() && SearchCurrentTurnEffects($cardID, $mainPlayer)) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "ONHITEFFECT");
        return true;
      }
      break;
// HNTPlayAbility()
if(TalentContains($cardID, "DRACONIC", $currentPlayer)) {
        AddCurrentTurnEffect($cardID, $currentPlayer);
      }
      break;
// HNTHitEffect()
AddDecisionQueue("FINDINDICES", $defPlayer, "EQUIP");
      AddDecisionQueue("CHOOSETHEIRCHARACTER", $mainPlayer, "<-", 1);
      AddDecisionQueue("MODDEFCOUNTER", $defPlayer, "-1", 1);
      AddDecisionQueue("DESTROYEQUIPDEF0", $mainPlayer, "-", 1);
      break;
```

### testament_of_valahai  — looks-aligned
text: 'If you control three or more Seismic Surge tokens, this gets +2{d}. If you control six or more, instead this gets +4{d}.\n\n**Guardwell**'
```json
{
  "slug": "testament_of_valahai",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Seismic Surge",
          "amount": 3
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Seismic Surge",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 4
        }
      ]
    }
  ]
}
```
Talishar:
```php
// BlockModifier()
$countSeismic = CountAura("seismic_surge", $defPlayer);
      if ($countSeismic >= 6) {
        $blockModifier += 4;
      }
      elseif ($countSeismic >= 3) {
        $blockModifier += 2;
      }
      break;
```

### sprocket_rocket_yellow  — looks-aligned
text: '**Boost**\n \nIf an item or equipment was banished from boosting this, this gets +1{p}.'
```json
{
  "slug": "sprocket_rocket_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "ITEM_OR_EQUIPMENT"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SelfBoostEffects()
if(SubtypeContains($boosted, "Item", $player) || IsEquipment($boosted, $player)) AddCurrentTurnEffect($cardID, $player);
      break;
```

### push_forward_blue  — looks-aligned
text: 'Your next weapon attack this turn gains +1{p}.\n\nIf you have attacked with a weapon this turn, your next attack this turn gains **dominate**.\n\n**Go again**'
```json
{
  "slug": "push_forward_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "WEAPON_ATTACKED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "DOMINATE"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "NEXT_ATTACK_IS_WEAPON"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CRUPlayAbility()
AddCurrentTurnEffect($cardID . "-1", $mainPlayer);
      if(GetClassState($currentPlayer, $CS_AttacksWithWeapon) > 0) {
        AddCurrentTurnEffect($cardID . "-2", $mainPlayer);
        $rv = "Gives your attack dominate because you've attacked with a weapon";
      }
      return $rv;
```

### unicycle  — looks-aligned
text: '**Instant** - Destroy this: {u} a cog you control.\n\n**Battleworn**'
```json
{
  "slug": "unicycle",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": "self",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// SEAPlayAbility()
$inds = GetTapped($currentPlayer, "MYITEMS", "subtype=Cog");   
      if(empty($inds)) break;
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "You may untap a cog you control");
      //technically should be a MAYCHOOSEMULTIZONE but for playerMacro we make it so it skips the step if there is 1 choice
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, $inds);
      AddDecisionQueue("MZTAP", $currentPlayer, "0", 1);
      break;
```

### mutiny_on_the_swiftwater_blue  — looks-aligned
text: 'For each hero that controls more Gold than you, **steal** a Gold token they control.\n\nIf you gain control of 1 or more Gold tokens this way, your next attack this turn gets **go again**.\n\n**Go again**'
```json
{
  "slug": "mutiny_on_the_swiftwater_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "STEAL_AURA_TOKEN",
          "aura_type": "Gold",
          "conditions": [
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "Gold",
              "opponent": true,
              "greater_than": true
            }
          ]
        },
        {
          "type": "SET_FLAG",
          "flag": "MUTINY_STOLE_GOLD",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "STEAL_GOLD_SUCCESS"
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "MUTINY_STOLE_GOLD"
        }
      ],
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesCurrentTurnEffectGrantGoAgain()
return true;
// SEAPlayAbility()
$myNumGold = CountItem("gold", $currentPlayer);
      $theirNumGold = CountItem("gold", $otherPlayer);
      if ($myNumGold < $theirNumGold) {
        AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "THEIRITEMS:type=T;cardID=gold");
        AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("MZOP", $currentPlayer, "GAINCONTROL", 1);
        AddCurrentTurnEffect($cardID, $currentPlayer);
      }
      break;
```

### barraging_brawnhide_blue  — looks-aligned
text: 'While Barraging Brawnhide is defended by less than 2 non-equipment cards, it has +1{p}.'
```json
{
  "slug": "barraging_brawnhide_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "DURING_TURN",
          "conditions": [
            {
              "type": "DEFENDER_USED_HAND_CARD",
              "amount": 2,
              "comparison": "lt"
            },
            {
              "type": "RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT",
              "comparison": "eq",
              "value": false
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += NumCardsNonEquipBlocking() < 2 ? 1 : 0;
        break;
```

### vengeance_never_rests_blue  — looks-aligned
text: '**Combo** - If Edge of Autumn was the last attack this combat chain, this gets **go again** and "When this hits a hero, banish it. You may play it this turn."'
```json
{
  "slug": "vengeance_never_rests_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "EDGE_OF_AUTUMN_LAST_ATTACK"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        },
        {
          "type": "BANISH",
          "target": "hero"
        },
        {
          "type": "BANISH_OPP_TOP_GRANT_PLAY",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Edge of Autumn") return true;
        break;
// AddOnHitTrigger()
if (ComboActive($cardID) && IsHeroAttackTarget()) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "ONHITEFFECT");
        return true;
      }
      break;
// DoesAttackHaveGoAgain()
return ComboActive($attackID);
// ASRHitEffect()
$combatChainState[$CCS_GoesWhereAfterLinkResolves] = "-"; 
      BanishCardForPlayer($cardID, $mainPlayer, "COMBATCHAIN", "TT", $mainPlayer);
      break;
```

### single_minded_determination_red  — looks-aligned
text: 'When this enters the arena, if you control no other Illusionist auras, put three +1{p} counters on this.\n\n**Ward 2**'
```json
{
  "slug": "single_minded_determination_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "conditions": [
        {
          "type": "NOT",
          "condition": {
            "type": "CONTROLS_TOKEN_TYPE",
            "token_type": "Illusionist"
          }
        }
      ],
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter_type": "power",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTPlayAbility()
if ($from != "PLAY") {
        $auras = &GetAuras($currentPlayer);
        $illusionistAuras = SearchAura($currentPlayer, class: "ILLUSIONIST");
        $arrayAuras = explode(",", $illusionistAuras);
        $amount = 3;
        if ($cardID == "single_minded_determination_yellow") $amount = 2;
        else if ($cardID == "single_minded_determination_blue") $amount = 1;
        if (count($arrayAuras) <= 1) {
          $index = count($auras) - AuraPieces();
          $auras[$index + 3] += $amount;
        }
      }
      return "";
```

### warriors_valor_blue  — looks-aligned
text: 'Your next weapon attack this turn gets +1{p} and "When this hits, it gets **go again**."\n\n**Go again**'
```json
{
  "slug": "warriors_valor_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "DURING_TURN"
        },
        {
          "type": "ATTACK_IS_WEAPON"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_HIT",
            "effects": [
              {
                "type": "GO_AGAIN"
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddEffectHitTrigger()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// EffectHitEffect()
GiveAttackGoAgain();
      break;
// WTREffectPowerModifier()
case "warriors_valor_blue": return 1;
// WTRCombatEffectActive()
case "warriors_valor_red": case "warriors_valor_yellow": case "warriors_valor_blue": return TypeContains($attackID, "W", $mainPlayer);
// WTRPlayAbility()
AddCurrentTurnEffect($cardID, $mainPlayer);
        return "";
```

### riled_up_blue  — looks-aligned
text: "If you've discarded a card with 6 or more {p} this turn, this gets +1{p}."
```json
{
  "slug": "riled_up_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DISCARDED_HIGH_POWER_CARD_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += (GetClassState($mainPlayer, $CS_Num6PowDisc) > 0 ? 1 : 0);
        break;
```

### back_alley_breakline_yellow  — looks-aligned
text: 'If an activated ability or action card effect puts Back Alley Breakline face up into a zone from your deck, gain 1 action point.'
```json
{
  "slug": "back_alley_breakline_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ACTIVATED_ABILITY_OR_ACTION_CARD_EFFECT"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "ACTION_POINTS",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PitchAbility()
if ($from == "DECK" && $currentPlayer == $mainPlayer) {
        WriteLog("Player ". $currentPlayer ." gained 1 action point from " . CardLink($cardID, $cardID).".");
        ++$actionPoints;
      }
      break;
```

### astral_etchings_blue  — looks-aligned
text: 'Put a +1{p} counter on target aura with **ward** you control.\n\nIf you control a Spectral Shield, you may play this as though it were an instant.'
```json
{
  "slug": "astral_etchings_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "power",
          "amount": 1,
          "target": "controlled_aura_with_ward"
        }
      ],
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Spectral Shield"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
$auras = &GetAuras($player);
      foreach ($auras as $aura) { 
        if (HasWard($aura, $player)) return false;
      }
      return true;
// CanPlayAsInstant()
if (SearchAuras("spectral_shield", $currentPlayer)) return true;
      break;
// GetLayerTarget()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYAURAS:hasWard=true");
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose target aura");
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// MSTPlayAbility()
$amount = 3;
      if ($cardID == "astral_etchings_yellow") $amount = 2;
      else if ($cardID == "astral_etchings_blue") $amount = 1;
      $params = explode("-", $target);
      if(substr($params[0], 0, 5) != "THEIR") {
        $zone = "MYAURAS-";
        $player = $currentPlayer;
      }
      else {
        $zone = "THEIRAURAS-";
        $player = $otherPlayer;
      }
      $index = SearchAurasForUniqueID($params[1], $player);
      if ($index != -1) {
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, $zone . $index, 1);
        AddDecisionQueue("MZADDCOUNTERS", $currentPlayer, $amount, 1);
      }
      else {
        WriteLog(CardLink($cardID, $cardID) . " layer fails as there are no remaining targets for the targeted effect.");
        return "";
      }
      return "";
```

### blossoming_decay_blue  — looks-aligned
text: '**Decompose** - When this attacks, you may banish 2 Earth cards and an action card from your graveyard. If you do, gain 1{h}.'
```json
{
  "slug": "blossoming_decay_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "BANISH",
          "amount": 2,
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "GRAVEYARD",
              "subtype": "Earth"
            }
          ]
        },
        {
          "type": "BANISH",
          "amount": 1,
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "GRAVEYARD",
              "subtype": "Action"
            }
          ]
        },
        {
          "type": "GAIN",
          "asset": "HEALTH",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "BANISHED_EARTH_ACTION"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
Decompose($player, "BLOSSOMINGDECAY");
        break;
// ROSPlayAbility()
AddDecisionQueue("ADDTRIGGER", $currentPlayer, $cardID, 1);
      return "";
```

### fealty  — looks-aligned
text: "**Instant** - Destroy this: The next card you play this turn is Draconic. At the beginning of your end phase, if you haven't created a Fealty token or played a Dragonic card this turn, destroy this."
```json
{
  "slug": "fealty",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "FEALTY_DESTROYED"
        },
        {
          "type": "SET_FLAG",
          "flag": "FEALTY_PLAYED"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FEALTY_DESTROYED"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FEALTY_PLAYED"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "conditions": [
        {
          "type": "NOT",
          "condition": {
            "type": "FLAG_SET",
            "flag": "FEALTY_DESTROYED"
          }
        },
        {
          "type": "NOT",
          "condition": {
            "type": "FLAG_SET",
            "flag": "FEALTY_PLAYED"
          }
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraBeginEndPhaseTriggers()
$fealtySurvives = GetClassState($mainPlayer, $CS_FealtyCreated) + GetClassState($mainPlayer, $CS_NumDraconicPlayed);
        if (!$fealtySurvives) {
          AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", "-", $auras[$i + 6]);
        }
        break;
// PayAuraAbilityAdditionalCosts()
DestroyAura($currentPlayer, $index);
      break;
// ProcessTrigger()
DestroyAuraUniqueID($player, $uniqueID);
        break;
// TalentOverride()
$cardType = CardType($cardID);
        if (!TypeContains($cardID, "W") && !TypeContains($cardID, "AA") && !IsStaticType($cardType)) { // We'll need to add cases for Allies and Emperor Attacking
          $talents[] = "DRACONIC";
        }
        break;
// SearchInner()
case "fealty":                     $talentMod_fealty      = true; break;
// HNTPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      break;
```

### harvest_season_blue  — looks-aligned
text: '**Go again**\n\nAt the beginning of your action phase, destroy this, then gain 1{h}.'
```json
{
  "slug": "harvest_season_blue",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "HEALTH",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraBeginningActionPhaseAbilities()
AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", "DESTROY", $auras[$i + 6]);
        break;
// ProcessTrigger()
$numHealthPointsGained = match ($parameter) {"harvest_season_red" => 3, "harvest_season_yellow" => 2, "harvest_season_blue" => 1};
        DestroyAuraUniqueID($player, $uniqueID);
        GainHealth($numHealthPointsGained, $player);
        break;
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
```

### volzar_the_lightning_rod  — looks-aligned
text: "If you control an aura permanent with Sigil in its name, this costs {r} less to activate.\n\n**Once per Turn Instant** - {r}: **Amp X**, where X is the number of Lightning cards you've played this turn."
```json
{
  "slug": "volzar_the_lightning_rod",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "PAY_LIFE",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "AMP",
          "amount": 1
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LIGHTNING_PLAYED_THIS_TURN"
        }
      ]
    },
    {
      "ability_type": "INSTANT",
      "activation_cost": 1,
      "effects": [
        {
          "type": "AMP",
          "amount": 1
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LIGHTNING_PLAYED_THIS_TURN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ArcaneModifierAmount()
return $effectArr[1];
// CurrentEffectArcaneModifier()
if ($currentTurnEffects[$i + 1] != $player) break;
        $modifier += $effectArr[1];
        $remove = true;
        break;
// ROSPlayAbility()
$ampAmount = GetClassState($currentPlayer, $CS_NumLightningPlayed);
      if($ampAmount > 0) {
        AddCurrentTurnEffect($cardID . "," . $ampAmount, $currentPlayer, "ABILITY");
      }
      return "Amp " . $ampAmount;
```

### tough_as_a_rok_blue  — looks-aligned
text: "If you have less {h} than each other hero, this card's base {p} is 6, otherwise it's 0."
```json
{
  "slug": "tough_as_a_rok_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "HEALTH_LT_OPP"
        }
      ],
      "effects": [
        {
          "type": "SET_BASE_POWER",
          "amount": 6
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "NOT",
          "condition": {
            "type": "HEALTH_LT_OPP"
          }
        }
      ],
      "effects": [
        {
          "type": "SET_BASE_POWER",
          "amount": 0
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerValue()
$basePower = PlayerHasLessHealth($player) ? 6 : 0;
      break;
```

### vigorous_engagement_red  — looks-aligned
text: "Target Warrior attack gets +3{p}. If it's defended by an attack action card, create a Vigor token."
```json
{
  "slug": "vigorous_engagement_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "class": "Warrior"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor",
          "conditions": [
            {
              "type": "DEFENDS_WITH_OTHER_HAND_CARD"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return !$CombatChain->HasCurrentLink() || !ClassContains($attackID, "WARRIOR", $mainPlayer);
// HVYPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      if (NumAttacksBlocking() > 0) PlayAura("vigor", $currentPlayer); 
      return "";
```

### tough_old_wrench_yellow  — looks-aligned
text: '**Galvanize** - When this defends, you may destroy an item you control. If you do, create a Golden Cog token.'
```json
{
  "slug": "tough_old_wrench_yellow",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "Galvanize"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "controlled_item"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Golden Cog"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
MZChooseAndDestroy($player, "MYITEMS", may: true, context: "Choose an item to galvanize for " . CardLink($parameter, $parameter) . " effect");
        AddDecisionQueue("PASSPARAMETER", $player, "golden_cog", 1);
        AddDecisionQueue("PUTPLAY", $player, "0", 1);
        break;
```

### yinti_yanti_yellow  — looks-aligned
text: 'While Yinti Yanti is attacking and you control an aura, it has +1{p}.\n\nWhile Yinti Yanti is defending and you control an aura, it has +1{d}.'
```json
{
  "slug": "yinti_yanti_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "IN_COMBAT",
          "combat_type": "ATTACK"
        },
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Aura"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "IN_COMBAT",
          "combat_type": "DEFEND"
        },
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Aura"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += count($mainAuras) >= 1 ? 1 : 0;
        break;
// BlockModifier()
return count($defAuras) >= 1 ? 1 : 0;
```

### vest_of_the_first_fist  — looks-aligned
text: 'When an attack action card you control hits, you may destroy Vest of the First Fist. If you do, gain {r}{r}.'
```json
{
  "slug": "vest_of_the_first_fist",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "CONTROLS_ATTACK_ACTION"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessMainCharacterHitEffect()
$index = FindCharacterIndex($player, $cardID);
      AddDecisionQueue("YESNO", $player, "if_you_want_to_destroy_".Cardlink($cardID, $cardID)."_to_gain_2_resources");
      AddDecisionQueue("NOPASS", $player, "");
      AddDecisionQueue("PASSPARAMETER", $player, "MYCHAR-" . $index, 1);
      AddDecisionQueue("MZDESTROY", $player, "-", 1);
      AddDecisionQueue("GAINRESOURCES", $player, 2, 1);
      break;
// MainCharacterHitTrigger()
if ($isAA && IsCharacterActive($mainPlayer, $i)) {
          AddLayer("TRIGGER", $mainPlayer, $characterID, $damageSource, "MAINCHARHITEFFECT");
        }
        break;
```

### clash_of_bravado_yellow  — looks-aligned
text: 'When this defends, **clash** with the attacking hero. The winner destroys an aura the other hero controls.'
```json
{
  "slug": "clash_of_bravado_yellow",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "CLASH",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "CLASH_ACTIVE"
            }
          ]
        },
        {
          "type": "DESTROY_TOKEN",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "CLASH_WIN"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
Clash($parameter, effectController: $player);
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
// WonClashAbility()
AddDecisionQueue("MULTIZONEINDICES", $playerID, "THEIRAURAS");
        AddDecisionQueue("CHOOSEMULTIZONE", $playerID, "<-", 1);
        AddDecisionQueue("SHOWCHOSENCARD", $playerID, "<-", 1);
        AddDecisionQueue("MZDESTROY", $playerID, "<-", 1);
        break;
```

### sigil_of_suffering_red  — looks-aligned
text: 'Deal 1 arcane damage to the attacking hero.\n\nIf you have dealt arcane damage this turn, Sigil of Suffering gains +1{d}.'
```json
{
  "slug": "sigil_of_suffering_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        },
        {
          "type": "SET_FLAG",
          "flag": "SIGIL_OF_SUFFERING_ARCANE_DEALT"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SIGIL_OF_SUFFERING_ARCANE_DEALT"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ELERunebladePlayAbility()
WriteLog(CardLink($cardID) . " only checks for arcane damage when it resolves.");
        DealArcane(1, 1, "PLAYCARD", $cardID);
        AddDecisionQueue("SPECIFICCARD", $currentPlayer, "SIGILOFSUFFERING", 1);
        return "";
```

### stacked_in_your_favor_red  — looks-aligned
text: '**Go again**\n\nYour attack action cards get +3{d} while defending.\n\nAt the start of your turn, destroy this, draw a card, then put a card from your hand on top of your deck.'
```json
{
  "slug": "stacked_in_your_favor_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 3
        }
      ],
      "conditions": [
        {
          "type": "IN_COMBAT"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "PUT_HAND_CARD_BOTTOM",
          "position": "top"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
$effectSource = $auras[$i];
        WriteLog("Resolving " . CardLink($auras[$i], $auras[$i]) . " ability");
        DestroyAuraUniqueID($mainPlayer, $auras[$i + 6]);
        Draw($mainPlayer, effectSource: $effectSource);
        MZMoveCard($mainPlayer, "MYHAND", "MYTOPDECK", silent: true);
        break;
// AuraBlockModifier()
if ($cardType == "AA") $blockModifier += 3;
        break;
```

### meganetic_shockwave_blue  — looks-aligned
text: 'The defending hero must defend Meganetic Shockwave with X equipment they control, where X is the number of times you have **boosted** this combat chain.'
```json
{
  "slug": "meganetic_shockwave_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT",
          "amount": "X"
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BOOSTED_COMBAT_CHAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CRUPlayAbility()
if($combatChainState[$CCS_NumBoosted] && IsHeroAttackTarget()) {
        if ($combatChainState[$CCS_NumBoosted] > 1 && IsOverpowerActive()) $combatChainState[$CCS_RequiredEquipmentBlock] = 1;
        else $combatChainState[$CCS_RequiredEquipmentBlock] = $combatChainState[$CCS_NumBoosted];
        $rv .= "Requires you to block with " . $combatChainState[$CCS_NumBoosted] . " equipment if able";
      }
      return $rv;
```

### suraya_archangel_of_erudition  — looks-aligned
text: "**Once per Turn Action** - {r}{r}: **Attack**\n\nWhen Suraya attacks, you may banish a card from your hero's soul. If you do, draw 2 cards.\n\n**Ward 4**"
```json
{
  "slug": "suraya_archangel_of_erudition",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 2,
      "effects": [
        {
          "type": "ATTACK"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "BANISH",
          "target": "hero_soul"
        },
        {
          "type": "DRAW",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SpecificAllyAttackAbilities()
AddLayer("TRIGGER", $mainPlayer, $attackID);
        break;
// ProcessTrigger()
$soul = &GetSoul($mainPlayer);
        if (count($soul) == 0) break;
        AddDecisionQueue("YESNO", $mainPlayer, "if you want to banish a card from soul");
        AddDecisionQueue("NOPASS", $mainPlayer, "-");
        MZMoveCard($mainPlayer, "MYSOUL", "MYBANISH,SOUL,-", isSubsequent: true);
        AddDecisionQueue("DRAW", $mainPlayer, "suraya_archangel_of_erudition,2", 1);
        break;
// DTDAbilityCost()
case "suraya_archangel_of_erudition": case "themis_archangel_of_judgment": case "aegis_archangel_of_protection": case "sekem_archangel_of_ravages"://Angels
// DTDAbilityType()
case "suraya_archangel_of_erudition": case "themis_archangel_of_judgment": case "aegis_archangel_of_protection": case "sekem_archangel_of_ravages"://Angels
```

### in_the_swing_blue  — looks-aligned
text: "Play this only if you've attacked 2 or more times with weapons this turn.\n\nTarget weapon attack gains +1{p}."
```json
{
  "slug": "in_the_swing_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ATTACKED_WITH_WEAPON_TWICE_OR_MORE"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ReactionRequirementsMet()
case "in_the_swing_red": case "in_the_swing_yellow": case "in_the_swing_blue": return GetClassState($currentPlayer, $CS_AttacksWithWeapon) >= 1;
```

### grow_claws_blue  — looks-aligned
text: 'If a Draconic attack was the last attack this combat chain, this gets +1{p}.\n\n**Go again**'
```json
{
  "slug": "grow_claws_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LAST_ATTACK_WAS_DRACONIC"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += isPreviousLinkDraconic() ? 1 : 0;
        break;
```

### plunder_run_blue  — looks-aligned
text: 'The next time an attack action card you control hits this turn, draw a card.\n\nIf Plunder Run is played from arsenal, the next attack action card you play this turn gains +1{p}.\n\n**Go again**'
```json
{
  "slug": "plunder_run_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "CONTROLS_ATTACK_ACTION"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "conditions": [
        {
          "type": "PLAYED_FROM_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger": "ON_PLAY",
            "conditions": [
              {
                "type": "CONTROLS_ATTACK_ACTION"
              }
            ],
            "effects": [
              {
                "type": "MODIFY_ATTACK",
                "mod": "add",
                "amount": 1
              }
            ]
          }
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCGenericPlayAbility()
AddCurrentTurnEffect($cardID . "-1", $currentPlayer);
      if($from == "ARS") {
        AddCurrentTurnEffect($cardID . "-2", $currentPlayer);
        $rv = "Played from arsenal: Gives your next attack action card +" . EffectPowerModifier($cardID . "-2");
      }
      return $rv;
```

### expedition_to_azuro_keys_red  — looks-aligned
text: 'When this attacks, you may put a gold counter on Treasure Island.'
```json
{
  "slug": "expedition_to_azuro_keys_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "GOLD",
          "target": "TREASURE_ISLAND"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SEAPlayAbility()
$treasureID = SearchLandmarksForID("treasure_island");
      if ($treasureID != -1) {
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Do you want to put a gold counter on for " . CardLink("treasure_island", "treasure_island") . "?");
        AddDecisionQueue("YESNO", $currentPlayer, "-");
        AddDecisionQueue("NOPASS", $currentPlayer, "-");
        AddDecisionQueue("ADDCOUNTERLANDMARK", $currentPlayer, $treasureID, 1);
      }
      break;
```

### soup_up_red  — looks-aligned
text: 'If an item you control has been destroyed this turn, this gets **go again**.\n\n**Galvanize** - When this defends, you may destroy an item you control. If you do, this gets +2{d}.'
```json
{
  "slug": "soup_up_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ITEM_DESTROYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "DEFENSE_REACTION",
      "effects": [
        {
          "type": "MAY",
          "effects": [
            {
              "type": "DESTROY_PERMANENT",
              "target": "controlled_item"
            },
            {
              "type": "MODIFY_DEFENSE_VALUE",
              "mod": "add",
              "amount": 2
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
case "steel_street_hoons_blue": //Galvanize
// DoesAttackHaveGoAgain()
return GetClassState($mainPlayer, $CS_NumItemsDestroyed) > 0;
```

### photon_rush_red  — looks-aligned
text: "**Lightning Flow** - If you've played a Lightning card this turn, this gets **go again**"
```json
{
  "slug": "photon_rush_red",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LIGHTNING_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
return GetClassState($mainPlayer, $CS_NumLightningPlayed) > 0;
```

### jinglewood_smash_hit  — looks-aligned
text: '**Once per Turn Action** - {r}{r}{r}: Target opposing hero chooses and creates a Might, Quicken, or Vigor token. You create a Copper token. **Go again**\n\n**Action** - 0: **Attack**. When this hits, destroy it.'
```json
{
  "slug": "jinglewood_smash_hit",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 3,
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Might"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Quicken"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Copper"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// GetAbilityNames()
if ($allNames) return "Create_tokens,Smash_Jinglewood";
      if ($index == -1) return "";
      return "Create_tokens,Smash_Jinglewood";
// EquipPayAdditionalCosts()
break; //Unlimited uses
// TCCHitEffect()
$charIndex = FindCharacterIndex($mainPlayer, $cardID);
      DestroyCharacter($mainPlayer, $charIndex);
      break;
// TCCPlayAbility()
$abilityType = GetResolvedAbilityType($cardID);
      $character = &GetPlayerCharacter($currentPlayer);
      $charIndex = FindCharacterIndex($mainPlayer, $cardID);
      if ($abilityType == "A") {
        AddDecisionQueue("SETDQCONTEXT", $otherPlayer, "Choose a token to create");
        AddDecisionQueue("MULTICHOOSETEXT", $otherPlayer, "1-Might (+1),Vigor (Resource),Quicken (Go Again)-1");
        AddDecisionQueue("SHOWMODES", $otherPlayer, $cardID, 1);
        AddDecisionQueue("MODAL", $otherPlayer, "JINGLEWOOD", 1);
        PutItemIntoPlayForPlayer("copper", $currentPlayer);
        --$character[$charIndex + 5];
      }
      return "";
```

### zap_yellow  — looks-aligned
text: 'Deal 2 arcane damage to target hero.'
```json
{
  "slug": "zap_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCWizardPlayAbility()
DealArcane(ArcaneDamage($cardID), 0, "PLAYCARD", $cardID, resolvedTarget: $target);
      return "";
// PlayRequiresTarget()
return 0;
// ActionsThatDoArcaneDamage()
return true;
```

### wreck_havoc_blue  — looks-aligned
text: "Defense reactions can't be played to this chain link.\n\nWhen this hits a hero, you may turn a card in their arsenal face up, then destroy a defense reaction in their arsenal."
```json
{
  "slug": "wreck_havoc_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "IN_COMBAT"
        }
      ],
      "effects": [
        {
          "type": "RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "REVEAL_TOP_DECK",
          "target": "OPPONENT"
        },
        {
          "type": "DESTROY_TOKEN",
          "target": "OPPONENT",
          "token_type": "DEFENSE_REACTION"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTHitEffect()
SetArsenalFacing("UP", $defPlayer);
        AddDecisionQueue("MULTIZONEINDICES", $mainPlayer, "THEIRARS:type=DR");
        AddDecisionQueue("SETDQCONTEXT", $mainPlayer, "Choose which card you want to destroy", 1);
        AddDecisionQueue("CHOOSEMULTIZONE", $mainPlayer, "<-", 1);
        AddDecisionQueue("MZDESTROY", $mainPlayer, "-", 1);
        break;
```

### teklonetic_force_field_yellow  — looks-aligned
text: 'When this defends an attack with **overpower**, this gets +2{d}.'
```json
{
  "slug": "teklonetic_force_field_yellow",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "ATTACK_HAS_KEYWORD",
          "keyword": "OVERPOWER"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// BlockModifier()
if (CachedOverpowerActive()) $blockModifier += 2;
      break;
```

### aegis_archangel_of_protection  — looks-aligned
text: "**Once per Turn Action** - {r}{r}: **Attack**\n\nWhen Aegis attacks, you may banish a card from your hero's soul. If you do, create 2 Spectral Shield tokens.\n\n**Ward 4**"
```json
{
  "slug": "aegis_archangel_of_protection",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 2,
      "effects": [
        {
          "type": "ATTACK"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "AEGIS_ATTACKED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": "hero_soul"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Spectral Shield",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SpecificAllyAttackAbilities()
AddLayer("TRIGGER", $mainPlayer, $attackID);
        break;
// ProcessTrigger()
$soul = &GetSoul($mainPlayer);
        if (count($soul) == 0) break;
        AddDecisionQueue("YESNO", $mainPlayer, "if you want to banish a card from soul");
        AddDecisionQueue("NOPASS", $mainPlayer, "-");
        MZMoveCard($mainPlayer, "MYSOUL", "MYBANISH,SOUL,-", isSubsequent: true);
        AddDecisionQueue("PLAYAURA", $mainPlayer, "spectral_shield-2", 1);
        break;
// DTDAbilityCost()
case "suraya_archangel_of_erudition": case "themis_archangel_of_judgment": case "aegis_archangel_of_protection": case "sekem_archangel_of_ravages"://Angels
// DTDAbilityType()
case "suraya_archangel_of_erudition": case "themis_archangel_of_judgment": case "aegis_archangel_of_protection": case "sekem_archangel_of_ravages"://Angels
```

### pleiades_superstar  — looks-aligned
text: '**Instant** - {t}, remove a suspense counter from an aura you control: You may put a suspense counter on an aura of suspense you control.\n\nWhenever the crowd cheers you, create a Confidence token.'
```json
{
  "slug": "pleiades_superstar",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "REMOVE_COUNTERS",
          "target": "controlled_aura",
          "counter": "suspense",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "MAY",
          "effects": [
            {
              "type": "PUT_COUNTER",
              "target": "controlled_aura",
              "counter": "suspense",
              "amount": 1,
              "conditions": [
                {
                  "type": "CONTROLS_TOKEN_TYPE",
                  "token_type": "suspense"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CLASH_WIN_REVEALED",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "confidence"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if (CheckTapped("MYCHAR-$index", $currentPlayer)) return true;
      //check that there's an aura with a suspense counter
      if (count(GetSuspenseAuras($currentPlayer, true)) == 0) return true;
      return false;
// ProcessTrigger()
PlayAura("confidence", $player, isToken:true, effectController:$player, effectSource:$parameter);
        break;
// EquipPayAdditionalCosts()
Tap("MYCHAR-$cardIndex", $currentPlayer);
      $suspAuras = implode(",", GetSuspenseAuras($currentPlayer, true));
      AddDecisionQueue("PASSPARAMETER", $currentPlayer, $suspAuras);
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose an aura to remove a suspense counter from", 1);
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SUSPENSE", $currentPlayer, "REMOVE", 1);
      break;
// SUPPlayAbility()
$suspAuras = GetSuspenseAuras($currentPlayer);
      if (count($suspAuras) > 0) {
        $suspAuras = implode(",", GetSuspenseAuras($currentPlayer));
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, $suspAuras);
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose an aura to add a suspense counter to (or pass)", 1);
        AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("SUSPENSE", $currentPlayer, "ADD", 1);
      }
      break;
// Cheer()
AddLayer("TRIGGER", $player, $char[0]);
          break;
```

### seduce_secrets_yellow  — looks-aligned
text: "Look at target hero's hand and the top card of their deck.\n\nIf this was played from arsenal, draw a card."
```json
{
  "slug": "seduce_secrets_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "LOOK_AT",
          "target": "hero_hand"
        },
        {
          "type": "LOOK_AT",
          "target": "hero_deck_top"
        },
        {
          "type": "DRAW",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "PLAYED_FROM_ARSENAL"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HVYPlayAbility()
LookAtTopCard($currentPlayer, $cardID, showHand: true);
      if ($from == "ARS") AddDecisionQueue("DRAW", $currentPlayer, "-");
      return "";
```

### annihilator_engine_red  — looks-aligned
text: 'If you have 1 or more Evos equipped, this gets "When this hits a hero, destroy all cards defending this,"\n\n- 2 or more, this costs {r}{r}{r} less to play,\n- 3 or more, this gets **overpower**,\n- 4 or more, this gets +3{p}.'
```json
{
  "slug": "annihilator_engine_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Evo"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "target": "defending"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Evo",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "subtract",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Evo",
          "amount": 3
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "OVERPOWER"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Evo",
          "amount": 4
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddOnHitTrigger()
if (IsHeroAttackTarget() && EvoUpgradeAmount($mainPlayer) >= 1) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "ONHITEFFECT");
        return true;
      }
      break;
// PowerModifier()
$power += EvoUpgradeAmount($mainPlayer) >= 4 ? 3 : 0;
        break;
// IsOverpowerActive()
return EvoUpgradeAmount($mainPlayer) >= 3;
// SelfCostModifier()
return EvoUpgradeAmount($currentPlayer) >= 2 ? -3 : 0;
// EVOHitEffect()
if (IsHeroAttackTarget() && EvoUpgradeAmount($mainPlayer) >= 1) {
        global $combatChain, $CombatChain;
        $defendingCardsStr = GetChainLinkCards($defPlayer, exclCardTypes: "C");
        if ($defendingCardsStr !== '') {
          $defendingCardsArr = explode(",", $defendingCardsStr);
          $cardLink = CardLink("annihilator_engine_red", "annihilator_engine_red");
          for ($i = count($defendingCardsArr) - 1; $i >= 0; --$i) {
            $defendingCard = $defendingCardsArr[$i];
            $cardVal = $combatChain[$defendingCard];
            WriteLog($cardLink . " destroyed " . CardLink($cardVal, $cardVal) . ".");
            if (CardType($cardVal) == "E") {
              DestroyCharacter($defPlayer, FindCharacterIndex($defPlayer, $cardVal));
            } else {
              AddGraveyard($cardVal, $defPlayer, "CC");
              $CombatChain->Remove($defendingCard);
            }
          }
        }
      }
      break;
```

### seek_enlightenment_blue  — looks-aligned
text: 'The next attack action card you play this turn gains +1{p} and "If this hits, put it into your hero\'s soul."\n\n**Go again**'
```json
{
  "slug": "seek_enlightenment_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "SEEK_ENLIGHTENMENT_ACTIVE"
            }
          ]
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_HIT",
            "effects": [
              {
                "type": "PUT_REF",
                "ref": "self",
                "zone": "hero_soul"
              }
            ]
          },
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "SEEK_ENLIGHTENMENT_ACTIVE"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddEffectHitTrigger()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// EffectHitEffect()
$combatChainState[$CCS_GoesWhereAfterLinkResolves] = "SOUL";
      break;
// MONEffectPowerModifier()
case "seek_enlightenment_blue": return 1;
// MONCombatEffectActive()
case "seek_enlightenment_red": case "seek_enlightenment_yellow": case "seek_enlightenment_blue": return CardType($attackID) == "AA";
// MONTalentPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### scramble_pulse_yellow  — looks-aligned
text: 'Equipment have -1{d} while defending this combat chain.\n\n**Boost**'
```json
{
  "slug": "scramble_pulse_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "subtract",
          "amount": 1,
          "conditions": [
            {
              "type": "IN_COMBAT"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// RemoveEffectsFromCombatChain()
$remove = 1;
        break;
// DYNPlayAbility()
case "scramble_pulse_red": case "scramble_pulse_yellow": case "scramble_pulse_blue": AddCurrentTurnEffect($cardID, $currentPlayer); return "";
```

### memorial_ground_red  — looks-aligned
text: 'Put target attack action card with cost 2 or less from your graveyard on top of your deck.'
```json
{
  "slug": "memorial_ground_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "PUT_CARDS_BOTTOM",
          "target": "GRAVEYARD",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "GRAVEYARD",
              "conditions": [
                {
                  "type": "ATTACK_COST_LTE",
                  "amount": 2
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
$maxCost = 2;
      if ($cardID == "memorial_ground_yellow") $maxCost = 1;
      elseif ($cardID == "memorial_ground_blue") $maxCost = 0;
      return SearchDiscard($player, "AA", "", $maxCost) == "";
// GetLayerTarget()
$maxCost = 2;
      if ($cardID == "memorial_ground_yellow") $maxCost = 1;
      elseif ($cardID == "memorial_ground_blue") $maxCost = 0;
      AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYDISCARD:maxCost=" . $maxCost . ";type=AA");
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// MONGenericPlayAbility()
$params = explode("-", $target);
        $index = SearchdiscardForUniqueID($params[1], $currentPlayer);
        if($index != -1) {
          AddDecisionQueue("PASSPARAMETER", $currentPlayer, "MYDISCARD-".$index, 1);
          AddDecisionQueue("MZADDZONE", $currentPlayer, "MYTOPDECK", 1);
          AddDecisionQueue("MZREMOVE", $currentPlayer, "-", 1);
        }
        else {
          WriteLog(CardLink($cardID, $cardID) . " layer fails as there are no remaining targets for the targeted effect.");
          return "";
        }
        return "";
```

### waning_vengeance_blue  — looks-aligned
text: "When this leaves the arena, if you've pitched a blue card this turn, create a Spectral Shield token.\n\n**Ward 1**"
```json
{
  "slug": "waning_vengeance_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_LEAVE_PLAY",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "PITCHED_BLUE_CARD_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Spectral Shield"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraLeavesPlay()
AddLayer("TRIGGER", $player, $cardID, "-", "-", $uniqueID);
      break;
// ProcessTrigger()
if (SearchPitchForColor($player, 3) > 0) PlayAura("spectral_shield", $player);
        break;
```

### amulet_of_oblation_blue  — looks-aligned
text: '**Go again**\n\n**Instant** - Destroy Amulet of Oblation: Until end of turn, target attack action gains "If this would be put into a graveyard, instead put it on the bottom of its owner\'s deck." Activate this ability only if a card has entered a graveyard this turn.'
```json
{
  "slug": "amulet_of_oblation_blue",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CARD_ENTERED_GRAVEYARD_THIS_TURN"
        }
      ],
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_DEATH",
          "conditions": [
            {
              "type": "REF_EXISTS",
              "ref": "TARGET_ATTACK_ACTION"
            }
          ],
          "effects": [
            {
              "type": "MOVE_REF",
              "ref": "TARGET_ATTACK_ACTION",
              "zone": "BOTTOM_DECK"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// GoesWhereEffectsModifier()
$effectArr = explode("-", $currentTurnEffects[$i], 2);
        if ($cardID == $effectArr[1]) {
          RemoveCurrentTurnEffect($i);
          return "BOTDECK";
        }
        break;
// IsPlayRestricted()
return $from == "PLAY" && (GetClassState(1, $CS_CardsEnteredGY) == 0 && GetClassState(2, $CS_CardsEnteredGY) == 0 || !$CombatChain->HasCurrentLink() || CardType($attackID) != "AA");
// PayItemAbilityAdditionalCosts()
DestroyItemForPlayer($currentPlayer, $index);
      break;
// EVRAbilityCost()
case "amulet_of_oblation_blue": return 0;
// EVRAbilityType()
if($from == "PLAY") return "I";
        else return "A";
// EVRPlayAbility()
if($from == "PLAY") {
          AddDecisionQueue("FINDINDICES", $currentPlayer, "CCAA");
          AddDecisionQueue("CHOOSECOMBATCHAIN", $currentPlayer, "<-", 1);
          AddDecisionQueue("AMULETOFOBLATION", $currentPlayer, $cardID."-!CC", 1);
        }
        return "";
```

### feisty_locals_blue  — looks-aligned
text: 'If this is defended by an action card, this gets +2{p}.'
```json
{
  "slug": "feisty_locals_blue",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "DEFENDS_WITH_OTHER_HAND_CARD"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += (CachedNumActionBlocked() > 0 ? 2 : 0);
        break;
```

### maxx_nitro  — looks-aligned
text: "**Once per Turn Action** - {r}{r}: Create a Hyper Driver token with 2 steam counters.  Activate this ability only if you've boosted this turn.\n\nHyper Drivers you control get **crank**."
```json
{
  "slug": "maxx_nitro",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 2,
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BOOSTED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Hyper Driver",
          "counters": [
            {
              "type": "steam",
              "amount": 2
            }
          ]
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GRANT_SUBTYPE",
          "subtype": "crank",
          "target": "Hyper Driver"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return $character[5] == 0;
// EVOPlayAbility()
$character = &GetPlayerCharacter($currentPlayer);
      PutItemIntoPlayForPlayer("hyper_driver", $currentPlayer, 2);
      --$character[5];
      return "";
```

### grind_them_down_blue  — looks-aligned
text: '**Crush** - When this deals 4 or more damage to a hero, destroy the top card of their deck.'
```json
{
  "slug": "grind_them_down_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CRUSH",
      "conditions": [
        {
          "type": "DID_NOT_HIT",
          "amount": 4
        }
      ],
      "effects": [
        {
          "type": "DESTROY_REF",
          "target": "OPPONENT_TOP_DECK"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessCrushEffect()
$deck = new Deck($defPlayer);
        if($deck->Empty()) break;
        else DestroyTopCard($defPlayer);
        break;
```

### escalate_bloodshed_red  — looks-aligned
text: "Whenever a hero draws a card during an action phase, they lose 1{h}.\n\nAt the beginning of each hero's action phase, they draw a card.\n\nAt the beginning of each hero's end phase, if a weapon did not attack this turn, destroy this."
```json
{
  "slug": "escalate_bloodshed_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DRAW",
      "conditions": [
        {
          "type": "DURING_TURN",
          "phase": "ACTION_PHASE"
        }
      ],
      "effects": [
        {
          "type": "LOSE_LIFE",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "DURING_TURN",
          "phase": "ACTION_PHASE"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "DURING_TURN",
          "phase": "END_PHASE"
        },
        {
          "type": "NOT",
          "condition": {
            "type": "ATTACK_IS_WEAPON"
          }
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraBeginningActionPhaseAbilities()
AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", "DESTROY", $auras[$i + 6]);
        break;
// AuraBeginningActionPhaseAbilities()
AddLayer("TRIGGER", $mainPlayer, $theirAuras[$i], "-", "-", $theirAuras[$i + 6]);
        break;
// AuraBeginEndPhaseTriggers()
if(GetClassState($mainPlayer, $CS_AttacksWithWeapon) == 0) {
          DestroyAuraUniqueID($mainPlayer, $auras[$i + 6]);
        }
        break;
// AuraBeginEndPhaseTriggers()
if(GetClassState($mainPlayer, $CS_AttacksWithWeapon) == 0) {
            DestroyAuraUniqueID($defPlayer, $theirAuras[$i + 6]);
          }
          break;
// ProcessTrigger()
Draw($player, effectSource:$parameter);
        break;
// Draw()
if ($mainPhase) {
          //TODO rework this to be a respondable trigger
          WriteLog("🩸 You bleed from " . CardLink("escalate_bloodshed_red", "escalate_bloodshed_red"));
          PlayerLoseHealth($num, $player, true);
        }
        break;
// Draw()
if ($mainPhase) {
          //TODO rework this to be a respondable trigger
          WriteLog("🩸 You bleed from " . CardLink("escalate_bloodshed_red", "escalate_bloodshed_red"));
          LoseHealth($num, $player);
        }
        break;
```

### lace_with_frailty_red  — looks-aligned
text: 'Your next arrow attack this turn gains +3{p} and "When this hits a hero, create a Frailty token under their control."\n\n**Go again**'
```json
{
  "slug": "lace_with_frailty_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "ATTACK_TYPE_IN",
          "types": [
            "Arrow"
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Frailty"
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddEffectHitTrigger()
if (IsHeroAttackTarget()) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $parameter, $cardID, "EFFECTHITEFFECT", $source);
        return true;
      }
      return false;
// EffectHitEffect()
if (IsHeroAttackTarget()) PlayAura($CID_Frailty, $defPlayer, effectController: $mainPlayer);
      break;
// OUTEffectPowerModifier()
case "lace_with_frailty_red": return 3;
// OUTCombatEffectActive()
case "lace_with_frailty_red": return CardSubType($attackID) == "Arrow";
// OUTPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### torque_tuned_blue  — looks-aligned
text: 'If an item you control has been destroyed this turn, this gets **overpower**.\n\n**Galvanize** - When this defends, you may destroy an item you control. If you do, this gets +2{d}.'
```json
{
  "slug": "torque_tuned_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ITEM_DESTROYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "OVERPOWER"
        }
      ]
    },
    {
      "ability_type": "DEFENSE_REACTION",
      "effects": [
        {
          "type": "MAY",
          "effects": [
            {
              "type": "DESTROY_PERMANENT",
              "target": "item"
            },
            {
              "type": "MODIFY_DEFENSE_VALUE",
              "mod": "add",
              "amount": 2
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
case "steel_street_hoons_blue": //Galvanize
// IsOverpowerActive()
return GetClassState($mainPlayer, $CS_NumItemsDestroyed) > 0;
```

### bet_big_red  — looks-aligned
text: '**Betsy Specialization**\n\nWhen this attacks a hero, you may **wager** a Gold, Might, and Vigor token with them.'
```json
{
  "slug": "bet_big_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "WAGER",
          "tokens": [
            "Gold",
            "Might",
            "Vigor"
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessWager()
PutItemIntoPlayForPlayer("gold", $wonWager, number:$amount, effectController:$mainPlayer);
        PlayAura("might", $wonWager, $amount);
        PlayAura("vigor", $wonWager, $amount);
        break;
// ResolveWagers()
if (!$chainClosed) {
              $triggerCardID = $currentTurnEffects[$i];
              AddLayer("TRIGGER", $mainPlayer, $triggerCardID, $wonWager, "WAGER");
            }
            RemoveCurrentTurnEffect($i);
            break;
// HVYPlayAbility()
if (IsHeroAttackTarget()) AskWager($cardID);
      return "";
```

### proclamation_of_abundance  — looks-aligned
text: '**Action** - {r}{r}{r}, destroy this: Each hero draws up to their {i}.'
```json
{
  "slug": "proclamation_of_abundance",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 3,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": "intellect"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// isClashLegal()
return true;
```

### hungering_demigon_blue  — looks-aligned
text: 'If an opposing hero has 1 or more cards in their soul, you may play this from your banished zone.\n\nWhen this hits a hero, banish a card from their soul.\n\n**Blood Debt**'
```json
{
  "slug": "hungering_demigon_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": "opponent_soul",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayableFromBanish()
$soul = &GetSoul($player == 1 ? 2 : 1);
      return count($soul) > 0;
// DTDHitEffect()
if(IsHeroAttackTarget()) MZMoveCard($mainPlayer, "THEIRSOUL", "THEIRBANISH,SOUL,-");
      break;
```

### death_touch_blue  — looks-aligned
text: "Death Touch can't be played from hand.\n\nWhen this hits a hero, create a Frailty, Inertia, or Bloodrot Pox token under their control."
```json
{
  "slug": "death_touch_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Frailty"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Inertia"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Bloodrot Pox"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return $from == "HAND";
// OUTHitEffect()
if(IsHeroAttackTarget())
        {
          AddDecisionQueue("CHOOSECARD", $mainPlayer, $CID_BloodRotPox . "," . $CID_Frailty . "," . $CID_Inertia);
          AddDecisionQueue("PUTPLAY", $defPlayer, $mainPlayer, 1);
        }
        break;
```

### cut_to_the_chase_blue  — looks-aligned
text: "Target Assassin attack action card with **contract** gains +1{p}.\n\nLook at the top card of the defending hero's deck. You may put it on the bottom."
```json
{
  "slug": "cut_to_the_chase_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "HAS_KEYWORD",
              "keyword": "CONTRACT"
            }
          ]
        },
        {
          "type": "LOOK_AT",
          "target": "OPPONENT_DECK_TOP"
        },
        {
          "type": "MAY",
          "effects": [
            {
              "type": "PUT_CARDS_BOTTOM",
              "amount": 1,
              "target": "OPPONENT_DECK_TOP"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return !$CombatChain->HasCurrentLink() || !ClassContains($attackID, "ASSASSIN", $mainPlayer) || ContractType($attackID) == "";
// ReactionRequirementsMet()
case "cut_to_the_chase_red": case "cut_to_the_chase_yellow": case "cut_to_the_chase_blue": return ClassContains($combatChain[0], "ASSASSIN", $mainPlayer) && CardType($combatChain[0]) == "AA" && ContractType($combatChain[0]) != "";
// DYNEffectPowerModifier()
case "cut_to_the_chase_blue": return 1;
// DYNCombatEffectActive()
case "cut_to_the_chase_red": case "cut_to_the_chase_yellow": case "cut_to_the_chase_blue": return true;
// DYNPlayAbility()
$otherPlayer = ($currentPlayer == 1 ? 2 : 1);
      AddDecisionQueue("DECKCARDS", $otherPlayer, "0", 1);
      AddDecisionQueue("SETDQVAR", $currentPlayer, "0", 1);
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose if you want sink <0>", 1);
      AddDecisionQueue("YESNO", $currentPlayer, "if_you_want_to_sink_the_opponent's_card", 1);
      AddDecisionQueue("NOPASS", $currentPlayer, "-", 1);
      AddDecisionQueue("FINDINDICES", $otherPlayer, "TOPDECK", 1);
      AddDecisionQueue("MULTIREMOVEDECK", $otherPlayer, "<-", 1);
      AddDecisionQueue("ADDBOTDECK", $otherPlayer, "-", 1);
      AddDecisionQueue("ELSE", $currentPlayer, "-");
      AddDecisionQueue("WRITELOG", $currentPlayer, "Left the card on top", 1);
      AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### grasp_of_darkness  — looks-aligned
text: 'If your hero would be dealt damage, you may banish this to prevent 2 of that damage.\n\n**Blood Debt**'
```json
{
  "slug": "grasp_of_darkness",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "DURING_TURN",
          "player": "self"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": "self"
        },
        {
          "type": "DEAL_ARCANE",
          "target": "opponent",
          "amount": -2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CharacterDamagePreventionAmount()
if ($check) return 0; // if we're only checking how much prevention is there, return 0
      if ($char[$index + 9] == 0) return 0;
      return 2;
// CharacterTakeDamageAbility()
if ($char[$index + 9] == 0) break;
      if ($damage > 0) {
        if ($preventable) $preventedDamage += 2;
        BanishCardForPlayer($char[$index], $player, "PLAY");
        DestroyCharacter($player, $index, skipDestroy: true);
      }
      break;
```

### palantir_aeronought_red  — looks-aligned
text: "The defending hero must defend this with an equipment they control if able.\n\n**Thrice per Turn Instant** - {t} a cog you control: This gets +1{p}. If this is the third time you've activated this ability, destroy a defending card."
```json
{
  "slug": "palantir_aeronought_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "IN_COMBAT"
        }
      ],
      "effects": [
        {
          "type": "RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT"
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "PITCH",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ACTIVATION_COUNT",
          "amount": 3
        }
      ],
      "additional_effects": [
        {
          "type": "DESTROY_REF",
          "target": "defending_card"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if ($player != $mainPlayer) return true;
      if ($from != "PLAY" && $from != "COMBATCHAINATTACKS") return false;
      if (GetUntapped($player, "MYITEMS", "subtype=Cog") == "") return true;
      if ($from == "PLAY" && $combatChain[11] >= 3) return true;
      if ($from == "COMBATCHAINATTACKS" && $chainLinks[$index][9] >= 3) return true;
      return false;
// CombatChainPayAdditionalCosts()
$inds = GetUntapped($currentPlayer, "MYITEMS", "subtype=Cog");
      if($inds != "") {//Tap(explode(",", $inds)[0], $currentPlayer);
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, $inds);
        AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("MZTAP", $currentPlayer, "<-", 1);
      }
      if ($from == "PLAY") ++$combatChain[$i + 11];
      else ++$chainLinks[$i][9];
      break;
// SEAPlayAbility()
if($from != "PLAY" && $from != "COMBATCHAINATTACKS" && IsHeroAttackTarget()) $combatChainState[$CCS_RequiredEquipmentBlock] = 1;
      elseif($from == "PLAY" || $from == "COMBATCHAINATTACKS") {
        $numUsed = 0;
        if ($from == "PLAY") {
          $numUsed = $combatChain[11];
          AddCurrentTurnEffect($cardID, $currentPlayer);
        }
        else {
          $attacks = GetCombatChainAttacks();
          $attackInd = -1;
          $attacksCount = count($attacks);
          $chainLinksPieces = ChainLinksPieces();
          for ($i = 0; $i < $attacksCount; $i += $chainLinksPieces) {
            if ($attacks[$i] == $cardID && $attacks[$i + 9] <= 3) {
              $numUsed = $attacks[$i + 9];
              $attackInd = intdiv($i, $chainLinksPieces);
            }
          }
        }
        if ($numUsed == 3) {
          $pastChoices = GetPastChainLinkCards($defPlayer, asMZInd: true);
          $currentChoices = GetChainLinkCards($defPlayer, asMZInd: true);
          if ($currentChoices == "") $choices = $pastChoices;
          elseif ($pastChoices == "") $choices = $currentChoices;
          else $choices = "$pastChoices,$currentChoices";
          if ($choices != "") {
            AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a defending card to destroy");
            AddDecisionQueue("PASSPARAMETER", $currentPlayer, $choices);
            AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
            AddDecisionQueue("SPECIFICCARD", $currentPlayer, "AERONOUGHT", 1);
          }
          if ($from == "PLAY") ++$combatChain[11];
          else ++$chainLinks[$attackInd][9];
        }
      }
      return "";
```

### wild_ride_yellow  — looks-aligned
text: 'When this attacks, draw a card then discard a random card. If a card with 6 or more {p} is discarded this way, this gets **go again**.'
```json
{
  "slug": "wild_ride_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "DISCARD_RANDOM"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DISCARD",
      "conditions": [
        {
          "type": "DISCARDED_CARD_POWER_GTE",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVRPlayAbility()
Draw($currentPlayer);
        $card = DiscardRandom();
        if(ModifiedPowerValue($card, $currentPlayer, "HAND", source:$cardID) >= 6) GiveAttackGoAgain();
        return "";
```

### perch_grapplers  — looks-aligned
text: '**Action** - {r}{r}, destroy Perch Grapplers: Until end of turn, face up arrow cards played from arsenal gain **go again**. **Go again**\n\n**Blade Break**'
```json
{
  "slug": "perch_grapplers",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 2,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "PERCH_GRAPPLERS_ACTIVE"
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "PERCH_GRAPPLERS_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "PERCH_GRAPPLERS_ACTIVE"
        },
        {
          "type": "CARD_IN_ZONE",
          "zone": "arsenal",
          "condition": "FACE_UP",
          "card_type": "arrow"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// DoesCurrentTurnEffectGrantGoAgain()
return true;
// IsCombatEffectPersistent()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// CRUAbilityCost()
case "perch_grapplers": return 2;
// CRUAbilityType()
case "perch_grapplers": return "A";
// CRUAbilityHasGoAgain()
case "red_liner": case "perch_grapplers": return true;
// CRUCombatEffectActive()
case "perch_grapplers": return $CombatChain->AttackCard()->From() == "ARS" && GetClassState($mainPlayer, $CS_ArsenalFacing) == "UP" && CardSubtype($attackID) == "Arrow"; //The card being played from ARS and being an Arrow implies that the card is UP.
// CRUPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### timekeepers_whim_blue  — looks-aligned
text: "Deal 3 arcane damage to target hero.\n\nIf Timekeeper's Whim is played during an opponent's turn, put it on the bottom of its owner's deck."
```json
{
  "slug": "timekeepers_whim_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 3
        },
        {
          "type": "PUT_SELF_BOTTOM_DECK",
          "conditions": [
            {
              "type": "IS_ACTIVE_PLAYER",
              "value": false
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// GoesWhereAfterResolving()
if ($player != $mainPlayer && substr($from, 0, 5) != "THEIR") return "BOTDECK";
      else if ($player != $mainPlayer) return "THEIRBOTDECK";
      else return "GY";
// PlayRequiresTarget()
return 0;
// ActionsThatDoArcaneDamage()
return true;
// EVRPlayAbility()
DealArcane(ArcaneDamage($cardID), 0, "PLAYCARD", $cardID, resolvedTarget: $target);
        return "";
```

### sigil_of_protection_yellow  — looks-aligned
text: '**Ward 3**\n\nAt the beginning of your action phase, destroy Sigil of Protection.'
```json
{
  "slug": "sigil_of_protection_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraBeginningActionPhaseAbilities()
AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", "DESTROY", $auras[$i + 6]);
        break;
// ProcessTrigger()
case $CID_Frailty:
```

### kassai_cintari_sellsword  — looks-aligned
text: 'Your second sword attack each turn costs {r} less.\n\nAt the beginning of your end phase, if you have attacked 2 or more times with weapons this turn, create a Copper token for each weapon attack that hit.'
```json
{
  "slug": "kassai_cintari_sellsword",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "DURING_TURN",
          "player": "self"
        },
        {
          "type": "ATTACK_IS_WEAPON",
          "attack_number": 2
        }
      ],
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ATTACKED_TWICE_WITH_WEAPONS"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Copper",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MainCharacterEndTurnAbilities()
if ($mainCharacter[$i + 1] == 1) break; //Do not process ability if it is disabled (e.g. Humble)
        KassaiEndTurnAbility();
        break;
// CharacterCostModifier()
if (CardSubtype($cardID) == "Sword" && GetClassState($currentPlayer, $CS_NumSwordAttacks) == 1) --$modifier;
        break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
```

### scar_for_a_scar_red  — looks-aligned
text: 'When this is played, if you have less {h} than an opposing hero, it gets **go again**.'
```json
{
  "slug": "scar_for_a_scar_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "conditions": [
        {
          "type": "HEALTH_LT_OPP"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CardPlayTrigger()
AddLayer("TRIGGER", $mainPlayer, $cardID);
        break;
// ProcessTrigger()
if(PlayerHasLessHealth($mainPlayer)) {
          WriteLog(CardLink($parameter, $parameter) . " gains Go Again!");
          GiveAttackGoAgain();
        }
        break;
```

### scour_the_battlescape_blue  — looks-aligned
text: 'You may put a card from your hand on the bottom of your deck. If you do, draw a card.\n\nIf Scour the Battlescape is played from arsenal, it gains **go again**.'
```json
{
  "slug": "scour_the_battlescape_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "PUT_HAND_CARD_BOTTOM"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "conditions": [
        {
          "type": "PLAYED_FROM_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// WTRPlayAbility()
BottomDeck($currentPlayer, true, shouldDraw:true);
        if($from == "ARS") { GiveAttackGoAgain(); $rv = "Gains go again"; }
        return $rv;
```

### merciless_battleaxe  — looks-aligned
text: "**Once per Turn Action** - {r}{r}{r}: **Atttack**\n\nWhen this attacks, if the attack's {p} is greater than twice its base, the attack gets **overpower**."
```json
{
  "slug": "merciless_battleaxe",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 3,
      "effects": [
        {
          "type": "ATTACK"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "SELF_ATTACK_POWER_GTE",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "OVERPOWER"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsOverpowerActive()
return SearchCurrentTurnEffects("merciless_battleaxe", $mainPlayer);
// DYNAbilityCost()
case "merciless_battleaxe": return 3;
// DYNAbilityType()
case "merciless_battleaxe": return "AA";
// DYNCombatEffectActive()
case "merciless_battleaxe": return true;
// DYNPlayAbility()
CacheCombatResult();
      if(IsWeaponGreaterThanTwiceBasePower()) AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### put_em_in_their_place_red  — looks-aligned
text: '**Valda Specialization**\n\n**Crush** - When this deals 4 or more damage to a hero, they discard their hand, then they draw that many cards.'
```json
{
  "slug": "put_em_in_their_place_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CRUSH",
      "conditions": [
        {
          "type": "DURING_TURN",
          "player": "self"
        },
        {
          "type": "ATTACK_CLASS_IN",
          "class": "Hero"
        }
      ],
      "effects": [
        {
          "type": "DISCARD",
          "target": "opponent",
          "amount": "hand_size"
        },
        {
          "type": "DRAW",
          "amount": "hand_size"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessCrushEffect()
$hand = &GetHand($defPlayer);
        $numDraw = count($hand);
        if ($numDraw > 0) {
          DiscardHand($defPlayer);
          Draw($defPlayer, num:$numDraw);
          WriteLog("Player $defPlayer discarded their hand and drew $numDraw cards");
        }
        break;
```

### lightning_greaves  — looks-aligned
text: '**Instant** - {r}, destroy this: Instant cards you play this turn get **go again**.\n\n**Arcane Barrier 1**\n\n**Battleworn**'
```json
{
  "slug": "lightning_greaves",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "LIGHTNING_GREAVES_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LIGHTNING_GREAVES_ACTIVE"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "HAND",
              "card_type": "INSTANT"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// CurrentEffectGrantsInstantGoAgain()
if ($cardID == $currentTurnEffects[$i + 2] && !$usedGreaves) {
            $hasGoAgain = true;
            $usedGreaves = true;
            RemoveCurrentTurnEffect($i);
          }
          break;
// ArcaneBarrierChoices()
++$barrierArray[1];
        $total += 1;
        break;
// ROSPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### haze_shelter_yellow  — looks-aligned
text: "**Ward X**, where X is 3 if you've pitched a blue card this turn, otherwise X is 1."
```json
{
  "slug": "haze_shelter_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "amount": 1
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "PITCHED_BLUE_CARD_THIS_TURN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "amount": 3
        }
      ],
      "conditions": [
        {
          "type": "NOT",
          "condition": {
            "type": "FLAG_SET",
            "flag": "PITCHED_BLUE_CARD_THIS_TURN"
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// WardAmount()
if (SearchPitchForColor($player, 3) > 0) return 3;
      else return 1;
// HasWard()
return true;
```

### second_swing_yellow  — looks-aligned
text: 'If you have attacked with a weapon this turn, your next attack this turn gains +3{p}.\n\n**Go again**'
```json
{
  "slug": "second_swing_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ATTACKED_WITH_WEAPON_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MONEffectPowerModifier()
case "second_swing_yellow": return 3;
// MONCombatEffectActive()
case "second_swing_red": case "second_swing_yellow": case "second_swing_blue": return true;
// MONWarriorPlayAbility()
if(GetClassState($currentPlayer, $CS_AttacksWithWeapon) == 0) return "Does nothing because there were no weapon attacks this turn";
        AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### glistening_steelblade_yellow  — looks-aligned
text: '**Dorinthea Specialization**\n\nYour next Dawnblade attack this turn has **go again**.\n\nWhenever Dawnblade hits a hero this turn, put a +1{p} counter on it.\n\n**Go again**'
```json
{
  "slug": "glistening_steelblade_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DORINTHEA_SPECIALIZATION_ACTIVE"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "Glistening_Steelblade_GoAgain"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_SUBTYPE_IN",
          "subtype": "Dawnblade"
        }
      ],
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "power",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesCurrentTurnEffectGrantGoAgain()
return true;
// DVRPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        AddCurrentTurnEffect($cardID . "-1", $currentPlayer);
        return "";
// DVRCombatEffectActive()
case "glistening_steelblade_yellow": case "glistening_steelblade_yellow-1": return CardNameContains($attackID, "Dawnblade", $mainPlayer, true);
```

### quick_clicks  — looks-aligned
text: "**Action** - Destroy this: Your next attack this turn gets **go again**. Activate this only if you've played a Nimblism this turn. **Go again**"
```json
{
  "slug": "quick_clicks",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "NIMBLISM_PLAYED_THIS_TURN"
        }
      ],
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "QUICK_CLICKS_GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return GetClassState($currentPlayer, $CS_PlayedNimblism) == 0;
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// DoesCurrentTurnEffectGrantGoAgain()
return true;
// SEAPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      break;
```

### stab_wound_blue  — looks-aligned
text: 'When this hits a hero, they lose X{h}, where X is the number of times a dagger has hit this combat chain.'
```json
{
  "slug": "stab_wound_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_TARGET_IS_HERO"
            },
            {
              "type": "IN_COMBAT"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "LOSE_LIFE",
          "amount": {
            "type": "CHAIN_HIT_COUNT_GTE",
            "value": 0
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTHitEffect()
$numDaggerHits = 0;
        $chainLinksCount = count($chainLinks);
        $chainLinkSummaryPieces = ChainLinkSummaryPieces();
        for($i=0; $i<$chainLinksCount; ++$i)
        {
          if(CardSubType($chainLinks[$i][0]) == "Dagger" && $chainLinkSummary[$i*$chainLinkSummaryPieces] > 0) ++$numDaggerHits;
        }
        $numDaggerHits += $combatChainState[$CCS_FlickedDamage];
        if($numDaggerHits > 0) WriteLog("Player " . $defPlayer . " lost " . $numDaggerHits . " life from " . CardLink("stab_wound_blue", "stab_wound_blue"));
        LoseHealth($numDaggerHits, $defPlayer);
        break;
```

### fatigue_shot_red  — looks-aligned
text: 'When Fatigue Shot hits a hero, the base {p} of the first attack action card they play during their next turn is halved, rounded up.'
```json
{
  "slug": "fatigue_shot_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "FATIGUE_SHOT_EFFECT_ACTIVE",
          "target": "opponent"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// LinkBasePower()
$basePower = ceil($basePower / 2);
          break;
// EVRCombatEffectActive()
case "fatigue_shot_red": case "fatigue_shot_yellow": case "fatigue_shot_blue": return CardType($attackID) == "AA";
// EVRHitEffect()
if(IsHeroAttackTarget()) AddNextTurnEffect($cardID, $defPlayer);
        break;
```

### murkmire_grapnel_red  — looks-aligned
text: "If Murkmire Grapnel has an aim counter, it has +1{p}.\n\nDamage that would be dealt by Murkmire Grapnel can't be prevented."
```json
{
  "slug": "murkmire_grapnel_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "COUNTER_GTE",
          "counter": "aim",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "ward_type": "damage_prevention"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTEffectPowerModifier()
case "murkmire_grapnel_red": case "murkmire_grapnel_yellow": case "murkmire_grapnel_blue": return 1;
// OUTCombatEffectActive()
case "murkmire_grapnel_red": case "murkmire_grapnel_yellow": case "murkmire_grapnel_blue": return true;
// OUTPlayAbility()
if(HasAimCounter()) {
          AddCurrentTurnEffect($cardID, $currentPlayer);
          $rv = "Gets +1.";
        }
        return $rv;
```

### sirens_of_safe_harbor_red  — looks-aligned
text: 'When this is put into your graveyard from anywhere, gain 1{h}.'
```json
{
  "slug": "sirens_of_safe_harbor_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "conditions": [
        {
          "type": "REF_EXISTS",
          "ref": "GRAVEYARD"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "HEALTH",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
GainHealth(1, $player);
        break;
// AddGraveyard()
if ($cardController == "" || $player == $cardController) // only if it goes to *your* graveyard
        AddLayer("TRIGGER", $player, $cardID);
      break;
```

### twelve_petal_kasaya  — looks-aligned
text: 'Whenever you **transcend**, you may gain {r}.\n\n**Instant** - {c}{c}{c}, destroy this: Create a Zen State token.\n\n**Blade Break**'
```json
{
  "slug": "twelve_petal_kasaya",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BECOME",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "TRANSCEND"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 3,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Zen State"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CardCareAboutChiPitch()
return true;
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// MSTPlayAbility()
PlayAura("zen_state", $currentPlayer); //Zen Token
      return "";
```

### flying_kick_yellow  — looks-aligned
text: 'If this was played as chain link 3 or higher, it gets +2{p}.'
```json
{
  "slug": "flying_kick_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "conditions": [
        {
          "type": "CHAIN_HIT_COUNT_GTE",
          "amount": 3
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += NumChainLinks() >= 3 ? 2 : 0;
        break;
```

### hundred_winds_blue  — looks-aligned
text: '**Combo** - If Hundred Winds was the last attack this combat chain, this attack gains +1{p} for each other card named Hundred Winds you control on this combat chain.\n\n**Go again**'
```json
{
  "slug": "hundred_winds_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "HUNDRED_WINDS_LAST_ATTACK"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "HUNDRED_WINDS"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Hundred Winds") return true;
        break;
// PowerModifier()
$power += (ComboActive() ? NumChainLinksWithName("Hundred Winds") - 1 : 0);
        break;
```

### steadfast_red  — looks-aligned
text: 'Prevent the next 6 damage that would be dealt to your hero this turn by a source of your choice.'
```json
{
  "slug": "steadfast_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "STEADFAST_ACTIVE"
        },
        {
          "type": "PUT_COUNTER",
          "counter": "STEADFAST",
          "amount": 6
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CurrentTurnEffectUses()
return 6;
// CurrentTurnEffectDamagePreventionAmount()
return $source == $currentTurnEffects[$index + 2] && $preventable ? $currentTurnEffects[$index + 3] : 0;
// CurrentEffectDamagePrevention()
if ($source == $currentTurnEffects[$index + 2]) {
        if ($preventable) {
          $origDamage = $damage;
          $preventedDamage += $currentTurnEffects[$index + 3];
          if ($preventedDamage > $damage) $preventedDamage = $damage;
          $currentTurnEffects[$index + 3] -= $origDamage;
        }
        if ($currentTurnEffects[$index + 3] <= 0) $remove = true;
        $multiAttack = match($source) {
          "explosive_growth_red", "explosive_growth_yellow", "explosive_growth_blue", "art_of_the_dragon_fire_red" => true,
          "vexing_malice_red", "vexing_malice_yellow", "vexing_malice_blue", "reckless_stampede_red" => true,
          "runic_fellingsong_red", "runic_fellingsong_yellow", "runic_fellingsong_blue" => true,
          "arcanic_shockwave_red", "arcanic_shockwave_yellow", "arcanic_shockwave_blue" => true,
          "arcanic_crackle_red", "arcanic_crackle_yellow", "arcanic_crackle_blue" => true,
          default => false,
        };
        if (SubtypeContains($source, "Dagger")) $multiAttack = true;
        if (TypeContains($source, "AA") && !$multiAttack) $remove = true; //To be removed when coded with Unique ID instead of cardID name as $source
        if ($source == "spectral_shield" || $source == "runechant" || $source == "aether_ashwing") $remove = true; //To be removed when coded with Unique ID instead of cardID name as $source
        if ($remove) RemoveCurrentTurnEffect($index);
      }
      break;
// EVRPlayAbility()
AddDecisionQueue("FINDINDICES", $currentPlayer, "DAMAGEPREVENTIONTARGET");
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a damage source for " . CardLink($cardID, $cardID));
        AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);
        AddDecisionQueue("MZOP", $currentPlayer, "GETCARDID", "-", 1);
        AddDecisionQueue("PREPENDLASTRESULT", $currentPlayer, "{$cardID}!{$from}!", 1);
        AddDecisionQueue("ADDCURRENTTURNEFFECT", $currentPlayer, "<-", 1);
        return "";
```

### swift_shot_red  — looks-aligned
text: 'When this is put face-up into your arsenal, it gets **go again** this turn.'
```json
{
  "slug": "swift_shot_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "arsenal",
          "card": "swift_shot_red"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddArsenal()
AddCurrentTurnEffect($cardID, $player, "", $uniqueID);
        break;
// DoesCurrentTurnEffectGrantGoAgain()
return true;
```

### hundred_winds_red  — looks-aligned
text: '**Combo** - If Hundred Winds was the last attack this combat chain, this attack gains +1{p} for each other card named Hundred Winds you control on this combat chain.\n\n**Go again**'
```json
{
  "slug": "hundred_winds_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "HUNDRED_WINDS_LAST_ATTACK"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "combat_chain",
              "card_name": "hundred_winds_red"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Hundred Winds") return true;
        break;
// PowerModifier()
$power += (ComboActive() ? NumChainLinksWithName("Hundred Winds") - 1 : 0);
        break;
```

### runeblood_incantation_yellow  — looks-aligned
text: '**Go again**\n\nRuneblood Incantation enters the arena with 2 verse counters on it.\n\nAt the beginning of your action phase, remove a verse counter from Runeblood Incantation. If you do create a Runechant token. Otherwise, destroy Runeblood Incantation.'
```json
{
  "slug": "runeblood_incantation_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter_type": "verse",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "REMOVE_COUNTER",
          "counter_type": "verse",
          "amount": 1
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "IS_ACTIVE_PLAYER"
        },
        {
          "type": "NOT",
          "condition": {
            "type": "COUNTER_GTE",
            "counter_type": "verse",
            "amount": 1
          }
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraPlayCounters()
return 2;
// AuraBeginningActionPhaseAbilities()
AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", "DESTROY", $auras[$i + 6]);
        break;
// ProcessTrigger()
$index = SearchAurasForUniqueID($uniqueID, $player);
        if ($index == -1) break;
        $auras = &GetAuras($player);
        if ($auras[$index + 2] == 0) DestroyAuraUniqueID($player, $uniqueID);
        else {
          --$auras[$index + 2];
          PlayAura("runechant", $player);
        }
        break;
```

### regain_composure_blue  — looks-aligned
text: 'Your next attack this turn gets +1{p} and "When this hits, {u} your hero."\n\n**Go again**'
```json
{
  "slug": "regain_composure_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "NEXT_ATTACK_MODIFIED"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_HIT",
          "effects": [
            {
              "type": "WARD",
              "target": "hero"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddCardEffectHitTrigger()
AddLayer("TRIGGER", $mainPlayer, $parameter, $cardID, "EFFECTHITEFFECT", $source);
      break;
// EffectHitEffect()
$inds = GetTapped($mainPlayer, "MYCHAR", "type=C");
      if(empty($inds)) return 1;
      AddDecisionQueue("SETDQCONTEXT", $mainPlayer, "You may untap your hero");
      AddDecisionQueue("CHOOSEMULTIZONE", $mainPlayer, $inds);
      AddDecisionQueue("MZTAP", $mainPlayer, "0", 1);
      return 1;
// SEAPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      break;
```

### for_the_realm_red  — looks-aligned
text: 'When this attacks a **marked** hero, create a Fealty token.'
```json
{
  "slug": "for_the_realm_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "OPPONENT_IS_MARKED"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Fealty"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HNTPlayAbility()
if(IsHeroAttackTarget() && CheckMarked($otherPlayer)) {
        PlayAura("fealty", $currentPlayer);
      }
      break;
```

### haunting_rendition_red  — looks-aligned
text: '**Instant** - Discard this: Prevent the next 2 damage that would be dealt to you this turn. The first time you prevent damage this way, create a Runechant token.'
```json
{
  "slug": "haunting_rendition_red",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "HAUNTING_RENDITION_ACTIVE"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "HAUNTING_RENDITION_ACTIVE"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CardCost()
if (GetResolvedAbilityType($cardID, "HAND") == "I" && $from == "HAND") return 0;
      return -1;
// GetAbilityNames()
if ($allNames) return "Block,Ability";
      if ($instantRestricted) return "-";
      return "Block,Ability";
// ProcessAbility()
AddCurrentTurnEffect($parameter."-2", $player);
      break;
// CanPlayAsInstant()
return $from == "HAND";
// CurrentTurnEffectDamagePreventionAmount()
if (!$preventable) return 0;
      return intval($effects[1]);
// CurrentEffectDamagePrevention()
if ($preventable) {
        $damageToPrevent = min($damage, $effects[1]);
        $preventedDamage += $damageToPrevent;
        if($effects[1] == 2) PlayAura("runechant", $player); 
        $effects[1] -= $damageToPrevent;
        $currentTurnEffects[$index] = $effects[0] . "-" . $effects[1];
      }
      if ($effects[1] <= 0 || !$preventable) RemoveCurrentTurnEffect($index);
      break;
// AddPrePitchDecisionQueue()
AddDecisionQueue("SETABILITYTYPEABILITY", $currentPlayer, $cardID);
      AddDecisionQueue("PASSPARAMETER", $currentPlayer, $cardID, 1);
      AddDecisionQueue("DISCARDCARD", $currentPlayer, "HAND-$cardID", 1);
      AddDecisionQueue("CONVERTLAYERTOABILITY", $currentPlayer, $cardID, 1);
      break;
```

### arctic_incarceration_blue  — looks-aligned
text: "Create a Frostbite token under target hero's control."
```json
{
  "slug": "arctic_incarceration_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_name": "Frostbite",
          "controller": "target_hero"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// UPRTalentPlayAbility()
$numFrostbites = match($cardID) { "arctic_incarceration_red" => 3, "arctic_incarceration_yellow" => 2, default => 1 };
        PlayAura("frostbite", $currentPlayer == 1 ? 2 : 1, $numFrostbites, effectController: $currentPlayer);
        return "";
```

### the_weakest_link_red  — looks-aligned
text: 'When this hits a hero, look at their hand and choose a card without base {d}. If you do, they discard it and you draw a card.'
```json
{
  "slug": "the_weakest_link_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_TARGET_IS_HERO"
            },
            {
              "type": "NOT",
              "condition": {
                "type": "ATTACK_HAS_KEYWORD",
                "keyword": "BASE_DEFENSE"
              }
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "LOOK_AT",
          "target": "OPPONENT_HAND"
        },
        {
          "type": "SELECT_FROM_REF",
          "ref": "OPPONENT_HAND",
          "conditions": [
            {
              "type": "NOT",
              "condition": {
                "type": "CARD_IN_ZONE",
                "zone": "OPPONENT_HAND",
                "conditions": [
                  {
                    "type": "HAS_KEYWORD",
                    "keyword": "BASE_DEFENSE"
                  }
                ]
              }
            }
          ],
          "effects": [
            {
              "type": "DISCARD",
              "target": "SELECTED_CARD"
            },
            {
              "type": "DRAW",
              "amount": 1
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTHitEffect()
LookAtHand($defPlayer);
      AddDecisionQueue("BLOCKLESS0HAND", $defPlayer, "THEIRHAND:maxDef=-1");
      AddDecisionQueue("SETDQCONTEXT", $mainPlayer, "Choose which card you want your opponent to discard", 1);
      AddDecisionQueue("CHOOSEMULTIZONE", $mainPlayer, "<-", 1);
      AddDecisionQueue("MZDISCARD", $mainPlayer, "HAND," . $mainPlayer, 1);
      AddDecisionQueue("MZREMOVE", $mainPlayer, "-", 1);
      AddDecisionQueue("DRAW", $mainPlayer, "-", 1);
      break;
```

### fang  — looks-aligned
text: 'Whenever you hit a **marked** hero, create a Fealty token.\n\nIf you control 3 or more Fealty tokens, dagger attacks cost you {r} less to activate.'
```json
{
  "slug": "fang",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "OPPONENT_IS_MARKED"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Fealty"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Fealty",
          "amount": 3
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA",
          "mod": "subtract",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessMainCharacterHitEffect()
PlayAura("fealty", $player);
      break;
// MainCharacterHitTrigger()
if ($mainCharacter[$i+1] < 3) {
          if ((IsHeroAttackTarget() || $targetPlayer == $defPlayer) && CheckMarked($targetPlayer)) {
            AddLayer("TRIGGER", $mainPlayer, $characterID,$damageSource, "MAINCHARHITEFFECT");
          }
        }
        break;
// CharacterCostModifier()
if (SubtypeContains($cardID, "Dagger") && substr_count(SearchAurasForCardName("Fealty", $currentPlayer), ",") >= 2) --$modifier;
        break;
```

### blood_tribute_red  — looks-aligned
text: '**Opt 3**, then banish the top card of your deck.'
```json
{
  "slug": "blood_tribute_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "OPT",
          "amount": 3
        },
        {
          "type": "BANISH",
          "target": "top_deck"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MONTalentPlayAbility()
switch ($cardID) {
// MONTalentPlayAbility()
$amount = 3;
          break;
```

### tuffnut  — looks-aligned
text: '**Instant** - {t}: Pitch the top card of your deck. If it has 6 or more {p}, **the crowd cheers** you.\n\nWhenever the crowd cheers you, create a Toughness token.'
```json
{
  "slug": "tuffnut",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "PITCH",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "CROWD_CHEERS"
        }
      ],
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "ref": "TOP_DECK",
          "pitch_power_gte": 6
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BECOME",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "TOUGHNESS"
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CROWD_CHEERS"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return CheckTapped("MYCHAR-$index", $currentPlayer);
// ProcessTrigger()
PlayAura("toughness", $player, isToken:true, effectController:$player, effectSource:$parameter);
        break;
// EquipPayAdditionalCosts()
Tap("MYCHAR-$cardIndex", $currentPlayer);
      break;
// SUPPlayAbility()
$top = PitchTopCard($currentPlayer);
      if (ModifiedPowerValue($top, $currentPlayer, "DECK") >= 6) {
        Cheer($currentPlayer);
      }
      break;
// Cheer()
AddLayer("TRIGGER", $player, $char[0]);
          break;
```

### snow_under_yellow  — looks-aligned
text: '**Ice Fusion**\n\nIf Snow Under was **fused**, it gains "If this hits a hero, create a Frostbite token under their control."'
```json
{
  "slug": "snow_under_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SNOW_UNDER_FUSED"
        },
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Frostbite",
          "controller": "opponent"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddEffectHitTrigger()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// EffectHitEffect()
if (IsHeroAttackTarget()) PlayAura("frostbite", $defPlayer, effectController: $mainPlayer);
      break;
// FuseAbility()
case "snow_under_red": case "snow_under_yellow": case "snow_under_blue": AddCurrentTurnEffect($cardID, $player); break;
// HasFusion()
case "snow_under_red": case "snow_under_yellow": case "snow_under_blue": return "ICE";
// ELECombatEffectActive()
case "snow_under_red": case "snow_under_yellow": case "snow_under_blue": return true;
```

### plunder_the_poor_yellow  — looks-aligned
text: "**Contract** - You are contracted to banish opponents' cards with cost 1 or less. Whenever you complete this contract, create a Silver token.\n\nWhen this hits a hero, banish the top card of their deck."
```json
{
  "slug": "plunder_the_poor_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": "OPPONENT_TOP_DECK"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNHitEffect()
if(IsHeroAttackTarget()) {
        $deck = new Deck($defPlayer);
        if($deck->Empty()) { WriteLog("The opponent deck is already... depleted."); break; }
        $deck->BanishTop(banishedBy:$cardID);
      }
      break;
// ContractType()
case "plunder_the_poor_red": case "plunder_the_poor_yellow": case "plunder_the_poor_blue": return "COST1ORLESS";
// ContractCompleted()
$EffectContext = $cardID;
      PutItemIntoPlayForPlayer("silver", $player);
      break;
```

### rise_up_red  — looks-aligned
text: '**Dromai or Fai Specialization**\n\n**Rupture** - If Rise Up is played as chain link 4 or higher, it has **dominate** and +X{p}, where X is twice the number of Phoenix Flames you control.'
```json
{
  "slug": "rise_up_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "conditions": [
        {
          "type": "OR",
          "conditions": [
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "Phoenix Flames"
            },
            {
              "type": "NOT",
              "condition": {
                "type": "CONTROLS_TOKEN_TYPE",
                "token_type": "Phoenix Flames"
              }
            }
          ]
        },
        {
          "type": "AND",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "CHAIN_LINK_4_OR_HIGHER"
            },
            {
              "type": "OR",
              "conditions": [
                {
                  "type": "HAS_KEYWORD",
                  "keyword": "Dromai"
                },
                {
                  "type": "HAS_KEYWORD",
                  "keyword": "Fai"
                }
              ]
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "DOMINATE"
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": {
            "type": "MULTIPLY",
            "value": 2,
            "multiplier": {
              "type": "COUNT_TOKENS",
              "token_type": "Phoenix Flames"
            }
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesEffectGrantsDominate()
return true;
// UPREffectPowerModifier()
case "rise_up_red": return NumChainLinksWithName("Phoenix Flame")*2;
// UPRCombatEffectActive()
case "rise_up_red": return true;
// UPRTalentPlayAbility()
if(RuptureActive()) AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### hocus_pocus_yellow  — looks-aligned
text: 'When this attacks, create a Runechant token.'
```json
{
  "slug": "hocus_pocus_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ROSPlayAbility()
PlayAura("runechant", $currentPlayer);
      return "";
```

### crash_down_the_gates_yellow  — looks-aligned
text: 'When this attacks a hero, they reveal the top card of their deck. If this has {p} greater than the revealed card, this gets +2{p}.\n\nWhen this hits a hero, destroy the top card of their deck.'
```json
{
  "slug": "crash_down_the_gates_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "REVEAL_TOP_DECK",
          "target": "opponent"
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2,
          "conditions": [
            {
              "type": "SELF_ATTACK_POWER_GTE",
              "amount": "REVEALED_CARD_POWER"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "target": "opponent_top_deck"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SEAPlayAbility()
if (IsHeroAttackTarget()) {
        $totalPower = 0;
        $totalDefense = 0;
        EvaluateCombatChain($totalPower, $totalDefense);
        $deck = new Deck($defPlayer);
        $deckPower = ($deck->Reveal()) ? ModifiedPowerValue($deck->Top(), $defPlayer, "DECK", source: $cardID) : -1;
        if ($totalPower > $deckPower) {
          WriteLog("Your power exceeds the gates!");
          AddCurrentTurnEffect($cardID, $currentPlayer);
        }
      }
      break;
// SEAHitEffect()
DestroyTopCard($defPlayer);
      break;
```

### gravy_bones  — looks-aligned
text: '**Instant** - {t}, destroy a Gold you control: Draw a card, then discard a card.\n\nIf a blue card has been put into your graveyard this turn, you may play cards with watery grave from your graveyard.'
```json
{
  "slug": "gravy_bones",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "controlled_gold"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "DISCARD",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BLUE_CARD_GRAVEYARD_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "PLAY_WATERY_GRAVE_FROM_GRAVEYARD"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if (CheckTapped("MYCHAR-$index", $currentPlayer)) return true;
      return CountItemByName("Gold", $currentPlayer) == 0;
// EquipPayAdditionalCosts()
QueueDestroyGold($currentPlayer, isMandatory:true, showContext:true, itemFallback:false, subsequent:0);
      Tap("MYCHAR-$cardIndex", $currentPlayer);
      break;
// SEAPlayAbility()
Draw($currentPlayer, effectSource:$cardID);
      PummelHit($currentPlayer);
      break;
```

### bonds_of_attraction_red  — looks-aligned
text: '**Stealth**\n\nWhen this hits a hero, banish the top card of their deck, then banish a card from their graveyard.\n\nWhenever this banishes a card and this has banished another card with the same color, gain 1{h}.'
```json
{
  "slug": "bonds_of_attraction_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": "OPPONENT_TOP_DECK"
        },
        {
          "type": "BANISH",
          "target": "OPPONENT_GRAVEYARD"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BANISH",
      "conditions": [
        {
          "type": "REF_EXISTS",
          "ref": "BANISHED_CARDS"
        },
        {
          "type": "AND",
          "conditions": [
            {
              "type": "REF_PITCH_IS",
              "ref": "BANISHED_CARDS",
              "pitch": "SAME_COLOR"
            },
            {
              "type": "REF_PITCH_IS",
              "ref": "BANISHED_CARDS",
              "pitch": "SAME_COLOR"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "HEALTH_POINTS",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTHitEffect()
if (IsHeroAttackTarget()) {
        $deck->BanishTop("Source-" . $CombatChain->AttackCard()->ID(), banishedBy: $attackCard);
        if ($discard->NumCards() > 0) MZMoveCard($mainPlayer, "THEIRDISCARD", "THEIRBANISH,GY,Source-$attackCard,$attackCard,$mainPlayer", silent: true);
      }
      break;
```

### chart_a_course_yellow  — looks-aligned
text: 'Your second attack this turn gets +3{p}.\n\nYou may put a gold counter on Treasure Island.\n\n**Go again**'
```json
{
  "slug": "chart_a_course_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "DURING_TURN",
          "turn": "second"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "gold",
          "target": "Treasure Island"
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SEAPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      $treasureID = SearchLandmarksForID("treasure_island");
      if ($treasureID != -1) {
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Do you want to put a gold counter on for " . CardLink("treasure_island", "treasure_island") . "?");
        AddDecisionQueue("YESNO", $currentPlayer, "-");
        AddDecisionQueue("NOPASS", $currentPlayer, "-");
        AddDecisionQueue("ADDCOUNTERLANDMARK", $currentPlayer, $treasureID, 1);
      }
      break;
```

### courageous_steelhand_red  — looks-aligned
text: "If you've **charged** this turn, target attack gains +3{p}."
```json
{
  "slug": "courageous_steelhand_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CHARGED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ReactionRequirementsMet()
case "courageous_steelhand_red": case "courageous_steelhand_yellow": case "courageous_steelhand_blue": return true;
```

### boltn_boots  — looks-aligned
text: '**Attack Reaction** - {r}, destroy this: Target arrow attack with {p} greater than its base gets **go again**.\n\n**Battleworn**'
```json
{
  "slug": "boltn_boots",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "activation_cost": 1,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ],
      "conditions": [
        {
          "type": "ATTACK_TYPE_IN",
          "attack_type": "ARROW"
        },
        {
          "type": "ATTACK_POWER_GT_BASE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
```

### overblast_red  — looks-aligned
text: 'Overblast gains +X{p}, where X is the number of times you have **boosted** this combat chain.'
```json
{
  "slug": "overblast_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "IN_COMBAT"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": "BOOST_COUNT"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += $combatChainState[$CCS_NumBoosted];
        break;
```

### jack_be_quick_red  — looks-aligned
text: 'When this attacks, you may banish a Nimblism from your graveyard. If you do, this gets +1{p} and **go again**.\n\nWhen this hits a hero, {u} an ally they control, then steal it until the end of this action phase.'
```json
{
  "slug": "jack_be_quick_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "BANISH",
          "target": "Nimblism",
          "zone": "GRAVEYARD",
          "optional": true
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "NIMBLISM_BANISHED"
            }
          ]
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "NIMBLISM_BANISHED"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "LOOK_AT",
          "target": "ALLY",
          "controller": "OPPONENT"
        },
        {
          "type": "STEAL_AURA_TOKEN",
          "target": "ALLY",
          "controller": "OPPONENT",
          "duration": "END_OF_ACTION_PHASE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SEAPlayAbility()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYDISCARD:isSameName=nimblism_red");
      AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("MZADDZONE", $currentPlayer, "MYBANISH,GY,-", 1);
      AddDecisionQueue("MZREMOVE", $currentPlayer, "-", 1);
      AddDecisionQueue("ADDCURRENTTURNEFFECT", $currentPlayer, $cardID, 1);
      AddDecisionQueue("OP", $currentPlayer, "GIVEATTACKGOAGAIN", 1);
      break;
// SEAHitEffect()
AddDecisionQueue("MULTIZONEINDICES", $mainPlayer, "THEIRALLY");
      AddDecisionQueue("CHOOSEMULTIZONE", $mainPlayer, "<-", 1);
      AddDecisionQueue("MZTAP", $mainPlayer, "0", 1);
      AddDecisionQueue("MZOP", $mainPlayer, "GAINCONTROL,Temporary", 1);
      break;
```

### starting_point  — looks-aligned
text: "**Attack Reaction** - Destroy this: Target attack gets **go again**. Activate this only if you've played a card or activated an ability this reaction step."
```json
{
  "slug": "starting_point",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ACTION_OR_ABILITY_PLAYED_THIS_REACTION_STEP"
        }
      ],
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return $combatChainState[$CCS_NumUsedInReactions] == 0;
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// HNTPlayAbility()
GiveAttackGoAgain();
      break;
```

### great_library_of_solana  — looks-aligned
text: '**Legendary**\n\nAt the beginning of each end phase, if a hero has 2 or more cards with yellow color strips in their pitch zone, they gain +1{i} until end of turn.\n\n**Action** - Discard 2 cards with yellow color strips: Destroy Great Library of Solana. Any hero may activate this ability. **Go again**'
```json
{
  "slug": "great_library_of_solana",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "pitch",
          "color": "yellow",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "INTELLECT",
          "amount": 1,
          "duration": "end_of_turn"
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "cost": [
        {
          "type": "DISCARD_CARD",
          "color": "yellow",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "DESTROY_REF",
          "target": "self"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return $from == "PLAY" && SearchCount(SearchHand($player, "", "", -1, -1, "", "", false, false, 2)) < 2;
// CurrentEffectIntellectModifier()
if($remove){// Handle transformations (Blasmophet, Dishonor, etc) restarting Intellect
            RemoveCurrentTurnEffect($i);
            break;
          }
          $intellectModifier += 1;
          break;
// LandmarkBeginEndPhaseAbilities()
if (SearchPitchForColor($mainPlayer, 2) >= 2) {
          AddCurrentTurnEffect("great_library_of_solana", $mainPlayer);
        }
        break;
// PayAbilityAdditionalCosts()
for ($i = 0; $i < 2; ++$i) {
        AddDecisionQueue("FINDINDICES", $currentPlayer, "HANDPITCH,2");
        AddDecisionQueue("CHOOSEHANDCANCEL", $currentPlayer, "<-", 1);
        AddDecisionQueue("MULTIREMOVEHAND", $currentPlayer, "-", 1);
        AddDecisionQueue("DISCARDCARD", $currentPlayer, "HAND-" . $currentPlayer, 1);
      }
      break;
// MONAbilityCost()
case "great_library_of_solana": return 0;
// MONAbilityType()
case "great_library_of_solana": return "A";
// MONAbilityHasGoAgain()
case "great_library_of_solana": return true;
// MONTalentPlayAbility()
if($from == "PLAY") DestroyLandmark(GetClassState($currentPlayer, $CS_PlayIndex));
        return "";
```

### phoenix_form_red  — looks-aligned
text: 'If you control 1 or more Phoenix Flames, Phoenix Form has **go again**. If you control 2 or more, it has +2{p}. If you control 3 or more, it has "When this hits a hero, draw 3 cards."'
```json
{
  "slug": "phoenix_form_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Phoenix Flames",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Phoenix Flames",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Phoenix Flames",
          "amount": 3
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "ability_type": "TRIGGERED",
            "trigger": "ON_HIT",
            "conditions": [
              {
                "type": "ATTACK_TARGET_IS_HERO"
              }
            ],
            "effects": [
              {
                "type": "DRAW",
                "amount": 3
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddOnHitTrigger()
if(IsHeroAttackTarget() && NumChainLinksWithName("Phoenix Flame") >= 3) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "ONHITEFFECT");
        return true;
      }
      return false;
// PowerModifier()
$power += (NumChainLinksWithName("Phoenix Flame") >= 2 ? 2 : 0);
        break;
// DoesAttackHaveGoAgain()
return NumChainLinksWithName("Phoenix Flame") >= 1;
// UPRNinjaHitEffect()
Draw($mainPlayer, num:3);
        break;
```

### three_of_a_kind_red  — looks-aligned
text: 'Draw 3 cards. Until end of turn, you may only play cards from arsenal.\n\n**Go again**'
```json
{
  "slug": "three_of_a_kind_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DRAW",
          "amount": 3
        },
        {
          "type": "SET_FLAG",
          "flag": "ONLY_PLAY_FROM_ARSENAL"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ONLY_PLAY_FROM_ARSENAL"
        },
        {
          "type": "DURING_TURN"
        }
      ],
      "effects": [
        {
          "type": "RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCRangerPlayAbility()
Draw($currentPlayer, num:3);
        AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### shock_frock  — looks-aligned
text: "**Action** - Destroy this: Gain {r}. Activate this only if you've played a Lightning card this turn. **Go again**\n\n**Battleworn**"
```json
{
  "slug": "shock_frock",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LIGHTNING_PLAYED_THIS_TURN"
        }
      ],
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return GetClassState($player, $CS_NumLightningPlayed) == 0;
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// ASTPlayAbility()
GainResources($currentPlayer, 1);
      return "";
```

### heart_of_vengeance  — looks-aligned
text: '**Instant** - Destroy this: Your next attack this turn that targets Arakni costs {r} less to play or activate.\n\n**Blade Break**'
```json
{
  "slug": "heart_of_vengeance",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "HEART_OF_VENGEANCE_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "HEART_OF_VENGEANCE_ACTIVE"
        },
        {
          "type": "ATTACK_TARGET_IS_HERO",
          "hero": "Arakni"
        }
      ],
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "resource": "RESOURCE_POINTS",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// CurrentEffectCostModifiers()
$otherChar = &GetPlayerCharacter(player: $otherPlayer);
          $resolvedType = GetResolvedAbilityType($cardID, $from);
          $isAttack = $resolvedType == "AA" || ($resolvedType == "" && $cardType == "AA");
          if (CardNameContains($otherChar[0], "Arakni") && $isAttack) {
            $costModifier -= 1;
            $remove = true;
          }
          break;
// HNTPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      break;
```

### vow_of_vengeance  — looks-aligned
text: '**Attack Reaction** - Destroy this: **Mark** target Arakni.\n\n**Blade Break**'
```json
{
  "slug": "vow_of_vengeance",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "MARK",
          "target": "target Arakni"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
$otherChar = &GetPlayerCharacter($otherPlayer);
      if (!CardNameContains($otherChar[0], "Arakni")) return true;
      break;
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// HNTPlayAbility()
MarkHero($otherPlayer);
      break;
```

### emeritus_scolding_yellow  — looks-aligned
text: 'Deal 3 arcane damage to target hero. If Emeritus Scolding is played during an opponents turn, instead deal 5 arcane damage to them.'
```json
{
  "slug": "emeritus_scolding_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER",
          "value": false
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 5
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayRequiresTarget()
return 0;
// ActionsThatDoArcaneDamage()
return true;
// EVRPlayAbility()
$oppTurn = $currentPlayer != $mainPlayer;
        $damage = match($cardID) {
          "emeritus_scolding_red" => $oppTurn ? 6 : 4,
          "emeritus_scolding_yellow" => $oppTurn ? 5 : 3,
          default => $oppTurn ? 4 : 2,
        };
        DealArcane($damage, 0, "PLAYCARD", $cardID, resolvedTarget: $target);
        return "";
```

### cut_down_to_size_yellow  — looks-aligned
text: 'When this hits a hero, if they have 4 or more cards in hand, they discard a card.'
```json
{
  "slug": "cut_down_to_size_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "HAND",
          "amount": 4,
          "player": "OPPONENT"
        }
      ],
      "effects": [
        {
          "type": "DISCARD",
          "target": "OPPONENT",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTHitEffect()
if(IsHeroAttackTarget())
        {
          $hand = &GetHand($defPlayer);
          if(count($hand) >= 4) PummelHit($defPlayer);
        }
        break;
```

### dampen_yellow  — looks-aligned
text: 'Deal 3 arcane damage to any target.\n\nPrevent the next X arcane damage that would be dealt to your hero this turn, where X is the damage dealt by Dampen.'
```json
{
  "slug": "dampen_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 3,
          "target": "any"
        },
        {
          "type": "SET_FLAG",
          "flag": "DAMPEN_DAMAGE_PREVENTED",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DAMPEN_DAMAGE_PREVENTED"
        },
        {
          "type": "DURING_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 3,
          "target": "hero"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayRequiresTarget()
return 2;
// ActionsThatDoArcaneDamage()
return true;
// UPRWizardPlayAbility()
$damage = match($cardID) { "dampen_red" => 4, "dampen_yellow" => 3, default => 2 };
        DealArcane($damage, 2, "PLAYCARD", $cardID, false, $currentPlayer, resolvedTarget: $target);
        AddDecisionQueue("SETCLASSSTATE", $currentPlayer, $CS_ArcaneDamagePrevention, 1);
        return "";
```

### swiftwater_sloop_blue  — looks-aligned
text: 'High Tide - If there are 2 or more blue cards in your pitch zone, this gets **go again**.'
```json
{
  "slug": "swiftwater_sloop_blue",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "color": "blue",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
return true;
```

### bramble_spark_blue  — looks-aligned
text: '**Earth Fusion**\n\nThe next attack action card you play this turn gains "When you attack with this, deal 1 arcane damage to target hero."\n\nIf Bramble Spark was **fused**, the next attack action card you play this turn gains +1{p}.\n\n**Go again**'
```json
{
  "slug": "bramble_spark_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "BRAMBLE_SPARK_FUSED"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BRAMBLE_SPARK_FUSED"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_ATTACK",
          "effects": [
            {
              "type": "DEAL_ARCANE",
              "amount": 1
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
DealArcane(1, 0, "PLAYCARD", $CombatChain->AttackCard()->ID(), true, resolvedTarget:$target);
        break;
// OnAttackEffects()
if ($attackType == "AA") {
            SetArcaneTarget($mainPlayer, $currentTurnEffects[$i], 0, 1);
            AddDecisionQueue("SHOWSELECTEDTARGET", $mainPlayer, "-", 1);
            AddDecisionQueue("ADDTRIGGER", $mainPlayer, $currentTurnEffects[$i], 1);
            $remove = true;
          }
          break;
// FuseAbility()
case "bramble_spark_red": case "bramble_spark_yellow": case "bramble_spark_blue": AddCurrentTurnEffect($cardID . "-FUSE", $player); break;
// HasFusion()
case "bramble_spark_red": case "bramble_spark_yellow": case "bramble_spark_blue": return "EARTH";
// ELERunebladePlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### scout_the_periphery_red  — looks-aligned
text: "Look at the top card of target hero's deck.\n\nThe next attack action card you play from arsenal this turn gains +3{p}.\n\n**Go again**"
```json
{
  "slug": "scout_the_periphery_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "LOOK_AT",
          "target": "hero_deck"
        },
        {
          "type": "SET_FLAG",
          "flag": "SCOUT_THE_PERIPHERY_ACTIVE"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SCOUT_THE_PERIPHERY_ACTIVE"
        },
        {
          "type": "DURING_TURN"
        },
        {
          "type": "CARD_IN_ZONE",
          "zone": "arsenal",
          "card_type": "attack_action"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTEffectPowerModifier()
case "scout_the_periphery_red": return 3;
// OUTCombatEffectActive()
case "scout_the_periphery_red": case "scout_the_periphery_yellow": case "scout_the_periphery_blue": return CardType($attackID) == "AA" && AttackPlayedFrom() == "ARS";
// OUTPlayAbility()
LookAtTopCard($currentPlayer, $cardID);
        AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### clash_of_mountains_red  — looks-aligned
text: 'When this defends a Guardian attack, **clash** with the attacking hero. The winner creates a Seismic Surge token.'
```json
{
  "slug": "clash_of_mountains_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "classes": [
                "Guardian"
              ]
            },
            {
              "type": "SOURCE_IS_ATTACK"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "CLASH",
          "target": "opponent"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Seismic Surge"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
Clash($parameter, effectController: $player);
        break;
// OnBlockResolveEffects()
if (ClassContains($combatChain[0], "GUARDIAN", $mainPlayer)) {
            AddLayer("TRIGGER", $defPlayer, $defendingCard, $defendingCard);
          }
          break;
// WonClashAbility()
PlayAura("seismic_surge", $playerID, 1, true, effectController:$effectController, effectSource:$cardID);
        break;
```

### dissipation_shield_yellow  — looks-aligned
text: 'Dissipation Shield enters the arena with 4 steam counters on it.\n\nAt the beginning of your action phase, destroy Dissipation Shield unless you remove a steam counter from it.\n\n**Instant** - Destroy Dissipation Shield: The next time your hero would be dealt damage this turn, prevent X damage, where X is the number of steam counters on Dissipation Shield.'
```json
{
  "slug": "dissipation_shield_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter_type": "STEAM",
          "amount": 4
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DISSIPATION_SHIELD_IN_GRAVEYARD"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "token_type": "Dissipation Shield"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DISSIPATION_SHIELD_IN_PLAY"
        }
      ],
      "effects": [
        {
          "type": "REMOVE_COUNTER",
          "counter_type": "STEAM",
          "amount": 1
        },
        {
          "type": "DESTROY_TOKEN",
          "token_type": "Dissipation Shield",
          "conditions": [
            {
              "type": "COUNTER_GTE",
              "counter_type": "STEAM",
              "amount": 0
            }
          ]
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "DAMAGE_PREVENTION_ACTIVE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ItemDefaultHoldTriggerState()
return 1;
// ProcessTrigger()
$index = SearchItemsForUniqueID($uniqueID, $player);
        --$items[$index + 1];
        if ($items[$index + 1] <= 0) DestroyItemForPlayer($player, $index);
        break;
// CurrentTurnEffectDamagePreventionAmount()
return intval($effects[1]);
// CurrentEffectDamagePrevention()
if ($preventable) $preventedDamage += intval($effects[1]);
      RemoveCurrentTurnEffect($index);
      break;
// PayItemAbilityAdditionalCosts()
AddAdditionalCost($currentPlayer, $items[$index + 1]);
      DestroyItemForPlayer($currentPlayer, $index);
      break;
// ItemBeginningActionPhaseAbilities()
AddLayer("TRIGGER", $mainPlayer, $items[$i], "-", "-", $items[$i + 4]);
        break;
// ARCMechanologistPlayAbility()
AddCurrentTurnEffect($cardID . "-" . $additionalCosts, $currentPlayer, "PLAY");
      $rv = "";
      return $rv;
// ARCAbilityType()
case "dissipation_shield_yellow": return "I";
```

### scrap_compactor_red  — looks-aligned
text: '**Scrap**\n\nWhen this attacks, if it **scrapped** a card, you may play your next Evo this turn as though it were an instant.'
```json
{
  "slug": "scrap_compactor_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SCRAPPED_CARD"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "PLAY_EVO_AS_INSTANT"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVOPlayAbility()
if (DelimStringContains($additionalCosts, "SCRAP", true)) AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### weave_ice_yellow  — looks-aligned
text: "The next Ice or Elemental attack action card you play this turn gains +2{p}.\n\nIf it's **fused**, it gains **dominate**.\n\n**Go again**"
```json
{
  "slug": "weave_ice_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "WEAVE_ICE_ACTIVE"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "WEAVE_ICE_ACTIVE"
        },
        {
          "type": "OR",
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Ice"
            },
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Elemental"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "WEAVE_ICE_ACTIVE"
        },
        {
          "type": "OR",
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Ice"
            },
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Elemental"
            }
          ]
        },
        {
          "type": "FLAG_SET",
          "flag": "FUSED"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "DOMINATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesEffectGrantsDominate()
return $combatChainState[$CCS_AttackFused] == 1;
// ELEEffectPowerModifier()
case "weave_ice_yellow": return 2;
// ELECombatEffectActive()
return CardType($attackID) == "AA" && TalentContainsAny($attackID, "ICE,ELEMENTAL",$mainPlayer);
// ELETalentPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### seerstone  — looks-aligned
text: '**Action** - {r}{r}{r}: Look at the top card of your deck. You may put it on the bottom. Create a Ponder token.'
```json
{
  "slug": "seerstone",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 3,
      "effects": [
        {
          "type": "LOOK_AT",
          "target": "TOP_DECK"
        },
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": 1,
          "optional": true
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Ponder"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNAbilityCost()
case "seerstone": return 3;
// DYNAbilityType()
case "seerstone": return "A";
// DYNPlayAbility()
PlayerOpt($currentPlayer, 1, false);
      PlayAura("ponder", $currentPlayer);
      return "";
```

### wax_on_yellow  — looks-aligned
text: 'While Wax On is defending an attack action card with cost 0, it gains +2{d}.'
```json
{
  "slug": "wax_on_yellow",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_COST_GTE",
              "amount": 0
            },
            {
              "type": "ATTACK_COST_LTE",
              "amount": 0
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// BlockModifier()
return (CardCost($attackID) == 0 && CardType($attackID) == "AA" ? 2 : 0);
```

### phantasmaclasm_red  — looks-aligned
text: "Look at the defending hero's hand and choose a card. They put it on the bottom of their deck then draw a card.\n\n**Phantasm**"
```json
{
  "slug": "phantasmaclasm_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "LOOK_AT",
          "target": "OPPONENT_HAND"
        },
        {
          "type": "SELECT_FROM_REF",
          "ref": "OPPONENT_HAND",
          "effects": [
            {
              "type": "PUT_CARDS_BOTTOM",
              "amount": 1,
              "target_ref": "SELECTED"
            },
            {
              "type": "DRAW",
              "amount": 1
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessAttackTrigger()
AddDecisionQueue("SHOWHANDWRITELOG", $defPlayer, "<-", 1);
      AddDecisionQueue("FINDINDICES", $defPlayer, "HAND");
      AddDecisionQueue("CHOOSETHEIRHAND", $player, "<-", 1);
      AddDecisionQueue("MULTIREMOVEHAND", $defPlayer, "-", 1);
      AddDecisionQueue("SETDQVAR", $player, "0", 1);
      AddDecisionQueue("WRITELOG", $player, "⬇️ <0> was put on the bottom of the deck.", 1);
      AddDecisionQueue("ADDBOTDECK", $defPlayer, "Skip", 1);
      AddDecisionQueue("DRAW", $defPlayer, "-");
      break;
// MONIllusionistPlayAbility()
AddLayer("TRIGGER", $currentPlayer, $cardID, "-", "ATTACKTRIGGER");
        return "";
```

### plow_through_red  — looks-aligned
text: 'Your next weapon attack this turn gains +3{p} and "If this weapon is defended by an attack action card, it gains +1{p} until end of turn."\n\n**Go again**'
```json
{
  "slug": "plow_through_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "DURING_TURN",
          "player": "self"
        },
        {
          "type": "IN_COMBAT",
          "player": "self"
        },
        {
          "type": "ATTACK_IS_WEAPON",
          "player": "self"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_DEFEND",
            "conditions": [
              {
                "type": "ATTACK_IS_WEAPON",
                "player": "self"
              }
            ],
            "effects": [
              {
                "type": "MODIFY_ATTACK",
                "mod": "add",
                "amount": 1
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MainCharacterPowerModifiers()
$modifier += 1;
          $powerModifiers[] = $mainCharacterEffects[$i + 1];
          $powerModifiers[] = 1;
          break;
// OnBlockEffects()
if ($cardType == "AA" && NumAttacksBlocking() == 1) {
            AddCharacterEffect($otherPlayer, $combatChainState[$CCS_WeaponIndex], $currentTurnEffects[$i]);
            WriteLog(CardLink($currentTurnEffects[$i], $currentTurnEffects[$i]) . " gives your weapon +1 for the rest of the turn");
          }
          break;
// MONEffectPowerModifier()
case "plow_through_red": return 3;
// MONCombatEffectActive()
case "plow_through_red": case "plow_through_yellow": case "plow_through_blue": return TypeContains($attackID, "W", $mainPlayer);
// MONWarriorPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### stir_the_wildwood_yellow  — looks-aligned
text: '**Earth Fusion**\n\nIf you have dealt arcane damage to an opposing hero this turn, Stir the Wildwood gains +2{p}.\n\nIf Stir the Wildwood was **fused**, it gains +2{p}.'
```json
{
  "slug": "stir_the_wildwood_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "EARTH_FUSION_DEALT_ARCANE_DAMAGE"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FUSED"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += GetClassState($defPlayer, $CS_ArcaneDamageTaken) >= 1 ? 2 : 0;
        break;
// FuseAbility()
case "stir_the_wildwood_red": case "stir_the_wildwood_yellow": case "stir_the_wildwood_blue": AddCurrentTurnEffect($cardID, $player); break;
// HasFusion()
case "stir_the_wildwood_red": case "stir_the_wildwood_yellow": case "stir_the_wildwood_blue": return "EARTH";
// ELEEffectPowerModifier()
case "stir_the_wildwood_red": case "stir_the_wildwood_yellow": case "stir_the_wildwood_blue": return 2;
// ELECombatEffectActive()
case "stir_the_wildwood_red": case "stir_the_wildwood_yellow": case "stir_the_wildwood_blue": return true;
```

### viserai_usurper  — looks-aligned
text: "The first attack action card with blood debt you play each turn gets **go again**.\n\nAt the beginning of each end phase, if you've created or activated a Gate to i'Arathael this turn, you may **traverse**."
```json
{
  "slug": "viserai_usurper",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BLOOD_DEBT_ATTACK_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "GATE_TO_ARATHAEL_CREATED_OR_ACTIVATED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "TRAVERSE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
if ($isFirstBloodDebtAttack) return true;
        break;
```

### dense_blue_mist_blue  — looks-aligned
text: "Attacks that target you this turn get -1{p}.\n\nIf a Chi was pitched to play this, effects don't trigger if an attack hits you this turn."
```json
{
  "slug": "dense_blue_mist_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA",
          "mod": "subtract",
          "amount": 1,
          "aura_type": "DENSE_BLUE_MIST_AURA"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PITCH",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "ref": "CHI"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "CHI_PITCHED_FOR_DENSE_BLUE_MIST"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CHI_PITCHED_FOR_DENSE_BLUE_MIST"
        }
      ],
      "effects": [
        {
          "type": "WARD"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTPlayAbility()
AddCurrentTurnEffect($cardID . "-DEBUFF", $otherPlayer);
      if (SearchCardList($additionalCosts, $currentPlayer, subtype: "Chi") != "") AddCurrentTurnEffect($cardID . "-HITPREVENTION", $currentPlayer);
      return "";
```

### beast_mode_blue  — looks-aligned
text: "If you've **intimidated** this turn, this gets +2{p}."
```json
{
  "slug": "beast_mode_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "INTIMIDATED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += GetClassState($mainPlayer, $CS_HaveIntimidated) > 0 ? 2 : 0;
        break;
```

### sutcliffes_research_notes_yellow  — looks-aligned
text: 'Reveal the top 2 cards of your deck. Create a Runechant token for each Runeblade attack action card revealed this way, then put the cards on top of your deck in any order.\n\n**Go again**'
```json
{
  "slug": "sutcliffes_research_notes_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "REVEAL_TOP_DECK",
          "amount": 2
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "revealed",
              "card_type": "attack_action",
              "card_class": "Runeblade"
            }
          ]
        },
        {
          "type": "PUT_CARDS_BOTTOM",
          "zone": "revealed",
          "order": "any"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CRUPlayAbility()
$count = match($cardID) { "sutcliffes_research_notes_red" => 3, "sutcliffes_research_notes_yellow" => 2, default => 1 };
      $deck = new Deck($currentPlayer);
      $numRunechants = 0;
      if($deck->Reveal($count)) {
        $cards = explode(",", $deck->Top(remove:true, amount:$count));
        $count = count($cards);
        for($i=0; $i<$count; ++$i) { $card = $cards[$i]; if(ClassContains($card, "RUNEBLADE", $currentPlayer) && CardType($card) == "AA") ++$numRunechants; }
        if($numRunechants > 0) PlayAura("runechant", $currentPlayer, number:$numRunechants);
        AddDecisionQueue("CHOOSETOP", $currentPlayer, implode(",", $cards));
      }
      return "";
```

### rotten_remains_blue  — looks-aligned
text: "When this attacks, you may banish a card with 1{p} from each hero's graveyard. If you do, this gets +1{p}, then repeat this process."
```json
{
  "slug": "rotten_remains_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "BANISH",
          "target": "hero_graveyard",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "hero_graveyard",
              "power": 1
            }
          ]
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_ATTACK"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HNTPlayAbility()
$myMaxCards = SearchCount(SearchDiscard($currentPlayer, maxAttack:1, minAttack:1));
      $oppMaxCards = SearchCount(SearchDiscard($otherPlayer, maxAttack:1, minAttack:1));
      $maxCards = min($myMaxCards, $oppMaxCards);
      for ($i = 0; $i < $maxCards; $i++) {
        AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYDISCARD:maxAttack=1;minAttack=1",1);
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a card to banish", 1);
        AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("MZBANISH", $currentPlayer, "GY,-," . $currentPlayer . ",1", 1);
        AddDecisionQueue("MZREMOVE", $currentPlayer, "-", 1);
        AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "THEIRDISCARD:maxAttack=1;minAttack=1", 1);
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a card to banish", 1);
        AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("MZBANISH", $currentPlayer, "GY,-," . $currentPlayer . ",1", 1);
        AddDecisionQueue("MZREMOVE", $currentPlayer, "-", 1);
        AddDecisionQueue("ADDCURRENTTURNEFFECT", $currentPlayer, $cardID, 1);
      }
      break;
```

### arcanic_shockwave_yellow  — looks-aligned
text: '**Lightning Fusion**\n\nWhen you attack with Arcanic Shockwave, if it was **fused**, deal 1 arcane damage to target hero.'
```json
{
  "slug": "arcanic_shockwave_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "Fusion"
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// FuseAbility()
case "arcanic_shockwave_red": case "arcanic_shockwave_yellow": case "arcanic_shockwave_blue": DealArcane(1, 0, "PLAYCARD", $cardID); break;
// HasFusion()
case "arcanic_shockwave_red": case "arcanic_shockwave_yellow": case "arcanic_shockwave_blue": return "LIGHTNING";
```

### teklo_core_blue  — looks-aligned
text: '**Dash Specialization**\n\nTeklo Core enters the arena with 2 steam counters on it. When Teklo Core has no steam counters on it, destroy it.\n\nAt the beginning of your action phase, remove a steam counter from Teklo Core and gain {r}{r}.'
```json
{
  "slug": "teklo_core_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter_type": "steam",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "COUNTER_GTE",
          "counter_type": "steam",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "REMOVE_COUNTER",
          "counter_type": "steam",
          "amount": 1
        },
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "COUNTER_GTE",
          "counter_type": "steam",
          "amount": 0
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ItemDefaultHoldTriggerState()
return 1;
// ProcessTrigger()
$index = SearchItemsForUniqueID($uniqueID, $player);
        --$items[$index + 1];
        GainResources($player, 2);
        if ($items[$index + 1] <= 0) DestroyItemForPlayer($player, $index);
        break;
// ItemBeginningActionPhaseAbilities()
AddLayer("TRIGGER", $mainPlayer, $items[$i], "-", "-", $items[$i + 4]);
        break;
```

### rising_knee_thrust_red  — looks-aligned
text: '**Combo** - If Leg Tap was the last attack this combat chain, Rising Knee Thrust gains +2{p} and **go again**.'
```json
{
  "slug": "rising_knee_thrust_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LEG_TAP_LAST_ATTACK"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Leg Tap") return true;
        break;
// PowerModifier()
$power += (ComboActive() ? 2 : 0);
        break;
// DoesAttackHaveGoAgain()
return ComboActive($attackID);
```

### agility  — looks-aligned
text: 'At the start of your turn, destroy this, then your next attack this turn gets **go again**.'
```json
{
  "slug": "agility",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "SET_FLAG",
          "flag": "AGILITY_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "AGILITY_ACTIVE"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
if (!SearchCurrentTurnEffects($auras[$i], $mainPlayer)) AddCurrentTurnEffect($auras[$i], $mainPlayer, "PLAY");
        WriteLog(CardLink($auras[$i]) . " will give your next attack go again!");
        DestroyAuraUniqueID($mainPlayer, $auras[$i + 6]);
        IncrementClassState($mainPlayer, $CS_NumAgilityDestroyed, 1);
        break;
// DoesCurrentTurnEffectGrantGoAgain()
return true;
```

### eye_of_ophidia_blue  — looks-aligned
text: '**Legendary**\n\nWhen you pitch Eye of Ophidia, **opt 2**.'
```json
{
  "slug": "eye_of_ophidia_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PITCH",
      "effects": [
        {
          "type": "OPT",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
Opt($parameter, 2);
        break;
// PitchAbility()
AddLayer("TRIGGER", $currentPlayer, $cardID);
      break;
```

### flatten_the_field_blue  — looks-aligned
text: '**Crush** - When this deals 4 or more damage to a hero, destroy a Seismic Surge token they control.'
```json
{
  "slug": "flatten_the_field_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CRUSH",
      "conditions": [
        {
          "type": "DID_NOT_HIT",
          "amount": 4
        }
      ],
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "token_type": "Seismic Surge"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessCrushEffect()
$indices = SearchMultizone($mainPlayer, "THEIRAURAS:cardID=seismic_surge");
        if(empty($indices)) break;
        MZChooseAndDestroy($mainPlayer, "THEIRAURAS:cardID=seismic_surge", context: "Choose a Seismic Surge token to destroy");
        WriteLog("Player $mainPlayer destroyed a " . CardLink("seismic_surge", "seismic_surge") . " token");
        break;
```

### tectonic_plating  — looks-aligned
text: '**Once per turn Action** - {r}: Create a Seismic Surge aura token. **Go again**\n\n**Battleworn**'
```json
{
  "slug": "tectonic_plating",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Seismic Surge"
        },
        {
          "type": "GO_AGAIN"
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "TECTONIC_PLATING_ACTION_USED_THIS_TURN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// WTRAbilityCost()
case "tectonic_plating": return 1;
// WTRAbilityType()
case "tectonic_plating": case "helm_of_isens_peak": return "A";
// WTRAbilityHasGoAgain()
case "tectonic_plating": return true;
// WTRPlayAbility()
PlayAura("seismic_surge", $mainPlayer);
        return "";
```

### deadwood_dirge_blue  — looks-aligned
text: 'Destroy an aura you control. If you do, create a Runechant token.\n\n**Go again**'
```json
{
  "slug": "deadwood_dirge_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "target": "self"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ROSPlayAbility()
$numRunechants = match ($cardID) {
        "deadwood_dirge_red" => 3,
        "deadwood_dirge_yellow" => 2,
        "deadwood_dirge_blue" => 1
      };
      if($currentPlayer == $mainPlayer){
        AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYAURAS");
      }
      else {
        $MZInds = MultiZoneIndices($currentPlayer, "MYAURAS&COMBATCHAINLINK:subtype=Aura");
        if ($MZInds == "PASS") $MZInds = "";
        $pastChoices = GetPastChainLinkCards($currentPlayer, asMZInd: true, subtype:"Aura");
        $MZInds = CombineSearches($MZInds, $pastChoices);
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, $MZInds);
      }
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("MZDESTROY", $currentPlayer, "-", 1);
      AddDecisionQueue("PLAYAURA", $currentPlayer, "runechant-$numRunechants-$cardID", 1);
      return "";
```

### rootbound_carapace_blue  — looks-aligned
text: '**Decompose** - You may banish 2 Earth cards and an action card from your graveyard. If you do, this gets +1{d}.'
```json
{
  "slug": "rootbound_carapace_blue",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "effects": [
        {
          "type": "BANISH",
          "amount": 2,
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "GRAVEYARD",
              "card_type": "Earth"
            }
          ]
        },
        {
          "type": "BANISH",
          "amount": 1,
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "GRAVEYARD",
              "card_type": "Action"
            }
          ]
        },
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "BANISHED_EARTH_ACTION"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ROSPlayAbility()
Decompose($currentPlayer, "ROOTBOUNDCARAPACE");
      return "";
```

### ride_the_tailwind_blue  — looks-aligned
text: 'When Ride the Tailwind hits, the next attack action card with 2 or less base {p} you play this combat chain gains **go again**.\n\n**Go again**'
```json
{
  "slug": "ride_the_tailwind_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "TAILWIND_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "TAILWIND_ACTIVE"
        },
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_TYPE_IN",
              "attack_type": "Attack"
            },
            {
              "type": "ATTACK_BASE_POWER_LTE",
              "amount": 2
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesCurrentTurnEffectGrantGoAgain()
return true;
// EVRCombatEffectActive()
case "ride_the_tailwind_red": case "ride_the_tailwind_yellow": case "ride_the_tailwind_blue": return CardType($attackID) == "AA" && PowerValue($attackID, $mainPlayer, "LAYER") <= 2;//Base attack
// EVRHitEffect()
AddCurrentTurnEffectFromCombat($cardID, $mainPlayer);
        break;
```

### reinforce_steel_yellow  — looks-aligned
text: 'Remove a -1{d} counter from a Guardian off-hand you control with 2 or less base {d}.'
```json
{
  "slug": "reinforce_steel_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "REMOVE_COUNTER",
          "counter": "-1d",
          "target": {
            "type": "SELF",
            "conditions": [
              {
                "type": "CONTROLS_TOKEN_TYPE",
                "subtype": "Guardian"
              },
              {
                "type": "HAS_KEYWORD",
                "keyword": "Off-hand"
              },
              {
                "type": "BASE_DEFENSE_LTE",
                "amount": 2
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNPlayAbility()
$maxDef = match($cardID) { "reinforce_steel_red" => 3, "reinforce_steel_yellow" => 2, default => 1 };
      AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYCHAR:type=E;subtype=Off-Hand;hasNegCounters=true;maxDef=" . $maxDef . ";class=GUARDIAN");
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("MZOP", $currentPlayer, "GETCARDINDEX", 1);
      AddDecisionQueue("MODDEFCOUNTER", $currentPlayer, "1", 1);
      return "";
```

### reckless_charge_blue  — looks-aligned
text: "**Kayo Specialization**\n\nRoll a 6 sided die. Gain action points equal to half the number rolled, rounded down.\n\nIf you've rolled a 6 on a die this turn, draw a card."
```json
{
  "slug": "reckless_charge_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "ROLL",
          "sides": 6,
          "on_success": [
            {
              "type": "GAIN",
              "keyword": "ACTION_POINTS",
              "amount": {
                "type": "HALF",
                "value": {
                  "type": "ROLL_RESULT"
                }
              }
            }
          ]
        },
        {
          "type": "SET_FLAG",
          "flag": "DIE_ROLLED_SIX"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DIE_ROLLED_SIX"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HVYPlayAbility()
$roll = GetDieRoll($currentPlayer);
      GainActionPoints(intval($roll / 2), $currentPlayer);
      if (GetClassState($currentPlayer, $CS_HighestRoll) == 6) Draw($currentPlayer);
      return "Rolled $roll and gained " . intval($roll / 2) . " action points";
```

### break_of_dawn_yellow  — looks-aligned
text: 'The next time a Shadow source would deal damage this turn, prevent 3 of that damage.'
```json
{
  "slug": "break_of_dawn_yellow",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "BREAK_OF_DAWN_ACTIVE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CurrentTurnEffectDamagePreventionAmount()
$prevention = match ($effects[0]) {
        "break_of_dawn_red" => 4,
        "break_of_dawn_yellow" => 3,
        "break_of_dawn_blue" => 2,
      };
      if (TalentContains($source, "SHADOW", $otherPlayer)) {
        return $prevention;
      }
      break;
// CurrentEffectDamagePrevention()
$prevention = match($effects[0]) {
        "break_of_dawn_red" => 4,
        "break_of_dawn_yellow" => 3,
        default => 2,
      };
      if (TalentContains($source, "SHADOW", $otherPlayer)) {
        if ($preventable) $preventedDamage += $prevention;
        RemoveCurrentTurnEffect($index);
      }
      break;
// DTDPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### well_grounded  — looks-aligned
text: '**Instant** - Destroy this: Prevent the next 2 damage that would be dealt to you this turn. Activate this only if there are 4 or more Earth cards in your banished zone.'
```json
{
  "slug": "well_grounded",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "BANISHED",
          "card_type": "Earth",
          "amount": 4
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "WELL_GROUNDED_ACTIVE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return SearchCount(SearchBanish($player, talent: "EARTH")) < 4;
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// CurrentTurnEffectDamagePreventionAmount()
return intval($effects[1]);
// CurrentEffectDamagePrevention()
if ($preventable) {
        $damageToPrevent = min($damage, $effects[1]);
        $preventedDamage += $damageToPrevent;
        $effects[1] -= $damageToPrevent;
        $currentTurnEffects[$index] = $effects[0] . "-" . $effects[1];
      }
      if ($effects[1] <= 0 || !$preventable) RemoveCurrentTurnEffect($index);
      break;
// ROSPlayAbility()
AddCurrentTurnEffect($cardID."-2", $currentPlayer);
      return "";
```

### cintari_sellsword  — looks-aligned
text: "**Once per Turn Action** - {r}: **Attack**. **Go again**\n\nCintari Sellsword can only attack if you've attacked with a weapon this turn."
```json
{
  "slug": "cintari_sellsword",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ATTACKED_WITH_WEAPON_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return GetClassState($player, $CS_AttacksWithWeapon) <= 0;
// DoesAttackHaveGoAgain()
return true;
```

### mighty_windup_yellow  — looks-aligned
text: '**Instant** - Discard this: Create a Might token.'
```json
{
  "slug": "mighty_windup_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "cost": [
        {
          "type": "DISCARD_SELF"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Might"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CardCost()
if (GetResolvedAbilityType($cardID, "HAND") == "I" && $from == "HAND") return 0;
      return 3;
// GetAbilityNames()
return GetEasyAbilityNames($cardID, $index, $from, $allNames);
// GoesOnCombatChain()
return $phase == "B" && count($layers) == 0 || GetResolvedAbilityType($cardID, $from) == "AA";
// ProcessAbility()
PlayAura("might", $player, isToken:true, effectController:$player, effectSource:$parameter);
      break;
```

### salvage_shot_red  — looks-aligned
text: "When this hits, put it on the bottom of its owner's deck."
```json
{
  "slug": "salvage_shot_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "PUT_SELF_BOTTOM_DECK"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCRangerHitEffect()
if(substr($from, 0, 5) != "THEIR") $combatChainState[$CCS_GoesWhereAfterLinkResolves] = "BOTDECK";
        else $combatChainState[$CCS_GoesWhereAfterLinkResolves] = "THEIRBOTDECK";
          break;
```

### funeral_moon_red  — looks-aligned
text: 'You may play this from your banished zone.\n\nIf a hero has lost {h} this turn, you may play this as though it were an instant.\n\nCreate a Runechant token.\n\n**Blood Debt**'
```json
{
  "slug": "funeral_moon_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "BANISH_FROM_GRAVEYARD",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "HERO_LOST_LIFE_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "INSTANT_MODE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayableFromBanish()
return true;
// CanPlayAsInstant()
if (str_contains($from, "THEIR")) return false; //only the owner can play it at instant speed
      if (GetClassState($currentPlayer, $CS_HealthLost) > 0 || GetClassState($otherPlayer, $CS_HealthLost) > 0) return true;
      break;
// DTDPlayAbility()
PlayAura("runechant", $currentPlayer);
      return "";
```

### mutated_mass_blue  — looks-aligned
text: "You may play Mutated Mass from your banished zone.\n\nMutated Mass's {p} and {d} is equal to twice the number of cards in your pitch zone with different costs.\n\n**Blood Debt**"
```json
{
  "slug": "mutated_mass_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "BANISH_FROM_GRAVEYARD",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA",
          "mod": "set",
          "amount": 2
        },
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "set",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// BlockValue()
$block = SearchPitchForNumCosts($defPlayer) * 2;
      break;
// PowerValue()
$basePower = SearchPitchForNumCosts($mainPlayer) * 2;
      break;
// PlayableFromBanish()
return true;
```

### qi_unleashed_red  — looks-aligned
text: '**Combo** - If Crouching Tiger was the last attack this combat chain, this gets +4{p}.'
```json
{
  "slug": "qi_unleashed_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CROUCHING_TIGER_LAST_ATTACK"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Crouching Tiger") return true;
        break;
// PowerModifier()
$power += (ComboActive() ? 4 : 0);
        break;
```

### oldhim  — looks-aligned
text: '**Essence of Earth and Ice**\n\n**Once per Turn Defense Reaction** - {r}{r}{r}: If an Earth card is pitched this way, prevent the next 2 damage that would be dealt to Oldhim this turn. If an Ice card is pitched this way, the attacking hero puts a card from their hand on top of their deck.'
```json
{
  "slug": "oldhim",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "OLDHIM_DEFENSE_REACTION_USED"
        }
      ],
      "effects": [
        {
          "type": "WARD",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "OLDHIM_DEFENSE_REACTION_USED"
        }
      ],
      "effects": [
        {
          "type": "PUT_HAND_CARD_TOP",
          "target": "opponent"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// GoesOnCombatChain()
// dreacts that don't go onto the chain
      return false;
// CurrentTurnEffectDamagePreventionAmount()
return intval($effects[1]);
// CurrentEffectDamagePrevention()
if ($preventable) {
        $damageToPrevent = min($damage, $effects[1]);
        $preventedDamage += $damageToPrevent;
        $effects[1] -= $damageToPrevent;
        $currentTurnEffects[$index] = $effects[0] . "-" . $effects[1];
      }
      if ($effects[1] <= 0 || !$preventable) RemoveCurrentTurnEffect($index);
      break;
// isCardLegalinHero()
$heroTalent[] = "ICE"; $heroTalent[] = "EARTH"; break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
// return_Hero_Type()
return Young;
		break;
// ELEGuardianPlayAbility()
if(SearchCardList($additionalCosts, $currentPlayer, talent:"EARTH") != "")
        { 
          AddCurrentTurnEffect($cardID."-2", $currentPlayer);
        }
        if(SearchCardList($additionalCosts, $currentPlayer, talent:"ICE") != "")
        {
          $otherPlayer = ($currentPlayer == 1 ? 2 : 1);
          AddDecisionQueue("FINDINDICES", $otherPlayer, "HAND");
          AddDecisionQueue("CHOOSEHAND", $otherPlayer, "<-", 1);
          AddDecisionQueue("MULTIREMOVEHAND", $otherPlayer, "-", 1);
          AddDecisionQueue("MULTIADDTOPDECK", $otherPlayer, "-", 1);
          $rv .= "The opponent must put a card from their hand on top of their deck.";
        }
        return $rv;
// ELEAbilityCost()
case "oldhim_grandfather_of_eternity": case "oldhim": return 3;
// ELEAbilityType()
case "oldhim_grandfather_of_eternity": case "oldhim": return "DR";
```

### potion_of_deja_vu_blue  — looks-aligned
text: '**Instant** - Destroy Potion of Déjà Vu: Put all cards from your pitch zone on top of your deck in any order.'
```json
{
  "slug": "potion_of_deja_vu_blue",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "PUT_CARDS_BOTTOM",
          "zone": "pitch",
          "order": "any"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PayItemAbilityAdditionalCosts()
DestroyItemForPlayer($currentPlayer, $index);
      break;
// EVRAbilityCost()
case "clarity_potion_blue": case "healing_potion_blue": case "potion_of_seeing_blue": case "potion_of_deja_vu_blue": case "potion_of_ironhide_blue": return 0;
// EVRAbilityType()
if($from == "PLAY") return "I";
        else return "A";
// EVRPlayAbility()
if($from == "PLAY"){
          $Pitch = new PitchZone($currentPlayer);
          $cards = [];
          for ($i = $Pitch->NumCards() - 1; $i >= 0; --$i) {
            $PitchCard = $Pitch->Card($i, true);
            $cards[] = $PitchCard->Remove();
          }
          if(count($cards) > 0) AddDecisionQueue("CHOOSETOP", $currentPlayer, implode(",", $cards));
        }
        return "";
```

### old_leather_and_vim_red  — looks-aligned
text: 'If you control a Toughness or Vigor token, this gets +1{p}.\n\nWhen this hits a hero, create a Toughness and a Vigor token.'
```json
{
  "slug": "old_leather_and_vim_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Toughness"
        },
        {
          "type": "OR",
          "conditions": [
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "Toughness"
            },
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "Vigor"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Toughness"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
if (SearchAurasForCard("toughness", $mainPlayer, false) != "") $power += 1;
        elseif (SearchAurasForCard("vigor", $mainPlayer, false) != "") $power += 1;
        else $power += 0;
        break;
// SUPHitEffect()
PlayAura("toughness", $mainPlayer, isToken:true, effectController:$mainPlayer, effectSource:$cardID);
      PlayAura("vigor", $mainPlayer, isToken:true, effectController:$mainPlayer, effectSource:$cardID);
      break;
```

### brand_with_cinderclaw_blue  — looks-aligned
text: 'Your next attack this combat chain is Draconic in addition to its other card types.\n\n**Go again**'
```json
{
  "slug": "brand_with_cinderclaw_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// TalentOverride()
if (TypeContains($cardID, "AA") || TypeContains($cardID, "W") || SubtypeContains($cardID, "Ally")) {
          $talents[] = "DRACONIC";
        }
        break;
// RemoveEffectsFromCombatChain()
$remove = 1;
        break;
// EffectPlayCardRestricted()
$hasBrandOrEnflame = true;
        break 2;
// SearchInner()
case "enflame_the_firebrand_red":  $talentMod_conditional = true; break;
// UPRNinjaPlayAbility()
AddCurrentTurnEffectFromCombat($cardID, $currentPlayer);
        return "";
// UPRCombatEffectActive()
case "brand_with_cinderclaw_red": case "brand_with_cinderclaw_yellow": case "brand_with_cinderclaw_blue": return true;
```

### chilling_icevein_red  — looks-aligned
text: '**Ice Fusion**\n\nIf Chilling Icevein was **fused**, whenever an attack deals damage to a hero this turn, they discard a card unless they pay {r}.'
```json
{
  "slug": "chilling_icevein_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FUSED"
        }
      ],
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "target": "hero",
          "resource_cost": 1,
          "damage_amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
PayOrDiscard($target, 1);
        break;
// CurrentEffectDamageEffects()
if (IsHeroAttackTarget() && CardType($source) == "AA")
          AddLayer("TRIGGER", $otherPlayer, $effectID, $target);
        break;
// IsCombatEffectPersistent()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// FuseAbility()
case "chilling_icevein_red": case "chilling_icevein_yellow": case "chilling_icevein_blue": AddCurrentTurnEffect($cardID, $player); break;
// HasFusion()
case "chilling_icevein_red": case "chilling_icevein_yellow": case "chilling_icevein_blue": return "ICE";
// ELECombatEffectActive()
case "chilling_icevein_red": case "chilling_icevein_yellow": case "chilling_icevein_blue": return true;
```

### fender_bender_yellow  — looks-aligned
text: '**Boost**\n\nThis gets +X{p}, where X is the number of equipment defending it.'
```json
{
  "slug": "fender_bender_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += NumEquipBlock();
        break;
```

### cinderskin_devotion_blue  — looks-aligned
text: 'If you control 2 or more Draconic chain links, this gets **go again**.'
```json
{
  "slug": "cinderskin_devotion_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "subtype": "Draconic",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
return NumDraconicChainLinks() >= 2;
```

### blessing_of_savagery_blue  — looks-aligned
text: 'At the start of your turn, destroy Blessing of Savagery then your next attack with 6 or more base {p} this turn gains +1{p}.'
```json
{
  "slug": "blessing_of_savagery_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "SET_FLAG",
          "flag": "BLESSING_OF_SAVAGERY_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BLESSING_OF_SAVAGERY_ACTIVE"
        },
        {
          "type": "SELF_ATTACK_POWER_GTE",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
if ($auras[$i] == "blessing_of_savagery_red") $amount = 3;
        else $amount = ($auras[$i] == "blessing_of_savagery_yellow") ? 2 : 1;
        AddCurrentTurnEffect($auras[$i], $mainPlayer, "PLAY");
        DestroyAuraUniqueID($mainPlayer, $auras[$i + 6]);
        break;
// DYNEffectPowerModifier()
case "blessing_of_savagery_blue": return 1;
// DYNCombatEffectActive()
case "blessing_of_savagery_red": case "blessing_of_savagery_yellow": case "blessing_of_savagery_blue": return PowerValue($attackID, $mainPlayer, "LAYER") >= 6;//Specifies base attack
```

### quicksilver_dagger  — looks-aligned
text: "**Once per Turn Action** - {r}: **Attack**\n\nIf another weapon you control has gained **go again** this turn, this card's attacks get **go again**."
```json
{
  "slug": "quicksilver_dagger",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "QUICKSILVER_DAGGER_GO_AGAIN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
return GetClassState($mainPlayer, $CS_AnotherWeaponGainedGoAgain) != "-";
// ReverseID()
return "DYN070";
// ReverseArt()
case "quicksilver_dagger": return "quicksilver_dagger_r";
// DYNAbilityCost()
case "quicksilver_dagger": case "quicksilver_dagger_r": return 1;
// DYNAbilityType()
case "quicksilver_dagger": case "quicksilver_dagger_r": return "AA";
```

### tide_chakra_red  — looks-aligned
text: "Target Assassin or Mystic attack action card gets +3{p}. If you've **transcended** this turn, instead it gets +5{p}."
```json
{
  "slug": "tide_chakra_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "TRANSCEDED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 5
        }
      ]
    },
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if (!$CombatChain->HasCurrentLink()) return true;
      if (CardType($attackID) == "AA" && (ClassContains($attackID, "ASSASSIN", $player) || TalentContains($attackID, "MYSTIC", $player))) return false;
      return true;
// MSTPlayAbility()
if (GetClassState($currentPlayer, $CS_Transcended) <= 0) AddCurrentTurnEffect($cardID . "-1", $currentPlayer);
      else AddCurrentTurnEffect($cardID . "-2", $currentPlayer);
      return "";
```

### recoil_blue  — looks-aligned
text: '**Combo** - If Head Jab was the last attack this combat chain, this has "When this hits a hero, they put a card from their hand on top of their deck."'
```json
{
  "slug": "recoil_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "HEAD_JAB_LAST_ATTACK"
        }
      ],
      "effects": [
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": 1,
          "target": "opponent"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Head Jab") return true;
        break;
// AddOnHitTrigger()
if (ComboActive($cardID) && IsHeroAttackTarget()) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "ONHITEFFECT");
        return true;
      }
      break;
// OUTHitEffect()
if(ComboActive() && IsHeroAttackTarget()) MZMoveCard($defPlayer, "MYHAND", "MYTOPDECK", silent:true);
        break;
```

### braveforge_bracers  — looks-aligned
text: '**Once per turn Action** - {r}: Your next weapon attack this turn gains +1{p}. Activate this ability only if a weapon you control has hit this turn. **Go again**\n\n**Battleworn**'
```json
{
  "slug": "braveforge_bracers",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "WEAPON_HAS_HIT_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return GetClassState($player, $CS_HitsWithWeapon) == 0;
// WTRAbilityCost()
case "braveforge_bracers": return 1;
// WTRAbilityType()
case "braveforge_bracers": return "A";
// WTRAbilityHasGoAgain()
case "braveforge_bracers": return true;
// WTREffectPowerModifier()
case "braveforge_bracers": return 1;
// WTRCombatEffectActive()
case "braveforge_bracers": return TypeContains($attackID, "W", $mainPlayer);
// WTRPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### quickening_sand_blue  — looks-aligned
text: "Create a Quicken token under target hero's control.\n\n**Go again**\n\nWhen this defends an attack with go again, {t} target hero or ally."
```json
{
  "slug": "quickening_sand_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Quicken"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "GO_AGAIN"
        }
      ],
      "effects": [
        {
          "type": "SELECT_FROM_REF",
          "ref": "hero_or_ally",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
$targetParts = explode("-", $target);
        $zone = $targetParts[0];
        $uid = $targetParts[1];
        $otherPlayer = 3 - $player;
        $MZIndex = match ($zone) {
          "THEIRALLY" => "$zone-" . SearchAlliesForUniqueID($uid, $otherPlayer),
          "MYALLY" => "$zone-" . SearchAlliesForUniqueID($uid, $player),
          "THEIRCHAR" => "$zone-" . SearchCharacterForUniqueID($uid, $otherPlayer),
          "THEIRCHARUID" => "$zone-" . SearchCharacterForUniqueID($uid, $otherPlayer),
          "MYCHAR" => "$zone-" . SearchCharacterForUniqueID($uid, $player),
          "MYCHARUID" => "$zone-" . SearchCharacterForUniqueID($uid, $player),
        };
        Tap($MZIndex, $player);
        break;
```

### radiant_forcefield_yellow  — looks-aligned
text: "If your hero would be dealt damage, banish a card from your hero's soul to prevent 1 of that damage.\n\nWhen there are no cards in your hero's soul, destroy this."
```json
{
  "slug": "radiant_forcefield_yellow",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "HERO_WOULD_BE_DEALT_DAMAGE"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": "HERO_SOUL",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_LEAVE_PLAY",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "HERO_SOUL",
          "amount": 0
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraNumUses()
return 1;
// AuraDamagePreventionAmount()
$auras = &GetAuras($player);
      if ($active) {
        $soul = &GetSoul($player);
        if (count($soul) > 0) {
          $cancelRemove = count($soul) > 1;
          MZMoveCard($player, "MYSOUL", "MYBANISH,SOUL,-");
          if ($damage > 1) $auras[$index + 5] = 0;
          $preventedDamage = 1;
        }
      } else if ($auras[$index + 5] == 1) {
        $preventedDamage = 1;
      } else {
        $auras[$index + 5] = 1;
        $preventedDamage = 0;
      }
      break;
```

### high_riser  — looks-aligned
text: "**Once per Turn Action** - {r}{r}{r}: **Attack**\n\nIf you've drawn a card this turn, this gets +1{p}."
```json
{
  "slug": "high_riser",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 3,
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DRAWN_CARD_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerValue()
case "high_riser": return GetClassState($mainPlayer, $CS_NumCardsDrawn) >= 1 ? $basePower+1 : $basePower;
```

### embermaw_cenipai_yellow  — looks-aligned
text: '**Phantasm**\n\nWhen Embermaw Cenipai is destroyed, create an Ash token.'
```json
{
  "slug": "embermaw_cenipai_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEATH",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Ash"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AttackDestroyed()
PutPermanentIntoPlay($mainPlayer, "ash");
      break;
```

### tiger_form_incantation_yellow  — looks-aligned
text: "The next Crouching Tiger you play this turn gets +2{p}.\n\nIf you've pitched a blue card this turn, create a Crouching Tiger in your hand.\n\n**Go again**"
```json
{
  "slug": "tiger_form_incantation_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CROUCHING_TIGER_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BLUE_PITCHED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token": "Crouching Tiger",
          "zone": "hand"
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      if (SearchPitchForColor($currentPlayer, 3) > 0) AddPlayerHand("crouching_tiger", $currentPlayer, $cardID, created:true);
      return "";
```

### out_muscle_red  — looks-aligned
text: "While Out Muscle isn't defended by a card with equal or greater {p}, it has **go again**."
```json
{
  "slug": "out_muscle_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "NOT",
          "condition": {
            "type": "DEFENDS_WITH_OTHER_HAND_CARD",
            "conditions": [
              {
                "type": "SELF_ATTACK_POWER_GTE",
                "amount": 6
              }
            ]
          }
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
return SearchHighestAttackDefended() < CachedTotalPower();
```

### minnowism_red  — looks-aligned
text: 'The next attack action card with 3 or less base {p} you play this turn gains +3{p}.\n\n**Go again**'
```json
{
  "slug": "minnowism_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "DURING_TURN"
        },
        {
          "type": "PLAYED_FROM_ARSENAL"
        },
        {
          "type": "ATTACK_TYPE_IN",
          "values": [
            "Action"
          ]
        },
        {
          "type": "SELF_ATTACK_POWER_GTE",
          "amount": 3
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MONGenericPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
// MONEffectPowerModifier()
case "minnowism_red": return 3;
// MONCombatEffectActive()
case "minnowism_red": case "minnowism_yellow": case "minnowism_blue": return CardType($attackID) == "AA" && PowerValue($attackID, $mainPlayer, "LAYER") <= 3;//Base power
```

### pour_the_mold_blue  — looks-aligned
text: 'Put a Mechanologist item with cost 0 from your hand into the arena.\n\nIf you have **boosted** this turn, put a steam counter on it.\n\n**Go again**'
```json
{
  "slug": "pour_the_mold_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "BOOSTED_THIS_TURN"
            }
          ]
        },
        {
          "type": "PUT_COUNTER",
          "counter": "steam",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "BOOSTED_THIS_TURN"
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCMechanologistPlayAbility()
$maxCost = match($cardID) { "pour_the_mold_red" => 2, "pour_the_mold_yellow" => 1, default => 0 };
      AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "MYHAND:subtype=Item;maxCost=$maxCost;class=MECHANOLOGIST");
      AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("MZREMOVE", $currentPlayer, "-", 1);
      AddDecisionQueue("PUTPLAY", $currentPlayer, (GetClassState($currentPlayer, $CS_NumBoosted) > 0 ? 1 : 0), 1);
      return "";
```

### blistering_assault_blue  — looks-aligned
text: 'If you have a yellow card in your pitch zone, this gets **go again**.'
```json
{
  "slug": "blistering_assault_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "color": "yellow"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DTDPlayAbility()
if(SearchPitchForColor($currentPlayer, 2) > 0) GiveAttackGoAgain();
      return "";
```

### captain_of_the_guard_blue  — looks-aligned
text: 'While this is defending, cards with {p} greater than the attack they are defending get +1{d}.'
```json
{
  "slug": "captain_of_the_guard_blue",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "IN_COMBAT"
        },
        {
          "type": "ATTACK_POWER_GT_BASE"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// BlockModifier()
if ($blockCard != "-" && $blockCard->TotalPower() > $totalPower) {
              if (!$noGain) ++$blockModifier;
            }
            break;
// BlockModifier()
if ($blockCard != "-" && $blockCard->TotalPower() > $totalPower) {
              if (!$noGain) ++$blockModifier;
            }
            break;
```

### rage_baiters  — looks-aligned
text: '**Attack Reaction** - {r}, {t}: Target attack with stealth gets "When this hits a hero, **mark** them."\n\n**Blade Break**'
```json
{
  "slug": "rage_baiters",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "cost": [
        {
          "type": "PAY_RESOURCES",
          "amount": 1
        },
        {
          "type": "PITCH",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_HIT",
          "conditions": [
            {
              "type": "ATTACK_TARGET_IS_HERO"
            }
          ],
          "effects": [
            {
              "type": "MARK"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayCardEffect()
break;
```

### lead_with_heart_blue  — looks-aligned
text: 'Your next Guardian or Warrior attack this turn gets +1{p}.\n\nCreate a Vigor token.\n\n**Go again**'
```json
{
  "slug": "lead_with_heart_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "LEAD_WITH_HEART_ACTIVE"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "LEAD_WITH_HEART_ACTIVE"
        },
        {
          "type": "OR",
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Guardian"
            },
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Warrior"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HVYPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      PlayAura("vigor", $currentPlayer); 
      return "";
```

### raise_an_army_yellow  — looks-aligned
text: '**Kassai Specialization**\n\nAs an additional cost to play this, destroy X Gold you control.\n\nCreate X Cintari Sellsword tokens.\n\n**Go again**'
```json
{
  "slug": "raise_an_army_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "controlled",
          "asset": "GOLD",
          "amount": "X"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token": "Cintari Sellsword",
          "amount": "X"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HVYPlayAbility()
PlayAlly("cintari_sellsword", $currentPlayer, number: intval($additionalCosts), from:$from);
      return "";
// PayAdditionalCosts()
$numGold = CountItemByName("Gold", $currentPlayer);
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose how many " . CardLink("gold") . " you want to destroy");
      AddDecisionQueue("BUTTONINPUT", $currentPlayer, GetIndices($numGold + 1));
      AddDecisionQueue("SETCLASSSTATE", $currentPlayer, $CS_AdditionalCosts, 1);
      AddDecisionQueue("SETDQVAR", $currentPlayer, 0, 1);
      AddDecisionQueue("WRITELOG", $currentPlayer, CardLink($cardID) . " was played with a cost of {0}", 1);
      AddDecisionQueue("SPECIFICCARD", $currentPlayer, "RAISEANARMY", 1);
      break;
```

### evo_recall_blue  — looks-aligned
text: 'If you have a base head equipped, transform it into this, then equip this.\n\nWhen this is equipped, put up to 1 Mechanologist action card from your banished zone on top of your deck.\n\n**Arcane Barrier 1**'
```json
{
  "slug": "evo_recall_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_EQUIP",
      "effects": [
        {
          "type": "SEARCH_BANISH_FACE_DOWN",
          "amount": 1,
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "BANISHED",
              "card_type": "ACTION",
              "class": "Mechanologist"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "ARCANE_BARRIER",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EvoTransformAbility()
MZMoveCard($player, "MYBANISH:type=AA;class=MECHANOLOGIST&MYBANISH:type=A;class=MECHANOLOGIST", "MYTOPDECK", true, true);
      break;
// ArcaneBarrierChoices()
++$barrierArray[1];
        $total += 1;
        break;
```

### rapid_reflex_yellow  — looks-aligned
text: 'Target attack action card with cost 0 gains +2{p}.'
```json
{
  "slug": "rapid_reflex_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2,
          "conditions": [
            {
              "type": "ATTACK_COST_GTE",
              "amount": 0
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ReactionRequirementsMet()
case "rapid_reflex_red": case "rapid_reflex_yellow": case "rapid_reflex_blue": return CardType($combatChain[0]) == "AA" && CardCost($combatChain[0]) == 0;
```

### hoist_em_up_red  — looks-aligned
text: 'When this defends, you may {t} an ally you control. If you do, this gets +1{d}.'
```json
{
  "slug": "hoist_em_up_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "effects": [
        {
          "type": "MAY",
          "cost": [
            {
              "type": "TAP_SELF",
              "target": "ALLY"
            }
          ],
          "effects": [
            {
              "type": "MODIFY_DEFENSE_VALUE",
              "mod": "add",
              "amount": 1
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
$inds = GetUntapped($defPlayer, "MYALLY");
        if (strlen($inds) > 0) {
          AddDecisionQueue("SETDQCONTEXT", $defPlayer, "Choose an ally to tap (or pass)");
          AddDecisionQueue("PASSPARAMETER", $defPlayer, $inds, 1);
          AddDecisionQueue("MAYCHOOSEMULTIZONE", $defPlayer, "<-", 1);
          AddDecisionQueue("MZTAP", $defPlayer, "<-", 1);
          AddDecisionQueue("PASSPARAMETER", $defPlayer, $target, 1);
          AddDecisionQueue("COMBATCHAINDEFENSEMODIFIER", $defPlayer, 1, 1);
        }
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
```

### sprocket_rocket_blue  — looks-aligned
text: '**Boost**\n \nIf an item or equipment was banished from boosting this, this gets +1{p}.'
```json
{
  "slug": "sprocket_rocket_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "ITEM_OR_EQUIPMENT"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SelfBoostEffects()
if(SubtypeContains($boosted, "Item", $player) || IsEquipment($boosted, $player)) AddCurrentTurnEffect($cardID, $player);
      break;
```

### censor_red  — looks-aligned
text: "When this hits a hero, name a card. They can't play the named card until the end of their next turn."
```json
{
  "slug": "censor_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "CENSOR_ACTIVE",
          "target": "opponent"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EffectPlayCardRestricted()
$effectParam = $commaPos !== false ? substr($currentTurnEffects[$i], $commaPos + 1) : '';
          if ($from != "PLAY" && !IsStaticType(CardType($cardID)) && GamestateSanitize(NameOverride($cardID)) == $effectParam) $restrictedBy = "censor_red";
          break;
// AddPrePitchDecisionQueue()
if (!SearchCurrentTurnEffects("amnesia_red", $currentPlayer)) {
              if (GamestateSanitize($names[0]) == $effectArr[1]) {
                $names[0] = "-";
              }
              elseif (GamestateSanitize($names[1]) == $effectArr[1]) {
                $names[1] = "-";
              }
            }
            break;
// DTDHitEffect()
if(IsHeroAttackTarget()) {
        AddDecisionQueue("INPUTCARDNAME", $mainPlayer, "-");
        AddDecisionQueue("SETDQVAR", $mainPlayer, "0");
        AddDecisionQueue("WRITELOG", $mainPlayer, "<b>📣{0}</b> was chosen");
        AddDecisionQueue("ADDCURRENTANDNEXTTURNEFFECT", $defPlayer, "censor_red,{0}");
      }
      break;
```

### viserai_rune_blood  — looks-aligned
text: "Whenever you play a Runeblade card, if you've played another non-attack action card this turn, create a Runechant token."
```json
{
  "slug": "viserai_rune_blood",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PLAY_ACTIVATE_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "NON_ATTACK_ACTION_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
ViseraiPlayCard($target);
        break;
// MainCharacterPlayCardAbilities()
if (!IsStaticType(CardType($cardID), $from, $cardID) && ClassContains($cardID, "RUNEBLADE", $currentPlayer) && !TypeContains($cardID, "B", $currentPlayer)) {
          AddLayer("TRIGGER", $currentPlayer, $characterID, $cardID);
        }
        break;
// return_Hero_Type()
return Adult;
		break;
// return_Hero_Type()
return Adult;
		break;
// return_Hero_Type()
return Adult;
		break;
// return_Hero_Type()
return Adult;
		break;
// return_Hero_Type()
return Adult;
		break;
// return_Hero_Type()
return Adult;
		break;
// return_Hero_Type()
return Adult;
		break;
// return_Hero_Type()
return Adult;
		break;
```

### billowing_mirage_blue  — looks-aligned
text: 'When you attack with Billowing Mirage, **transform** up to 1 ash you control into an Aether Ashwing.\n\n**Go again**'
```json
{
  "slug": "billowing_mirage_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "TRANSFORM_HERO",
          "from": "ash",
          "to": "aether_ashwing",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// UPRIllusionistPlayAbility()
case "billowing_mirage_red": case "billowing_mirage_yellow": case "billowing_mirage_blue": Transform($currentPlayer, "Ash", "aether_ashwing", true); return "";
```

### sonata_galaxia_red  — looks-aligned
text: 'This costs {r} less to play for each Runechant you control.\n\nSearch your deck for a Runeblade aura with cost X or less, put it into the arena, then shuffle.\n\nIf X is 2 or more, this gets **go again**.'
```json
{
  "slug": "sonata_galaxia_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "PAY_LIFE",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "SEARCH_DECK",
          "target": "Runeblade Aura",
          "cost": "X",
          "max_cost": 2,
          "put_into": "arena",
          "shuffle": true
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN",
          "conditions": [
            {
              "type": "CHAIN_HIT_COUNT_GTE",
              "amount": 2
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DynamicCost()
if(SearchCurrentTurnEffectsAny(["bloodsheath_skeleta-NAA", "bloodsheath_skeleta-AA"], $currentPlayer)) {
        return "0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,40,42,44,46,48,50,52,54,56,58,60,62,64,66,68,70,72,74,76,78,80,82,84,86,88,90,92,94,96,98,100,102,104,106,108,110";
      }
      return "0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,40,42,44,46,48,50,52,54,56,58,60";
// SelfCostModifier()
return -1 * NumRunechants($currentPlayer);
// HVYPlayAbility()
$xVal = $resourcesPaid / 2;
      MZMoveCard($currentPlayer, "MYDECK:maxCost=" . $xVal . ";subtype=Aura;class=RUNEBLADE", "MYAURAS", may: true);
      AddDecisionQueue("SHUFFLEDECK", $currentPlayer, "-");
      if ($xVal >= 2) {
        global $CS_NextNAACardGoAgain;
        SetClassState($currentPlayer, $CS_NextNAACardGoAgain, 1);
      }
      return "";
```

### geyser_of_seismic_stirrings_blue  — looks-aligned
text: '**Go again**\n\nThis enters the arena with an energy counter. When it has none, destroy it.\n\nAt the beginning of your end phase, remove an energy counter from this and create a Seismic Surge token.'
```json
{
  "slug": "geyser_of_seismic_stirrings_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "energy",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "COUNTER_GTE",
          "counter": "energy",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "REMOVE_COUNTER",
          "counter": "energy",
          "amount": 1
        },
        {
          "type": "CREATE_TOKEN",
          "token": "Seismic Surge"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraPlayCounters()
return 1;
// AuraBeginEndPhaseTriggers()
--$auras[$i + 2];
        PlayAura("seismic_surge", $mainPlayer, 1, true, effectController:$mainPlayer, effectSource:$auras[$i]);
        if ($auras[$i + 2] == 0) DestroyAuraUniqueID($mainPlayer, $auras[$i + 6]);
        break;
```

### fluster_fist_blue  — looks-aligned
text: '**Combo** - If Open the Center was the last attack this combat chain, Fluster Fist gains +1{p} for each attack that has hit this combat chain.'
```json
{
  "slug": "fluster_fist_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "OPEN_THE_CENTER_PLAYED_THIS_COMBAT"
        },
        {
          "type": "COMBO"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Open the Center") return true;
        break;
// PowerModifier()
$power += (ComboActive() ? NumAttacksHit() : 0);
        break;
```

### rising_solartide_blue  — looks-aligned
text: "If Rising Solartide hits, put it into your hero's soul."
```json
{
  "slug": "rising_solartide_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "PUT_SELF_BOTTOM_DECK"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MONTalentHitEffect()
case "rising_solartide_blue": $combatChainState[$CCS_GoesWhereAfterLinkResolves] = "SOUL"; break;
```

### cloud_skiff_red  — looks-aligned
text: '**Once per Turn Instant** - {t} a cog you control: This gets +1{p} or go again.'
```json
{
  "slug": "cloud_skiff_red",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "PITCH",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if ($player != $mainPlayer) return true;
      if ($from != "PLAY" && $from != "COMBATCHAINATTACKS") return false;
      if (GetUntapped($player, "MYITEMS", "subtype=Cog") == "") return true;
      if ($from == "PLAY" && $combatChain[11] >= 1) return true;
      if ($from == "COMBATCHAINATTACKS" && $chainLinks[$index][9] >= 1) return true;
      return false;
// CombatChainPayAdditionalCosts()
$inds = GetUntapped($currentPlayer, "MYITEMS", "subtype=Cog");
      if($inds != "") {//Tap(explode(",", $inds)[0], $currentPlayer);
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, $inds);
        AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("MZTAP", $currentPlayer, "<-", 1);
      }
      if ($from == "PLAY") ++$combatChain[$i + 11];
      else ++$chainLinks[$i][9];
      break;
// SEAPlayAbility()
if ($from == "PLAY") {
        AddDecisionQueue("BUTTONINPUTNOPASS", $currentPlayer, "+1 Power,Go Again");
        AddDecisionQueue("SPECIFICCARD", $currentPlayer, "COGCONTROL-".$cardID, 1);
      }
      elseif ($from == "COMBATCHAINATTACKS") WriteLog("For now activating " . CardLink($cardID, $cardID) . " on a previous chain link will have no effect");
      break;
```

### impenetrable_belief_red  — looks-aligned
text: "If 3 or more cards have been put into an opposing hero's banished zone this turn, Impenetrable Belief gains +2{d} while defending."
```json
{
  "slug": "impenetrable_belief_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "OPPONENT_BANISHED_3_OR_MORE"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// BlockModifier()
return GetClassState($mainPlayer, $CS_CardsBanished) >= 3 ? 2 : 0;
```

### wrecking_ball_red  — looks-aligned
text: 'When you attack with Wrecking Ball, draw a card then discard a random card. If a card with 6 or more {p} is discarded this way, **intimidate**.'
```json
{
  "slug": "wrecking_ball_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "DISCARD_RANDOM"
        },
        {
          "type": "INTIMIDATE",
          "conditions": [
            {
              "type": "DISCARDED_CARD_POWER_GTE",
              "amount": 6
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// RVDPlayAbility()
Draw($currentPlayer);
      $card = DiscardRandom();
      $rv = "Discarded " . CardLink($card, $card);
      if(ModifiedPowerValue($card, $currentPlayer, "HAND", source:"wrecking_ball_red") >= 6) {
        Intimidate();
      }
      return "";
```

### wreck_havoc_yellow  — looks-aligned
text: "Defense reactions can't be played to this chain link.\n\nWhen this hits a hero, you may turn a card in their arsenal face up, then destroy a defense reaction in their arsenal."
```json
{
  "slug": "wreck_havoc_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "IN_COMBAT"
        }
      ],
      "effects": [
        {
          "type": "RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "REVEAL_TOP_DECK",
          "target": "opponent"
        },
        {
          "type": "DESTROY_TOKEN",
          "target": "opponent",
          "token_type": "DEFENSE_REACTION"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTHitEffect()
SetArsenalFacing("UP", $defPlayer);
        AddDecisionQueue("MULTIZONEINDICES", $mainPlayer, "THEIRARS:type=DR");
        AddDecisionQueue("SETDQCONTEXT", $mainPlayer, "Choose which card you want to destroy", 1);
        AddDecisionQueue("CHOOSEMULTIZONE", $mainPlayer, "<-", 1);
        AddDecisionQueue("MZDESTROY", $mainPlayer, "-", 1);
        break;
```

### song_of_jack_be_quick_blue  — looks-aligned
text: "Create a Quicken token under each other hero's control."
```json
{
  "slug": "song_of_jack_be_quick_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Quicken"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// TCCPlayAbility()
PlayAura("quicken", $otherPlayer);
      return "";
```

### cut_through_yellow  — looks-aligned
text: "If you've hit with a dagger this combat chain, this gets +1{p} and **go again**."
```json
{
  "slug": "cut_through_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DAGGER_HIT_THIS_COMBAT"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$numDaggerHits = 0;
        $chainLinksSummaryPieces = ChainLinkSummaryPieces();
        $chainLinksCount = count($chainLinks);
        for ($i = 0; $i < $chainLinksCount; ++$i) {
          if (SubtypeContains($chainLinks[$i][0], "Dagger") && $chainLinkSummary[$i * $chainLinksSummaryPieces] > 0) ++$numDaggerHits;
        }
        $numDaggerHits += $combatChainState[$CCS_FlickedDamage];
        $power += $numDaggerHits > 0 ? 1 : 0;
        break;
// DoesAttackHaveGoAgain()
$numDaggerHits = 0;
      $chainLinksCount = count($chainLinks);
      $chainLinkSummaryPieces = ChainLinkSummaryPieces();
        for($i=0; $i<$chainLinksCount; ++$i)
        {
          if(SubtypeContains($chainLinks[$i][0], "Dagger") && $chainLinkSummary[$i*$chainLinkSummaryPieces] > 0) ++$numDaggerHits;
        }
        $numDaggerHits += $combatChainState[$CCS_FlickedDamage];
      return $numDaggerHits > 0;
```

### breaking_scales  — looks-aligned
text: '**Attack Reaction** - Destroy Breaking Scales: Target attack action card with **combo** gains +1{p}.\n\n**Battleworn**'
```json
{
  "slug": "breaking_scales",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "HAS_KEYWORD",
              "keyword": "COMBO"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ReactionRequirementsMet()
case "breaking_scales": return HasCombo($combatChain[0]);
```

### blessing_of_focus_blue  — looks-aligned
text: "At the start of your turn, destroy Blessing of Focus then **opt 1** and reveal the top card of your deck. If it's an arrow, put it face up into your arsenal with an aim counter."
```json
{
  "slug": "blessing_of_focus_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "OPT",
          "amount": 1
        },
        {
          "type": "REVEAL_TOP_DECK",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "deck",
              "card_type": "arrow"
            }
          ],
          "effects": [
            {
              "type": "PUT_ARSENAL_BOTTOM",
              "card_type": "arrow",
              "add_counter": "aim"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
if ($auras[$i] == "blessing_of_focus_red") $amount = 3;
        else $amount = ($auras[$i] == "blessing_of_focus_yellow") ? 2 : 1;
        DestroyAuraUniqueID($mainPlayer, $auras[$i + 6]);
        PlayerOpt($mainPlayer, $amount);
        AddDecisionQueue("SPECIFICCARD", $mainPlayer, "BLESSINGOFFOCUS", 1);
        break;
```

### vengeful_apparition_yellow  — looks-aligned
text: 'When this leaves the arena, if you control no Illusionist auras, you may play your next aura with cost 1 or less this turn as though it were an instant. If you do, it enters the arena with a +1{p} counter.\n\n**Ward 1**'
```json
{
  "slug": "vengeful_apparition_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_LEAVE_PLAY",
      "conditions": [
        {
          "type": "NOT",
          "condition": {
            "type": "CONTROLS_TOKEN_TYPE",
            "token_type": "Illusionist"
          }
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "VENGEFUL_APPARITION_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "VENGEFUL_APPARITION_ACTIVE"
        }
      ],
      "effects": [
        {
          "type": "APPLY_CONTINUOUS",
          "effect": {
            "type": "PAY_OR_DAMAGE",
            "amount": 1,
            "damage_type": "ARCANE"
          },
          "target": {
            "type": "TOKEN",
            "token_type": "Aura",
            "cost_lte": 1
          }
        },
        {
          "type": "APPLY_CONTINUOUS",
          "effect": {
            "type": "PUT_COUNTER",
            "counter_type": "POWER",
            "amount": 1
          },
          "target": {
            "type": "TOKEN",
            "token_type": "Aura",
            "cost_lte": 1
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraLeavesPlay()
$illusionistAuras = SearchAura($player, class: "ILLUSIONIST");
      if ($illusionistAuras == "" || strpos($illusionistAuras, ",") === false) AddLayer("TRIGGER", $player, $cardID, "-", "-", $uniqueID);
      break;
// ProcessTrigger()
AddCurrentTurnEffect($parameter . "-INST", $player, "PLAY");
        break;
```

### mounting_anger_blue  — looks-aligned
text: 'When Mounting Anger hits, you may banish an attack action card from your hand with cost less than the number of Draconic chain links you control. If you do, it gains +1{p} and you may play it this turn.\n\n**Go again**'
```json
{
  "slug": "mounting_anger_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "BANISH",
          "target": "hand",
          "conditions": [
            {
              "type": "AND",
              "conditions": [
                {
                  "type": "CARD_IN_ZONE",
                  "zone": "hand",
                  "card_type": "attack"
                },
                {
                  "type": "ATTACK_COST_LTE",
                  "amount": {
                    "type": "COUNT_CONTROLLERS",
                    "controller_type": "draconic_chain_links"
                  }
                }
              ]
            }
          ]
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "BANISHED_ATTACK_ACTION"
            }
          ]
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "BANISHED_ATTACK_ACTION"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
$numDraconicLinks = NumDraconicChainLinks();
        MZMoveCard($mainPlayer, "MYHAND:type=AA;maxCost=" . ($numDraconicLinks > 0 ? $numDraconicLinks - 1 : -2), "MYBANISH,HAND,TT", may: true);
        AddDecisionQueue("PASSPARAMETER", $mainPlayer, "MYBANISH", 1);
        AddDecisionQueue("MZOP", $mainPlayer, "LASTMZINDEX", 1);
        AddDecisionQueue("MZOP", $mainPlayer, "GETUNIQUEID", 1);
        AddDecisionQueue("ADDLIMITEDCURRENTEFFECT", $mainPlayer, $parameter . ",HIT", 1);
        break;
// UPRNinjaHitEffect()
AddLayer("TRIGGER", $mainPlayer, $cardID);
        break;
// UPREffectPowerModifier()
case "mounting_anger_red": case "mounting_anger_yellow": case "mounting_anger_blue": return 1;
// UPRCombatEffectActive()
case "mounting_anger_red": case "mounting_anger_yellow": case "mounting_anger_blue": return true;
```

### pound_town_red  — looks-aligned
text: "**Beat Chest**\n\nWhen this attacks, if you've **beaten chest** this turn, create a Might token."
```json
{
  "slug": "pound_town_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BEAT_CHEST_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Might"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HVYPlayAbility()
if (SearchCurrentTurnEffects("BEATCHEST", $currentPlayer)) PlayAura("might", $currentPlayer);
      return "";
```

### wage_gold_blue  — looks-aligned
text: '**Universal**\n\nWhen this attacks a hero, you may **wager** a Gold token with them.'
```json
{
  "slug": "wage_gold_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "WAGER"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessWager()
PutItemIntoPlayForPlayer("gold", $wonWager, number:$amount, effectController:$mainPlayer);
        break;
// ResolveWagers()
if (!$chainClosed) {
              $triggerCardID = $currentTurnEffects[$i];
              AddLayer("TRIGGER", $mainPlayer, $triggerCardID, $wonWager, "WAGER");
            }
            RemoveCurrentTurnEffect($i);
            break;
// HVYPlayAbility()
if (IsHeroAttackTarget()) AskWager($cardID);
      return "";
```

### big_bertha_red  — looks-aligned
text: '**Boost**\n\nWhen this is banished from boosting, put a steam counter on a Hyper Driver you control.'
```json
{
  "slug": "big_bertha_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BECOME",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BOOSTED"
        }
      ],
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "steam",
          "target": {
            "type": "CARD",
            "subtype": "Hyper Driver",
            "controller": "self"
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
AddDecisionQueue("SETDQCONTEXT", $player, "Choose a Hyper Driver to get a steam counter", 1);
        AddDecisionQueue("MULTIZONEINDICES", $player, "MYITEMS:isSameName=hyper_driver_red");
        AddDecisionQueue("CHOOSEMULTIZONE", $player, "<-", 1);
        AddDecisionQueue("MZADDCOUNTER", $player, "-", 1);
        break;
// OnBoostedEffects()
AddLayer("TRIGGER", $player, $boosted);
      break;
```

### impulsive_desire_blue  — looks-aligned
text: '**Stealth**\n\nWhen this hits a hero, banish the top card of their deck.\n\nWhenever this banishes a reaction or instant card, gain 1{h}.'
```json
{
  "slug": "impulsive_desire_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": "OPPONENT_TOP_DECK"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BANISH",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "BANISHED",
          "card_type": "REACTION"
        },
        {
          "type": "OR",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "BANISHED",
              "card_type": "INSTANT"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "HEALTH",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTHitEffect()
if (IsHeroAttackTarget()) {
        $deck->BanishTop("Source-" . $attackCard, banishedBy: $attackCard);
      }
      break;
```

### runic_reaping_yellow  — looks-aligned
text: 'The next Runeblade attack action card you play this turn gains "When this hits, create 2 Runechant tokens".\n\nIf an attack card was pitched to play Runic Reaping, the next Runeblade attack action card you play this turn gains +1{p}.\n\n**Go again**'
```json
{
  "slug": "runic_reaping_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "RUNIC_REAPING_PLAYED_THIS_TURN"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "RUNIC_REAPING_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_HIT",
            "effects": [
              {
                "type": "CREATE_TOKEN",
                "token_type": "Runechant",
                "amount": 2
              }
            ]
          }
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "RUNIC_REAPING_PITCHED"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DYNPlayAbility()
$amount = match($cardID) { "runic_reaping_red" => 3, "runic_reaping_yellow" => 2, default => 1 };
      AddCurrentTurnEffect($cardID . "-HIT", $currentPlayer);
      if(SearchCardList($additionalCosts, $currentPlayer, "AA") != "") AddCurrentTurnEffect($cardID . "-BUFF", $currentPlayer);
      return "";
```

### tremor_of_iarathael_red  — looks-aligned
text: "If a card has been put into your banished zone this turn, Tremor of i'Arathael gains +2{p}."
```json
{
  "slug": "tremor_of_iarathael_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CARD_BANISHED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += GetClassState($mainPlayer, $CS_CardsBanished) > 0 ? 2 : 0;
        break;
```

### fervent_forerunner_yellow  — looks-aligned
text: 'If Fervent Forerunner hits, **opt 2**.\n\nIf Fervent Forerunner is played from arsenal, it gains **go again**.'
```json
{
  "slug": "fervent_forerunner_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "OPT",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "conditions": [
        {
          "type": "PLAYED_FROM_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ARCGenericPlayAbility()
if($from == "ARS") GiveAttackGoAgain();
      return "";
// ARCGenericHitEffect()
PlayerOpt($mainPlayer, 2);
      break;
```

### rake_the_embers_red  — looks-aligned
text: 'Create an Ash token, then **transform** up to 3 ash you control into Aether Ashwings.\n\n**Go again**'
```json
{
  "slug": "rake_the_embers_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Ash"
        },
        {
          "type": "TRANSFORM_HERO",
          "from": "Ash",
          "to": "Aether Ashwings",
          "max_count": 3
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// UPRIllusionistPlayAbility()
PutPermanentIntoPlay($currentPlayer, "ash");
        $maxTransform = match($cardID) { "rake_the_embers_red" => 3, "rake_the_embers_yellow" => 2, default => 1 };
        for($i=0; $i<$maxTransform; ++$i) Transform($currentPlayer, "Ash", "aether_ashwing", true, ($i == 0 ? false : true), ($i == 0 ? false : true));
        return "";
```

### rout_red  — looks-aligned
text: 'Target weapon attack gains +3{p}.\n\n**Reprise** - If the defending hero has defended with a card from their hand this chain link, you may return target non-equipment defending card to its owners hand.'
```json
{
  "slug": "rout_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "REPRISE_ACTIVE"
        },
        {
          "type": "DEFENDS_WITH_OTHER_HAND_CARD"
        }
      ],
      "effects": [
        {
          "type": "RETURN_TO_HAND",
          "target": "defending_card",
          "conditions": [
            {
              "type": "NOT",
              "condition": {
                "type": "HAS_KEYWORD",
                "keyword": "EQUIPMENT"
              }
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if (!$CombatChain->HasCurrentLink()) return true;
      if (SearchCombatChainAttacks($mainPlayer, type:"W") != "") return false;
      if (TypeContains($attackID, "W", $mainPlayer)) return false;
      return true;
// ReactionRequirementsMet()
case "stroke_of_foresight_red": case "stroke_of_foresight_yellow": case "stroke_of_foresight_blue": return TypeContains($combatChain[0], "W", $mainPlayer);
// GetLayerTarget()
AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "COMBATCHAINATTACKS:type=W&ACTIVEATTACK:type=W");
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a weapon attack");
      AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
      AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);  
      AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      break;
// WTREffectPowerModifier()
case "rout_red": return 3;
// WTRCombatEffectActive()
case "rout_red": case "singing_steelblade_yellow": case "overpower_red": case "overpower_yellow": case "overpower_blue": return true;
// WTRPlayAbility()
$options = GetChainLinkCards($defPlayer, "", "E,C", exclCardSubTypes:"Evo");
        if(RepriseActive() && $options != "") {
          AddDecisionQueue("MAYCHOOSECOMBATCHAIN", $mainPlayer, $options);
          AddDecisionQueue("ADDHANDOWNER", $defPlayer, "-", 1);
          AddDecisionQueue("REMOVECOMBATCHAIN", $mainPlayer, "-", 1);
        }
        if (!str_contains($target, "COMBATCHAINATTACKS")) AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### flock_of_the_feather_walkers_red  — looks-aligned
text: 'As an additional cost to play Flock of the Feather Walkers, reveal a card in your hand with cost 1 or less.\n\nWhen you attack with Flock of the Feather Walkers, create a Quicken token.'
```json
{
  "slug": "flock_of_the_feather_walkers_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "REVEAL_CARD_COST_LTE",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Quicken"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return SearchCount(SearchHand($currentPlayer, "", "", 1, 0)) < 1;
// PayAdditionalCosts()
$indices = SearchHand($currentPlayer, "", "", 1, 0);
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a card to reveal");
      AddDecisionQueue("CHOOSEHANDCANCEL", $currentPlayer, $indices);
      AddDecisionQueue("REVEALHANDCARDS", $currentPlayer, "-");
      break;
// WTRPlayAbility()
PlayAura("quicken", $currentPlayer);
        return "";
```

### tide_chakra_blue  — looks-aligned
text: "Target Assassin or Mystic attack action card gets +1{p}. If you've **transcended** this turn, instead it gets +3{p}."
```json
{
  "slug": "tide_chakra_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "TRANSCEDED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if (!$CombatChain->HasCurrentLink()) return true;
      if (CardType($attackID) == "AA" && (ClassContains($attackID, "ASSASSIN", $player) || TalentContains($attackID, "MYSTIC", $player))) return false;
      return true;
// MSTPlayAbility()
if (GetClassState($currentPlayer, $CS_Transcended) <= 0) AddCurrentTurnEffect($cardID . "-1", $currentPlayer);
      else AddCurrentTurnEffect($cardID . "-2", $currentPlayer);
      return "";
```

### be_like_water_blue  — looks-aligned
text: 'When this hits, you may pay {r}. If you do, choose Head Jab, Surging Strike, or Twin Twisters. This gains the chosen name.\n\n**Go again**'
```json
{
  "slug": "be_like_water_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "amount": 1,
          "on_success": [
            {
              "type": "CHOOSE",
              "options": [
                {
                  "name": "Head Jab",
                  "effects": [
                    {
                      "type": "MODIFY_ATTACK",
                      "mod": "add",
                      "amount": 1
                    }
                  ]
                },
                {
                  "name": "Surging Strike",
                  "effects": [
                    {
                      "type": "MODIFY_ATTACK",
                      "mod": "add",
                      "amount": 2
                    }
                  ]
                },
                {
                  "name": "Twin Twisters",
                  "effects": [
                    {
                      "type": "MODIFY_ATTACK",
                      "mod": "add",
                      "amount": 3
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CurrentEffectNameModifier()
$name = $effectParameter;
      break;
// OUTCombatEffectActive()
case "be_like_water_red": case "be_like_water_yellow": case "be_like_water_blue": return true;
// OUTHitEffect()
$hand = &GetHand($mainPlayer);
        $resources = &GetResources($mainPlayer);
        if(Count($hand) > 0 || $resources[0] > 0)
        {
          AddDecisionQueue("YESNO", $mainPlayer, "if you want to pay 1 to give ".CardLink($cardID, $cardID)." a name", 0, 1);
          AddDecisionQueue("NOPASS", $mainPlayer, "-", 1);
          AddDecisionQueue("PASSPARAMETER", $mainPlayer, "1", 1);
          AddDecisionQueue("PAYRESOURCES", $mainPlayer, "<-", 1);
          AddDecisionQueue("BUTTONINPUT", $mainPlayer, "Head_Jab,Surging_Strike,Twin_Twisters", 1);
          AddDecisionQueue("SETDQVAR", $mainPlayer, "0", 1);
          AddDecisionQueue("WRITELOG", $mainPlayer, CardLink($cardID) . " gains the name <b>{0}</b>", 1);
          AddDecisionQueue("PREPENDLASTRESULT", $mainPlayer, $cardID . "-", 1);
          AddDecisionQueue("ADDCURRENTTURNEFFECT", $mainPlayer, "<-", 1);
        }
        break;
```

### runerager_swarm_blue  — looks-aligned
text: "If you've played or created an aura this turn, this gets **go again**."
```json
{
  "slug": "runerager_swarm_blue",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "AURA_PLAYED_OR_CREATED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesAttackHaveGoAgain()
return GetClassState($mainPlayer, $CS_NumAuras) > 0;
```

### rumble_grunting_yellow  — looks-aligned
text: "Play Rumble Grunting only if you've discarded a card with 6 or more {p} this turn.\n\nYour next Brute attack this turn gains +3{p}.\n\n**Go again**"
```json
{
  "slug": "rumble_grunting_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "DISCARD_CARD",
          "conditions": [
            {
              "type": "DISCARDED_CARD_POWER_GTE",
              "amount": 6
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "RUMBLE_GRUNTING_ACTIVE"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "RUMBLE_GRUNTING_ACTIVE"
        },
        {
          "type": "IS_ACTIVE_PLAYER"
        },
        {
          "type": "ATTACK_CLASS_IN",
          "classes": [
            "Brute"
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return GetClassState($mainPlayer, $CS_Num6PowDisc) > 0 ? 0 : 1;
// DYNEffectPowerModifier()
case "rumble_grunting_yellow": return 3;
// DYNCombatEffectActive()
case "rumble_grunting_red": case "rumble_grunting_yellow": case "rumble_grunting_blue": return ClassContains($attackID, "BRUTE", $mainPlayer);
// DYNPlayAbility()
case "rumble_grunting_red": case "rumble_grunting_yellow": case "rumble_grunting_blue": AddCurrentTurnEffect($cardID, $currentPlayer); return "";
```

### humble_yellow  — looks-aligned
text: 'When this hits a hero, they lose all hero card abilities until the end of their next turn.'
```json
{
  "slug": "humble_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "HUMBLE_ACTIVE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTHitEffect()
if(IsHeroAttackTarget())
        {
          AddCurrentTurnEffect($cardID, $defPlayer);
          AddNextTurnEffect($cardID, $defPlayer);
          $char = &GetPlayerCharacter($defPlayer);
          $char[1] = 3;
        }
        break;
```

### demolition_crew_red  — looks-aligned
text: 'As an additional cost to play Demolition Crew, reveal a card in your hand with cost 2 or greater.\n\n**Dominate**'
```json
{
  "slug": "demolition_crew_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "REVEAL_CARD_COST_GTE",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "DOMINATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return SearchCount(SearchHand($currentPlayer, "", "", -1, 2)) < 1;
// HasDominate()
return true;
// IsDominateActive()
return true;
// PayAdditionalCosts()
$indices = SearchHand($currentPlayer, "", "", -1, 2);
      AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a card to reveal");
      AddDecisionQueue("CHOOSEHANDCANCEL", $currentPlayer, $indices);
      AddDecisionQueue("REVEALHANDCARDS", $currentPlayer, "-");
      break;
```

### blessing_of_occult_red  — looks-aligned
text: 'At the start of your turn, destroy Blessing of Occult then create 3 Runechant tokens.'
```json
{
  "slug": "blessing_of_occult_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraStartTurnAbilities()
if ($auras[$i] == "blessing_of_occult_red") $amount = 3;
        else $amount = ($auras[$i] == "blessing_of_occult_yellow") ? 2 : 1;
        PlayAura("runechant", $mainPlayer, $amount, true);
        DestroyAuraUniqueID($mainPlayer, $auras[$i + 6]);
        break;
```

### spire_sniping_yellow  — looks-aligned
text: 'When Spire Sniping is put or turned face up in arsenal, look at the top 2 cards of your deck, then put them back in any order.'
```json
{
  "slug": "spire_sniping_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "effects": [
        {
          "type": "LOOK_AT",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddArsenal()
SpireSnipingAbility($player);
        break;
// ArsenalTurnFaceUpAbility()
SpireSnipingAbility($player);
      break;
```

### leap_frog_vocal_sac  — looks-aligned
text: 'When an opponent plays or activates an attack reaction, you may add this to the active chain link as a defending card.\n\n**Blade Break**'
```json
{
  "slug": "leap_frog_vocal_sac",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ACTIVATE",
      "conditions": [
        {
          "type": "OR",
          "conditions": [
            {
              "type": "ON_PLAY_ACTIVATE_ATTACK"
            },
            {
              "type": "ON_ACTIVATE",
              "conditions": [
                {
                  "type": "ATTACK_REACTION"
                }
              ]
            }
          ]
        },
        {
          "type": "CONTROLS_ATTACK_ACTION",
          "opponent": true
        }
      ],
      "effects": [
        {
          "type": "ADD_DEFEND",
          "target": "self"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// canBeAddedToChainDuringDR()
return true;
// AddCharacterPlayCardTrigger()
if ($playType == "AR" && SearchCharacterActive($otherPlayer, $otherChar[$i], checkGem: true)) {
          AddLayer("TRIGGER", $otherPlayer, $otherChar[$i]);
        }
        break;
// ProcessTrigger()
AddDecisionQueue("YESNO", $player, "if_you_want_to_add_".Cardlink($parameter,$parameter)."_to_active_chain_link");
        AddDecisionQueue("NOPASS", $player, "-", 1);
        AddDecisionQueue("LEAPFROG", $player, $parameter, 1);
        break;
```

### quickfire_red  — looks-aligned
text: 'This costs {r} less to play for each Hyper Driver you control.\n\nThe next attack you **boost** this turn gets +4{p}.\n\n**Go again**'
```json
{
  "slug": "quickfire_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "BOOSTED_ATTACK_THIS_TURN"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// SelfCostModifier()
return SearchCount(SearchMultizone($currentPlayer, "MYITEMS:isSameName=hyper_driver_red")) * -1;
// EVOPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### a_drop_in_the_ocean_blue  — looks-aligned
text: "**Legendary**\n\nTarget attack gets -1{p}.\n\nIf you've played another blue card this turn, **transcend**."
```json
{
  "slug": "a_drop_in_the_ocean_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "subtract",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BLUE_CARD_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "TRANSFORM_HERO",
          "hero": "Transcend"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// GoesWhereAfterResolving()
if (GetClassState($currentPlayer, $CS_NumBluePlayed) > 1) return "-";
        else return "THEIRDISCARD";
// GoesWhereAfterResolving()
if (GetClassState($currentPlayer, $CS_NumBluePlayed) > 1) return "-";
      else return "GY";
// IsPlayRestricted()
if ($CombatChain->HasCurrentLink()) return false;//If there's an attack, there's a valid target
      if (count($chainLinks) > 0) return false; //If there's an attack on previous chain links, there's a valid target
      return !IsLayerStep();
// GetLayerTarget()
$inds = MultiZoneIndices($currentPlayer, "COMBATCHAINATTACKS&ACTIVEATTACK");
      if ($inds == "PASS") $inds = "";
      if (IsLayerStep()) {
        if ($inds == "PASS") $inds .= ",LAYER-" . $Stack->BottomLayer()->Index();
        else $inds = "LAYER-" . $Stack->BottomLayer()->Index();
      }
      if ($inds != "") {
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, $inds);
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose an attack");
        AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);  
        AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      }
      break;
// MSTPlayAbility()
if ($target == "COMBATCHAINLINK-0" || str_contains($target, "LAYER")) AddCurrentTurnEffect($cardID, $mainPlayer);
      if (GetClassState($currentPlayer, $CS_NumBluePlayed) > 1) AddDecisionQueue("TRANSCEND", $currentPlayer, "MST095_inner_chi_blue," . $from);
      return "";
```

### overload_yellow  — looks-aligned
text: '**Dominate**\n\nIf Overload hits, it gains **go again**.'
```json
{
  "slug": "overload_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HasDominate()
return true;
// IsDominateActive()
return true;
// MONGenericHitEffect()
case "overload_red": case "overload_yellow": case "overload_blue": GiveAttackGoAgain(); break;
```

### brandish_yellow  — looks-aligned
text: 'If Brandish hits, your next weapon attack this turn gains +1{p}.\n\n**Go again**'
```json
{
  "slug": "brandish_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "BRANDISH_HIT"
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MONGenericHitEffect()
case "brandish_red": case "brandish_yellow": case "brandish_blue": AddCurrentTurnEffectFromCombat($cardID, $mainPlayer); break;
// MONEffectPowerModifier()
case "brandish_red": case "brandish_yellow": case "brandish_blue": return 1;
// MONCombatEffectActive()
case "brandish_red": case "brandish_yellow": case "brandish_blue": return IsWeaponAttack();
```

### lay_waste_blue  — looks-aligned
text: "**Boost**\n\nThis can't be defended by equipment."
```json
{
  "slug": "lay_waste_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CanBlockWithEquipment()
return false;
```

### herald_of_ravages_red  — looks-aligned
text: "When this hits, put it into your hero's soul and deal 1 arcane damage to target hero.\n\n**Phantasm**"
```json
{
  "slug": "herald_of_ravages_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "PUT_SELF_BOTTOM_DECK"
        },
        {
          "type": "DEAL_ARCANE",
          "amount": 1,
          "target": "hero"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MONIllusionistHitEffect()
DealArcane(1, 0, "PLAYCARD", $cardID, false, $mainPlayer);
        if (DoesAttackHaveGoAgain()) GiveAttackGoAgain();
        $combatChainState[$CCS_GoesWhereAfterLinkResolves] = "-"; 
        AddSoul($attackCard, $mainPlayer, "CC");
        break;
```

### conduit_of_frostburn  — looks-aligned
text: '**Instant** - Destroy Conduit of Frostburn: The next card you play this turn with an effect that deals arcane damage gains "When this deals arcane damage to a hero, destroy a **frozen** card in their arsenal."\n\n**Quell 1**'
```json
{
  "slug": "conduit_of_frostburn",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_PLAY_ACTIVATE_ATTACK",
          "conditions": [
            {
              "type": "HAS_KEYWORD",
              "keyword": "DEAL_ARCANE"
            }
          ],
          "effects": [
            {
              "type": "TRIGGERED",
              "trigger": "ON_DEAL_ARCANE",
              "effects": [
                {
                  "type": "DESTROY_TOKEN",
                  "conditions": [
                    {
                      "type": "HAS_KEYWORD",
                      "keyword": "FROZEN"
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// UPRAbilityType()
case "conduit_of_frostburn": return "I";
// UPRWizardPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
```

### phantasmify_blue  — looks-aligned
text: 'The next attack action card you play this turn is Illusionist in addition to its other class types, and gains +3{p} and **phantasm**.\n\n**Go again**'
```json
{
  "slug": "phantasmify_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "PHANTASMIFY_ACTIVE"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "PHANTASMIFY_ACTIVE"
        },
        {
          "type": "DURING_TURN"
        },
        {
          "type": "CARD_IN_ZONE",
          "zone": "HAND",
          "card_type": "ACTION"
        }
      ],
      "effects": [
        {
          "type": "GRANT_SUBTYPE",
          "subtype": "Illusionist"
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        },
        {
          "type": "SET_FLAG",
          "flag": "PHANTASM"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ClassOverride()
$classes[] = "ILLUSIONIST";
        break;
// MONIllusionistPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
// MONEffectPowerModifier()
case "phantasmify_blue": return 3;
// MONCombatEffectActive()
case "phantasmify_red": case "phantasmify_yellow": case "phantasmify_blue": return CardType($attackID) == "AA";
```

### cut_through_red  — looks-aligned
text: "If you've hit with a dagger this combat chain, this gets +1{p} and **go again**."
```json
{
  "slug": "cut_through_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DAGGER_HIT_THIS_COMBAT"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$numDaggerHits = 0;
        $chainLinksSummaryPieces = ChainLinkSummaryPieces();
        $chainLinksCount = count($chainLinks);
        for ($i = 0; $i < $chainLinksCount; ++$i) {
          if (SubtypeContains($chainLinks[$i][0], "Dagger") && $chainLinkSummary[$i * $chainLinksSummaryPieces] > 0) ++$numDaggerHits;
        }
        $numDaggerHits += $combatChainState[$CCS_FlickedDamage];
        $power += $numDaggerHits > 0 ? 1 : 0;
        break;
// DoesAttackHaveGoAgain()
$numDaggerHits = 0;
      $chainLinksCount = count($chainLinks);
      $chainLinkSummaryPieces = ChainLinkSummaryPieces();
        for($i=0; $i<$chainLinksCount; ++$i)
        {
          if(SubtypeContains($chainLinks[$i][0], "Dagger") && $chainLinkSummary[$i*$chainLinkSummaryPieces] > 0) ++$numDaggerHits;
        }
        $numDaggerHits += $combatChainState[$CCS_FlickedDamage];
      return $numDaggerHits > 0;
```

### humble_red  — looks-aligned
text: 'When this hits a hero, they lose all hero card abilities until the end of their next turn.'
```json
{
  "slug": "humble_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "HUMBLE_ACTIVE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// OUTHitEffect()
if(IsHeroAttackTarget())
        {
          AddCurrentTurnEffect($cardID, $defPlayer);
          AddNextTurnEffect($cardID, $defPlayer);
          $char = &GetPlayerCharacter($defPlayer);
          $char[1] = 3;
        }
        break;
```

### herald_of_triumph_blue  — looks-aligned
text: 'Attack action cards get -1{p} while defending this.\n\nWhen this hits, put it into your soul.\n\n**Phantasm**'
```json
{
  "slug": "herald_of_triumph_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "subtract",
          "amount": 1,
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "DEFENDING",
              "card_type": "ATTACK_ACTION"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "PUT_SELF_BOTTOM_DECK",
          "zone": "SOUL"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EffectDefenderPowerModifiers()
$mod -= 1;
          break;
// MONIllusionistPlayAbility()
AddCurrentTurnEffect($cardID, $defPlayer);
        return "";
// MONIllusionistHitEffect()
if (DoesAttackHaveGoAgain()) GiveAttackGoAgain();
        $combatChainState[$CCS_GoesWhereAfterLinkResolves] = "-"; 
        AddSoul($attackCard, $mainPlayer, "CC");
        break;
// MONEffectPowerModifier()
case "herald_of_triumph_red": case "herald_of_triumph_yellow": case "herald_of_triumph_blue": return -1;
// MONCombatEffectActive()
case "herald_of_triumph_red": case "herald_of_triumph_yellow": case "herald_of_triumph_blue": return CardType($attackID) == "AA";
```

### harmony_of_the_hunt_blue  — looks-aligned
text: "When this attacks, if you've pitched a blue card this turn, create a Crouching Tiger in your hand.\n\n**Go again**"
```json
{
  "slug": "harmony_of_the_hunt_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "PITCHED_BLUE_CARD_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Crouching Tiger",
          "zone": "HAND"
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTPlayAbility()
if (SearchPitchForColor($currentPlayer, 3) > 0) AddPlayerHand("crouching_tiger", $currentPlayer, $cardID, created:true);
      return "";
```

### driving_blade_yellow  — looks-aligned
text: 'Your next weapon attack this turn gains +2{p} and **go again**.\n\n**Go again**'
```json
{
  "slug": "driving_blade_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "DRIVING_BLADE_ACTIVE"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DRIVING_BLADE_ACTIVE"
        },
        {
          "type": "DURING_TURN"
        },
        {
          "type": "ATTACK_IS_WEAPON"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesCurrentTurnEffectGrantGoAgain()
return true;
// WTREffectPowerModifier()
case "driving_blade_yellow": return 2;
// WTRCombatEffectActive()
case "driving_blade_red": case "driving_blade_yellow": case "driving_blade_blue": return TypeContains($attackID, "W", $mainPlayer);
// WTRPlayAbility()
AddCurrentTurnEffect($cardID, $mainPlayer);
        return "";
```

### silver_talons_red  — looks-aligned
text: 'When this attacks a hero, if it is Draconic, you may have target dagger you control deal 1 damage to them. If damage is dealt this way, the dagger has hit. Destroy the dagger.'
```json
{
  "slug": "silver_talons_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_TARGET_IS_HERO"
            },
            {
              "type": "ATTACK_CLASS_IN",
              "classes": [
                "Draconic"
              ]
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "MAY",
          "effects": [
            {
              "type": "SELECT_FROM_REF",
              "ref": "dagger",
              "conditions": [
                {
                  "type": "CONTROLS_ATTACK_ACTION"
                }
              ],
              "effects": [
                {
                  "type": "DEAL_GENERIC",
                  "amount": 1,
                  "target": "opponent"
                },
                {
                  "type": "SET_FLAG",
                  "flag": "DAGGER_HAS_HIT"
                },
                {
                  "type": "DESTROY_REF",
                  "ref": "dagger"
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HNTPlayAbility()
if(TalentContains($cardID, "DRACONIC", $currentPlayer) && IsHeroAttackTarget()) {
        ThrowWeapon("Dagger", $cardID, true);
      }
      break;
```

### torque_tuned_red  — looks-aligned
text: 'If an item you control has been destroyed this turn, this gets **overpower**.\n\n**Galvanize** - When this defends, you may destroy an item you control. If you do, this gets +2{d}.'
```json
{
  "slug": "torque_tuned_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ITEM_DESTROYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "OVERPOWER"
        }
      ]
    },
    {
      "ability_type": "DEFENSE_REACTION",
      "effects": [
        {
          "type": "MAY",
          "effects": [
            {
              "type": "DESTROY_PERMANENT",
              "target": "item"
            },
            {
              "type": "MODIFY_DEFENSE_VALUE",
              "mod": "add",
              "amount": 2
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
case "steel_street_hoons_blue": //Galvanize
// IsOverpowerActive()
return GetClassState($mainPlayer, $CS_NumItemsDestroyed) > 0;
```

### crankshaft_blue  — looks-aligned
text: '**Boost**\n\nWhen this is banished from boosting, put a steam counter on a Hyper Driver you control.'
```json
{
  "slug": "crankshaft_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_LEAVE_PLAY",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BOOSTED"
        }
      ],
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "steam",
          "target": "self",
          "conditions": [
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "Hyper Driver"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
AddDecisionQueue("MULTIZONEINDICES", $player, "MYITEMS:isSameName=hyper_driver_red");
        AddDecisionQueue("SETDQCONTEXT", $player, "Choose a ".Cardlink("hyper_driver", "hyper_driver")." to get a steam counter", 1);
        AddDecisionQueue("CHOOSEMULTIZONE", $player, "<-", 1);
        AddDecisionQueue("MZADDCOUNTER", $player, "-", 1);
        break;
```

### out_pace_red  — looks-aligned
text: "**Boost**\n\nThis can't be defended by equipment."
```json
{
  "slug": "out_pace_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CanBlockWithEquipment()
return false;
```

### phantasmify_yellow  — looks-aligned
text: 'The next attack action card you play this turn is Illusionist in addition to its other class types, and gains +4{p} and **phantasm**.\n\n**Go again**'
```json
{
  "slug": "phantasmify_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "PHANTASMIFY_ACTIVE"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "PHANTASMIFY_ACTIVE"
        },
        {
          "type": "DURING_TURN"
        },
        {
          "type": "CARD_IN_ZONE",
          "zone": "HAND",
          "card_type": "ACTION"
        }
      ],
      "effects": [
        {
          "type": "GRANT_SUBTYPE",
          "subtype": "Illusionist"
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4
        },
        {
          "type": "SET_FLAG",
          "flag": "PHANTASM"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ClassOverride()
$classes[] = "ILLUSIONIST";
        break;
// MONIllusionistPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
// MONEffectPowerModifier()
case "phantasmify_yellow": return 4;
// MONCombatEffectActive()
case "phantasmify_red": case "phantasmify_yellow": case "phantasmify_blue": return CardType($attackID) == "AA";
```

### valiant_thrust_blue  — looks-aligned
text: "If you've **charged** this turn, Valiant Thrust gains +3{p}."
```json
{
  "slug": "valiant_thrust_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CHARGED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += GetClassState($mainPlayer, $CS_NumCharged) > 0 ? 3 : 0;
        break;
```

### sigil_of_protection_red  — looks-aligned
text: '**Ward 4**\n\nAt the beginning of your action phase, destroy Sigil of Protection.'
```json
{
  "slug": "sigil_of_protection_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "amount": 4
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraBeginningActionPhaseAbilities()
AddLayer("TRIGGER", $mainPlayer, $auras[$i], "-", "DESTROY", $auras[$i + 6]);
        break;
// ProcessTrigger()
case $CID_Frailty:
```

### patch_the_hole  — looks-aligned
text: '**Instant** - Destroy this: Return a card from your arsenal to your hand.'
```json
{
  "slug": "patch_the_hole",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "RETURN_TO_HAND",
          "zone": "arsenal"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// SEAPlayAbility()
MZMoveCard($currentPlayer, "MYARS", "MYHAND", silent: true);
      break;
```

### v_for_valor_yellow  — looks-aligned
text: "**Attack Reaction** - {r}, destroy this, **charge** your hero's soul: Target attack gains +2{p}."
```json
{
  "slug": "v_for_valor_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "cost": [
        {
          "type": "PAY_RESOURCES",
          "amount": 1
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "CHARGE",
          "target": "hero_soul"
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PayAuraAbilityAdditionalCosts()
$hand = &GetHand($currentPlayer);
      if (count($hand) == 0) {
        WriteLog("You do not have a card to charge. Reverting gamestate.", highlight: true);
        RevertGamestate();
        return;
      }
      DestroyAura($currentPlayer, $index);
      Charge(may: false);
      break;
// IsPlayRestricted()
$hand = &GetHand($currentPlayer);
      return $from == "PLAY" && count($hand) == 0;
// DTDAbilityCost()
case "v_for_valor_red": case "v_for_valor_yellow": case "v_for_valor_blue": return 1;
// DTDAbilityType()
case "v_for_valor_red": case "v_for_valor_yellow": case "v_for_valor_blue": return "AR";
// DTDEffectPowerModifier()
case "v_for_valor_yellow": return 2;
// DTDCombatEffectActive()
case "v_for_valor_red": case "v_for_valor_yellow": case "v_for_valor_blue": return true;
// DTDPlayAbility()
case "v_for_valor_red": case "v_for_valor_yellow": case "v_for_valor_blue"://V for Valor
```

### figment_of_tenacity_yellow  — looks-aligned
text: '**Legendary**\n\nWhen this enters the arena, your next attack this turn gets **dominate**.'
```json
{
  "slug": "figment_of_tenacity_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "DOMINATE_NEXT_ATTACK"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DoesEffectGrantsDominate()
return true;
// DTDCombatEffectActive()
case "figment_of_tenacity_yellow": return true;
// DTDPlayAbility()
if(count($combatChain) > 0 || IsLayerStep()) AddCurrentTurnEffectFromCombat($cardID, $currentPlayer);
      else AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### platinum_amulet_blue  — looks-aligned
text: '**Instant** - Destroy this: Target defending card gets +1{d} until end of turn.\n\n**Legend of the Watery Grave**'
```json
{
  "slug": "platinum_amulet_blue",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 1,
          "duration": "end_of_turn"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return $from == "PLAY" && NumCardsBlocking() < 1;
// OnBlockEffects()
$charInd = SearchCharacterForUniqueID($currentTurnEffects[$i+2], $defPlayer);
          $defChar = GetPlayerCharacter($defPlayer);
          if($charInd != -1 && $defChar[$charInd] == $chainCard->ID()) {
            $chainCard->ModifyDefense(1);
          }
          break;
// PayItemAbilityAdditionalCosts()
DestroyItemForPlayer($currentPlayer, $index);
      break;
// GetLayerTarget()
if ($from == "PLAY"){
        $numOptions = explode(",", GetChainLinkCards($defPlayer, "", "C"));
        $options = [];
        foreach ($numOptions as $num) $options[] = "COMBATCHAINLINK-$num";
        $options = implode(",", $options);
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a defending card to buff");
        AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, $options, 1);
        AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);
        AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      }
      break;
// PlayCardEffect()
break;
// SEAPlayAbility()
if($from == "PLAY") {
        $targetCard = GetMZCard($currentPlayer, $target);
        $targetInd = explode("-", $target, 2)[1];
        if (TypeContains($targetCard, "E")) {
          // I'm going to assume that a player can't have two copies of the same blocking equipment
          AddCurrentTurnEffect($cardID, $defPlayer, uniqueID:$combatChain[$targetInd+8]);
          CombatChainDefenseModifier($targetInd, 1);
        }
        else {
          CombatChainDefenseModifier($targetInd, 1);
        }
      }
      return "";
```

### cartilage_crush_blue  — looks-aligned
text: '**Crush** - When this deals 4 or more damage to a hero, their first action during their next turn costs an additional {r} to play or activate.'
```json
{
  "slug": "cartilage_crush_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CRUSH",
      "conditions": [
        {
          "type": "DID_NOT_HIT",
          "amount": 4
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "CARTILAGE_CRUSH_ACTIVE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CurrentEffectCostModifiers()
if (IsAction($cardID, $from)) {
            $costModifier += 1;
            $remove = true;
          }
          break;
// ProcessCrushEffect()
AddNextTurnEffect($cardID, $defPlayer);
        break;
```

### scrap_hopper_yellow  — looks-aligned
text: '**Scrap**\n\nWhen this attacks, if it **scrapped** a card, create a Quicken token.'
```json
{
  "slug": "scrap_hopper_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SCRAPPED_CARD"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Quicken"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVOPlayAbility()
if (DelimStringContains($additionalCosts, "SCRAP", true)) PlayAura("quicken", $currentPlayer);
      return "";
```

### monstrous_veil  — looks-aligned
text: '**Rhinar Specialization**\n\n**Action** - Destroy this: Draw a card then discard a random card. **Go again**\n\n**Battleworn**'
```json
{
  "slug": "monstrous_veil",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "DISCARD_RANDOM"
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// HVYPlayAbility()
Draw($currentPlayer);
      DiscardRandom($currentPlayer, $cardID);
      return "";
```

### riled_up_yellow  — looks-aligned
text: "If you've discarded a card with 6 or more {p} this turn, this gets +1{p}."
```json
{
  "slug": "riled_up_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DISCARDED_HIGH_POWER_CARD_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += (GetClassState($mainPlayer, $CS_Num6PowDisc) > 0 ? 1 : 0);
        break;
```

### gallow_end_of_the_line_yellow  — looks-aligned
text: "**Action** - {r}, {t}: **Attack**\n\n**Instant** - {t}, discard a card with watery grave: Until end of turn, effects controlled by opponents don't trigger when their attacks hit.\n\n**Watery Grave**"
```json
{
  "slug": "gallow_end_of_the_line_yellow",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "PITCH",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "ATTACK"
        }
      ]
    },
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "PITCH",
          "amount": 2
        },
        {
          "type": "DISCARD_CARD",
          "conditions": [
            {
              "type": "HAS_KEYWORD",
              "keyword": "WATERY_GRAVE"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "WATERY_GRAVE_ACTIVE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// BlockValue()
$block = -1;
      break;
```

### terra  — looks-aligned
text: 'At the beginning of each end phase, if there is an Earth card in your pitch zone, you may pay {r}. If you do, create a Might token.\n\n**Essence of Earth**'
```json
{
  "slug": "terra",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "pitch",
          "card_type": "Earth"
        }
      ],
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "resource": "RESOURCE_POINTS",
          "amount": 1,
          "on_success": [
            {
              "type": "CREATE_TOKEN",
              "token_type": "Might"
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
TerraEndPhaseAbility($parameter, $player);
        break;
// MainCharacterBeginEndPhaseTriggers()
AddLayer("TRIGGER", $mainPlayer, $characterID);
        break;
// MainCharacterBeginEndPhaseTriggers()
AddLayer("TRIGGER", $defPlayer, $characterID);
        break;
// isCardLegalinHero()
$heroTalent[] = "EARTH"; break;
// return_Hero_Type()
return Young;
		break;
```

### teklo_foundry_heart  — looks-aligned
text: "**Once per Turn Action** - {r}: Banish the top 2 cards of your deck. Gain {r} for each Mechanologist card banished this way. Activate this ability only if you've **boosted** this turn. **Go again**\n\n**Battleworn**"
```json
{
  "slug": "teklo_foundry_heart",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BOOSTED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "amount": 2
        },
        {
          "type": "GAIN",
          "keyword": "RESOURCE_POINTS",
          "amount": 1,
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "BANISHED",
              "card_class": "Mechanologist"
            }
          ]
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return GetClassState($player, $CS_NumBoosted) < 1;
// ARCMechanologistPlayAbility()
$deck = new Deck($currentPlayer);
      for($i = 0; $i < 2 && !$deck->Empty(); ++$i) {
        $banished = $deck->BanishTop();
        if(ClassContains($banished, "MECHANOLOGIST", $currentPlayer)) GainResources($currentPlayer, 1);
      }
      return "";
// ARCAbilityCost()
case "teklo_foundry_heart": return 1;
// ARCAbilityType()
case "teklo_foundry_heart": return "A";
// ARCAbilityHasGoAgain()
case "teklo_foundry_heart": return true;
```

### sizzle_red  — looks-aligned
text: 'Your next Lightning or Elemental attack this turn gets +3{p}.\n\n**Go again**'
```json
{
  "slug": "sizzle_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "DURING_TURN",
              "player": "self"
            },
            {
              "type": "OR",
              "conditions": [
                {
                  "type": "ATTACK_CLASS_IN",
                  "class": "Lightning"
                },
                {
                  "type": "ATTACK_CLASS_IN",
                  "class": "Elemental"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AURPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### reinforce_the_line_blue  — looks-aligned
text: 'Target defending attack action card gets +2{d}.'
```json
{
  "slug": "reinforce_the_line_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
$found = SearchCombatChainLink($player, "AA");
      return $found == "" || $found == "0";
// PlayBlockModifier()
return 2;
// CRUPlayAbility()
$options = GetChainLinkCards($defPlayer, "AA");
      if($options == "") return "No defending attack action cards";
      AddDecisionQueue("CHOOSECOMBATCHAIN", $currentPlayer, $options);
      AddDecisionQueue("COMBATCHAINDEFENSEMODIFIER", $currentPlayer, PlayBlockModifier($cardID), 1);
      return "";
```

### smash_and_grab_red  — looks-aligned
text: 'If you\'ve **boosted** 2 or more times this turn, this gets +2{p} and "When this hits a hero, gain control of an item they control."'
```json
{
  "slug": "smash_and_grab_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BOOSTED_TWICE_OR_MORE_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_HIT",
            "conditions": [
              {
                "type": "ATTACK_TARGET_IS_HERO"
              }
            ],
            "effects": [
              {
                "type": "STEAL_AURA_TOKEN",
                "target": "item"
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddEffectHitTrigger()
if(!$check) AddLayer("TRIGGER", $mainPlayer, $parameter, $cardID, "EFFECTHITEFFECT", $source);
      return true;
// EffectHitEffect()
if (IsHeroAttackTarget()) {
        AddDecisionQueue("MULTIZONEINDICES", $mainPlayer, "THEIRITEMS");
        AddDecisionQueue("SETDQCONTEXT", $mainPlayer, "Choose an item to take");
        AddDecisionQueue("CHOOSEMULTIZONE", $mainPlayer, "<-", 1);
        AddDecisionQueue("MZOP", $mainPlayer, "GAINCONTROL", 1);
      }
      break;
// EVOPlayAbility()
if (GetClassState($currentPlayer, $CS_NumBoosted) >= 2) AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### channel_lightning_valley_yellow  — looks-aligned
text: 'The first time you deal damage to an opposing hero each turn, draw a card.\n\n**Channel Lightning** - At the beginning of your end phase, put a flow counter on this, then destroy it unless you put a Lightning card from your pitch zone on the bottom of your deck for each flow counter on it.'
```json
{
  "slug": "channel_lightning_valley_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CHANNEL_LIGHTNING_VALLEY_ACTIVATED"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "CHANNEL_LIGHTNING_VALLEY_ACTIVATED"
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CHANNEL_LIGHTNING_VALLEY_ACTIVATED"
        }
      ],
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "flow",
          "amount": 1
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": "self",
          "conditions": [
            {
              "type": "NOT",
              "condition": {
                "type": "BANISH_FROM_GRAVEYARD",
                "card_type": "Lightning",
                "amount": {
                  "type": "COUNTER_GTE",
                  "counter": "flow"
                }
              }
            }
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraNumUses()
return 1;
// AuraBeginEndPhaseTriggers()
AddLayer("TRIGGER", $mainPlayer, $auras[$i], $auras[$i+6], "CHANNEL");
        break;
// AuraDamageTakenAbilities()
if (!$selfInflicted) {
          if(GetClassState($otherPlayer, $CS_DamageDealtToOpponent) == 0 && $damage > 0 && $otherAuras[$i + 5] > 0){
            $otherAuras[$i + 5] -= 1;
            if (CardType($source) != "AA" || !SearchCurrentTurnEffects("tarpit_trap_yellow", $otherPlayer) && !HitEffectsArePrevented($source)) {
              AddLayer("TRIGGER", $otherPlayer, $otherAuras[$i], uniqueID: $otherAuras[$i + 6]);
            }
          }
        }
        break;
// ProcessTrigger()
if ($additionalCosts == "CHANNEL") {
          ChannelTalent($target, "LIGHTNING");
        }
        else {
          WriteLog(CardLink($parameter, $parameter) . " draws a card");
          Draw($player);
        }
        break;
```

### ridge_rider_shot_red  — looks-aligned
text: 'If Ridge Rider Shot is put into your arsenal face up, **opt 1**.'
```json
{
  "slug": "ridge_rider_shot_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "RIDGE_RIDER_SHOT_IN_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "OPT",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
Opt($parameter, 1);
        break;
// AddArsenal()
AddLayer("TRIGGER", $player, $cardID);
        break;
```

### master_cog_yellow  — looks-aligned
text: '**Legendary**\n\nWhen this is pitched, you may put a steam counter on an item you control with **crank**.'
```json
{
  "slug": "master_cog_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PITCH",
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "steam",
          "target": {
            "type": "CARD",
            "zone": "arsenal",
            "controller": "self",
            "conditions": [
              {
                "type": "HAS_KEYWORD",
                "keyword": "crank"
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
AddDecisionQueue("MULTIZONEINDICES", $player, "MYITEMS:hasCrank=true&LAYER:hasCrank=true");
        AddDecisionQueue("SETDQCONTEXT", $player, "Choose a card with Crank to put a steam counter", 1);
        AddDecisionQueue("CHOOSEMULTIZONE", $player, "<-", 1);
        AddDecisionQueue("MZADDCOUNTER", $player, $parameter, 1);
        break;
// PitchAbility()
AddLayer("TRIGGER", $currentPlayer, $cardID);
      break;
```

### zap_clappers  — looks-aligned
text: 'When this defends, you may reveal an instant card from your hand. If you do, deal 1 arcane damage to the attacking hero.\n\n**Blade Break**'
```json
{
  "slug": "zap_clappers",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "effects": [
        {
          "type": "REVEAL_TOP_DECK",
          "amount": 1,
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "HAND",
              "card_type": "INSTANT"
            }
          ]
        },
        {
          "type": "DEAL_ARCANE",
          "amount": 1,
          "target": "ATTACKER"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
if (CanRevealCards($player)) {
          QueueRevealInstant($player);
          AddDecisionQueue("DEALARCANE", $player, "1-zap_clappers-TRIGGER", 1);
        }
        break;
// OnBlockResolveEffects()
AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
```

### second_strike_red  — looks-aligned
text: "When this attacks, if you've dealt damage this turn, this gets +1{p} and **go again**."
```json
{
  "slug": "second_strike_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DAMAGE_DEALT_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessAttackTrigger()
$totalDamage = GetClassState($player, $CS_DamageDealt) + GetClassState($player, $CS_ArcaneDamageDealt);
      if ($totalDamage > 0) {
        AddCurrentTurnEffect($cardID, $player);
      }
      if ($totalDamage > 0) GiveAttackGoAgain();
      break;
// ROSPlayAbility()
AddLayer("TRIGGER", $currentPlayer, $cardID, "-", "ATTACKTRIGGER");
      return "";
```

### vengeful_apparition_blue  — looks-aligned
text: 'When this leaves the arena, if you control no Illusionist auras, you may play your next aura with cost 0 this turn as though it were an instant. If you do, it enters the arena with a +1{p} counter.\n\n**Ward 1**'
```json
{
  "slug": "vengeful_apparition_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_LEAVE_PLAY",
      "conditions": [
        {
          "type": "NOT",
          "condition": {
            "type": "CONTROLS_TOKEN_TYPE",
            "token_type": "Illusionist"
          }
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "VENGEFUL_APPARITION_AURA_PLAYABLE"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "VENGEFUL_APPARITION_AURA_PLAYABLE"
        }
      ],
      "effects": [
        {
          "type": "APPLY_CONTINUOUS",
          "effect": {
            "type": "MODIFY_ATTACK",
            "mod": "add",
            "amount": 1
          },
          "target": {
            "type": "TOKEN",
            "token_type": "Aura"
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AuraLeavesPlay()
$illusionistAuras = SearchAura($player, class: "ILLUSIONIST");
      if ($illusionistAuras == "" || strpos($illusionistAuras, ",") === false) AddLayer("TRIGGER", $player, $cardID, "-", "-", $uniqueID);
      break;
// ProcessTrigger()
AddCurrentTurnEffect($parameter . "-INST", $player, "PLAY");
        break;
```

### rumble_grunting_red  — looks-aligned
text: "Play Rumble Grunting only if you've discarded a card with 6 or more {p} this turn.\n\nYour next Brute attack this turn gains +4{p}.\n\n**Go again**"
```json
{
  "slug": "rumble_grunting_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "DISCARD_CARD",
          "conditions": [
            {
              "type": "DISCARDED_CARD_POWER_GTE",
              "amount": 6
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "DURING_TURN",
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Brute"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return GetClassState($mainPlayer, $CS_Num6PowDisc) > 0 ? 0 : 1;
// DYNEffectPowerModifier()
case "rumble_grunting_red": return 4;
// DYNCombatEffectActive()
case "rumble_grunting_red": case "rumble_grunting_yellow": case "rumble_grunting_blue": return ClassContains($attackID, "BRUTE", $mainPlayer);
// DYNPlayAbility()
case "rumble_grunting_red": case "rumble_grunting_yellow": case "rumble_grunting_blue": AddCurrentTurnEffect($cardID, $currentPlayer); return "";
```

### one_two_punch_blue  — looks-aligned
text: '**Combo** - If Head Jab was the last attack this combat chain, this has "When this hits a hero, deal 2 damage to them."'
```json
{
  "slug": "one_two_punch_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "HEAD_JAB_LAST_ATTACK"
        },
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "DEAL_GENERIC",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Head Jab") return true;
        break;
// AddOnHitTrigger()
if (ComboActive($cardID) && IsHeroAttackTarget()) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "ONHITEFFECT");
        return true;
      }
      break;
// OUTHitEffect()
if(ComboActive() && IsHeroAttackTarget())
        {
          AddDecisionQueue("PASSPARAMETER", $defPlayer, "2-" . $cardID . "-DAMAGE-" . $cardID . "-" . $mainPlayer, 1);
          AddDecisionQueue("DEALDAMAGE", $defPlayer, "MYCHAR-0", 1);
        }
        break;
```

### richter_scale  — looks-aligned
text: '**Action** - Destroy this: Create 2 Seismic Surge tokens.\n\n**Battleworn**'
```json
{
  "slug": "richter_scale",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Seismic Surge",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// MPGPlayAbility()
PlayAura("seismic_surge", $currentPlayer, 2, true, effectController:$currentPlayer, effectSource:$cardID);
      return "";
```

### cut_from_the_same_cloth_yellow  — looks-aligned
text: 'Target opposing hero reveals their hand. If an attack reaction card is revealed this way, **mark** them.\n\nYour next dagger attack this turn gets +3{p}.\n\n**Go again**'
```json
{
  "slug": "cut_from_the_same_cloth_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "REVEAL_HAND_MARK_IF_TYPE",
          "target": "opponent",
          "mark_type": "MARK"
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "NEXT_DAGGER_ATTACK"
            }
          ]
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HNTPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      AddDecisionQueue("FINDINDICES", $otherPlayer, "HAND");
      AddDecisionQueue("REVEALHANDCARDS", $otherPlayer, "-", 1);
      AddDecisionQueue("IFTYPEREVEALED", $otherPlayer, "AR", 1);
      AddDecisionQueue("MARKHERO", $otherPlayer, "-", 1);
      break;
```

### ice_bolt_yellow  — looks-aligned
text: 'Deal 4 arcane damage to any target.'
```json
{
  "slug": "ice_bolt_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 4
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayRequiresTarget()
return 2;
// ActionsThatDoArcaneDamage()
return true;
// UPRWizardPlayAbility()
$damage = match($cardID) { "ice_bolt_red" => 5, "ice_bolt_yellow" => 4, default => 3 };
        DealArcane($damage, 2, "PLAYCARD", $cardID, false, $currentPlayer, resolvedTarget: $target);
        return "";
```

### graven_call  — looks-aligned
text: '**Once per Turn Action** - {r}{r}: **Attack**. **Go again**\n\n**Piercing 1**\n\n**Instant** - Destroy 2 Silver you control: Equip this with a +1{p} counter. Activate this ability only while this is in your graveyard.'
```json
{
  "slug": "graven_call",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 2,
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self",
          "amount": 2,
          "subtype": "Silver"
        }
      ],
      "effects": [
        {
          "type": "PUT_COUNTER",
          "target": "self",
          "counter": {
            "type": "add",
            "amount": 1
          }
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "IN_GRAVEYARD"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if ($from == "GY") return CountItem("silver", $currentPlayer) < 2; else return false;
// HasPiercing()
return true;
// EffectHasBlockModifier()
return true;
// HVYPlayAbility()
if ($from == "GY") {
        $discardIndex = SearchDiscardForUniqueID($target, $currentPlayer);
        if ($discardIndex != -1) {
          RemoveDiscard($currentPlayer, $discardIndex);
          $character = &GetPlayerCharacter($currentPlayer);
          $uniqueID = EquipWeapon($currentPlayer, "graven_call");
          $charCount = count($character);
          $charPieces = CharacterPieces();
          for ($i = 0; $i < $charCount; $i += $charPieces) {
            if ($character[$i + 11] == $uniqueID) {
              if ($character[$i + 3] == 0) {
                ++$character[$i + 3];
              }
            }
          }
        }
        else {
          WriteLog("Graven Call failed to be equipped");
        }
      }
      return "";
// PayAdditionalCosts()
if ($from == "GY") {
        //mark which specific graven call was activated
        $graveyard = GetDiscard($currentPlayer);
        $layerIndex = SearchLayersForPhase($cardID);
        $layers[$layerIndex+3] = $graveyard[$index + 1];
        AddDecisionQueue("PASSPARAMETER", $currentPlayer, "silver-2", 1);
        AddDecisionQueue("FINDANDDESTROYITEM", $currentPlayer, "<-", 1);
      }
      break;
```

### mulch_red  — looks-aligned
text: '**Earth Fusion**\n\nIf Mulch was **fused**, it gains "If this hits a hero, put a card from their arsenal on the bottom of their deck."'
```json
{
  "slug": "mulch_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FUSED"
        },
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "PUT_CARDS_BOTTOM",
          "amount": 1,
          "zone": "arsenal",
          "target": "opponent"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddEffectHitTrigger()
case $Card_LifeBanner:
    case $Card_ResourceBanner:
// EffectHitEffect()
if (IsHeroAttackTarget()) {
        AddDecisionQueue("MULTIZONEINDICES", $mainPlayer, "THEIRARS", 1);
        AddDecisionQueue("SETDQCONTEXT", $mainPlayer, "Choose which card you want to put on the bottom of the deck", 1);
        AddDecisionQueue("CHOOSEMULTIZONE", $mainPlayer, "<-", 1);
        AddDecisionQueue("MZADDZONE", $mainPlayer, "THEIRBOTDECK", 1);
        AddDecisionQueue("MZREMOVE", $mainPlayer, "-", 1);
      }
      break;
// FuseAbility()
case "mulch_red": case "mulch_yellow": case "mulch_blue": AddCurrentTurnEffect($cardID, $player); break;
// HasFusion()
case "mulch_red": case "mulch_yellow": case "mulch_blue": return "EARTH";
// ELECombatEffectActive()
case "mulch_red": case "mulch_yellow": case "mulch_blue": return true;
```

### war_cry_of_themis_yellow  — looks-aligned
text: 'Your next angel attack this turn gets +4{p}.\n\n**Go again**\n\n**Instant** - Discard this, banish X cards from your soul: Turn X target cards in a banished zone face-down.'
```json
{
  "slug": "war_cry_of_themis_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4,
          "conditions": [
            {
              "type": "AND",
              "conditions": [
                {
                  "type": "DURING_TURN"
                },
                {
                  "type": "ATTACK_CLASS_IN",
                  "class": "Angel"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "cost": [
        {
          "type": "DISCARD_SELF"
        },
        {
          "type": "BANISH_NAMED_GRAVEYARD_OPTIONAL",
          "amount": "X"
        }
      ],
      "effects": [
        {
          "type": "FLIP_REF",
          "target": "X",
          "zone": "BANISHED"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// GetAbilityNames()
return GetEasyAbilityNames($cardID, $index, $from, $allNames);
// CanPlayAsInstant()
return $from == "HAND";
// AddPrePitchDecisionQueue()
$names = GetAbilityNames($cardID, $index, $from);
      if (SearchCurrentTurnEffects("red_in_the_ledger_red", $currentPlayer) && GetClassState($currentPlayer, $CS_NumActionsPlayed) >= 1) {
        AddDecisionQueue("SETABILITYTYPEABILITY", $currentPlayer, $cardID);
      } elseif ($names != "" && $from == "HAND"){
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose to play the ability or the action");
        AddDecisionQueue("BUTTONINPUT", $currentPlayer, $names);
        AddDecisionQueue("SETABILITYTYPE", $currentPlayer, $cardID);
      } else{
        AddDecisionQueue("SETABILITYTYPEACTION", $currentPlayer, $cardID);
      }
      // fix this later
      break;
// PayAdditionalCosts()
if (GetResolvedAbilityType($cardID, $from) == "I")   
      {
        AddDecisionQueue("FINDINDICES", $currentPlayer, "SOULINDICES");
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose how many cards to banish from your soul");
        AddDecisionQueue("BUTTONINPUT", $currentPlayer, "<-", 1);
        AddDecisionQueue("SETCLASSSTATE", $currentPlayer, $CS_AdditionalCosts, 1);
        AddDecisionQueue("PREPENDLASTRESULT", $currentPlayer, "GETINDICES,", 1);
        AddDecisionQueue("FINDINDICES", $currentPlayer, "<-", 1);
        AddDecisionQueue("MULTIBANISHSOUL", $currentPlayer, "-", 1);
      }
      break;
// HNTPlayAbility()
if (GetResolvedAbilityType($cardID, "HAND") == "A") {
        AddCurrentTurnEffectNextAttack($cardID, $currentPlayer);
      }
      else {
        for ($i = 0; $i < GetClassState($currentPlayer, piece: $CS_AdditionalCosts); $i++) {
          AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "THEIRBANISH&MYBANISH");
          AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a card to turn face-down");
          AddDecisionQueue("MAYCHOOSEMULTIZONE", $currentPlayer, "<-", 1);
          AddDecisionQueue("MZOP", $currentPlayer, "TURNBANISHFACEDOWN", 1);
        }
      }
      break;
```

### rotwood_reaper  — looks-aligned
text: "**Once per Turn Action** - {r}{r}: **Attack**\n\nIf you've played or created an aura this turn, this gets +2{p}."
```json
{
  "slug": "rotwood_reaper",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 2,
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "AURA_PLAYED_OR_CREATED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerValue()
case "rotwood_reaper": return GetClassState($mainPlayer, $CS_NumAuras) > 0 ? $basePower+2 : $basePower;
```

### hot_on_their_heels_red  — looks-aligned
text: 'If you control 2 or more Draconic chain links, this gets **go again** and "When this hits a hero, **mark** them."'
```json
{
  "slug": "hot_on_their_heels_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Draconic",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "MARK"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Draconic",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// AddOnHitTrigger()
if (IsHeroAttackTarget() && NumDraconicChainLinks() > 1) {
        if (!$check) AddLayer("TRIGGER", $mainPlayer, $cardID, $cardID, "ONHITEFFECT");
        return true;
      }
      break;
// DoesAttackHaveGoAgain()
return NumDraconicChainLinks() >= 2;
// HNTHitEffect()
MarkHero($defPlayer);
      break;
```

### rift_bind_blue  — looks-aligned
text: "You may play Rift Bind from your banished zone. If you do, it gains +X{p}, where X is the number of 'non-attack' action cards you have played this turn.\n\n**Blood Debt**"
```json
{
  "slug": "rift_bind_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "BANISH_FROM_GRAVEYARD",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": {
            "type": "COUNT",
            "condition": {
              "type": "CARD_IN_ZONE",
              "zone": "play",
              "condition": {
                "type": "NOT",
                "condition": {
                  "type": "HAS_KEYWORD",
                  "keyword": "Attack"
                }
              }
            }
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PlayableFromBanish()
return true;
// MONRunebladePlayAbility()
if($from == "BANISH") AddCurrentTurnEffect($cardID, $currentPlayer);
        return "";
// MONEffectPowerModifier()
case "rift_bind_red": case "rift_bind_yellow": case "rift_bind_blue": return GetClassState($mainPlayer, $CS_NumNonAttackCards);
// MONCombatEffectActive()
case "rift_bind_red": case "rift_bind_yellow": case "rift_bind_blue": return true;
```

### tuffnut_bumbling_hulkster  — looks-aligned
text: '**Instant** - {t}: Pitch the top card of your deck. If it has 6 or more {p}, **the crowd cheers** you.\n\nWhenever the crowd cheers you, create a Toughness token.'
```json
{
  "slug": "tuffnut_bumbling_hulkster",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "PITCH",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "CROWD_CHEERS"
        }
      ],
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "ref": "TOP_DECK",
          "pitch_power_gte": 6
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BECOME",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "TOUGHNESS"
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CROWD_CHEERS"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return CheckTapped("MYCHAR-$index", $currentPlayer);
// ProcessTrigger()
PlayAura("toughness", $player, isToken:true, effectController:$player, effectSource:$parameter);
        break;
// EquipPayAdditionalCosts()
Tap("MYCHAR-$cardIndex", $currentPlayer);
      break;
// SUPPlayAbility()
$top = PitchTopCard($currentPlayer);
      if (ModifiedPowerValue($top, $currentPlayer, "DECK") >= 6) {
        Cheer($currentPlayer);
      }
      break;
// Cheer()
AddLayer("TRIGGER", $player, $char[0]);
          break;
```

### hold_the_line_blue  — looks-aligned
text: 'If the attacking hero has drawn 2 or more cards this turn, prevent the next 3 damage that would be dealt to your hero this turn.'
```json
{
  "slug": "hold_the_line_blue",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "ATTACKER_DRAWN_2_OR_MORE_CARDS"
        }
      ],
      "effects": [
        {
          "type": "WARD",
          "amount": 3
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HasEffectActive()
case "hold_the_line_blue": return GetClassState($otherPlayer, $CS_NumCardsDrawn) >= 2;
// CurrentTurnEffectDamagePreventionAmount()
return intval($effects[1]);
// CurrentEffectDamagePrevention()
if ($preventable) {
        $damageToPrevent = min($damage, $effects[1]);
        $preventedDamage += $damageToPrevent;
        $effects[1] -= $damageToPrevent;
        $currentTurnEffects[$index] = $effects[0] . "-" . $effects[1];
      }
      if ($effects[1] <= 0 || !$preventable) RemoveCurrentTurnEffect($index);
      break;
// DTDPlayAbility()
if(GetClassState($otherPlayer, $CS_NumCardsDrawn) >= 2)
      {
        AddCurrentTurnEffect($cardID . "-3", $currentPlayer);
      }
      return "";
```

### precision_press_blue  — looks-aligned
text: 'Your next sword or dagger attack this turn has **go again** and **piercing 1**.\n\n**Go again**'
```json
{
  "slug": "precision_press_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "PRECISION_PRESS_ACTIVE"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "PRECISION_PRESS_ACTIVE"
        },
        {
          "type": "OR",
          "conditions": [
            {
              "type": "ATTACK_TYPE_IN",
              "attack_type": "Sword"
            },
            {
              "type": "ATTACK_TYPE_IN",
              "attack_type": "Dagger"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        },
        {
          "type": "GAIN",
          "keyword": "PIERCING",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// HasPiercing()
return !IsPlayRestricted($cardID, $restriction, $from) || IsCombatEffectActive($cardID);
// DoesCurrentTurnEffectGrantGoAgain()
return true;
// DYNEffectPowerModifier()
case "precision_press_blue": return (NumEquipBlock() > 0 ? 1 : 0);
// DYNCombatEffectActive()
$subtype = CardSubType($attackID);
      return ($subtype == "Sword") || ($subtype == "Dagger");
// DYNPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### art_of_desire_mind_blue  — looks-aligned
text: '**Stealth**\n\nWhen this hits a hero, banish the top card of their deck.\n\nWhenever this banishes a blue card, draw a card and gain 1{h}.'
```json
{
  "slug": "art_of_desire_mind_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": "OPPONENT_TOP_DECK"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BANISH",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "pitch": "BLUE"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "GAIN",
          "asset": "HEALTH",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// MSTHitEffect()
if (IsHeroAttackTarget()) {
        $deck->BanishTop("Source-" . $attackCard, banishedBy: $attackCard);
      }
      break;
```

### icy_encounter_blue  — looks-aligned
text: 'If Icy Encounter hits a hero, create a Frostbite token under their control.'
```json
{
  "slug": "icy_encounter_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Frostbite",
          "controller": "opponent"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ELETalentHitEffect()
if(IsHeroAttackTarget()) PlayAura("frostbite", $defPlayer, effectController: $mainPlayer);
        break;
```

### hundred_winds_yellow  — looks-aligned
text: '**Combo** - If Hundred Winds was the last attack this combat chain, this attack gains +1{p} for each other card named Hundred Winds you control on this combat chain.\n\n**Go again**'
```json
{
  "slug": "hundred_winds_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "HUNDRED_WINDS_LAST_ATTACK"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "HUNDRED_WINDS"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Hundred Winds") return true;
        break;
// PowerModifier()
$power += (ComboActive() ? NumChainLinksWithName("Hundred Winds") - 1 : 0);
        break;
```

### breed_anger_yellow  — looks-aligned
text: '**Combo** - When this attacks, if Crouching Tiger was the last attack this combat chain, this gets **go again** and create a Crouching Tiger in your banished zone. You may play it this turn.'
```json
{
  "slug": "breed_anger_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CROUCHING_TIGER_LAST_ATTACK"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        },
        {
          "type": "CREATE_TOKEN",
          "token": "CROUCHING_TIGER",
          "zone": "BANISHED"
        },
        {
          "type": "BANISH_OPP_TOP_GRANT_PLAY",
          "amount": 1
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ComboActive()
if ($lastAttackName == "Crouching Tiger") return true;
        break;
// DoesAttackHaveGoAgain()
return ComboActive($attackID);
// MSTPlayAbility()
if (ComboActive()) {
        BanishCardForPlayer("crouching_tiger", $currentPlayer, "-", "TT", $currentPlayer, created:true);
        GiveAttackGoAgain();
      }
      return "";
```

### second_strike_blue  — looks-aligned
text: "When this attacks, if you've dealt damage this turn, this gets +1{p} and **go again**."
```json
{
  "slug": "second_strike_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DAMAGE_DEALT_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessAttackTrigger()
$totalDamage = GetClassState($player, $CS_DamageDealt) + GetClassState($player, $CS_ArcaneDamageDealt);
      if ($totalDamage > 0) {
        AddCurrentTurnEffect($cardID, $player);
      }
      if ($totalDamage > 0) GiveAttackGoAgain();
      break;
// ROSPlayAbility()
AddLayer("TRIGGER", $currentPlayer, $cardID, "-", "ATTACKTRIGGER");
      return "";
```

### den_of_the_spider_red  — looks-aligned
text: 'When this defends an attack with {p} greater than its base, **mark** the attacking hero.'
```json
{
  "slug": "den_of_the_spider_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "ATTACK_POWER_GT_BASE"
        }
      ],
      "effects": [
        {
          "type": "MARK"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
WriteLog("The Hunter stumbles into the spider");
        MarkHero($mainPlayer);
        break;
// OnDefenseReactionResolveEffects()
if (HasIncreasedAttack()) AddLayer("TRIGGER", $defPlayer, $cardID);
      break;
```

### intoxicating_shot_blue  — looks-aligned
text: '**Riptide Specialization**\n\nWhen this hits a hero, they create a Courage and Quicken token.'
```json
{
  "slug": "intoxicating_shot_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_TARGET_IS_HERO"
            },
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "Courage"
            },
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "Quicken"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Courage"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Quicken"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// EVOHitEffect()
if (IsHeroAttackTarget()) {
        PlayAura("courage", $defPlayer);
        PlayAura("quicken", $defPlayer);
      }
      break;
```

### good_time_chapeau  — looks-aligned
text: '**Betsy Specialization**\n\n**Action** - Destroy a Gold you control: Your next attack this turn gets "When this attacks a hero, **wager** a Might and a Vigor token with them." **Go again**\n\n**Temper**'
```json
{
  "slug": "good_time_chapeau",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "controlled_gold"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "WAGER_FLAG"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "WAGER_FLAG"
        },
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "WAGER",
          "tokens": [
            "Might",
            "Vigor"
          ]
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return CountItem("gold", $currentPlayer) <= 0;
// EquipPayAdditionalCosts()
QueueDestroyGold($currentPlayer, isMandatory:true, showContext:true, subsequent:0);
      break;
// ProcessWager()
PlayAura("might", $wonWager, $amount, effectSource:$attackCard);
        PlayAura("vigor", $wonWager, $amount, effectSource:$attackCard);
        break;
// ResolveWagers()
if (!$chainClosed) {
              $triggerCardID = $currentTurnEffects[$i];
              AddLayer("TRIGGER", $mainPlayer, $triggerCardID, $wonWager, "WAGER");
            }
            RemoveCurrentTurnEffect($i);
            break;
// HVYPlayAbility()
AddCurrentTurnEffect($cardID . "-PAID", $currentPlayer);
      return "";
```

### droplet_blue  — looks-aligned
text: "If you've played another blue card this turn, this gets +2{p}."
```json
{
  "slug": "droplet_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BLUE_CARD_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    }
  ]
}
```
Talishar:
```php
// PowerModifier()
$power += GetClassState($mainPlayer, $CS_NumBluePlayed) > 1 ? 2 : 0;
        break;
```

### aether_conduit  — looks-aligned
text: '**Once per Turn Action** - {r}{r}: Deal 2 arcane damage to target hero.'
```json
{
  "slug": "aether_conduit",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 2,
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 2,
          "target": "hero"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CRUAbilityCost()
case "aether_conduit": return 2;
// CRUAbilityType()
case "aether_conduit": return "A";
// CRUPlayAbility()
DealArcane(2, 0, "ABILITY", $cardID);
      return "";
```

### sutcliffes_suede_hides  — looks-aligned
text: "**Attack Reaction** - {r}, destroy this: Target attack action card gets **go again**. Activate this only if you've played a non-attack action card this turn."
```json
{
  "slug": "sutcliffes_suede_hides",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "activation_cost": 1,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "NON_ATTACK_ACTION_PLAYED"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return !$CombatChain->HasCurrentLink() || CardType($attackID) != "AA" || GetClassState($currentPlayer, $CS_NumNonAttackCards) == 0;
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// ReactionRequirementsMet()
case "sutcliffes_suede_hides": return CardType($combatChain[0]) == "AA" && GetClassState($currentPlayer, $CS_NumNonAttackCards) > 0;
// ELERunebladePlayAbility()
GiveAttackGoAgain();
        return "";
// ELEAbilityCost()
case "rosetta_thorn": case "duskblade": case "spellbound_creepers": case "sutcliffes_suede_hides": return 1;
// ELEAbilityType()
case "sutcliffes_suede_hides": return "AR";
```

### heat_seeker_red  — looks-aligned
text: 'When this hits, at the beginning of your end phase, put the top card of your deck face up into your arsenal.'
```json
{
  "slug": "heat_seeker_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "END_OF_TURN",
            "effects": [
              {
                "type": "PUT_TOP_DECK_BOTTOM",
                "zone": "arsenal"
              }
            ]
          }
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
$deck = new Deck($player);
        if (!$deck->Empty() && !ArsenalFull($player)) AddArsenal($deck->Top(remove: true), $player, "DECK", "UP");
        break;
// BeginEndPhaseEffectTriggers()
AddLayer("TRIGGER", $mainPlayer, "heat_seeker_red", $currentTurnEffects[$i + 1], "-", "-");
        break;
// DYNHitEffect()
case "heat_seeker_red": AddCurrentTurnEffectFromCombat($cardID, $mainPlayer); break;
```

### hocus_pocus_blue  — looks-aligned
text: 'When this attacks, create a Runechant token.'
```json
{
  "slug": "hocus_pocus_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ROSPlayAbility()
PlayAura("runechant", $currentPlayer);
      return "";
```

### tectonic_crust  — looks-aligned
text: 'When this defends together with an Earth card, create a Seismic Surge token.\n\n**Temper**'
```json
{
  "slug": "tectonic_crust",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "Earth"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Seismic Surge"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
PlayAura("seismic_surge", $defPlayer, effectController: $defPlayer);
        break;
// OnBlockResolveEffects()
$sub = TalentContains($defendingCard, "EARTH", $defPlayer) == true ? 1 : 0; //necessary for a fringe case where the chest but not the other blocking card loses its talent
          if ($blockedWithEarth - $sub > 0) AddLayer("TRIGGER", $defPlayer, $defendingCard, $i);
          break;
```

### wallop_red  — looks-aligned
text: 'When you win a **clash** revealing this, create a Vigor token.'
```json
{
  "slug": "wallop_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CLASH_WIN_REVEALED",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// ProcessTrigger()
PlayAura("vigor", $player); 
        WriteLog(CardLink($parameter, $parameter) . " created a ".CardLink("vigor", "vigor")." token for Player " . $player);
        break;
// WonClashAbility()
AddLayer("TRIGGER", $playerID, $deckTop);
          break;
```

### kayo_strong_arm  — looks-aligned
text: 'You start the game with 1 weapon zone.\n\n**Instant** - {r}{r}{r}{r}, {t}: Target attack action card you control has 6 base {p}.\n\nWhenever the crowd boos you, create a Vigor token.'
```json
{
  "slug": "kayo_strong_arm",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "activation_cost": 4,
      "cost": [
        {
          "type": "PITCH",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "SET_BASE_POWER",
          "amount": 6,
          "target": "attack_action"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BOO",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
if (CheckTapped("MYCHAR-$index", $currentPlayer)) return true;
      if ($currentPlayer == $mainPlayer) {
        if(!$CombatChain->HasCurrentLink() && SearchLayersForPhase("RESOLUTIONSTEP") == -1 && !IsLayerStep()) return true;
        $previousLink = SearchCombatChainAttacks($currentPlayer, type:"AA") == "";
        $currentLink = !TypeContains($attackID, "AA", $currentPlayer);
        $unresolvedAttacks = SearchLayersCardType("AA") == "";
        if ($previousLink && $currentLink && $unresolvedAttacks) return true;
      }
      else {
        //for now only support buffing cards on the current chain link
        $numOptions = GetChainLinkCards($currentPlayer, "AA", "C");
        if ($numOptions == "") return true;
      }
      return false;
// ProcessTrigger()
PlayAura("vigor", $player, isToken:true, effectController:$player, effectSource:$parameter);
        break;
// EquipPayAdditionalCosts()
if ($currentPlayer == $mainPlayer) {
        if (ShouldAutotargetOpponent($currentPlayer)) {
          AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "ACTIVEATTACK:type=AA");
        }
        else AddDecisionQueue("MULTIZONEINDICES", $currentPlayer, "COMBATCHAINATTACKS:type=AA&ACTIVEATTACK:type=AA");
        AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose an attack action card");
        AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, "<-", 1);
        AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);
        AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
      }
      else {
        $numOptions = GetChainLinkCards($currentPlayer, "AA", "C");
        if ($numOptions != "") {
          $numOptions = explode(",", $numOptions);
          $options = [];
          foreach ($numOptions as $num) $options[] = "COMBATCHAINLINK-$num";
          $options = implode(",", $options);
          AddDecisionQueue("SETDQCONTEXT", $currentPlayer, "Choose a defending card to buff the power of");
          AddDecisionQueue("CHOOSEMULTIZONE", $currentPlayer, $options, 1);
          AddDecisionQueue("SHOWSELECTEDTARGET", $currentPlayer, "-", 1);
          AddDecisionQueue("SETLAYERTARGET", $currentPlayer, $cardID, 1);
        }
      }
      Tap("MYCHAR-$cardIndex", $currentPlayer);
      break;
// LinkBasePower()
if ($mainPlayer == $currentTurnEffects[$i + 1]) $basePower = 6;
          break;
// SUPPlayAbility()
if ($currentPlayer == $mainPlayer) {
        //check to make sure they targeted the current chain link
        $uid = $CombatChain->AttackCard()->UniqueID();
        AddCurrentTurnEffect($cardID, $currentPlayer, $uid);
      }
      else {
        $targetIndex = intval(explode("-", $target, 2)[1]);
        $uid = $CombatChain->Card($targetIndex)->UniqueID();
        AddCurrentTurnEffect($cardID, $currentPlayer, "", $uid);
        ReEvalCombatChain();
      }
      break;
// BOO()
AddLayer("TRIGGER", $player, $char[0]);
        break;
```

### push_forward_yellow  — looks-aligned
text: 'Your next weapon attack this turn gains +2{p}.\n\nIf you have attacked with a weapon this turn, your next attack this turn gains **dominate**.\n\n**Go again**'
```json
{
  "slug": "push_forward_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "IN_COMBAT",
          "condition": "ATTACK_IS_WEAPON"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "IN_COMBAT",
          "condition": "ATTACK_IS_WEAPON"
        },
        {
          "type": "AND",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "HAS_ATTACKED_WITH_WEAPON"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "DOMINATE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CRUPlayAbility()
AddCurrentTurnEffect($cardID . "-1", $mainPlayer);
      if(GetClassState($currentPlayer, $CS_AttacksWithWeapon) > 0) {
        AddCurrentTurnEffect($cardID . "-2", $mainPlayer);
        $rv = "Gives your attack dominate because you've attacked with a weapon";
      }
      return $rv;
```

### captains_coat  — looks-aligned
text: "**Action** - Destroy this: Gain {r}. Activate this only if you've drawn a card this turn. **Go again**"
```json
{
  "slug": "captains_coat",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 1
        },
        {
          "type": "GO_AGAIN"
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DRAWN_CARD_THIS_TURN"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// IsPlayRestricted()
return GetClassState($currentPlayer, $CS_NumCardsDrawn) == 0;
// EquipPayAdditionalCosts()
DestroyCharacter($currentPlayer, $cardIndex);
      break;
// SEAPlayAbility()
GainResources($currentPlayer, 1);
      break;
```

### break_of_dawn_red  — looks-aligned
text: 'The next time a Shadow source would deal damage this turn, prevent 4 of that damage.'
```json
{
  "slug": "break_of_dawn_red",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "BREAK_OF_DAWN_ACTIVE"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// CurrentTurnEffectDamagePreventionAmount()
$prevention = match ($effects[0]) {
        "break_of_dawn_red" => 4,
        "break_of_dawn_yellow" => 3,
        "break_of_dawn_blue" => 2,
      };
      if (TalentContains($source, "SHADOW", $otherPlayer)) {
        return $prevention;
      }
      break;
// CurrentEffectDamagePrevention()
$prevention = match($effects[0]) {
        "break_of_dawn_red" => 4,
        "break_of_dawn_yellow" => 3,
        default => 2,
      };
      if (TalentContains($source, "SHADOW", $otherPlayer)) {
        if ($preventable) $preventedDamage += $prevention;
        RemoveCurrentTurnEffect($index);
      }
      break;
// DTDPlayAbility()
AddCurrentTurnEffect($cardID, $currentPlayer);
      return "";
```

### figment_of_protection_yellow  — looks-aligned
text: '**Legendary**\n\nWhen this enters the arena, create a Spectral Shield token.'
```json
{
  "slug": "figment_of_protection_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Spectral Shield"
        }
      ]
    }
  ]
}
```
Talishar:
```php
// DTDPlayAbility()
PlayAura("spectral_shield", $currentPlayer);
      return "";
```

### sharpening_sparks_red  — no-talishar-logic
text: 'Target sword attack gets +2{p} and "When this hits, **sharpen** this sword."'
```json
{
  "slug": "sharpening_sparks_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_HIT",
          "effects": [
            {
              "type": "SET_FLAG",
              "flag": "SHARPENED"
            }
          ]
        }
      ],
      "target": {
        "filter": [
          {
            "type": "WEAPON_SUBTYPE_IN",
            "subtypes": [
              "sword"
            ]
          }
        ]
      }
    }
  ]
}
```

### puffer_jacket  — no-talishar-logic
text: 'Non-token Hyper Drivers you control enter the arena with an additional steam counter.\n\n**Temper**'
```json
{
  "slug": "puffer_jacket",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Hyper Driver"
        },
        {
          "type": "NOT",
          "condition": {
            "type": "TOKEN_TYPE_IN",
            "token_types": [
              "Token"
            ]
          }
        }
      ],
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter_type": "steam",
          "amount": 1
        }
      ]
    }
  ]
}
```

### auric_shards_yellow  — no-talishar-logic
text: 'When this enters the arena, up to 1 target attack with fragment gets +1{p}. If this has a holo counter, instead the attack gets +3{p}.\n\n**Ward 1**'
```json
{
  "slug": "auric_shards_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "NOT",
              "condition": {
                "type": "FLAG_SET",
                "flag": "HOLO_COUNTER"
              }
            }
          ]
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "HOLO_COUNTER"
            }
          ]
        }
      ],
      "target": {
        "filter": [
          {
            "type": "ATTACK_TYPE_IN",
            "types": [
              "fragment"
            ]
          }
        ]
      }
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "amount": 1
        }
      ]
    }
  ]
}
```

### act_of_glory_blue  — no-talishar-logic
text: '**Suspense**\n\nWhen this leaves the arena, your next attack this turn gets +4{p}.'
```json
{
  "slug": "act_of_glory_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_LEAVE_PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 4,
          "conditions": [
            {
              "type": "DURING_TURN"
            }
          ]
        }
      ]
    }
  ]
}
```

### dramatic_pause_blue  — no-talishar-logic
text: '**Suspense**\n\nWhen this enters the arena, target defending action card gets +1{d} this chain link.'
```json
{
  "slug": "dramatic_pause_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "amount": 1
        }
      ]
    }
  ]
}
```

### silken_symphony  — no-talishar-logic
text: 'When this is destroyed, create a Might token.\n\n**Ward 1**'
```json
{
  "slug": "silken_symphony",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEATH",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Might"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "amount": 1
        }
      ]
    }
  ]
}
```

### bully_tactics_red  — no-talishar-logic
text: 'When this attacks a hero, you may pay up to {r}{r}{r}. **Intimidate** them that many times.'
```json
{
  "slug": "bully_tactics_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "INTIMIDATE",
          "amount": "PAYMENT_AMOUNT"
        }
      ],
      "additional_cost": [
        {
          "type": "PAY_RESOURCES",
          "amount": "UP_TO_3"
        }
      ]
    }
  ]
}
```

### baalghor_omen_of_the_end  — no-talishar-logic
text: 'Whenever you pitch a card, banish it.\n\nAttack action cards played from your banished zone get +3{p}.'
```json
{
  "slug": "baalghor_omen_of_the_end",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PITCH",
      "effects": [
        {
          "type": "BANISH"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "BANISHED",
          "card_type": "ACTION"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```

### disarm_yellow  — no-talishar-logic
text: "When this attacks, if you've been cheered this turn, create a Toughness token.\n\nWhen this defends, if it has 6 or more {d}, the attacking hero puts a card from their hand on the bottom of their deck."
```json
{
  "slug": "disarm_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CHEERED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "TOUGHNESS"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "COUNTER_GTE",
          "counter": "DEFENSE",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "PUT_HAND_CARD_BOTTOM",
          "target": "opponent"
        }
      ]
    }
  ]
}
```

### pilfer_the_tomb_blue  — no-talishar-logic
text: "Choose 1 or both;\n\n- Banish target instant from an opposing hero's graveyard.\n- Banish target yellow card from an opposing hero's graveyard."
```json
{
  "slug": "pilfer_the_tomb_blue",
  "abilities": [
    {
      "ability_type": "MODAL",
      "choose": 1,
      "modes": [
        {
          "type": "BANISH_REF",
          "target": "opponent",
          "zone": "GRAVEYARD",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "card_type": "INSTANT"
            }
          ]
        },
        {
          "type": "BANISH_REF",
          "target": "opponent",
          "zone": "GRAVEYARD",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "card_type": "YELLOW"
            }
          ]
        }
      ]
    }
  ]
}
```

### painful_passage_red  — no-talishar-logic
text: 'You may banish an attack action card from your hand. If you do, it gets +3{p} or **go again** until end of turn.\n\n**Go again**'
```json
{
  "slug": "painful_passage_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "BANISH",
          "target": "HAND",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "HAND",
              "card_type": "ACTION"
            }
          ],
          "additional_effects": [
            {
              "type": "MODIFY_ATTACK",
              "mod": "add",
              "amount": 3
            },
            {
              "type": "GAIN",
              "keyword": "GO_AGAIN",
              "duration": "END_OF_TURN"
            }
          ]
        }
      ]
    }
  ]
}
```

### steel_on_steel_yellow  — no-talishar-logic
text: 'While this is defending a weapon attack, this gets +1{d}.'
```json
{
  "slug": "steel_on_steel_yellow",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "ATTACK_IS_WEAPON"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "amount": 1
        }
      ]
    }
  ]
}
```

### rough_up_yellow  — no-talishar-logic
text: 'When this attacks, if there is a card with 6 or more {p} in your pitch zone, this gets +1{p}.'
```json
{
  "slug": "rough_up_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "pitch_power_gte": 6
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```

### rift_breaker_yellow  — no-talishar-logic
text: 'When this hits a hero, destroy a Lightning Flow token they control.'
```json
{
  "slug": "rift_breaker_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "token_type": "Lightning Flow"
        }
      ]
    }
  ]
}
```

### throttle_red  — no-talishar-logic
text: '**Boost**'
```json
{
  "slug": "throttle_red",
  "abilities": []
}
```

### fluttersteps  — no-talishar-logic
text: 'When this is destroyed, you may play your next aura this turn as though it were an instant.\n\n**Ward 1**'
```json
{
  "slug": "fluttersteps",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEATH",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "PLAY_AURA_AS_INSTANT"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "amount": 1
        }
      ]
    }
  ]
}
```

### buckwild_yellow  — no-talishar-logic
text: 'If there is a card with 6 or more {p} in your pitch zone, this gets **go again**.'
```json
{
  "slug": "buckwild_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "pitch_power_gte": 6
        }
      ],
      "effects": [
        {
          "type": "GRANT_SUBTYPE",
          "subtype": "GoAgain"
        }
      ]
    }
  ]
}
```

### volatile_fluxor_red  — no-talishar-logic
text: "If you've played an instant card this chain link, this gets +3{p}.\n\nWhen this hits, create a Lightning Flow token.\n\n**Go again**"
```json
{
  "slug": "volatile_fluxor_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Lightning Flow"
        }
      ]
    }
  ]
}
```

### comet_collision_red  — no-talishar-logic
text: 'Deal 3 arcane damage to any target.\n\n**Starfall** - If an instant card has been put into your graveyard this turn, instead deal 4 arcane damage.'
```json
{
  "slug": "comet_collision_red",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 3
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "STARFALL_FLAG"
        }
      ],
      "alternative_effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 4
        }
      ]
    }
  ]
}
```

### gas_guzzler_blue  — no-talishar-logic
text: '**Boost**'
```json
{
  "slug": "gas_guzzler_blue",
  "abilities": []
}
```

### edict_of_steel_red  — no-talishar-logic
text: '**Sharpen** target sword you control.\n\nIf it has 1 or more +1{p} counters, create a Flurry token.\n\n**Go again**'
```json
{
  "slug": "edict_of_steel_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "STEAL_AURA_TOKEN"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Flurry",
          "conditions": [
            {
              "type": "COUNTER_GTE",
              "amount": 1
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### glide_through_starlight_red  — no-talishar-logic
text: '**Instant** - {r}, discard this: Prevent the next 1 damage that would be dealt to you this turn. If you prevent damage this way, create a Lightning Flow token.'
```json
{
  "slug": "glide_through_starlight_red",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "PAY_LIFE",
          "amount": 1
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "WARD",
          "amount": 1
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Lightning Flow"
        }
      ]
    }
  ]
}
```

### heavy_artillery_red  — no-talishar-logic
text: "**Evo Upgrade** - The defending hero can't defend this with attack action cards with cost less than X, where X is the number of Evos you have equipped."
```json
{
  "slug": "heavy_artillery_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "EvoUpgrade"
        }
      ],
      "effects": [
        {
          "type": "RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT",
          "conditions": [
            {
              "type": "ATTACK_COST_LTE",
              "amount": "EVO_COUNT"
            }
          ]
        }
      ]
    }
  ]
}
```

### starfield_carapace  — no-talishar-logic
text: '**Instant** - Destroy this: Until end of turn, an Aphrodias you control costs {r} less to activate and gets "Whenever this deals damage to an opposing hero, create a Lightning Flow token."\n\n**Blade Break**'
```json
{
  "slug": "starfield_carapace",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_ACTIVATE",
          "conditions": [
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "Aphrodias"
            }
          ],
          "effects": [
            {
              "type": "PAY_OR_DAMAGE",
              "amount": -1
            },
            {
              "type": "INJECT_TRIGGER",
              "trigger": "ON_DEAL_DAMAGE",
              "conditions": [
                {
                  "type": "ATTACK_TARGET_IS_HERO",
                  "opponent": true
                }
              ],
              "effects": [
                {
                  "type": "CREATE_TOKEN",
                  "token_type": "Lightning Flow"
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

### goon_beatdown_blue  — no-talishar-logic
text: 'If you control 3 or more auras, this gets +3{p} and "When this hits a hero, **the crowd boos** you."'
```json
{
  "slug": "goon_beatdown_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "aura",
          "amount": 3
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "CROWD_BOO"
        }
      ]
    }
  ]
}
```

### doomsaying_red  — no-talishar-logic
text: '**Go again**\n\nAt the beginning of your end phase, put a doom counter on this, then each hero destroys X auras they control, where X is the number of doom counters on this.'
```json
{
  "slug": "doomsaying_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "doom"
        },
        {
          "type": "DESTROY_TOKEN",
          "amount": "doom"
        }
      ]
    }
  ]
}
```

### beckoning_haunt  — no-talishar-logic
text: '**Action** - {x}{x}{r}, destroy this: Return target aura with cost X from your graveyard to your hand.\n\n**Guardwell**'
```json
{
  "slug": "beckoning_haunt",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 2,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "RETURN_DR_FROM_GRAVEYARD",
          "cost": "X"
        }
      ]
    }
  ]
}
```

### spell_fray_tiara  — no-talishar-logic
text: '**Spellvoid 1**'
```json
{
  "slug": "spell_fray_tiara",
  "abilities": []
}
```

### heart_wrencher_red  — no-talishar-logic
text: '**Boost**'
```json
{
  "slug": "heart_wrencher_red",
  "abilities": []
}
```

### give_em_a_piece_of_your_mind_blue  — no-talishar-logic
text: "When the combat chain closes, if this didn't hit, the defending hero creates a Vigor token."
```json
{
  "slug": "give_em_a_piece_of_your_mind_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_COMBAT_CLOSE",
      "conditions": [
        {
          "type": "DID_NOT_HIT"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor"
        }
      ]
    }
  ]
}
```

### familiar_stench_red  — no-talishar-logic
text: 'When 1 or more Brute cards defend this, create a Vigor token.'
```json
{
  "slug": "familiar_stench_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "classes": [
                "brute"
              ]
            },
            {
              "type": "CHAIN_HIT_COUNT_GTE",
              "amount": 1
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor"
        }
      ]
    }
  ]
}
```

### downswing_red  — no-talishar-logic
text: 'Target sword attack gets +1{p} and **wagers** with the defending hero. The winner loses 1{h}.'
```json
{
  "slug": "downswing_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "CLASH",
          "target": "defending_hero"
        },
        {
          "type": "LOSE_LIFE",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "CLASH_WIN"
            }
          ]
        },
        {
          "type": "LOSE_LIFE",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "CLASH_LOSE"
            }
          ]
        }
      ],
      "target": {
        "filter": [
          {
            "type": "WEAPON_SUBTYPE_IN",
            "subtypes": [
              "sword"
            ]
          }
        ]
      }
    }
  ]
}
```

### leech_memory_red  — no-talishar-logic
text: 'The next attack action card you play this turn gets +3{p} and "Whenever this deals damage to a hero, you may put an attack action card from your graveyard on the bottom of your deck."\n\n**Go again**'
```json
{
  "slug": "leech_memory_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "DURING_TURN"
            }
          ]
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_DEAL_DAMAGE",
            "target": {
              "filter": [
                {
                  "type": "CARD_IN_ZONE",
                  "zones": [
                    "hero"
                  ]
                }
              ]
            },
            "effects": [
              {
                "type": "PUT_CARDS_BOTTOM",
                "amount": 1,
                "source": "GRAVEYARD",
                "conditions": [
                  {
                    "type": "MAY"
                  }
                ]
              }
            ]
          }
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### dashing_flashfoot_yellow  — no-talishar-logic
text: '**Quickstrike** - If this has go again, it gets +1{p} and "When this attacks a hero, deal 1 arcane damage to them."\n\nThe first time this deals damage to a hero, create an Embodiment of Lightning token.'
```json
{
  "slug": "dashing_flashfoot_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "GO_AGAIN"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        },
        {
          "type": "FLAG_SET",
          "flag": "DASHING_FLASHFOOT_FIRST_DAMAGE"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "EMBODIMENT_OF_LIGHTNING"
        }
      ]
    }
  ]
}
```

### incision_yellow  — no-talishar-logic
text: 'Target dagger attack gets +2{p}.'
```json
{
  "slug": "incision_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 2
        }
      ],
      "target": {
        "filter": [
          {
            "type": "ATTACK_TYPE_IN",
            "types": [
              "dagger"
            ]
          }
        ]
      }
    }
  ]
}
```

### deathmatch_arena  — no-talishar-logic
text: '**Legendary**\n\n**Go again**\n\nHeroes can attack any opposing hero.\n\nWhen a hero deals lethal damage to another hero, they create Gold tokens equal to the number of heroes who started this game.'
```json
{
  "slug": "deathmatch_arena",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEATH",
      "conditions": [
        {
          "type": "ATTACK_TYPE_IN",
          "types": [
            "hero"
          ]
        },
        {
          "type": "ATTACK_SUBTYPE_IN",
          "subtypes": [
            "hero"
          ]
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Gold",
          "amount": "STARTING_HERO_COUNT"
        }
      ]
    }
  ]
}
```

### robe_of_resourcefulness  — no-talishar-logic
text: 'When this leaves the arena, gain {r}{r}.\n\n**Blade Break**'
```json
{
  "slug": "robe_of_resourcefulness",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_LEAVE_PLAY",
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```

### grille_of_repentance  — no-talishar-logic
text: '**Instant** - Destroy this: Turn a card with blood debt in your banished zone face-down.'
```json
{
  "slug": "grille_of_repentance",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "BANISH_REF",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "BANISHED",
              "keywords": [
                "blood_debt"
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

### evo_magneto_blue  — no-talishar-logic
text: 'If you have a base arms equipped, transform it into this, then equip this.\n\nWhen this defends, you may destroy a card under it. If you do, gain control of target item with cost 0 or 1 controlled by the attacking hero.\n\n**Temper**'
```json
{
  "slug": "evo_magneto_blue",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "effects": [
        {
          "type": "MAY_DESTROY_SILVERS_TO_EQUIP",
          "amount": 1
        },
        {
          "type": "BANISH_REF",
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zones": [
                  "arsenal"
                ],
                "cost_gte": 0,
                "cost_lte": 1,
                "controlled_by": "opponent"
              }
            ]
          }
        }
      ]
    }
  ]
}
```

### ebbing_arcstride_red  — no-talishar-logic
text: 'Whenever this fragments, it gets **go again**.\n\n**Fragment**'
```json
{
  "slug": "ebbing_arcstride_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BECOME",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "FRAGMENT"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### mist_hunter_red  — no-talishar-logic
text: "**Contract** - You are contracted to banish opponents' blue cards. Whenever you complete this contract, create a Silver token.\n\nWhen this hits a Mystic hero, search their deck for any number of Inner Chi and banish them. Then shuffle."
```json
{
  "slug": "mist_hunter_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "classes": [
            "mystic"
          ]
        }
      ],
      "effects": [
        {
          "type": "SEARCH_DECK",
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zones": [
                  "deck"
                ],
                "subtypes": [
                  "Inner Chi"
                ]
              }
            ]
          },
          "action": "BANISH"
        },
        {
          "type": "REORDER_REF",
          "ref": "deck",
          "action": "SHUFFLE"
        }
      ]
    }
  ]
}
```

### ronin_renegade_red  — no-talishar-logic
text: '**Go again**'
```json
{
  "slug": "ronin_renegade_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### unbound_by_shadow_red  — no-talishar-logic
text: "When this attacks, if it was played from your banished zone, create a Gate to i'Arathael token.\n\n**Blood Debt**"
```json
{
  "slug": "unbound_by_shadow_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "PLAYED_FROM_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token": "Gate_to_iArathael"
        }
      ]
    }
  ]
}
```

### quick_succession_red  — no-talishar-logic
text: 'The next Runeblade or Lightning attack action card you play this turn gets **go again**.\n\nYour next 3 attacks this turn get +1{p} while they have go again.\n\n**Go again**'
```json
{
  "slug": "quick_succession_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "APPLY_CONTINUOUS",
          "conditions": [
            {
              "type": "DURING_TURN"
            },
            {
              "type": "ATTACK_CLASS_IN",
              "classes": [
                "runeblade",
                "lightning"
              ]
            },
            {
              "type": "FLAG_SET",
              "flag": "QUICK_SUCCESSION_GO_AGAIN"
            }
          ],
          "effect": {
            "type": "GAIN",
            "keyword": "GO_AGAIN"
          }
        },
        {
          "type": "APPLY_CONTINUOUS",
          "conditions": [
            {
              "type": "DURING_TURN"
            },
            {
              "type": "FLAG_SET",
              "flag": "QUICK_SUCCESSION_GO_AGAIN"
            }
          ],
          "effect": {
            "type": "MODIFY_ATTACK",
            "mod": "add",
            "amount": 1
          }
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "QUICK_SUCCESSION_GO_AGAIN"
        }
      ]
    }
  ]
}
```

### zane_broadly_beloved  — no-talishar-logic
text: 'You may equip 2H swords as though they were 1H.\n\nWhenever you win a wager, **the crowd cheers** you.\n\nThe first time the crowd cheers you each turn, each hero draws a card.'
```json
{
  "slug": "zane_broadly_beloved",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GRANT_SUBTYPE",
          "subtype": "1H"
        }
      ],
      "conditions": [
        {
          "type": "WEAPON_SUBTYPE_IN",
          "subtypes": [
            "2H"
          ]
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CLASH_WIN_REVEALED",
      "effects": [
        {
          "type": "CROWD_BOO",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CLASH_WIN_REVEALED",
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        }
      ],
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CROWD_BOO"
        }
      ]
    }
  ]
}
```

### shamanic_shinbones  — no-talishar-logic
text: '**Arcane Barrier 1**'
```json
{
  "slug": "shamanic_shinbones",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "ARCANE_BARRIER",
          "amount": 1
        }
      ]
    }
  ]
}
```

### donkey_blue  — no-talishar-logic
text: 'Target sword attack gets +1{p} and **wagers** with the defending hero. The winner destroys a card in their own arsenal.'
```json
{
  "slug": "donkey_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "CLASH",
          "target": "defender"
        }
      ],
      "target": {
        "filter": [
          {
            "type": "WEAPON_SUBTYPE_IN",
            "subtypes": [
              "sword"
            ]
          }
        ]
      }
    }
  ]
}
```

### stormwind_sheath_red  — no-talishar-logic
text: '**Lightning Bond** - If a Lightning card was pitched to play this, create an Embodiment of Lightning token.'
```json
{
  "slug": "stormwind_sheath_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "pitch": "lightning"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token": "embodiment_of_lightning"
        }
      ]
    }
  ]
}
```

### robe_of_repentance  — no-talishar-logic
text: '**Instant** - Destroy this: Turn a card with blood debt in your banished zone face-down.'
```json
{
  "slug": "robe_of_repentance",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "BANISH_REF",
          "target": {
            "filter": [
              {
                "type": "CARD_IN_ZONE",
                "zone": "BANISHED",
                "keywords": [
                  "blood_debt"
                ]
              }
            ]
          },
          "action": "FACE_DOWN"
        }
      ]
    }
  ]
}
```

### evo_engine_room_yellow  — no-talishar-logic
text: 'If you have a base chest equipped, **transform** it into this, then equip this.\n\n**Once per Turn Instant** - Destroy a card under this: Your next weapon attack this turn costs {r} less to activate.\n\n**Blade Break**'
```json
{
  "slug": "evo_engine_room_yellow",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "per_turn": 1,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "under_this"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA",
          "amount": -1,
          "duration": "this_turn"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```

### stinging_sprite_blue  — no-talishar-logic
text: 'When this attacks or defends, deal 1 arcane damage to target hero.'
```json
{
  "slug": "stinging_sprite_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        }
      ]
    }
  ]
}
```

### cruel_ambition_red  — no-talishar-logic
text: 'Create 3 Might tokens.\n\n**Go again**'
```json
{
  "slug": "cruel_ambition_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Might",
          "amount": 3
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### pulsing_cardia_yellow  — no-talishar-logic
text: 'Whenever this fragments, gain {r}.\n\n**Fragment**'
```json
{
  "slug": "pulsing_cardia_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BECOME",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "Fragment"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 1
        }
      ]
    }
  ]
}
```

### pulsing_cardia_red  — no-talishar-logic
text: 'Whenever this fragments, gain {r}.\n\n**Fragment**'
```json
{
  "slug": "pulsing_cardia_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BECOME",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "Fragment"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 1
        }
      ]
    }
  ]
}
```

### clearwater_elixir_red  — no-talishar-logic
text: 'Your next attack this turn gets +3{p}.\n\nYou may destroy a Bloodrot Pox token you control. If you do, gain 1{h}.\n\n**Go again**'
```json
{
  "slug": "clearwater_elixir_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "DURING_TURN"
            }
          ]
        },
        {
          "type": "MAY_DESTROY_SILVERS_TO_EQUIP",
          "target": {
            "filter": [
              {
                "type": "CONTROLS_TOKEN_TYPE",
                "token_types": [
                  "Bloodrot Pox"
                ]
              }
            ]
          },
          "effects": [
            {
              "type": "GAIN",
              "asset": "HEALTH",
              "amount": 1
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### phoenix_bannerman_head_red  — no-talishar-logic
text: '**Legendary**\n\nSearch your deck for a Phoenix Flame, reveal it, put it into your hand, then shuffle.\n\nCreate a Ponder token.\n\n**Go again**'
```json
{
  "slug": "phoenix_bannerman_head_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SEARCH_DECK",
          "target": "Phoenix Flame",
          "amount": 1,
          "reveal": true,
          "put_into_hand": true,
          "shuffle": true
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Ponder"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### rainbow_goo_trap_red  — no-talishar-logic
text: "When this defends an attack with {p} greater than its base, dominate, and go again, the attack gets -2{p} and loses and can't gain abilities."
```json
{
  "slug": "rainbow_goo_trap_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "ATTACK_POWER_GT_BASE"
        }
      ],
      "effects": [
        {
          "type": "DOMINATE"
        },
        {
          "type": "GO_AGAIN"
        },
        {
          "type": "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA",
          "mod": "subtract",
          "amount": 2
        },
        {
          "type": "REMOVE_COUNTERS",
          "counter_type": "ABILITIES"
        }
      ]
    }
  ]
}
```

### diced_red  — no-talishar-logic
text: 'Target dagger attack gets +1{p}.\n\nYour next dagger attack this turn gets +3{p}.'
```json
{
  "slug": "diced_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "ATTACK_TYPE_IN",
          "attack_type": "Dagger"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "DURING_TURN"
        },
        {
          "type": "ATTACK_TYPE_IN",
          "attack_type": "Dagger"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```

### razor_ring_blue  — no-talishar-logic
text: '**Legendary**\n\n**Action** - {r}, {t}, destroy this when the combat chain closes: **Attack**. **Go again**\n\nWhen this hits a hero, the next action card they defend with this combat chain gets -1{d} until end of turn.'
```json
{
  "slug": "razor_ring_blue",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "subtract",
          "amount": 1,
          "duration": "end_of_turn"
        }
      ]
    }
  ]
}
```

### power_of_make_believe_blue  — no-talishar-logic
text: 'This gets +1{p} for each card with 6 or more {p} defending it.\n\n**Mirage**'
```json
{
  "slug": "power_of_make_believe_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "defending",
              "conditions": [
                {
                  "type": "SELF_ATTACK_POWER_GTE",
                  "amount": 6
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

### erode_authority_blue  — no-talishar-logic
text: '**Dominate**\n\n**Fragment**'
```json
{
  "slug": "erode_authority_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DOMINATE"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "FRAGMENT"
        }
      ]
    }
  ]
}
```

### spirit_of_christmas_blue  — no-talishar-logic
text: 'Each hero chooses another hero. The chosen hero creates an Agility, Might, Vigor, and Gold token.\n\n**Go again**'
```json
{
  "slug": "spirit_of_christmas_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "subtype": "Agility"
        },
        {
          "type": "CREATE_TOKEN",
          "subtype": "Might"
        },
        {
          "type": "CREATE_TOKEN",
          "subtype": "Vigor"
        },
        {
          "type": "CREATE_TOKEN",
          "subtype": "Gold"
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### fasting_carcass_blue  — no-talishar-logic
text: 'The next blue action card you play this turn gets **go again**.\n\n**Go again**\n\n**Blood Debt**'
```json
{
  "slug": "fasting_carcass_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "FASTING_CARCASS_FLAG"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PLAY_ACTIVATE_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FASTING_CARCASS_FLAG"
        },
        {
          "type": "CARD_IN_ZONE",
          "zone": "HAND",
          "card_class": "Blue",
          "card_type": "Action"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "BLOOD_DEBT"
        }
      ]
    }
  ]
}
```

### goon_battery_blue  — no-talishar-logic
text: 'If you control 3 or more auras, this gets +3{p} and "When this hits a hero, {t} them."'
```json
{
  "slug": "goon_battery_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Aura",
          "amount": 3
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_HIT",
            "conditions": [
              {
                "type": "ATTACK_TARGET_IS_HERO"
              }
            ],
            "effects": [
              {
                "type": "TAP_SELF"
              }
            ]
          }
        }
      ]
    }
  ]
}
```

### laden_with_frost_red  — no-talishar-logic
text: "Your next attack this turn gets +3{p}.\n\n**Ice Bond** - If an Ice card was pitched to play this, create a Frostbite token under target hero's control.\n\n**Go again**"
```json
{
  "slug": "laden_with_frost_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_PLAY",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "ref": "ICE"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Frostbite",
          "controller": "opponent"
        }
      ]
    }
  ]
}
```

### frail_swingline_blue  — no-talishar-logic
text: "Create a Frailty token under target hero's control.\n\n**Go again**\n\nWhen this defends an attack with {p} less than its base, its controller discards a card."
```json
{
  "slug": "frail_swingline_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Frailty"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "ATTACK_POWER_GT_BASE",
          "amount": 3
        }
      ],
      "effects": [
        {
          "type": "DISCARD"
        }
      ]
    }
  ]
}
```

### painful_premonition_blue  — no-talishar-logic
text: 'Deal 1 arcane damage to any target.\n\nIf this deals damage, create a Sigil of Fate token.'
```json
{
  "slug": "painful_premonition_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Sigil of Fate"
        }
      ]
    }
  ]
}
```

### flex_strength_blue  — no-talishar-logic
text: 'If this has 6 or more {p}, it gets +3{p}.'
```json
{
  "slug": "flex_strength_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "COUNTER_GTE",
          "counter": "power",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```

### starlight_road_blue  — no-talishar-logic
text: 'Create an Embodiment of Lightning or Lightning Flow token.'
```json
{
  "slug": "starlight_road_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "EMBODIMENT_OF_LIGHTNING"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "LIGHTNING_FLOW"
        }
      ]
    }
  ]
}
```

### tentacular_toll_red  — no-talishar-logic
text: 'Turn up to 3 ally cards in your graveyard face-down, then create that many Gold tokens.\n\n**Go again**'
```json
{
  "slug": "tentacular_toll_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "BANISH_OPP_TOP_GRANT_PLAY",
          "amount": 3
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Gold",
          "amount": 3
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### mage_hunter_arrow_red  — no-talishar-logic
text: '**Instant** - Destroy this: The next time you would be dealt arcane damage this turn, prevent 3 of that damage. Activate this only while this is face-up in your arsenal.\n\nWhen this hits a Runeblade or Wizard hero, you may destroy an aura they control.'
```json
{
  "slug": "mage_hunter_arrow_red",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_DEATH",
            "conditions": [
              {
                "type": "FLAG_SET",
                "flag": "MAGE_HUNTER_ARROW_ACTIVE"
              }
            ],
            "effects": [
              {
                "type": "PAY_OR_DAMAGE",
                "amount": 3,
                "damage_type": "ARCANE"
              }
            ]
          }
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "OR",
          "conditions": [
            {
              "type": "ATTACK_TARGET_IS_HERO",
              "hero_type": "Runeblade"
            },
            {
              "type": "ATTACK_TARGET_IS_HERO",
              "hero_type": "Wizard"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "target": "opponent",
          "token_type": "Aura"
        }
      ]
    }
  ]
}
```

### clench_the_upper_hand_yellow  — no-talishar-logic
text: 'When this attacks or defends, if you have less {h} than each other hero, **the crowd boos** you.'
```json
{
  "slug": "clench_the_upper_hand_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "HEALTH_LT_OPP"
        }
      ],
      "effects": [
        {
          "type": "CROWD_BOO"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "HEALTH_LT_OPP"
        }
      ],
      "effects": [
        {
          "type": "CROWD_BOO"
        }
      ]
    }
  ]
}
```

### malign_yellow  — no-talishar-logic
text: "**Stealth**\n\nDamage that would be dealt by Malign can't be prevented."
```json
{
  "slug": "malign_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "ward_type": "UNPREVENTABLE"
        }
      ]
    }
  ]
}
```

### chromatic_refinement_blue  — no-talishar-logic
text: 'At the beginning of your action phase, destroy this, then the next blue card you play this turn costs {r} less to play. The first time that card would deal damage this turn, instead it deals that much plus 1.'
```json
{
  "slug": "chromatic_refinement_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "conditions": [
        {
          "type": "IS_ACTIVE_PLAYER"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_REF",
          "target": "self"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CHROMATIC_REFINEMENT_FLAG"
        }
      ],
      "effects": [
        {
          "type": "PAY_OR_DAMAGE",
          "target": "next_blue_card_played",
          "resource_cost": 1
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "target": "next_blue_card_played",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "CHROMATIC_REFINEMENT_DEALT_DAMAGE"
            }
          ]
        }
      ]
    }
  ]
}
```

### rites_of_earthlore_red  — no-talishar-logic
text: 'When this enters the arena, create a Seismic Surge token.\n\nAt the start of your turn, destroy this, then the next Guardian attack action card you play this turn gets +3{p}.'
```json
{
  "slug": "rites_of_earthlore_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_name": "Seismic Surge"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_PLAY",
            "conditions": [
              {
                "type": "ATTACK_CLASS_IN",
                "class": "Guardian"
              }
            ],
            "effects": [
              {
                "type": "MODIFY_ATTACK",
                "mod": "add",
                "amount": 3
              }
            ]
          }
        }
      ]
    }
  ]
}
```

### song_of_larinkmorth_white_blue  — no-talishar-logic
text: "Create a Frostbite token under each other hero's control."
```json
{
  "slug": "song_of_larinkmorth_white_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Frostbite",
          "controller": "opponent"
        }
      ]
    }
  ]
}
```

### grandstand_legplates  — no-talishar-logic
text: "Grandstand Legplates' {d} is equal to the number of opposing heroes with greater {h} than you.\n\n**Blade Break**"
```json
{
  "slug": "grandstand_legplates",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "amount": {
            "type": "COUNT",
            "condition": {
              "type": "AND",
              "conditions": [
                {
                  "type": "CARD_IN_ZONE",
                  "zone": "opponent_heroes"
                },
                {
                  "type": "HEALTH_GT_OPP"
                }
              ]
            }
          }
        }
      ]
    },
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```

### swordmasters_path_blue  — no-talishar-logic
text: 'Your next sword attack this turn gets +1{p}.\n\nThe next time you would sharpen a sword this turn, instead **sharpen** it an additional time.\n\n**Go again**'
```json
{
  "slug": "swordmasters_path_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "ATTACK_SUBTYPE_IN",
              "subtype": "Sword"
            }
          ]
        },
        {
          "type": "GAIN",
          "keyword": "SHARPEN",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "SHARPEN_FLAG"
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### surging_strike_yellow  — no-talishar-logic
text: '**Go again**'
```json
{
  "slug": "surging_strike_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### backspin_thrust_red  — no-talishar-logic
text: '**Once per Turn Instant** - {u} a cog you control: This gets +1{p} or **go again**.'
```json
{
  "slug": "backspin_thrust_red",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "PAY_RESOURCES",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### flow_through_blue  — no-talishar-logic
text: 'Target Lightning attack gets +1{p} and "When this hits, create a Lightning Flow token."'
```json
{
  "slug": "flow_through_blue",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_HIT",
          "effects": [
            {
              "type": "CREATE_TOKEN",
              "token_type": "Lightning Flow"
            }
          ]
        }
      ]
    }
  ]
}
```

### fight_fair_red  — no-talishar-logic
text: "If this is defended by a Reviled card, this gets +1{p}.\n\nWhen this hits a Reviled hero, put this on the bottom of its owner's deck."
```json
{
  "slug": "fight_fair_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "opponent",
          "card_type": "Reviled"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "opponent",
          "card_type": "Reviled"
        }
      ],
      "effects": [
        {
          "type": "PUT_SELF_BOTTOM_DECK"
        }
      ]
    }
  ]
}
```

### gauntlets_of_unity  — no-talishar-logic
text: '**Unity** - When this defends together with a card from hand, this gets +1{d} until end of turn.\n\n**Temper**'
```json
{
  "slug": "gauntlets_of_unity",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "UNITY_FLAG"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "amount": 1,
          "duration": "END_OF_TURN"
        }
      ]
    }
  ]
}
```

### erode_authority_yellow  — no-talishar-logic
text: '**Dominate**\n\n**Fragment**'
```json
{
  "slug": "erode_authority_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DOMINATE"
        },
        {
          "type": "GAIN",
          "keyword": "FRAGMENT"
        }
      ]
    }
  ]
}
```

### fry_red  — no-talishar-logic
text: '**Go again**'
```json
{
  "slug": "fry_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### depths_of_despair_blue  — no-talishar-logic
text: 'When this defends, banish it when the combat chain closes.\n\n**Blood Debt**'
```json
{
  "slug": "depths_of_despair_blue",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "BANISH",
          "target": "self"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "BLOOD_DEBT_FLAG"
        }
      ]
    }
  ]
}
```

### high_pitched_howl_yellow  — no-talishar-logic
text: 'When this attacks, if there is a card with 6 or more {p} in your pitch zone, create a Vigor token.'
```json
{
  "slug": "high_pitched_howl_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "ref": "pitch_zone",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor"
        }
      ]
    }
  ]
}
```

### old_favorite_yellow  — no-talishar-logic
text: "When this attacks, if you've been cheered this turn, create a Toughness token.\n\nWhen this defends, if it has 6 or more {d}, put it on the bottom of its owner's deck when the combat chain closes."
```json
{
  "slug": "old_favorite_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CHEERED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "TOUGHNESS"
        }
      ]
    },
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "COUNTER_GTE",
          "counter": "DEFENSE",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "PUT_SELF_BOTTOM_DECK"
        }
      ]
    }
  ]
}
```

### cosmic_suture_red  — no-talishar-logic
text: 'Prevent the next 4 damage that would be dealt to you this turn.\n\n**Starfall** - If an instant card has been put into your graveyard this turn, deal 1 arcane damage to target hero.'
```json
{
  "slug": "cosmic_suture_red",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "activation_cost": 2,
      "cost": [
        {
          "type": "PAY_RESOURCES",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "WARD",
          "amount": 4
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "INSTANT_GRAVEYARD_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        }
      ]
    }
  ]
}
```

### spectral_rider_red  — no-talishar-logic
text: 'When you play Spectral Rider, if you control a Spectral Shield, this gains **overpower**.\n\n**Phantasm**'
```json
{
  "slug": "spectral_rider_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Spectral Shield"
        }
      ],
      "effects": [
        {
          "type": "GRANT_SUBTYPE",
          "subtype": "Overpower"
        }
      ]
    }
  ]
}
```

### corrupt_and_conquer_red  — no-talishar-logic
text: 'If this was played from your banished zone, it gets "Defense reaction cards can\'t be played this chain link.\n\nWhen this hits a hero, banish all cards in their arsenal.\n\n**Blood Debt**'
```json
{
  "slug": "corrupt_and_conquer_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "conditions": [
        {
          "type": "CARD_IN_ZONE",
          "zone": "BANISHED",
          "source": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "DEFENSE_REACTION_BLOCKED"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "BANISH",
          "target": "OPPONENT_ARSENAL"
        }
      ]
    }
  ]
}
```

### stellar_glide_blue  — no-talishar-logic
text: 'When this attacks, you may destroy a Lightning Flow you control. If you do, this gets **go again**.'
```json
{
  "slug": "stellar_glide_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Lightning Flow"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "token_type": "Lightning Flow"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### carrion_crown  — no-talishar-logic
text: '**Action** - Discard an ally, destroy this: Draw a card. **Go again**\n\n**Blade Break**'
```json
{
  "slug": "carrion_crown",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DISCARD_RANDOM",
          "target": "ALLY"
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```

### path_of_same_ends_red  — no-talishar-logic
text: 'When this attacks a hero, deal 1 arcane damage to them. If damage is dealt this way, this gets **go again**.\n\n**Instant** - {r}: This gets **go again**.'
```json
{
  "slug": "path_of_same_ends_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### wounding_blow_blue  — no-talishar-logic
text: ''
```json
{
  "slug": "wounding_blow_blue",
  "abilities": []
}
```

### teklo_base_head  — no-talishar-logic
text: '**Blade Break**'
```json
{
  "slug": "teklo_base_head",
  "abilities": [
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```

### energetic_impact_blue  — no-talishar-logic
text: 'When this defends together with a card with 6 or more {p}, create a Vigor token.'
```json
{
  "slug": "energetic_impact_blue",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "DEFENDS_WITH_OTHER_HAND_CARD"
            },
            {
              "type": "SELF_ATTACK_POWER_GTE",
              "amount": 6
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Vigor"
        }
      ]
    }
  ]
}
```

### bait  — no-talishar-logic
text: "You can't play or activate cards you own.\n\n**Action** - Destroy this when the chain link resolves: **Attack**\n\n**Once per Turn Attack Reaction** - 0: This gets +1{p} and **go again**."
```json
{
  "slug": "bait",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BAIT_IN_PLAY"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "CANNOT_PLAY_OR_ACTIVATE_OWN_CARDS"
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "BAIT_DESTROYED"
        }
      ]
    },
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "BAIT_IN_PLAY"
        },
        {
          "type": "CHAIN_HIT_COUNT_GTE",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### comeback_kid_red  — no-talishar-logic
text: "When this attacks a hero, if you have less {h} than them, **the crowd cheers** you.\n\nIf you've been cheered this turn, this gets +1{p}."
```json
{
  "slug": "comeback_kid_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "HEALTH_LT_OPP"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "CROWD_CHEERS"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CROWD_CHEERS"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```

### flurry  — no-talishar-logic
text: 'When you activate a weapon attack, destroy this and you may attack with the weapon twice this turn.'
```json
{
  "slug": "flurry",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ACTIVATE",
      "conditions": [
        {
          "type": "ATTACK_TYPE_IN",
          "attack_type": "WEAPON"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```

### nebula_duality_yellow  — no-talishar-logic
text: 'Deal 2 arcane damage to any target.\n\n**Instant** - {r}, discard this: Deal 1 arcane damage to target hero. Create a Lightning Flow token.'
```json
{
  "slug": "nebula_duality_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 2
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Lightning Flow"
        }
      ]
    }
  ]
}
```

### goon_tactics_blue  — no-talishar-logic
text: 'If you control 3 or more auras, this gets +3{p} and "When this hits a hero, destroy the top card of their deck."'
```json
{
  "slug": "goon_tactics_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Aura",
          "amount": 3
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_HIT",
            "conditions": [
              {
                "type": "ATTACK_TARGET_IS_HERO"
              }
            ],
            "effects": [
              {
                "type": "DESTROY_REF",
                "ref": "OPPONENT_DECK_TOP"
              }
            ]
          }
        }
      ]
    }
  ]
}
```

### tentacular_toll_yellow  — no-talishar-logic
text: 'Turn up to 2 ally cards in your graveyard face-down, then create that many Gold tokens.\n\n**Go again**'
```json
{
  "slug": "tentacular_toll_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "BANISH_OPP_TOP_GRANT_PLAY",
          "amount": 2
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Gold",
          "amount": 2
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### hala  — no-talishar-logic
text: '**Action** - {r}{r}{r}, {t}: **Sharpen** target sword you control. **Go again**'
```json
{
  "slug": "hala",
  "abilities": [
    {
      "ability_type": "PLAY",
      "activation_cost": 3,
      "cost": [
        {
          "type": "PITCH",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1,
          "conditions": [
            {
              "type": "WEAPON_SUBTYPE_IN",
              "subtype": "Sword"
            },
            {
              "type": "CONTROLS_ATTACK_ACTION"
            }
          ]
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### tear_down_the_idols_red  — no-talishar-logic
text: 'When this attacks a Revered hero, **intimidate** them.\n\nWhen this hits a Revered hero, they discard a card.'
```json
{
  "slug": "tear_down_the_idols_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_TARGET_IS_HERO",
              "hero_type": "Revered"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_TARGET_IS_HERO",
              "hero_type": "Revered"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "DISCARD",
          "target": "opponent",
          "amount": 1
        }
      ]
    }
  ]
}
```

### oath_of_oak_yellow  — no-talishar-logic
text: 'Create 2 Embodiment of Earth tokens.'
```json
{
  "slug": "oath_of_oak_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Embodiment of Earth",
          "amount": 2
        }
      ]
    }
  ]
}
```

### anticipating_gaze  — no-talishar-logic
text: 'When a sword attack you control hits, you may remove a +1{p} counter from the sword. If you do, destroy this and draw a card.\n\n**Blade Break**'
```json
{
  "slug": "anticipating_gaze",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_CLASS_IN",
              "class": "Sword"
            },
            {
              "type": "CONTROLS_ATTACK_ACTION"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "REMOVE_COUNTER",
          "counter": "+1{p}"
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```

### take_that_red  — no-talishar-logic
text: "When the combat chain closes, if this didn't hit, the defending hero creates a Might token."
```json
{
  "slug": "take_that_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_COMBAT_CLOSE",
      "conditions": [
        {
          "type": "DID_NOT_HIT"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Might"
        }
      ]
    }
  ]
}
```

### whos_the_tough_guy_yellow  — no-talishar-logic
text: "When the combat chain closes, if this didn't hit, the defending hero creates a Toughness token."
```json
{
  "slug": "whos_the_tough_guy_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_COMBAT_CLOSE",
      "conditions": [
        {
          "type": "DID_NOT_HIT"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "TOUGHNESS"
        }
      ]
    }
  ]
}
```

### horrors_of_the_past_yellow  — no-talishar-logic
text: '**Stealth**\n\nWhen this attacks, it gets the base abilities of the last attack action card with stealth you control on the combat chain.'
```json
{
  "slug": "horrors_of_the_past_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "COPY_BANISHED_STEALTH_ATTACK"
        }
      ]
    }
  ]
}
```

### off_cuts_blue  — no-talishar-logic
text: '**Frankie Specialization**\n\nEach hero destroys an equipment they control.\n\n**Go again**'
```json
{
  "slug": "off_cuts_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FRANKIE_SPECIALIZATION"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "target": "equipment",
          "controller": "opponent"
        }
      ]
    }
  ]
}
```

### sit_red  — no-talishar-logic
text: 'When this defends a Brute attack, this gets +3{d}.'
```json
{
  "slug": "sit_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "ATTACK_CLASS_IN",
          "class": "Brute"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```

### hunter_or_hunted_blue  — no-talishar-logic
text: "When this defends, name a card. The attacking hero reveals the top card of their deck. If it's the named card, banish it, search their hand, deck, and arsenal for up to 3 cards with that name and banish them, then they shuffle.\n\n**Contract** - While this is defending, you are contracted to banish opponents' cards with the chosen name. Whenever you complete this contract, create a Silver token."
```json
{
  "slug": "hunter_or_hunted_blue",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "REVEAL_TOP_DECK",
          "target": "opponent"
        },
        {
          "type": "BANISH",
          "target": "opponent",
          "conditions": [
            {
              "type": "REF_PITCH_IS",
              "ref": "named_card"
            }
          ]
        },
        {
          "type": "SEARCH_BANISH_FACE_DOWN",
          "target": "opponent",
          "zone": "hand",
          "amount": 3,
          "conditions": [
            {
              "type": "REF_PITCH_IS",
              "ref": "named_card"
            }
          ]
        },
        {
          "type": "SEARCH_BANISH_FACE_DOWN",
          "target": "opponent",
          "zone": "deck",
          "amount": 3,
          "conditions": [
            {
              "type": "REF_PITCH_IS",
              "ref": "named_card"
            }
          ]
        },
        {
          "type": "SEARCH_BANISH_FACE_DOWN",
          "target": "opponent",
          "zone": "arsenal",
          "amount": 3,
          "conditions": [
            {
              "type": "REF_PITCH_IS",
              "ref": "named_card"
            }
          ]
        },
        {
          "type": "PUT_CARDS_BOTTOM",
          "target": "opponent",
          "zone": "deck"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CONTRACT_ACTIVE"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Silver"
        }
      ]
    }
  ]
}
```

### beckon_steel_blue  — no-talishar-logic
text: 'Target sword attack gets "When this hits, **sharpen** this sword. Then if the sword has 3 or more +1{p} counters, **attack** with it."'
```json
{
  "slug": "beckon_steel_blue",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "SHARPEN",
          "amount": 1
        },
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "ON_HIT",
            "conditions": [
              {
                "type": "COUNTER_GTE",
                "counter": "SHARPEN",
                "amount": 3
              }
            ],
            "effects": [
              {
                "type": "ATTACK"
              }
            ]
          }
        }
      ]
    }
  ]
}
```

### flowing_stormstrike_red  — no-talishar-logic
text: '**Twice per Turn Instant** - {r}: This gets +1{p}.\n\nWhen this hits, create a Lightning Flow token.'
```json
{
  "slug": "flowing_stormstrike_red",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FLOWING_STORMSTRIKE_ACTIVATED_THIS_TURN",
          "count": 2,
          "comparison": "lt"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "SET_FLAG",
          "flag": "FLOWING_STORMSTRIKE_ACTIVATED_THIS_TURN",
          "increment": true
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Lightning Flow"
        }
      ]
    }
  ]
}
```

### volzar_meteor_storm  — no-talishar-logic
text: '**Instant** - {t}: **Amp 1**. Activate this only if an instant card has been put into your graveyard this turn.'
```json
{
  "slug": "volzar_meteor_storm",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "INSTANT_PUT_IN_GRAVEYARD_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "AMP",
          "amount": 1
        }
      ]
    }
  ]
}
```

### vantom_banshee_blue  — no-talishar-logic
text: '**Rune Gate**\n\n**Blood Debt**'
```json
{
  "slug": "vantom_banshee_blue",
  "abilities": []
}
```

### malign_blue  — no-talishar-logic
text: "**Stealth**\n\nDamage that would be dealt by Malign can't be prevented."
```json
{
  "slug": "malign_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "ward_type": "STEALTH"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "ARCANE_BARRIER",
          "amount": 0
        }
      ]
    }
  ]
}
```

### singeing_flowstride_yellow  — no-talishar-logic
text: '**Quickstrike** - If this has go again, it gets "When this attacks a hero, deal 1 arcane damage to them."\n\nThe first time this deals damage to a hero, create a Lightning Flow token.'
```json
{
  "slug": "singeing_flowstride_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "GO_AGAIN_ACTIVE"
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEAL_DAMAGE",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        },
        {
          "type": "FLAG_SET",
          "flag": "FIRST_DAMAGE_TO_HERO"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Lightning Flow"
        }
      ]
    }
  ]
}
```

### evo_thruster_yellow  — no-talishar-logic
text: 'If you have a base legs equipped, **transform** it into this, then equip this.\n\n**Once per Turn Instant** - Destroy a card under this: You may attack an additional time with target weapon this turn.\n\n**Blade Break**'
```json
{
  "slug": "evo_thruster_yellow",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```

### teklo_base_chest  — no-talishar-logic
text: '**Blade Break**'
```json
{
  "slug": "teklo_base_chest",
  "abilities": [
    {
      "ability_type": "STATIC_TRIGGERED",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```

### speed_demon_red  — no-talishar-logic
text: '**Scrap**\n\nIf you control a Hyper Driver, this gets +1{p}.\n\nWhen this attacks, if it scrapped a Hyper Driver, create a Hyper Driver token with 2 steam counters.'
```json
{
  "slug": "speed_demon_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Hyper Driver"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SCRAPPED_HYPER_DRIVER"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Hyper Driver",
          "amount": 1,
          "counters": {
            "steam": 2
          }
        }
      ]
    }
  ]
}
```

### shimmering_specter_yellow  — no-talishar-logic
text: 'While this is attacking or defending, when this leaves the arena, create a Spectral Shield token.\n\n**Mirage**'
```json
{
  "slug": "shimmering_specter_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "OR",
          "conditions": [
            {
              "type": "IN_COMBAT",
              "combat_role": "ATTACKER"
            },
            {
              "type": "IN_COMBAT",
              "combat_role": "DEFENDER"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_LEAVE_PLAY",
          "effects": [
            {
              "type": "CREATE_TOKEN",
              "token_type": "Spectral Shield"
            }
          ]
        }
      ]
    }
  ]
}
```

### take_the_upper_hand_red  — no-talishar-logic
text: "Play this only if you've wagered this chain link.\n\nTarget attack gets +3{p}."
```json
{
  "slug": "take_the_upper_hand_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "WAGERED_THIS_CHAIN_LINK"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```

### creep_red  — no-talishar-logic
text: '**Stealth**\n\nWhen this attacks, the next attack with stealth you play this combat chain gets **go again**.'
```json
{
  "slug": "creep_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "CREEP_STEALTH_GO_AGAIN"
        }
      ]
    }
  ]
}
```

### steel_on_steel_blue  — no-talishar-logic
text: 'While this is defending a weapon attack, this gets +1{d}.'
```json
{
  "slug": "steel_on_steel_blue",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "ATTACK_IS_WEAPON"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```

### frosthaven_sheath_red  — no-talishar-logic
text: "**Ice Bond** - If an Ice card was pitched to play this, create a Frostbite token under the attacking hero's control."
```json
{
  "slug": "frosthaven_sheath_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "ref": "ICE"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Frostbite",
          "controller": "attacker"
        }
      ]
    }
  ]
}
```

### circular_flowtide_yellow  — no-talishar-logic
text: 'When this leaves the arena, create a Lightning Flow token.\n\n**Ward 2**'
```json
{
  "slug": "circular_flowtide_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_LEAVE_PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Lightning Flow"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "amount": 2
        }
      ]
    }
  ]
}
```

### haven_veil_red  — no-talishar-logic
text: 'When this enters the arena, prevent the next 3 arcane damage that would be dealt to you this turn.\n\nAt the beginning of your action phase, destroy this.'
```json
{
  "slug": "haven_veil_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "HAVEN_VEIL_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "HAVEN_VEIL_ACTIVE"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    }
  ]
}
```

### arc_ramp_red  — no-talishar-logic
text: '**Amp 3**\n\nYou may destroy a Lightning Flow you control. If you do, this gets **go again**.'
```json
{
  "slug": "arc_ramp_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "AMP",
          "amount": 3
        },
        {
          "type": "MAY_DESTROY_SILVERS_TO_EQUIP",
          "target": "Lightning Flow",
          "conditions": [
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "Lightning Flow"
            }
          ],
          "effects_if_destroyed": [
            {
              "type": "GAIN",
              "keyword": "GO_AGAIN"
            }
          ]
        }
      ]
    }
  ]
}
```

### heroic_pose_blue  — no-talishar-logic
text: 'Your next attack this turn gets +1{p}.\n\n**The crowd cheers** you.\n\n**Go again**'
```json
{
  "slug": "heroic_pose_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "HEROIC_POSE_ACTIVE"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "HEROIC_POSE_ACTIVE"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```

### starworld_warning_yellow  — no-talishar-logic
text: 'Create 2 Lightning Flow tokens.'
```json
{
  "slug": "starworld_warning_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Lightning Flow",
          "amount": 2
        }
      ]
    }
  ]
}
```

### burnished_bunkerplate  — no-talishar-logic
text: '**Defense Reaction** - Destroy this: You may add an action card from your arsenal to the active chain link as a defending card.'
```json
{
  "slug": "burnished_bunkerplate",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "MAY",
          "effect": {
            "type": "PUT_REF_BOTTOM",
            "ref": "arsenal",
            "conditions": [
              {
                "type": "CARD_IN_ZONE",
                "zone": "arsenal",
                "card_type": "action"
              }
            ]
          }
        }
      ]
    }
  ]
}
```

### grasp_of_the_darknight  — no-talishar-logic
text: '**Action** - {r}, destroy this: **Opt 1**, then create a Runechant token. **Go again**'
```json
{
  "slug": "grasp_of_the_darknight",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "OPT",
          "amount": 1
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Runechant"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### spell_fray_cloak  — no-talishar-logic
text: '**Spellvoid 1**'
```json
{
  "slug": "spell_fray_cloak",
  "abilities": []
}
```

### insult_to_injury_red  — no-talishar-logic
text: 'When this attacks a hero, if you have more {h} than them, this gets **go again**.'
```json
{
  "slug": "insult_to_injury_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "AND",
          "conditions": [
            {
              "type": "ATTACK_TARGET_IS_HERO"
            },
            {
              "type": "HEALTH_GT_OPP"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### betsy_skin_in_the_game  — no-talishar-logic
text: 'Whenever an attack you control **wagers**, you may pay {r}{r}. If you do, the attack gets +1{p} and **overpower**.'
```json
{
  "slug": "betsy_skin_in_the_game",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ACTIVATE",
      "conditions": [
        {
          "type": "CONTROLS_ATTACK_ACTION"
        },
        {
          "type": "HAS_KEYWORD",
          "keyword": "WAGER"
        }
      ],
      "cost": [
        {
          "type": "PAY_RESOURCES",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "OVERPOWER"
        }
      ]
    }
  ]
}
```

### song_of_sinew_yellow  — no-talishar-logic
text: 'Reveal the top 4 cards of your deck. Your next attack this turn gets +X{p}, where X is the number of cards with 6 or more {p} revealed this way. Put them back in any order.\n\n**Go again**'
```json
{
  "slug": "song_of_sinew_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "REVEAL_TOP_DECK",
          "amount": 4
        },
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": {
            "type": "COUNT",
            "condition": {
              "type": "CARD_IN_ZONE",
              "zone": "REVEALED",
              "conditions": [
                {
                  "type": "ATTACK_POWER_GTE",
                  "amount": 6
                }
              ]
            }
          }
        },
        {
          "type": "PUT_CARDS_BOTTOM",
          "zone": "REVEALED"
        },
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### cosmic_duality_red  — no-talishar-logic
text: '**Instant** - {r}, discard this: Deal 1 arcane damage to target hero. Create a Lightning Flow token.\n\n**Fragment**'
```json
{
  "slug": "cosmic_duality_red",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "DISCARD_SELF"
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "target": "hero",
          "amount": 1
        },
        {
          "type": "CREATE_TOKEN",
          "token": "Lightning Flow"
        }
      ]
    }
  ]
}
```

### concealed_nerve_gas  — no-talishar-logic
text: "**Cloaked**\n\nWhile this is equipped face-down, when an attack with go again hits you, destroy this and create a Frailty token under each opponent's control."
```json
{
  "slug": "concealed_nerve_gas",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CLOAKED"
        },
        {
          "type": "HAS_KEYWORD",
          "keyword": "GO_AGAIN"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Frailty",
          "amount": 1,
          "target": "opponent"
        }
      ]
    }
  ]
}
```

### full_of_bravado_yellow  — no-talishar-logic
text: 'When this attacks or defends, if you control an aura of suspense, create a Confidence token.'
```json
{
  "slug": "full_of_bravado_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Suspense"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Confidence"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_DEFEND",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Suspense"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Confidence"
        }
      ]
    }
  ]
}
```

### incision_red  — no-talishar-logic
text: 'Target dagger attack gets +3{p}.'
```json
{
  "slug": "incision_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```

### beckoning_hunger_red  — no-talishar-logic
text: 'When this attacks, banish the top card of your deck.\n\nWhen this hits, create a Blasmophet, the Insatiable Hunger token.\n\n**Blood Debt**'
```json
{
  "slug": "beckoning_hunger_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "BANISH",
          "target": "top_deck"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_name": "Blasmophet, the Insatiable Hunger"
        }
      ]
    }
  ]
}
```

### tough_smashup_blue  — no-talishar-logic
text: "When this defends, **clash** with the attacking hero. The winner creates a Toughness token. You may put your revealed card on the bottom of its owner's deck."
```json
{
  "slug": "tough_smashup_blue",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "CLASH"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "TOUGHNESS"
        },
        {
          "type": "PUT_HAND_CARD_BOTTOM",
          "target": "revealed"
        }
      ]
    }
  ]
}
```

### inflame_red  — no-talishar-logic
text: "When you attack with Inflame, if you've played another red card this turn, you may return a Phoenix Flame from your graveyard to your hand.\n\n**Go again**"
```json
{
  "slug": "inflame_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "RED_CARD_PLAYED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "RETURN_TO_HAND",
          "target": "Phoenix Flame",
          "zone": "GRAVEYARD"
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### swift_pickup_red  — no-talishar-logic
text: 'When this attacks, you may put a shuriken item from your graveyard on the bottom of your deck. If you do, this gets +1{p}.\n\n**Go again**'
```json
{
  "slug": "swift_pickup_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "effects": [
        {
          "type": "MAY",
          "effects": [
            {
              "type": "MOVE_REF",
              "ref": "shuriken_item",
              "from": "GRAVEYARD",
              "to": "BOTTOM_DECK"
            },
            {
              "type": "MODIFY_ATTACK",
              "mod": "add",
              "amount": 1
            }
          ]
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### power_play_red  — no-talishar-logic
text: 'If this was played from arsenal, it gets +5{p}.'
```json
{
  "slug": "power_play_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "PLAYED_FROM_ARSENAL"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 5
        }
      ]
    }
  ]
}
```

### two_steps_ahead_blue  — no-talishar-logic
text: 'At the start of your turn, destroy this, then create a Confidence and 3 Might tokens.'
```json
{
  "slug": "two_steps_ahead_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Confidence",
          "amount": 1
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Might",
          "amount": 3
        }
      ]
    }
  ]
}
```

### right_behind_you_red  — no-talishar-logic
text: 'When this defends together with another card from hand, this gets +1{d} and you may look at the top card of your deck. You may put it on the bottom.'
```json
{
  "slug": "right_behind_you_red",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "DEFENDS_WITH_OTHER_HAND_CARD"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "LOOK_AT",
          "target": "top_deck"
        },
        {
          "type": "PUT_CARDS_BOTTOM",
          "target": "top_deck",
          "optional": true
        }
      ]
    }
  ]
}
```

### king_shark_harpoon_red  — no-talishar-logic
text: "**Go Fish** - When this hits a hero, they choose and reveal a card from their hand. If it's an attack action card, they discard it and you create a Gold token. If you've activated a cannon this turn, instead look at their hand and you choose the card."
```json
{
  "slug": "king_shark_harpoon_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "REVEAL_HAND_MARK_IF_TYPE",
          "card_type": "ATTACK_ACTION",
          "on_true": [
            {
              "type": "DISCARD",
              "target": "opponent"
            },
            {
              "type": "CREATE_TOKEN",
              "token_type": "Gold"
            }
          ],
          "on_false": [
            {
              "type": "FLAG_SET",
              "flag": "KING_SHARK_HARPOON_REVEAL"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ACTIVATE",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "KING_SHARK_HARPOON_REVEAL"
        },
        {
          "type": "FLAG_SET",
          "flag": "CANNON_ACTIVATED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "LOOK_AT",
          "target": "opponent_hand"
        },
        {
          "type": "SELECT_FROM_REF",
          "ref": "opponent_hand",
          "amount": 1
        }
      ]
    }
  ]
}
```

### fasting_carcass_yellow  — no-talishar-logic
text: 'The next yellow action card you play this turn gets **go again**.\n\n**Go again**\n\n**Blood Debt**'
```json
{
  "slug": "fasting_carcass_yellow",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "FASTING_CARCASS_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "FASTING_CARCASS_ACTIVE"
        },
        {
          "type": "AND",
          "conditions": [
            {
              "type": "CARD_IN_ZONE",
              "zone": "HAND",
              "card_type": "ACTION",
              "color": "YELLOW"
            },
            {
              "type": "DURING_TURN"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### gloves_of_astral_sanctuary  — no-talishar-logic
text: '**Instant** - {t} your hero, destroy this: Prevent the next 1 damage that would be dealt to you this turn.'
```json
{
  "slug": "gloves_of_astral_sanctuary",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "ASTRAL_SANCTUARY_ACTIVE"
        }
      ]
    }
  ]
}
```

### instill_fear_red  — no-talishar-logic
text: 'When this attacks a hero, **intimidate** them.'
```json
{
  "slug": "instill_fear_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```

### smashing_ground_blue  — no-talishar-logic
text: 'If this has 6 or more {p}, it gets "When this hits a hero, destroy a card in their arsenal."'
```json
{
  "slug": "smashing_ground_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [
        {
          "type": "SELF_ATTACK_POWER_GTE",
          "amount": 6
        },
        {
          "type": "ATTACK_TARGET_IS_HERO"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_ARSENAL",
          "target": "opponent"
        }
      ]
    }
  ]
}
```

### arcanic_cunning_blue  — no-talishar-logic
text: 'While this is attacking, defending, or on the stack, if you would be dealt arcane damage, prevent 1 of that damage.'
```json
{
  "slug": "arcanic_cunning_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "OR",
          "conditions": [
            {
              "type": "IN_COMBAT",
              "combat_role": "ATTACKER"
            },
            {
              "type": "IN_COMBAT",
              "combat_role": "DEFENDER"
            },
            {
              "type": "FLAG_SET",
              "flag": "ON_STACK"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "WARD",
          "ward_type": "ARCANE"
        }
      ]
    }
  ]
}
```

### renounce_violence_blue  — no-talishar-logic
text: 'Destroy up to 3 Might tokens. Create a Toughness token for each token destroyed this way.'
```json
{
  "slug": "renounce_violence_blue",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "token_type": "Might",
          "max_destroy": 3
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Toughness",
          "amount": 3
        }
      ]
    }
  ]
}
```

### shattering_flowtide_red  — no-talishar-logic
text: 'Whenever this fragments, create a Lightning Flow token.\n\n**Fragment**'
```json
{
  "slug": "shattering_flowtide_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BECOME",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "Fragment"
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Lightning Flow"
        }
      ]
    }
  ]
}
```

### blessing_of_bellona_yellow  — no-talishar-logic
text: '**Go again**\n\nWhenever a card is put into your soul, create a Courage token.\n\nAt the start of your turn, put this into your soul.'
```json
{
  "slug": "blessing_of_bellona_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_TOKEN_CREATED",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "ref": "soul",
          "pitch": 2
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Courage"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "MOVE_REF",
          "source_ref": "self",
          "destination_ref": "soul"
        }
      ]
    }
  ]
}
```

### good_deeds_dont_go_unnoticed_yellow  — no-talishar-logic
text: "At the start of each other hero's turn, choose 1; they draw a card, they gain {r}, they gain 1{h}, or their next attack this turn gains +1{p}.\n\nAt the start of your turn, destroy this. If another hero drew a card from this, you draw a card, then repeat for {r}, {h}, and {p}."
```json
{
  "slug": "good_deeds_dont_go_unnoticed_yellow",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DRAWN_FROM_AURA"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "SET_FLAG",
          "flag": "DRAWN_FROM_AURA",
          "value": false
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "GAINED_RESOURCE_FROM_AURA"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 1
        },
        {
          "type": "SET_FLAG",
          "flag": "GAINED_RESOURCE_FROM_AURA",
          "value": false
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "GAINED_LIFE_FROM_AURA"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "LIFE",
          "amount": 1
        },
        {
          "type": "SET_FLAG",
          "flag": "GAINED_LIFE_FROM_AURA",
          "value": false
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "GAINED_ATTACK_FROM_AURA"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "SET_FLAG",
          "flag": "GAINED_ATTACK_FROM_AURA",
          "value": false
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "DRAWN_FROM_AURA"
        }
      ],
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        },
        {
          "type": "SET_FLAG",
          "flag": "DRAWN_FROM_AURA",
          "value": false
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "GAINED_RESOURCE_FROM_AURA"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "RESOURCE_POINTS",
          "amount": 1
        },
        {
          "type": "SET_FLAG",
          "flag": "GAINED_RESOURCE_FROM_AURA",
          "value": false
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "GAINED_LIFE_FROM_AURA"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "asset": "LIFE",
          "amount": 1
        },
        {
          "type": "SET_FLAG",
          "flag": "GAINED_LIFE_FROM_AURA",
          "value": false
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN_IN_GRAVEYARD",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "GAINED_ATTACK_FROM_AURA"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        },
        {
          "type": "SET_FLAG",
          "flag": "GAINED_ATTACK_FROM_AURA",
          "value": false
        }
      ]
    }
  ]
}
```

### luminaris  — no-talishar-logic
text: 'During your action phase, Illusionist auras you control are weapons with 1 base {p} and "**Once per Turn Action** - 0: **Attack**"\n\nIf there is a yellow card in your pitch zone, your Illusionist attacks get **go again**.'
```json
{
  "slug": "luminaris",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "DURING_TURN",
          "player": "self"
        },
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Illusionist"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA",
          "mod": "set",
          "amount": 1
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "color": "yellow"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### shining_courage_red  — no-talishar-logic
text: 'Up to one target defending action card gets +3{d} this turn.\n\n**The crowd cheers** you.'
```json
{
  "slug": "shining_courage_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 3,
          "target": "defending_action_card",
          "max_targets": 1
        },
        {
          "type": "SET_FLAG",
          "flag": "THE_CROWD_CHEERS"
        }
      ]
    }
  ]
}
```

### cosmic_suture_yellow  — no-talishar-logic
text: 'Prevent the next 3 damage that would be dealt to you this turn.\n\n**Starfall** - If an instant card has been put into your graveyard this turn, deal 1 arcane damage to target hero.'
```json
{
  "slug": "cosmic_suture_yellow",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "COSMIC_SUTURE_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "COSMIC_SUTURE_ACTIVE"
        }
      ],
      "effects": [
        {
          "type": "WARD",
          "amount": 3
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "STARFALL_TRIGGERED"
        }
      ],
      "effects": [
        {
          "type": "DEAL_ARCANE",
          "amount": 1
        }
      ]
    }
  ]
}
```

### gloves_of_azure_waves  — no-talishar-logic
text: '**Arcane Barrier 1**\n\n**High Tide** - If there are 2 or more blue cards in your pitch zone, this gets +3{d} and **blade break**.'
```json
{
  "slug": "gloves_of_azure_waves",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "ARCANE_BARRIER",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "REF_PITCH_IS",
          "ref": "self",
          "color": "blue",
          "amount": 2
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 3
        },
        {
          "type": "INTIMIDATE"
        }
      ]
    }
  ]
}
```

### small_problem_yellow  — no-talishar-logic
text: 'If this has {p} greater than its base, it gets +1{p}.\n\n**Crush** - When this deals 4 or more damage to a hero, destroy an aura they control.'
```json
{
  "slug": "small_problem_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "SELF_ATTACK_POWER_GTE",
          "amount": 4
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_CRUSH",
      "effects": [
        {
          "type": "DESTROY_TOKEN",
          "target": "OPPONENT_CONTROLLED_AURA"
        }
      ]
    }
  ]
}
```

### runebleed_robe  — no-talishar-logic
text: '**Instant** - Destroy this and a Runechant you control: Prevent the next 1 arcane damage that would be dealt to you this turn.\n\n**Arcane Barrier 1**'
```json
{
  "slug": "runebleed_robe",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": "controlled",
          "conditions": [
            {
              "type": "HAS_KEYWORD",
              "keyword": "Runechant"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "RUNEBLEED_ROBE_ARCANE_BARRIER_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "ARCANE_BARRIER",
          "amount": 1,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "RUNEBLEED_ROBE_ARCANE_BARRIER_ACTIVE"
            }
          ]
        }
      ]
    }
  ]
}
```

### insult_to_injury_yellow  — no-talishar-logic
text: 'When this attacks a hero, if you have more {h} than them, this gets **go again**.'
```json
{
  "slug": "insult_to_injury_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        },
        {
          "type": "HEALTH_GT_OPP"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### waxing_specter_yellow  — no-talishar-logic
text: "If you've pitched a blue card this turn, this enters the arena with a +1{p} counter.\n\n**Ward 2**"
```json
{
  "slug": "waxing_specter_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "PITCHED_BLUE_CARD_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "PUT_COUNTER",
          "counter": "power",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "WARD",
          "amount": 2
        }
      ]
    }
  ]
}
```

### frost_hex_blue  — no-talishar-logic
text: '**Iyslander Specialization**\n\nFrostbites you control have "At the beginning of your end phase, this deals 1 arcane damage to you."'
```json
{
  "slug": "frost_hex_blue",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "CONTROLS_TOKEN_TYPE",
          "token_type": "Frostbite"
        }
      ],
      "effects": [
        {
          "type": "INJECT_TRIGGER",
          "trigger": {
            "trigger_type": "END_OF_TURN",
            "effects": [
              {
                "type": "DEAL_ARCANE",
                "amount": 1,
                "target": "self"
              }
            ]
          }
        }
      ]
    }
  ]
}
```

### hala_bladesaint_of_the_vow  — no-talishar-logic
text: '**Action** - {r}{r}{r}, {t}: **Sharpen** target sword you control. **Go again**'
```json
{
  "slug": "hala_bladesaint_of_the_vow",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 3,
      "cost": [
        {
          "type": "PITCH",
          "amount": 1
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "SHARPEN"
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### unwinding_finality_red  — no-talishar-logic
text: 'When this hits, draw a card.\n\nWhenever this fragments, you may put a Lightning instant card from your graveyard on top of your deck.\n\n**Fragment**'
```json
{
  "slug": "unwinding_finality_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [
        {
          "type": "DRAW",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BECOME",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "Fragment"
        }
      ],
      "effects": [
        {
          "type": "SEARCH_DECK",
          "card_type": "Instant",
          "card_class": "Lightning",
          "amount": 1,
          "destination": "TOP_DECK"
        }
      ]
    }
  ]
}
```

### flittering_forcefield_blue  — no-talishar-logic
text: "While this is defending, if you've played an instant card this chain link, this gets +1{d}."
```json
{
  "slug": "flittering_forcefield_blue",
  "abilities": [
    {
      "ability_type": "DEFENSE_REACTION",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "INSTANT_PLAYED_THIS_CHAIN_LINK"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_DEFENSE_VALUE",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```

### spellbane_trap_red  — no-talishar-logic
text: 'Your next arrow attack this turn gets +3{p}.\n\n**Go again**\n\nWhen this defends and the attacking hero has dealt arcane damage this turn, create a Spellbane Aegis token.'
```json
{
  "slug": "spellbane_trap_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3,
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "SPELLBANE_TRAP_ACTIVATED"
            }
          ]
        }
      ]
    },
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    },
    {
      "ability_type": "DEFENSE_REACTION",
      "trigger": "ON_DEFEND",
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_name": "Spellbane Aegis",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "OPPONENT_DEALT_ARCANE_DAMAGE"
            }
          ]
        }
      ]
    }
  ]
}
```

### aurora_emissary_of_lightning  — no-talishar-logic
text: '**Instant** - {r}{r}, {t}, destroy a Lightning Flow you control: Create an Embodiment of Lightning token.'
```json
{
  "slug": "aurora_emissary_of_lightning",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 2,
      "cost": [
        {
          "type": "PITCH",
          "amount": 1
        },
        {
          "type": "DESTROY_PERMANENT",
          "target": "self",
          "conditions": [
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "Lightning Flow"
            }
          ]
        }
      ],
      "effects": [
        {
          "type": "CREATE_TOKEN",
          "token_type": "Embodiment of Lightning"
        }
      ]
    }
  ]
}
```

### comeback_kid_blue  — no-talishar-logic
text: "When this attacks a hero, if you have less {h} than them, **the crowd cheers** you.\n\nIf you've been cheered this turn, this gets +1{p}."
```json
{
  "slug": "comeback_kid_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "conditions": [
        {
          "type": "ATTACK_TARGET_IS_HERO"
        },
        {
          "type": "HEALTH_LT_OPP"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "CROWD_CHEERS_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CROWD_CHEERS_ACTIVE"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 1
        }
      ]
    }
  ]
}
```

### stellar_glide_yellow  — no-talishar-logic
text: 'When this attacks, you may destroy a Lightning Flow you control. If you do, this gets **go again**.'
```json
{
  "slug": "stellar_glide_yellow",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "MAY_DESTROY_SILVERS_TO_EQUIP",
          "target": "Lightning Flow",
          "conditions": [
            {
              "type": "CONTROLS_TOKEN_TYPE",
              "token_type": "Lightning Flow"
            }
          ]
        },
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "DESTROYED_LIGHTNING_FLOW"
            }
          ]
        }
      ]
    }
  ]
}
```

### ominous_excavation_blue  — no-talishar-logic
text: 'You may shuffle an instant card from your graveyard into your deck.\n\nIf an aura you control was destroyed this turn, create a Ponder token.'
```json
{
  "slug": "ominous_excavation_blue",
  "abilities": [
    {
      "ability_type": "INSTANT",
      "effects": [
        {
          "type": "BANISH_TRAP_FROM_GRAVEYARD_PLAYABLE",
          "card_type": "Instant"
        },
        {
          "type": "CREATE_TOKEN",
          "token_type": "Ponder",
          "conditions": [
            {
              "type": "FLAG_SET",
              "flag": "AURA_DESTROYED_THIS_TURN"
            }
          ]
        }
      ]
    }
  ]
}
```

### ebbing_arcstride_blue  — no-talishar-logic
text: 'Whenever this fragments, it gets **go again**.\n\n**Fragment**'
```json
{
  "slug": "ebbing_arcstride_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_BECOME",
      "conditions": [
        {
          "type": "HAS_KEYWORD",
          "keyword": "Fragment"
        }
      ],
      "effects": [
        {
          "type": "GAIN",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```

### templar_spellbane  — no-talishar-logic
text: "**Instant** - Destroy this: Prevent the next 1 arcane damage that would be dealt to you this turn. If you've activated a weapon this turn, instead prevent the next 2.\n\n**Battleworn**"
```json
{
  "slug": "templar_spellbane",
  "abilities": [
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 0,
      "cost": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ],
      "effects": [
        {
          "type": "SET_FLAG",
          "flag": "TEMPLAR_SPELLBANE_ACTIVE"
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "TEMPLAR_SPELLBANE_ACTIVE"
        }
      ],
      "effects": [
        {
          "type": "ARCANE_BARRIER",
          "amount": 1
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "TEMPLAR_SPELLBANE_ACTIVE"
        },
        {
          "type": "FLAG_SET",
          "flag": "WEAPON_ACTIVATED_THIS_TURN"
        }
      ],
      "effects": [
        {
          "type": "ARCANE_BARRIER",
          "amount": 2
        }
      ]
    }
  ]
}
```

### volcanic_vice  — no-talishar-logic
text: "If you've created a Seismic Surge this turn, this gets **spellvoid 3**."
```json
{
  "slug": "volcanic_vice",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "SEISMIC_SURGE_CREATED"
        }
      ],
      "effects": [
        {
          "type": "GRANT_SUBTYPE",
          "subtype": "Spellvoid",
          "amount": 3
        }
      ]
    }
  ]
}
```

### flex_strength_red  — no-talishar-logic
text: 'If this has 6 or more {p}, it gets +3{p}.'
```json
{
  "slug": "flex_strength_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "SELF_ATTACK_POWER_GTE",
          "amount": 6
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK",
          "mod": "add",
          "amount": 3
        }
      ]
    }
  ]
}
```

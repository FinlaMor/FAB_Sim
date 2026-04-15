# Card Set Status

See also: [[Architecture Hub]] | [[Card Effects System]] | [[Work Tracks]]

Implementation priority: cards needed by target decks first, then full set coverage.

## Target Decks (Immediate Priority)
| Hero | Format | Status |
|------|--------|--------|
| Kayo | CC | ✅ Done (OUT set) |
| Victor | CC | ❌ Not started |
| Mario | CC | ❌ Not started |

## Set Implementation Status

| Set | Code | Heroes Covered | Status | Notes |
|-----|------|---------------|--------|-------|
| Welcome to Rathe | WTR | Dorinthea, Rhinar, Bravo, Katsu | ✅ Done | All 4 blitz decks + WTR cards |
| Arcane Rising | ARC | — | ❓ Partial | Some cards via hero files |
| Crucible of War | CRU | — | ❌ Not started | |
| Monarch | MON | — | ❌ Not started | |
| Tales of Aria | ELE | — | ❌ Not started | |
| Dynasty | DYN | — | ❌ Not started | |
| Everfest | EVR | — | ❌ Not started | |
| Uprising | UPR | — | ❌ Not started | |
| Outsiders | OUT | Kayo | ✅ Done | Reviled mechanic, Vigor/Might tokens |
| Dead the Dead | DTD | — | ❌ Not started | |
| Misteria | MST | — | ❌ Not started | |
| Rosetta | ROS | — | ❌ Not started | |
| Heavy Hitters | HVY | — | ❌ Not started | |
| Hunted | HNT | Arakni Marionette | ✅ Done | Mark, Stealth, Retrieve, graphene_chelicera |
| Part the Mistveil | PTM | — | ❌ Not started | |
| High Seas | SEA | Marlynn | ✅ Done | Go Fish, Gold token, harpoon hits |

## Hero Class Files
| File | Heroes/Cards |
|------|-------------|
| `card_effects/card_triggers_extended.py` | All per-card triggers |
| `card_effects/registry.py` | All play/hit/reaction registries |

## Mechanics Implemented
| Mechanic | CR Ref | Status |
|----------|--------|--------|
| Battleworn | 8.3.1 | ✅ |
| Blade Break | 8.3.2 | ✅ |
| Boost | 8.3.3 | ✅ |
| Combo | 8.4.1 | ✅ |
| Crush | 8.4.2 | ✅ |
| Dominate | 8.3.7 | ✅ |
| Go Again | 8.3.8 | ✅ |
| Intimidate | 8.5.17 | ✅ |
| Overpower | 8.3.16 | ✅ |
| Phantasm | 8.4.6 | ✅ |
| Piercing | 8.3.18 | ✅ |
| Reprise | 8.4.8 | ✅ |
| Spectra | — | ✅ (aura self-destruct) |
| Stealth | — | ✅ (HNT) |
| Temper | 8.3.22 | ✅ |
| Mark | — | ✅ (HNT) |
| Reviled | — | ✅ (OUT) |
| Fusion | 8.4.3 | ✅ |
| Surge | 8.4.9 | ✅ |
| Rupture | 8.4 | ✅ |
| Arcane Barrier | 8.3 | ✅ |
| Ward | — | ✅ |
| Channel | — | ✅ |
| Chi payment | — | ✅ |
| Retrieve | — | ✅ (HNT) |
| Heave | — | ✅ |
| Crank | — | ✅ |
| Suspense | — | ✅ |
| Blood Debt | — | ✅ |
| Galvanize | — | ✅ |

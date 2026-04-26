# Card Set Status

See also: [[Architecture Hub]] | [[Card Effects System]] | [[Work Tracks]]

Implementation priority: cards needed by target decks first, then full set coverage.

## Target Decks (Immediate Priority)
| Hero   | Format | Status        |
| ------ | ------ | ------------- |
| Kayo   | CC     | ❓ Partial     |
| Victor | CC     | ❌ Not started |
| Mario  | CC     | ❌ Not started |

## Set Implementation Status

| Set               | Code | Heroes Covered    | Status        | Notes                                       |
| ----------------- | ---- | ----------------- | ------------- | ------------------------------------------- |
| Welcome to Rathe  | WTR  | -                 | ❓ Partial     |                                             |
| Arcane Rising     | ARC  | —                 | ❓ Partial     | Some cards via hero files                   |
| Crucible of War   | CRU  | —                 | ❌ Not started |                                             |
| Monarch           | MON  | —                 | ❌ Not started |                                             |
| Tales of Aria     | ELE  | —                 | ❌ Not started |                                             |
| Dynasty           | DYN  | —                 | ❌ Not started |                                             |
| Everfest          | EVR  | —                 | ❌ Not started |                                             |
| Uprising          | UPR  | —                 | ❌ Not started |                                             |
| Outsiders         | OUT  | -                 | ❌ Not started |                                             |
| Dusk til Dawn     | DTD  | —                 | ❌ Not started |                                             |
| Part the Mistveil | MST  | —                 | ❌ Not started |                                             |
| Rosetta           | ROS  | —                 | ❌ Not started |                                             |
| Heavy Hitters     | HVY  | —                 | ❌ Not started | Vigor/Might tokens                          |
| Hunted            | HNT  | Arakni Marionette | ❓ Partial     | Mark, Stealth, Retrieve, graphene_chelicera |
| High Seas         | SEA  | Marlynn           | ❓ Partial     | Go Fish, Gold token, harpoon hits           |
| Superslam         | SUP  | RKO               | ❓ Partial     | Reviled mechanic                            |

## Trigger Files
| File                                     | Heroes/Cards                     |
| ---------------------------------------- | -------------------------------- |
| `card_effects/card_triggers_extended.py` | All per-card triggers            |
| `card_effects/registry.py`               | All play/hit/reaction registries |

## Mechanics Implemented
| Mechanic       | CR Ref | Status                 |
| -------------- | ------ | ---------------------- |
| Battleworn     | 8.3.1  | ✅                      |
| Blade Break    | 8.3.2  | ✅                      |
| Boost          | 8.3.3  | ✅                      |
| Combo          | 8.4.1  | ✅                      |
| Crush          | 8.4.2  | ✅                      |
| Dominate       | 8.3.7  | ✅                      |
| Go Again       | 8.3.8  | ✅                      |
| Intimidate     | 8.5.17 | ✅                      |
| Overpower      | 8.3.16 | ✅                      |
| Phantasm       | 8.4.6  | ✅                      |
| Piercing       | 8.3.18 | ✅                      |
| Reprise        | 8.4.8  | ✅                      |
| Spectra        | —      | ✅ (aura self-destruct) |
| Stealth        | —      | ✅ (DYN)                |
| Temper         | 8.3.22 | ✅                      |
| Mark           | —      | ✅ (HNT)                |
| Reviled        | —      | ✅ (SUP)                |
| Fusion         | 8.4.3  | ✅                      |
| Surge          | 8.4.9  | ✅                      |
| Rupture        | 8.4    | ✅                      |
| Arcane Barrier | 8.3    | ✅                      |
| Ward           | —      | ✅                      |
| Channel        | —      | ✅                      |
| Chi payment    | —      | ✅                      |
| Retrieve       | —      | ✅ (HNT)                |
| Heave          | —      | ✅                      |
| Crank          | —      | ✅                      |
| Suspense       | —      | ✅                      |
| Blood Debt     | —      | ✅                      |
| Galvanize      | —      | ✅                      |

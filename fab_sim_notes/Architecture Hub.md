# Architecture Hub

Central map of the FAB Simulator codebase. Click any link to open that note.

## Layers

```
[RL / Training]  →  [[ML Pipeline]]
[State Encoding] →  encoder/
[Game Engine]    →  [[Engine Overview]]
[Card Effects]   →  [[Card Effects System]]
[Card Data]      →  card_data/ slug_index
```

## Module Notes
- [[Engine Overview]] — game loop, state, actions, effects
- [[Card Effects System]] — registries, triggers, keywords, parser
- [[Card Set Status]] — which sets and heroes are implemented
- [[Work Tracks]] — what needs to be done next
- [[ML Pipeline]] — IQL training, encoder, data collection

## Key Files (by size / importance)
| File                                   | Lines | Role                                       |
| -------------------------------------- | ----- | ------------------------------------------ |
| card_effects/card_triggers_extended.py | 5473  | Per-card triggers                          |
| engine/effect_keywords.py              | 3659  | CR 8.5 primitives                          |
| card_effects/triggers.py               | 3505  | Trigger system                             |
| card_effects/registry.py               | 3052  | Card-specfic effects registry              |
| card_effects/card_keywords.py          | 1984  | Keyword impls                              |
| engine/engine.py                       | 1694  | Game loop                                  |
| engine/state.py                        | 1273  | Data structures. Gamestate, Zones, Player  |
| card_effects/text_trigger_parser.py    | 1172  | Auto-parser                                |
| engine/actions.py                      | 1086  | Action objects. Old action generator code. |
| engine/card.py                         | 811   | Card model                                 |
| engine/play.py                         | 594   | Legal action generator (new)               |
| engine/effects.py                      | 570   | Continuous effects                         |

## Quick Links
- [[Work Tracks#Track 1 — Engine Rules|Engine rules gaps]]
- [[Work Tracks#Track 2 — Card Implementations|Card implementation status]]
- [[Card Set Status]]

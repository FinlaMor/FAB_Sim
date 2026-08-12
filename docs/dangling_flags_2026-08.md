# Flags read but never set — 167 flags, 195 cards (2026-08-12)

The largest defect class found so far, and the cheapest to detect. A `FLAG_SET`
condition compiles to `flag in player.current_turn_effects`. If nothing ever
appends that string, the condition is **permanently False** and the ability it
gates **can never fire under any circumstances** — while the card still loads,
still passes its own test, and looks fully implemented.

**195 of 1,011 cards (~19%) have at least one such ability.**

## The sweep

```python
# readers: any {"type": "FLAG_SET", "flag": X}
# setters: ANY json node carrying a "flag" key that is not a FLAG_SET
#          (cost_types.py can set a flag from a COST, not just SET_FLAG)
# plus the strings engine python actually appends to current_turn_effects
```

Run it after any bulk authoring. It is the same shape as the param-key sweep
and the hallucinated-keyword sweep: one query, whole class, invisible per-card.

### Getting the number right

The first two attempts over-reported, and the third under-reported. Worth
repeating the method rather than the number:

1. **Grep engine source for the flag name** — too loose. A name can appear in a
   comment or an unrelated identifier.
2. **Extract what engine code actually writes** into `current_turn_effects`.
   Only **13 strings**, nearly all lowercase, against ~221 mostly-uppercase
   names the cards read. This is the authoritative list.
3. **Count any node with a `flag` key as a setter**, not just `SET_FLAG`
   effects — `cost_types.py` sets a flag from a *cost*, which a SET_FLAG-only
   sweep misses. The count held at 167 flags / 195 cards.

## Why the names diverged

The engine's markers are lowercase and often parameterised; the cards invented
uppercase constants. Verified case by case:

| Mechanic | Engine writes | Cards read |
|---|---|---|
| Fusion | `fused_<slug>` (`ability_keywords.fusion`) | `FUSED`, `FUSED_FLAG`, `FUSION`, … |
| Boost | `boosted_this_turn` | `BOOSTED_THIS_TURN`, `BOOSTED`, … |
| Crowd boo | `crowd_booed` | (fine — via `IS_BOOED`) |

Two cards (`buzz_bolt_blue`, `chilling_icevein_yellow`) already used the correct
`fused_<slug>` form, which is how we know the convention works and the rest
simply did not follow it. `ability_keywords.fusion` even documents it in a
comment.

## Fixed (30 cards)

The three families with a known-correct target were renamed mechanically, each
card carrying a `_comment`: fusion → `fused_<slug>`, boost → `boosted_this_turn`,
Lightning Flow → `played_lightning`.

**Lightning Flow needed an engine fix too, not just a rename.** `played_lightning`
was read by `ability_keywords.check_lightning_flow` and by 7 cards, and **nothing
wrote it either** — the mechanic was inert engine-side. Renaming alone would have
moved those cards from one dead flag to a second dead flag while looking like a
fix. The writer now lives in `play._apply_play_card` (the single hand-play path):
playing a card with the Lightning talent records the marker. Note the *readers*
are Elemental Runeblade cards (Harness Lightning is not itself a Lightning card);
the *setters* are the 289 cards carrying the Lightning talent.

## Still open (~137 flags)

The remainder are card-specific state with **no engine mechanic behind them at
all** — `SCRAPPED_CARD`, `CHARGED_THIS_TURN`, `BEAT_CHEST_THIS_TURN`,
`TRANSCEDED_THIS_TURN` (also misspelled), `HUNDRED_WINDS_LAST_ATTACK`, and so on.
Each needs a real decision — implement the mechanic, or re-model the card without
it — so none can be swept. Grouped by mechanic they cluster into a modest number
of families (scrap, charge, transcend, chakra, beat-chest, arrow/dagger tracking),
so working family-by-family will be far faster than card-by-card.

## The testing lesson

Two tests written *earlier in this same effort* failed once the flags were
corrected — because they hand-appended the dead flag (`BOOSTED_THIS_TURN`,
`FUSED`) to set up their state. They passed while proving the card worked **only
in a state no game can ever reach.**

That is the same false-confidence pattern this whole effort keeps finding, but in
the tests instead of the cards. `test_misfire_dampener_prevents_2_arcane_when_boosted`
now drives the real `boost()` keyword and asserts the engine's own marker
appears. **Prefer driving the real mechanic over asserting an internal flag** —
a test that sets up state by hand can only ever confirm the code does what the
test author already believed.

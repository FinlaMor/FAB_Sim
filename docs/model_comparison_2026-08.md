# Implementer/auditor model comparison — 14B vs 30B (2026-08-13)

Two 20-card passes over `pen`, same prompt (Talishar-grounded), same gates,
back to back. Measured with `scripts/audit_run.py` plus a hand read of five
cards against their printed text.

| | qwen2.5-coder:14b | qwen3-coder-30b-ctx8k |
|---|---|---|
| loaded OK | 15/20 (75%) | **19/20 (95%)** |
| **verified `done`** | 0/20 (0%) | **2/20 (10%)** |
| needs_review | 8 | **1** |
| mechanical defects | 0/12 | 2/19 (11%) |
| semantically correct (sampled) | 2/5 | ~1.5/5 |
| throughput | 5.42 tok/s | **5.64 tok/s** |

**Recommendation: use the 30B for both roles.** It is markedly better at
producing structurally valid output — 95% load rate, needs_review down from 8 to
1, and the first non-zero verification rate observed (10%, against 0% here and
6% historically) — at no cost in wall-clock time.

## Why the 30B is not slower

It is a Mixture-of-Experts model (A3B, ~3B active parameters), so its parameter
count does not translate into proportional compute. A 20-card pass took ~35
minutes. There is no speed/quality tradeoff to weigh here.

Both roles run the same model deliberately: Ollama cannot hold a 14B and a 30B
in 12 GB of VRAM, so alternating per card would thrash on model loads. The cost
is that implementer and auditor changed together, so an improvement cannot be
attributed to one. Given the 14B pass already showed 0% mechanical defects with
testing as the blocker, most of the gain is probably the auditor — inferred, not
measured.

## Benchmarking trap: the two servers fight over the GPU

llama.cpp (`serve-qwen-gpu.cmd`, `-ngl 999`) holds the VRAM, and Ollama then
silently falls back to CPU. An earlier measurement of "Ollama 14B at 2.3 tok/s"
was that starvation, not Ollama being slow — with the GPU free it does 5.42
tok/s. **Only one of the two should hold the GPU at a time**, and any
model/endpoint benchmark is meaningless unless the other is stopped.

Stopping llama.cpp needs care: the launcher's `:loop` respawns `llama-server`
within seconds, so killing the child alone never works. Kill the parent
`cmd.exe` first, and loop parent-then-child until the port stays down.

## The finding that matters more than the model

Both models got `blackstone_greaves` wrong **in exactly the same way**, and that
is not coincidence. The card reads "If you've dealt arcane damage this turn,
this gets +1{d}" — and the engine has no such state. Faced with an inexpressible
requirement, both invented a flag instead of emitting `NEEDS_NEW_DSL` as rule 23
instructs.

Note *how* the 30B invented: `dealt_arcane_damage_this_turn`, **lowercase**,
mimicking the engine convention rule 23 teaches. It absorbed the rule's surface
form and missed its substance — it learned what invented flags should look like.

This reframes a large share of the ~137 open dangling flags. They are not all
carelessness; many are a model correctly identifying a mechanic the DSL cannot
express. **A better model cannot fix those — only new primitives can.** That is
the honest explanation for a semantic-accuracy ceiling that model size does not
move.

## Where the constraint now sits

1. **Test-writing.** 17 of 19 loadable cards produced no passing test in 3
   samples. This is the binding gate, and best-of-N on a stochastic model is
   not clearing it.
2. **Missing primitives.** Cards whose text needs state the engine does not
   track will keep producing invented flags whatever model runs.

Neither is addressed by scaling the model further. The higher-leverage work is
turning the dangling-flag families into real mechanics, and rethinking how the
test gate establishes that a card behaves correctly.

---

# Qwen3.8-27B: rejected on this hardware (2026-08-16)

Tried as a possible quality jump over the 30B MoE. **Do not use it here.**

| | qwen3-coder-30b-ctx8k | qwen3.8:27b |
|---|---|---|
| architecture | MoE, ~3B active | **dense, 27B active** |
| resident size | ~18 GB | 24 GB |
| GPU/CPU split | GPU-resident | **71% CPU / 29% GPU** |
| throughput | 5.6–15.3 tok/s | **~1 tok/s** |

A 100-token completion took 98 s. Card prompts are thousands of tokens in and
hundreds out, so one card would cost 10+ minutes — a 5–15x regression. That is
decisive without a pipeline run, so no quality comparison was attempted.

The cause is architectural, not a tuning problem: a dense 27B activates every
parameter per token and does not fit 12 GB of VRAM, so most layers run on CPU.
Requires Ollama ≥ 0.32.12 for the manifest (0.32.11 returns HTTP 412).

**Rule of thumb for this box: prefer MoE, and check `ollama ps` for the
CPU/GPU split before benchmarking anything.** A model that spills to CPU will
look like a bad model when it is really a bad fit.

# Attacking the real constraint: the test gate (2026-08-16)

Rather than scale the model, the 823 recorded test-gate failure notes were
aggregated to find out what actually fails:

| Count | Share | Failure |
|---|---|---|
| 215 | 26% | AssertionError (wrong expectation, or a genuinely wrong card) |
| 211 | 26% | **AttributeError — an invented attribute** |
| 28 | 3% | TypeError — wrong helper signature |
| 21 | 3% | SyntaxError — prose after the last test |

Within the AttributeErrors, **one invented name accounts for 62 failures
(7.5% of every recorded failure): `.flags`** on GameState/Player/CombatState.
The prompt already forbids inventing attributes and names examples; the model
does it anyway. Consistent with the pen audit: **mechanisms beat prose rules.**

So the fixes are mechanisms, not a 26th rule:

1. **Syntax salvage** — `extract_test_code` now `ast.parse`-validates and keeps
   the longest valid prefix, so a trailing prose paragraph costs the prose
   instead of the whole sample.
2. **Tolerant helpers** — `_card("x", cost=3)`, `stock_deck(..., color="yellow")`
   and `hit(st, damage=4)` express legitimate preconditions and now work
   instead of raising TypeError. `set_turn_flag(st, pid, marker)` gives the
   `.flags` impulse a real destination (`current_turn_effects`).
3. **Repair loop** — a failed attempt now feeds the ACTUAL pytest traceback back
   to the model instead of re-rolling blind on a new seed. The traceback
   usually names the wrong attribute outright.
4. **Vacuous-test guard** — showing a model its failing test invites the cheapest
   fix: delete the assertion. A test that passes while asserting nothing marks a
   card *verified* on no evidence, which is worse than no test at all. Tests
   whose every assertion is a literal are rejected even though pytest passes
   them, and the repair prompt states that weakening the test is a failure.
5. **Harness header refresh** — the committed `test_<set>_generated.py` embeds a
   COPY of the harness. Adding a helper would make a gate-passing test
   `NameError` once committed, so `append_test` now refreshes a stale header in
   place, preserving the tests below it.

## Measuring it honestly

`scripts/bench_test_gate.py` re-runs the gate over `candidate` cards. That tier
means "the JSON loads and is not a stub, but no generated test passed", so the
**baseline is 0 by definition** — no cherry-picking is possible, and any pass is
attributable to the changes.

Full 29-card run: **6 / 29 (20%) against a 0 / 29 baseline**, in 3103 s.

| Attempts to pass | Cards |
|---|---|
| 1 (harness fixes alone) | 4 |
| 2 (repair loop rescued) | 1 |
| 3 (repair loop rescued) | 1 |

**A third of the passes came from the repair loop**, so feeding the traceback
back is doing real work and not just riding on the tolerant helpers.

## The result that matters more than 20%

Re-running 8 of these cards with the failure class recorded: **all 5 residual
failures are `AssertionError`. Zero AttributeError, zero TypeError, zero
SyntaxError.**

The original 823-failure distribution was 32% mechanical (26% AttributeError,
3% TypeError, 3% SyntaxError). Those classes have effectively disappeared from
the gate. What remains is the test and the card disagreeing about behaviour —
which is exactly what a gate is *for*. A failure now means "someone is wrong
about this card", not "the auditor misspelled an attribute".

That reframes the remaining 80%: it is no longer harness friction that more
prompt engineering could clear. It is the genuinely hard part — deciding whether
the card or the expectation is wrong — and some of it is the known
missing-primitives problem (`blackstone_greaves` is in this failing set, and it
still cannot be expressed).

**Implication for next steps:** further test-gate plumbing has low remaining
value. The leverage moved to the DSL primitives and to semantic review of the
cards themselves.

## Benchmarking trap, second instance

The run died with 1.2 GB free: Ollama held the 30B (19 GB) while the full pytest
suite ran. This is the SAME trap this document already warned about one section
above, in a new form — the earlier warning was about the GPU, this is RAM.
**Run the model and the suite one at a time, not concurrently**; `ollama stop`
returns ~19 GB immediately.

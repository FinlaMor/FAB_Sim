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

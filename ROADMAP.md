# Roadmap

## Done
- [x] Rules-accurate game engine (turn structure, combat chain, LIFO stack, priority system)
- [x] Keywords: Go Again, Dominate, Overpower, Phantasm, Reprise, Blood Debt, Intimidate, Arcane Barrier, and more (CR 8.x)
- [x] Card effect system: JSON-defined abilities, DSL interpreter, trigger registry
- [x] Four CC hero decks implemented: Kayo, Arakni, Oscillio, Marlynn
- [x] State/action encoder (transformer embeddings over hand, board, deck composition)
- [x] IQL agent — beats random baseline; v3 checkpoint trained on 3.3M steps
- [x] Game data logger (SQLite) and batch data collection pipeline
- [x] Offline AI development assistant: RAG + fine-tuned Qwen2.5 7B for rules Q&A and card validation

## In Progress
- [ ] Complete card implementations for all four hero decks (accuracy pass)

## Planned
- [ ] Expand card coverage to additional heroes and sets
- [ ] Transformer policy network (state + legal actions → action distribution)
- [ ] Self-play training loop (AlphaZero-style, IQL per hero)
- [ ] Benchmarking framework: agent vs. agent head-to-head with ELO tracking

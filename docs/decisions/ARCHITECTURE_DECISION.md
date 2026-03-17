# Architecture Decision Record: RL Policy Serving Path

## Status: Decided — Dual Pipeline, IQL-First

## Context

The FAB_Sim RL system has two separate model architectures:

1. **IQL Pipeline** (offline RL): GameStateEmbedder (3628-dim) + ActionEmbedder (835-dim) → MLP Q/V/Actor networks. Trained on replay data via `train_iql.py`. Outputs a continuous action embedding decoded to legal actions via nearest-neighbor search (`iql_decode_agent.py`).

2. **Transformer Pipeline** (sequence model): Raw GameState → CardEmbedder tokens → multi-head attention → policy/value heads. Defined in `transformer_policy.py`. No training loop exists — heads are randomly initialized.

These pipelines share the `CardEmbedder` module but have no weight transfer, gradient bridge, or training path connecting them.

## Decision

**IQL is the production policy path.** The Transformer pipeline is a research prototype for future supervised/RL training and is not part of the deployment path.

### Rationale

- IQL has a complete training loop (`train_iql.py`), data collection (`collect_iql_mixed_data.py`), replay storage (`replay_db.py`), and inference decode (`iql_decode_agent.py`).
- The Transformer has no training code — its policy and value heads are untrained.
- Offline RL (IQL) is appropriate for the current data regime: self-play replay data with sparse terminal rewards.

### Inference Path

```
GameState → GameStateEmbedder → state_vec (3628-d)
                                     ↓
                              IQLTrainer.actor → predicted_action_emb (835-d)
                                     ↓
Legal Actions → ActionEmbedder → action_embs (N × 835-d)
                                     ↓
                              cosine similarity → best legal action
```

Implemented in `rl_agents/iql_decode_agent.py::IQLDecodeAgent`.

## Future Work

- **Transformer training**: Add supervised distillation from IQL actor or direct policy gradient training to `AskAgentTransformer`.
- **Weight transfer**: Explore initializing Transformer card tokens from IQL's shared `CardEmbedder` weights.
- **Online fine-tuning**: Use the Transformer's attention-based architecture for online RL once sufficient self-play data exists.

## References

- Kostrikov et al. (2021), "Offline Reinforcement Learning with Implicit Q-Learning"
- `rl_agents/iql.py` — IQL trainer with target value network
- `rl_agents/iql_decode_agent.py` — Inference decode agent
- `rl_agents/transformer_policy.py` — Transformer prototype (no training path)

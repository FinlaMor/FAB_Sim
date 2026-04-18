from rl_agents.random_agent import RandomAgent, UserInputAgent

# HumanAgent currently depends on ActionType variants that may be temporarily
# unavailable while action enums are being refactored. Keep package import
# resilient so non-interactive tooling can still run.
try:
    from rl_agents.human_agent import HumanAgent
except Exception:  # pragma: no cover - defensive import guard
    HumanAgent = None

# IQL imports are deferred because iql.py -> dataset_adapter.py -> data_collection.replay_db
# which may not be installed. Import IQLConfig/IQLTrainer explicitly when needed:
#   from rl_agents.iql import IQLConfig, IQLTrainer

# Transformer policy imports moved to archive/ — import directly if needed:
#   from archive.rl_agents.transformer_policy import TransformerPolicyAgent, ...

__all__ = [
    "RandomAgent",
    "UserInputAgent",
]

if HumanAgent is not None:
    __all__.append("HumanAgent")

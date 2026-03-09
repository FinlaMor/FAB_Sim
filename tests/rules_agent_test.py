import sys
import pathlib

# Ensure FAB_Sim_v2/ is on the path regardless of working directory
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from offline_agents.agents.rules_agent import RulesAgent

agent = RulesAgent()

# Ask a rules question
answer = agent.ask("Can Arcane Barrier be used after damage has already been dealt?")
print(answer)

# Review a code snippet for rules compliance
keywords_path = pathlib.Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "keywords.py"
code = keywords_path.read_text(encoding="utf-8")
report = agent.review_code(code, "Check the arcane damage flow against CR 8.3.8 and CR 8.5.47")
print(report)

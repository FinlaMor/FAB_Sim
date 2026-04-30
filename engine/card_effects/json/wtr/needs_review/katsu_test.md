# katsu — test — Needs New DSL

**Reason:** The provided JSON effect definition does not match the expected structure for the DSL system. Specifically, the "DISCARD_RANDOM_CONDITIONAL" effect is not properly defined to include a condition for discarding a card with cost 0. Additionally, the "SEARCH_DECK" and "BANISH" effects are not properly linked to handle the conditional discard.

## Raw claw-code output

```
claw-code agent  model=qwen2.5-coder:14b  ctx=8192  cwd=C:\Users\Joseph\Desktop\claw-code
```python
import pytest, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.card_effects.dsl import dispatch, get_card

NEEDS_NEW_DSL: The provided JSON effect definition does not match the expected structure for the DSL system. Specifically, the "DISCARD_RANDOM_CONDITIONAL" effect is not properly defined to include a condition for discarding a card with cost 0. Additionally, the "SEARCH_DECK" and "BANISH" effects are not properly linked to handle the conditional discard.
```

```

"""The cards say "destroyed"; the trigger is spelled ON_DEATH.

32 cards read "when this is destroyed, ...". Five are implemented, and all five
use `ON_DEATH`. The backlog pass flagged the phrasing as a MISSING MECHANIC and
I was one step from building an `ON_DESTROY` trigger that already existed under
another name -- which is the single commonest wrong answer in this corpus, and
the exact failure the triage prompt warns about.

The alias costs nothing and removes the trap: without it, authoring the obvious
spelling raises at load.

Also pinned here: a card authoring a keyword the card DB already prints is NOT
a defect. The review pass flagged 278 such cards as "keyword-reimplemented",
and CombatState.grant_keyword is idempotent -- three grants produce one
keyword, and the action-point path tests set membership rather than counting.
Mass-editing 278 cards on that finding would have been the most damaging thing
available; the finding is cosmetic and the tests below say so.
"""
import copy

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards
from engine.card_effects.dsl.trigger_types import TRIGGER_TO_EVENT
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


@pytest.mark.parametrize("spelling", ["ON_DESTROY", "ON_DESTROYED",
                                      "WHEN_DESTROYED"])
def test_the_obvious_spellings_reach_the_real_trigger(spelling):
    assert TRIGGER_TO_EVENT.get(spelling) == "ON_DEATH"


def test_on_death_itself_is_unchanged():
    assert TRIGGER_TO_EVENT.get("ON_DEATH") == "ON_DEATH"


def test_the_cards_really_do_say_destroyed():
    """The premise: if the corpus stopped using that wording, the alias is
    pointless and this says so rather than passing quietly."""
    import json
    import re
    from pathlib import Path
    idx = json.load(open(Path(__file__).resolve().parent.parent
                         / "card_data" / "slug_index.json", encoding="utf-8"))["by_slug"]
    pat = re.compile(r"when (this|.{0,24}?) is destroyed", re.I)
    n = sum(1 for v in idx.values() if pat.search(v.get("functionalText") or ""))
    assert n >= 20, f"only {n} cards say 'when ... is destroyed'"


# --- granting a printed keyword again is idempotent -------------------------

def test_granting_the_same_keyword_repeatedly_adds_it_once():
    st = _make_state()
    card = copy.deepcopy(DB.get("brutal_assault_red"))
    card.owner = card.controller = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=card, keywords=[])

    for _ in range(3):
        st.combat.grant_keyword("Go Again")

    assert st.combat.keywords == ["Go Again"]
    assert st.combat.keyword_effects == {"Go Again"}

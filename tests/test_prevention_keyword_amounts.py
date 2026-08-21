"""Ward N / Arcane Barrier N / Spellvoid N / Quell N / Arcane Shelter N.

The amount was read off the end of the keyword STRING. No keyword in the corpus
carries one: the card DB stores the bare name ("ArcaneBarrier") and the number
lives in the text ("**Arcane Barrier 2**"). Every one of the 191 cards with one
of these keywords therefore prevented ZERO.

That is not a no-op. Ward is not optional (CR 8.3.20) — the card destroys itself
whether or not anything is prevented — so a Ward card was paying its full cost
to prevent nothing, which is strictly worse than not implementing Ward at all.
"""
import copy
import json
import re

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.effects import EffectManager
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

PREVENTION_KEYWORDS = {"ward", "arcanebarrier", "spellvoid", "quell",
                       "arcaneshelter"}


def _registered(slug):
    card = copy.deepcopy(DB.get(slug))
    assert card is not None, f"unknown slug {slug}"
    card.owner = card.controller = 1
    card.zone = "arms"
    mgr = EffectManager()
    mgr.register_prevention_effects(card, _make_state())
    return mgr.replacement_effects


@pytest.mark.parametrize("slug,expected", [
    ("nullrune_gloves", 1),           # **Arcane Barrier 1**
    ("aetherstorm_wellingtons", 2),   # **Arcane Barrier 2**
    ("shamanic_shinbones", 1),
])
def test_amount_comes_from_the_card_text(slug, expected):
    effects = _registered(slug)
    assert effects, f"{slug} registered no prevention effect at all"
    assert [e.prevention_amount for e in effects] == [expected]


def test_no_prevention_keyword_registers_zero_unless_its_amount_is_a_formula():
    """A blanket sweep, because the defect was uniform across the corpus.

    The only cards allowed to remain at zero are the "Ward X, where X is ..."
    printings, whose amount is a formula evaluated when the damage happens and
    cannot be a fixed number decided at registration time. They are still
    wrong — listed here so the gap is counted rather than invisible.
    """
    idx = json.load(open('card_data/slug_index.json', encoding='utf-8'))['by_slug']
    zero_but_not_a_formula = []
    checked = 0
    for slug, raw in idx.items():
        kws = raw.get('keywords') or []
        if not any(k.lower().replace(' ', '').rstrip('0123456789')
                   in PREVENTION_KEYWORDS for k in kws):
            continue
        if DB.get(slug) is None or get_card(slug) is None:
            # Unimplemented slugs cannot appear in a game — new_game refuses to
            # start without a JSON definition — so they are not a live defect.
            continue
        checked += 1
        text = raw.get('functionalText') or ''
        formula = re.search(r'\b(ward|spellvoid|quell|arcane\s*barrier|'
                            r'arcane\s*shelter)\s*\**\s*X\b', text, re.I)
        for eff in _registered(slug):
            if eff.prevention_amount <= 0 and not formula:
                zero_but_not_a_formula.append(slug)

    assert checked >= 30, "the sweep found almost no cards — it is not looking"
    assert not zero_but_not_a_formula, (
        f"{len(zero_but_not_a_formula)} cards prevent 0 with a printed number: "
        f"{sorted(set(zero_but_not_a_formula))[:20]}")


def test_a_dsl_static_declaration_can_supply_the_amount():
    """The declarative escape hatch, alongside MATERIAL / RUNE_GATE.

    Cards authored a STATIC with ARCANE_BARRIER/WARD and an amount; nothing
    dispatches a plain STATIC, so those were dead. They are now read as the
    declaration site, which is what they were written to be.
    """
    from engine.card_effects.dsl.loader import get_card
    declared = get_card("aetherstorm_wellingtons")
    amounts = [e.params.get("amount") for a in declared.abilities
               if (a.ability_type or "").upper() == "STATIC"
               for e in a.effects
               if (e.effect_type or "").upper() == "ARCANE_BARRIER"]
    assert amounts == [2], "the card no longer declares its Arcane Barrier amount"
    assert [e.prevention_amount for e in _registered("aetherstorm_wellingtons")] == [2]


def test_the_card_database_misspells_one_arcane_barrier():
    """plutonic_starplate's text reads "**Arcane Barrer 1**" — a typo in the
    card DB, not in this engine. It has no JSON implementation yet, so it
    cannot reach a game; when one is written, the amount must come from a DSL
    STATIC declaration, because no amount of text parsing will find it.
    """
    raw = json.load(open('card_data/slug_index.json',
                         encoding='utf-8'))['by_slug']['plutonic_starplate']
    assert 'Arcane Barrer' in (raw.get('functionalText') or ''),         "the DB typo was corrected upstream — drop the workaround note above"
    assert get_card('plutonic_starplate') is None,         "plutonic_starplate is now implemented: declare its Arcane Barrier 1"

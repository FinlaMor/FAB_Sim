"""Situations for a generated scenario are derived from the card's own text.

scripts/generate_talishar_states.py builds one board per situation, and the
situation that matters for a Combo card is "the named attack was the last chain
link". That list has to come from the card text rather than a table here --
card-specific knowledge belongs in engine/card_effects/, and a table would go
stale against the 4600-slug pool.

The negative cases carry the weight. Matching every card name that appears
anywhere in a text against the whole pool produces nonsense links, so the
matcher is restricted to attacks and excludes the card itself; without those
two guards a plain vanilla attack picks up partners it has no combo with.

No adapter or Docker needed: this is the pure derivation, not the build.
"""
import pytest

from scripts.talishar_scenario import combo_partners, slug_index


@pytest.fixture(scope="module")
def index():
    return slug_index()


def test_combo_card_finds_the_attack_its_text_names(index):
    # "Combo - If Surging Strike was the last attack this combat chain..."
    assert combo_partners("whelming_gustwave_red", index) == ["surging_strike_red"]


def test_second_combo_card_finds_its_own_partner(index):
    # A different named partner, so a hardcoded answer cannot pass both.
    assert "head_jab_red" in combo_partners("open_the_center_red", index)


def test_a_card_with_no_named_attack_gets_no_partners(index):
    # Head Jab's text is just "Go again" -- nothing to combo off.
    assert combo_partners("head_jab_red", index) == []


def test_a_card_never_lists_itself(index):
    for slug in ("whelming_gustwave_red", "open_the_center_red",
                 "surging_strike_red", "head_jab_red"):
        assert slug not in combo_partners(slug, index)


def test_partners_are_attacks(index):
    """A chain link is an attack. Anything else would build a board that could
    not have happened, and the oracle would be answering a nonsense question."""
    for slug in ("whelming_gustwave_red", "open_the_center_red",
                 "mugenshi_release_yellow"):
        for partner in combo_partners(slug, index):
            subtypes = (index.get(partner) or {}).get("subtypes") or []
            assert "Attack" in subtypes, "%s -> %s is not an attack" % (slug, partner)


def test_unknown_slug_is_empty_not_an_error(index):
    assert combo_partners("not_a_real_card_zzz", index) == []


def test_a_typo_is_refused_before_the_adapter_sees_it(index):
    """Talishar accepts an unknown card id: it puts it in the zone and then
    offers it as a legal play. A typo would build a board with a phantom card
    in it and no error anywhere -- and the adapter's round-trip check cannot
    catch it, because the field lands exactly as requested."""
    from scripts.talishar_scenario import Scenario, ScenarioError, validate

    with pytest.raises(ScenarioError) as exc:
        validate(Scenario(card="whelming_gustwave_red",
                          hand=["whelming_gustwave_red", "not_a_real_card_zzz"],
                          chain_links=["also_not_real"]), index)
    message = str(exc.value)
    assert "not_a_real_card_zzz" in message and "also_not_real" in message

    # And a real board is not refused.
    validate(Scenario(card="whelming_gustwave_red",
                      chain_links=["surging_strike_red"]), index)

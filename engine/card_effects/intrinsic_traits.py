"""Traits a card has in EVERY zone, which the card DB does not record.

Same contract as token_meta.py: card-specific knowledge lives here, never in
engine/*.py, and the engine only consults the table.

WHY THIS CANNOT BE A DSL ABILITY. The DSL expresses continuous statics as
WHILE_STATIC, which is dispatched from `engine._dsl_recalc_listener` on
RECALC_ATTACK_POWER. That listener walks the attack card, both heroes and the
in-play permanents/equipment — it never looks in a graveyard, banished zone or
deck. A card whose text applies "in any zone" is therefore unreachable by every
mechanism the DSL has, which is why the one card needing it had no DSL file at
all rather than a broken one.

Applied at card construction (engine.card.Card.from_raw), so the trait is
simply part of the card wherever it goes. That is a simplification in one
direction only: it ignores "face-up". Every reader that cares already gates on
visibility separately — CARD_IN_ZONE takes a `face_up` parameter and tests
`is_public` — so a face-down card is excluded before its traits are consulted.

FOUND BY: scripts/talishar_attack_replay.py. felling_of_the_crown_red gets
+4{p} for "4 or more Earth cards in your banished zone". With Colors of Aria
sitting face-up in banish, Talishar counted 4 and we counted 3, so we computed
4 power where Talishar computed 8 — an unimplemented card silently corrupting
an implemented card's condition.
"""
from __future__ import annotations

#: slug -> talents the card has in addition to its printed ones, in all zones.
#:
#: colors_of_aria_red: "While this is face-up in any zone, it's Earth, Ice, and
#: Lightning." The card DB types it Elemental only. It is the sole card in the
#: corpus phrased this way, which is why this is a table and not a text rule —
#: a "generic" parser for one card is a card-specific rule wearing a costume.
INTRINSIC_TALENTS: dict[str, list[str]] = {
    "colors_of_aria_red": ["Earth", "Ice", "Lightning"],
}


def talents_for(slug: str, printed: list[str] | None) -> list[str]:
    """Printed talents plus any intrinsic ones, order preserved, no duplicates."""
    extra = INTRINSIC_TALENTS.get(slug or "")
    if not extra:
        return list(printed or [])
    out = list(printed or [])
    have = {t.lower() for t in out}
    for talent in extra:
        if talent.lower() not in have:
            have.add(talent.lower())
            out.append(talent)
    return out

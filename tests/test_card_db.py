"""Tests for CardDB — slug resolution, field mapping, and template cache."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from engine.card import CardDB, Card


@pytest.fixture(scope="module")
def db():
    return CardDB()


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------

def test_cache_miss_builds_card(db):
    """First get() for a slug builds and caches the template."""
    slug = next(iter(db._by_slug))
    db._card_cache.pop(slug, None)  # ensure cold

    card = db.get(slug)

    assert card is not None
    assert slug in db._card_cache


def test_cache_hit_returns_copy(db):
    """Second get() for the same slug returns a copy, not the cached template."""
    slug = next(iter(db._by_slug))
    db._card_cache.pop(slug, None)

    c1 = db.get(slug)
    c2 = db.get(slug)

    assert c1 is not c2


def test_cache_copies_are_independent(db):
    """Mutating one returned card does not affect a subsequent get()."""
    slug = next(iter(db._by_slug))
    db._card_cache.pop(slug, None)

    c1 = db.get(slug)
    c1.zone = "hand"
    c1.tapped = True

    c2 = db.get(slug)

    assert c2.zone != "hand"
    assert c2.tapped is False


def test_cache_template_is_not_mutated(db):
    """The cached template itself is never the returned object."""
    slug = next(iter(db._by_slug))
    db._card_cache.pop(slug, None)

    card = db.get(slug)
    card.zone = "graveyard"

    template = db._card_cache[slug]
    assert template.zone != "graveyard"


def test_cache_grows_by_one_per_unique_slug(db):
    """Each unique slug adds exactly one entry to the cache."""
    db._card_cache.clear()
    slugs = list(db._by_slug.keys())[:5]

    for slug in slugs:
        db.get(slug)

    assert len(db._card_cache) == 5


def test_repeated_gets_do_not_grow_cache(db):
    """Repeated gets of the same slug keep cache size stable."""
    db._card_cache.clear()
    slug = next(iter(db._by_slug))

    for _ in range(10):
        db.get(slug)

    assert len(db._card_cache) == 1


# ---------------------------------------------------------------------------
# Field mapping — slug_index → Card
# ---------------------------------------------------------------------------

def test_hero_life_and_intellect_mapped(db):
    """Hero 'life' and 'intellect' from index.ts map to raw_health / raw_intelligence."""
    card = db.get("arakni")
    assert card is not None
    assert card.raw_life == 20
    assert card.raw_intellect == 4
    assert card.base_life == 20
    assert card.base_intellect == 4


def test_keywords_populated(db):
    """'keywords' from index.ts maps to raw_card_keywords."""
    card = db.get("10000_year_reunion_red")
    assert card is not None
    assert "Ward" in card.raw_card_keywords


def test_talents_populated(db):
    """'talents' field populated for classed cards."""
    card = db.get("a_drop_in_the_ocean_blue")
    assert card is not None
    assert "Mystic" in card.talents


def test_opposite_side_identifiers_populated(db):
    """Double-faced cards have oppositeSideCardIdentifiers populated."""
    card = db.get("a_drop_in_the_ocean_blue")
    assert card is not None
    assert "inner-chi-blue" in card.opposite_side_card_identifiers


def test_special_defense_populated(db):
    """specialDefense '*' is stored as a string."""
    card = db.get("arcanite_fortress")
    assert card is not None
    assert card.special_defense == "*"


def test_specializations_populated(db):
    """'specializations' field populated for specialization cards."""
    card = db.get("germinate_blue")
    assert card is not None
    assert "Florian" in card.specializations


# ---------------------------------------------------------------------------
# Slug resolution
# ---------------------------------------------------------------------------

def test_hyphen_slug_resolves(db):
    """Slugs with hyphens (index.ts style) resolve to underscore canonical slug."""
    card = db.get("a-drop-in-the-ocean-blue")
    assert card is not None
    assert card.slug == "a_drop_in_the_ocean_blue"


def test_unknown_slug_returns_none(db):
    """Completely unknown slug returns None."""
    card = db.get("this_slug_does_not_exist_xyz")
    assert card is None


def test_none_slug_returns_none(db):
    """None input returns None without raising."""
    assert db.get(None) is None

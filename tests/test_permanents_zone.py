"""Comprehensive unit tests for SubZoneView and the unified permanents zone."""

from __future__ import annotations

from engine.card import Card
from engine.state import Player, SubZoneView, Zone


def _make_hero() -> Card:
    return Card(slug="hero", name="Hero", types=["Hero"], base_life=40, base_intellect=4)


def _make_player() -> Player:
    return Player(1, _make_hero())


# ---------------------------------------------------------------------------
# SubZoneView filtering
# ---------------------------------------------------------------------------

def test_add_via_items_appears_in_permanents_and_items():
    p = _make_player()
    card = Card(slug="gold_token", name="Gold", types=["Token", "Item"])
    p.items.add(card)
    assert card in p.permanents.cards
    assert card in p.items.cards


def test_add_via_auras_appears_in_permanents():
    p = _make_player()
    card = Card(slug="spectral_shield", name="Spectral Shield", types=["Aura"])
    p.auras.add(card)
    assert card in p.permanents.cards
    assert card in p.auras.cards


# ---------------------------------------------------------------------------
# SubZoneView add/remove
# ---------------------------------------------------------------------------

def test_add_to_subzone_routes_to_permanents():
    p = _make_player()
    card = Card(slug="item1", name="Item1", types=["Item"])
    p.items.add(card)
    assert card in p.permanents.cards
    assert card.zone == "permanents"


def test_remove_from_subzone_removes_from_permanents():
    p = _make_player()
    card = Card(slug="item1", name="Item1", types=["Item"])
    p.items.add(card)
    p.items.remove(card)
    assert card not in p.permanents.cards
    assert card not in p.items.cards


# ---------------------------------------------------------------------------
# SubZoneView isolation
# ---------------------------------------------------------------------------

def test_items_does_not_include_auras():
    p = _make_player()
    item = Card(slug="item1", name="Item1", types=["Item"])
    aura = Card(slug="aura1", name="Aura1", types=["Aura"])
    p.items.add(item)
    p.auras.add(aura)
    assert item in p.items.cards
    assert aura not in p.items.cards


def test_auras_does_not_include_items():
    p = _make_player()
    item = Card(slug="item1", name="Item1", types=["Item"])
    aura = Card(slug="aura1", name="Aura1", types=["Aura"])
    p.items.add(item)
    p.auras.add(aura)
    assert aura in p.auras.cards
    assert item not in p.auras.cards


# ---------------------------------------------------------------------------
# Soul sub-zone
# ---------------------------------------------------------------------------

def test_soul_subzone():
    p = _make_player()
    card = Card(slug="soul_card", name="Soul Card", types=["Action"])
    p.soul.add(card)
    assert card.permanent_subtype == "Soul"
    assert card in p.soul.cards
    assert card in p.permanents.cards


def test_soul_does_not_match_by_type():
    """Soul filtering uses permanent_subtype exclusively, not types."""
    p = _make_player()
    # Card with 'Soul' in types but added via items should NOT appear in soul
    item = Card(slug="item1", name="Item1", types=["Item"])
    p.items.add(item)
    assert item not in p.soul.cards


# ---------------------------------------------------------------------------
# Empty sub-zone
# ---------------------------------------------------------------------------

def test_empty_subzone_returns_empty_list():
    p = _make_player()
    assert p.items.cards == []


def test_empty_subzone_len_zero():
    p = _make_player()
    assert len(p.items) == 0


def test_empty_subzone_bool_false():
    p = _make_player()
    assert not p.items


# ---------------------------------------------------------------------------
# zone_by_name compatibility
# ---------------------------------------------------------------------------

def test_zone_by_name_permanents():
    p = _make_player()
    assert p.zone_by_name("permanents") is p.permanents


def test_zone_by_name_items_returns_subzoneview():
    p = _make_player()
    result = p.zone_by_name("items")
    assert result is not None
    assert isinstance(result, SubZoneView)


def test_zone_by_name_auras_returns_subzoneview():
    p = _make_player()
    result = p.zone_by_name("auras")
    assert isinstance(result, SubZoneView)


# ---------------------------------------------------------------------------
# Card.zone tracking
# ---------------------------------------------------------------------------

def test_card_zone_is_permanents():
    p = _make_player()
    card = Card(slug="item1", name="Item1", types=["Item"])
    p.items.add(card)
    assert card.zone == "permanents"


def test_card_permanent_subtype_set():
    p = _make_player()
    card = Card(slug="item1", name="Item1", types=["Item"])
    p.items.add(card)
    assert card.permanent_subtype == "Item"


def test_card_permanent_subtype_soul():
    p = _make_player()
    card = Card(slug="action1", name="Action", types=["Action"])
    p.soul.add(card)
    assert card.permanent_subtype == "Soul"


# ---------------------------------------------------------------------------
# to_dict serialization
# ---------------------------------------------------------------------------

def test_to_dict_includes_permanents_key():
    p = _make_player()
    d = p.to_dict()
    assert "permanents" in d


def test_to_dict_includes_subzone_keys():
    p = _make_player()
    d = p.to_dict()
    for key in ("items", "auras", "allies", "tokens", "soul"):
        assert key in d


def test_to_dict_permanents_contains_all_cards():
    p = _make_player()
    item = Card(slug="item1", name="Item1", types=["Item"])
    aura = Card(slug="aura1", name="Aura1", types=["Aura"])
    p.items.add(item)
    p.auras.add(aura)
    d = p.to_dict()
    perm_names = [c["name"] for c in d["permanents"]["cards"]]
    assert "Item1" in perm_names
    assert "Aura1" in perm_names


# ---------------------------------------------------------------------------
# SubZoneView.to_dict
# ---------------------------------------------------------------------------

def test_subzoneview_to_dict():
    p = _make_player()
    card = Card(slug="item1", name="Item1", types=["Item"])
    p.items.add(card)
    d = p.items.to_dict()
    assert d["name"] == "permanents:Item"
    assert len(d["cards"]) == 1
    assert d["cards"][0]["name"] == "Item1"


# ---------------------------------------------------------------------------
# all_zones includes permanents
# ---------------------------------------------------------------------------

def test_all_zones_includes_permanents():
    p = _make_player()
    zone_names = [z.name for z in p.all_zones()]
    assert "permanents" in zone_names


def test_all_zones_does_not_include_old_zone_names():
    p = _make_player()
    zone_names = [z.name for z in p.all_zones()]
    for old_name in ("items", "auras", "allies", "tokens", "soul"):
        assert old_name not in zone_names


# ---------------------------------------------------------------------------
# arena_cards includes permanents
# ---------------------------------------------------------------------------

def test_arena_cards_includes_permanents():
    p = _make_player()
    item = Card(slug="item1", name="Item1", types=["Item"])
    p.items.add(item)
    assert item in p.arena_cards


# ---------------------------------------------------------------------------
# SubZoneView extended API
# ---------------------------------------------------------------------------

def test_subzoneview_find():
    p = _make_player()
    card = Card(slug="item1", name="Item1", types=["Item"])
    p.items.add(card)
    assert p.items.find("item1") is card
    assert p.items.find("nonexistent") is None


def test_subzoneview_find_all():
    p = _make_player()
    c1 = Card(slug="gold", name="Gold", types=["Item"])
    c2 = Card(slug="gold", name="Gold", types=["Item"])
    p.items.add(c1)
    p.items.add(c2)
    found = p.items.find_all("gold")
    assert len(found) == 2


def test_subzoneview_extend():
    p = _make_player()
    cards = [
        Card(slug="item1", name="Item1", types=["Item"]),
        Card(slug="item2", name="Item2", types=["Item"]),
    ]
    p.items.extend(cards)
    assert len(p.items) == 2
    assert len(p.permanents) == 2


def test_subzoneview_iter():
    p = _make_player()
    card = Card(slug="item1", name="Item1", types=["Item"])
    p.items.add(card)
    iterated = list(p.items)
    assert iterated == [card]


def test_subzoneview_repr():
    p = _make_player()
    card = Card(slug="item1", name="Item1", types=["Item"])
    p.items.add(card)
    r = repr(p.items)
    assert "SubZoneView" in r
    assert "item1" in r


# ---------------------------------------------------------------------------
# Token dispatch via sub-zone views
# ---------------------------------------------------------------------------

def test_token_added_via_tokens_subzone():
    p = _make_player()
    token = Card(slug="runechant", name="Runechant", types=["Token", "Aura"])
    p.tokens.add(token)
    assert token in p.permanents.cards
    assert token in p.tokens.cards
    assert token.permanent_subtype == "Token"
    assert token.zone == "permanents"

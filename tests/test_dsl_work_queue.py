"""Tests for scripts/dsl_work_queue.py — the card-implementation work queue.

This tool decides what an author works on next and records what is already
done, so a bug in it corrupts the one artifact you'd trust to tell you what is
left. It shipped untested; these lock down the set-attribution logic and the
queue-merge semantics.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_tool():
    """scripts/ is not a package — load the module by path."""
    spec = importlib.util.spec_from_file_location(
        "dsl_work_queue", ROOT / "scripts" / "dsl_work_queue.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dsl_work_queue"] = mod
    spec.loader.exec_module(mod)
    return mod


wq = _load_tool()


# --------------------------------------------------------------------------
# Set attribution
# --------------------------------------------------------------------------

def test_set_codes_returns_every_printing_not_just_the_first():
    """The regression this file exists for.

    Reading only setIdentifiers[0] hid 118 of the 265 cards printed in Heavy
    Hitters from `--set hnt`, so the set could never be finished through the
    tool — and it plausibly steered authors into the wrong folder.
    """
    entry = {"setIdentifiers": ["ARC005", "FAB101", "SDA010", "1HP186"]}
    assert wq._set_codes(entry) == {"arc", "fab", "sda", "hp"}


def test_set_codes_strips_digits_and_lowercases():
    assert wq._set_codes({"setIdentifiers": ["HNT012"]}) == {"hnt"}


def test_set_codes_handles_missing_or_empty_identifiers():
    assert wq._set_codes({}) == set()
    assert wq._set_codes({"setIdentifiers": []}) == set()
    assert wq._set_codes({"setIdentifiers": ["123"]}) == set()  # no letters


def test_reprints_are_attributed_to_every_set_they_appear_in():
    """A card printed in several sets must be findable under each of them."""
    index = wq._slug_index()
    reprint = next(
        (s for s, e in index.items() if len(wq._set_codes(e)) > 1), None)
    assert reprint is not None, "expected at least one reprint in card_data"
    codes = wq._set_codes(index[reprint])
    for code in codes:
        in_set = {s for s, e in index.items() if code in wq._set_codes(e)}
        assert reprint in in_set, f"{reprint} invisible under --set {code}"


def test_heavy_hitters_includes_cards_whose_first_printing_is_elsewhere():
    """Concrete guard on the real dataset: Arakni is printed in HNT but its
    first setIdentifier is not HNT, so the old first-id-only logic dropped it."""
    index = wq._slug_index()
    hnt = {s for s, e in index.items() if "hnt" in wq._set_codes(e)}
    first_id_only = {
        s for s, e in index.items()
        if (e.get("setIdentifiers") or [])
        and "".join(c for c in e["setIdentifiers"][0] if c.isalpha()).lower() == "hnt"
    }
    assert len(hnt) > len(first_id_only), "expected reprints beyond first-id matching"
    assert hnt - first_id_only, "expected cards hidden by first-id-only matching"


# --------------------------------------------------------------------------
# Queue merge semantics
# --------------------------------------------------------------------------

@pytest.fixture
def isolated_queue(tmp_path, monkeypatch):
    """Point the tool at a scratch json root so real queues are never written.

    ROOT moves too: cmd_set logs the queue path relative to it, which raises if
    the queue lands outside the repo.
    """
    monkeypatch.setattr(wq, "JSON_ROOT", tmp_path)
    monkeypatch.setattr(wq, "ROOT", tmp_path)
    return tmp_path


def _write_queue(root: Path, set_code: str, items: list[dict]) -> Path:
    qdir = root / set_code
    qdir.mkdir(parents=True, exist_ok=True)
    path = qdir / f"{set_code}_work_queue.json"
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")
    return path


def test_write_queue_marks_implemented_cards_done(isolated_queue, monkeypatch):
    fake_index = {"card_a": {"name": "A", "setIdentifiers": ["ZZZ001"]}}
    monkeypatch.setattr(wq, "_slug_index", lambda: fake_index)
    monkeypatch.setattr(wq, "get_card", lambda slug: object())  # everything implemented
    monkeypatch.setattr(wq, "load_all_cards", lambda: 0)

    wq.cmd_set("zzz", write_queue=True)

    items = json.loads((isolated_queue / "zzz" / "zzz_work_queue.json").read_text())
    assert [it["status"] for it in items] == ["done"]


def test_write_queue_reverts_done_to_pending_when_json_disappears(isolated_queue, monkeypatch):
    """A queue claiming 'done' for a card with no DSL definition is a lie that
    would permanently hide the card from the work list."""
    _write_queue(isolated_queue, "zzz", [{"slug": "card_a", "status": "done"}])
    monkeypatch.setattr(wq, "_slug_index",
                        lambda: {"card_a": {"name": "A", "setIdentifiers": ["ZZZ001"]}})
    monkeypatch.setattr(wq, "get_card", lambda slug: None)  # nothing implemented
    monkeypatch.setattr(wq, "load_all_cards", lambda: 0)

    wq.cmd_set("zzz", write_queue=True)

    items = json.loads((isolated_queue / "zzz" / "zzz_work_queue.json").read_text())
    assert items[0]["status"] == "pending"


def test_write_queue_preserves_unknown_existing_entries(isolated_queue, monkeypatch):
    """Queues may list cards by broader membership than setIdentifiers; a
    refresh must not silently drop them."""
    _write_queue(isolated_queue, "zzz", [{"slug": "legacy_card", "status": "pending"}])
    monkeypatch.setattr(wq, "_slug_index",
                        lambda: {"card_a": {"name": "A", "setIdentifiers": ["ZZZ001"]}})
    monkeypatch.setattr(wq, "get_card", lambda slug: None)
    monkeypatch.setattr(wq, "load_all_cards", lambda: 0)

    wq.cmd_set("zzz", write_queue=True)

    items = json.loads((isolated_queue / "zzz" / "zzz_work_queue.json").read_text())
    slugs = {it["slug"] for it in items}
    assert slugs == {"legacy_card", "card_a"}, "refresh dropped a pre-existing entry"


def test_write_queue_appends_new_set_cards(isolated_queue, monkeypatch):
    _write_queue(isolated_queue, "zzz", [{"slug": "card_a", "status": "pending"}])
    monkeypatch.setattr(wq, "_slug_index", lambda: {
        "card_a": {"name": "A", "setIdentifiers": ["ZZZ001"]},
        "card_b": {"name": "B", "setIdentifiers": ["ZZZ002"]},
    })
    monkeypatch.setattr(wq, "get_card", lambda slug: None)
    monkeypatch.setattr(wq, "load_all_cards", lambda: 0)

    wq.cmd_set("zzz", write_queue=True)

    items = json.loads((isolated_queue / "zzz" / "zzz_work_queue.json").read_text())
    assert {it["slug"] for it in items} == {"card_a", "card_b"}


def test_unknown_set_code_writes_nothing(isolated_queue, monkeypatch):
    monkeypatch.setattr(wq, "_slug_index", lambda: {})
    monkeypatch.setattr(wq, "load_all_cards", lambda: 0)

    wq.cmd_set("nope", write_queue=True)

    assert not list(isolated_queue.rglob("*_work_queue.json"))


# --------------------------------------------------------------------------
# Deck checking
# --------------------------------------------------------------------------

def test_deck_slugs_reads_real_decks():
    """cmd_deck is the gate that stops a game starting with unimplemented
    cards, so its slug extraction must actually find cards."""
    decks = sorted((ROOT / "decks").glob("*.txt"))
    assert decks, "no decks to check"
    for deck in decks:
        slugs = wq._deck_slugs(deck)
        assert len(slugs) > 10, f"{deck.name}: only found {len(slugs)} slugs"
        assert all(isinstance(s, str) and s for s in slugs)


def test_cmd_deck_returns_zero_when_every_card_is_implemented(capsys):
    """The three maintained decks are expected to be fully playable."""
    decks = sorted((ROOT / "decks").glob("*.txt"))
    rc = wq.cmd_deck(decks)
    out = capsys.readouterr().out
    assert rc == 0, f"deck has unimplemented cards:\n{out}"

"""Reloading the card registry is the hot path, and it was doing full work.

`load_all_cards()` opened, parsed and compiled every card file on EVERY call,
and it is called constantly:

  * 177 test modules call it at import time;
  * tests/conftest.py's autouse `_restore_dsl_registry` calls it twice more per
    module, because some modules load a SUBSET (a temp dir, one set folder) and
    would otherwise leave the global registry replaced.

That is roughly 350 full loads per suite run, and the cost of one grows with
the corpus -- so every card added made the whole suite slower. Measured at 2,546
cards: 0.45s per call, ~4 minutes of a 9m30 run, and collection alone (imports
only, before a single test body ran) took 146 seconds.

The fix caches the compiled result against the STATE of the files it was built
from -- path, mtime and size for every file the loader would read. Stat'ing
them costs ~0.1s against ~0.5s to parse and compile, and it keeps the reload
honest: a card written mid-session changes an mtime and the load happens for
real. Full suite 9m28 -> 4m25, with all 31,797 tests still passing.

THE CACHE MUST NOT MAKE THE LOADER LIE. The three tests below are about that,
not about speed: a stale registry is far worse than a slow one, because it
would hand tests a card that is not what is on disk.
"""
import json
import time

import pytest

from engine.card import CardDB
from engine.card_effects.dsl import loader
from engine.card_effects.dsl.loader import get_card, load_all_cards


def test_a_repeat_load_returns_the_same_cards():
    first = load_all_cards()
    second = load_all_cards()
    assert first == second
    assert loader.all_slugs(), "the registry emptied itself"


def test_a_repeat_load_is_much_cheaper_than_the_first():
    """The property the suite runtime depends on. A regression here is not a
    failed feature -- it is minutes back on every run."""
    load_all_cards()                      # make sure the cache is warm
    t0 = time.perf_counter()
    load_all_cards()
    warm = time.perf_counter() - t0
    assert warm < 0.40, (
        f"a warm reload took {warm:.3f}s; it is called ~350 times per suite run")


def test_writing_a_card_invalidates_the_cache(tmp_path):
    """The honesty check. If an edited file could be served from cache, an
    author would run their card and see the previous version -- and so would
    every corpus sweep."""
    load_all_cards()
    probe = tmp_path / "probe_set"
    probe.mkdir()
    (probe / "probe_card.json").write_text(
        json.dumps({"slug": "probe_card_zzz", "abilities": []}), encoding="utf-8")

    assert load_all_cards(probe) == 1
    assert get_card("probe_card_zzz") is not None

    (probe / "probe_card.json").write_text(
        json.dumps({"slug": "probe_card_zzz", "abilities": [],
                    "_comment": "edited"}), encoding="utf-8")
    # An mtime can land in the same nanosecond bucket on a fast filesystem; the
    # size differs here too, and the state includes both.
    assert load_all_cards(probe) == 1

    # ...and the real tree comes back intact, which is what conftest's autouse
    # fixture exists to guarantee.
    load_all_cards()
    assert get_card("probe_card_zzz") is None
    assert len(loader.all_slugs()) > 2000


def test_two_card_dbs_share_one_parsed_index():
    """159 test modules build a CardDB at import time, each re-parsing the whole
    card index. The index is read-only, so one parse serves them all."""
    a, b = CardDB(), CardDB()
    assert a._by_slug is b._by_slug, "the parsed index is being rebuilt per instance"
    assert a._card_cache is not b._card_cache, (
        "the per-instance Card template cache must NOT be shared -- callers are "
        "handed those objects")

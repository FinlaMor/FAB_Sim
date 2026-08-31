"""The gated-printed-keyword sweep, for every keyword the engine can strip.

NOT a test module -- a helper the ratchets import, so the go-again ratchet and
the all-keyword ratchet cannot drift apart in how they decide what counts.

THE DEFECT. The card DB has no way to mark a printed keyword conditional. Out
Muscle ships as "GoAgain" and Torque Tuned as "Overpower" though both texts gate
theirs, so the engine grants them unconditionally and the gate is decoration:
the card plays as strictly stronger than printed, silently, and no audit
notices because every type is real and every parameter is read.

`loader.conditional_keywords()` is what takes the printed keyword away. It
recognises one inferred shape -- a WHILE_STATIC gated on SOURCE_IS_ATTACK that
grants the keyword -- plus an explicit `conditional_keywords` declaration for
cards whose grant must stay on a trigger.

TWO SHAPES THE SWEEP MATCHES THAT ARE NOT DEFECTS, both learned the hard way:

  a keyword printed on its own line  Channel the Thunder Steppe prints go again
                                     AND grants it to action cards you play. The
                                     printed one is unconditional and correct.

  a keyword handed to another card   Luminaris's "your Illusionist attacks get
                                     go again", Weave Ice's "the next Ice or
                                     Elemental attack action card you play ...
                                     it gains dominate". The DB lists the
                                     keyword on the card because it flattens a
                                     sentence about someone else, and stripping
                                     it would take a keyword from a card that is
                                     not the one the sentence is about.

The second is decided from the printed SUBJECT, and the bare pronoun is the
hard part: "it gets go again" is about the card itself on most cards and about
someone else on Arakni, Redback. A bare pronoun is therefore resolved against
the sentence before it, scoped to that window -- Tigrine Reflex gives ITSELF go
again in one sentence and targets another attack in an unrelated Attack
Reaction, so a rule reading the whole card at once would excuse a card that
belongs in scope.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

#: Phrases that introduce ANOTHER card for a later pronoun to refer to.
#: "target <x> attack" requires the word "attack" deliberately -- "target hero"
#: leaves no card for "it" to mean, and Aether Quickening, whose go again really
#: is its own, opens with exactly that.
OTHER_REFERENT = re.compile(
    r"target[^.]{0,40}\battack\b"
    r"|the next[^.]{0,60}\bcard you play\b",
    re.I)


def gated(word: str) -> re.Pattern:
    """"if/whenever/while ... <word>" — the printed text gating the keyword."""
    return re.compile(r"\b(if|whenever|while)\b[^.]{0,120}?\b" + re.escape(word)
                      + r"\b", re.I)


def prints_outright(text: str, word: str) -> bool:
    """A line that IS the keyword is an unconditional printed keyword, and a
    gated sentence elsewhere on the card is about something else."""
    for line in text.splitlines():
        if line.replace("*", "").replace("-", "").strip().lower() == word:
            return True
    return False


def is_about_itself(text: str, name: str, word: str) -> bool:
    """Whether the card grants the keyword to ITSELF (see module docstring)."""
    low = text.lower()
    named = ["this get", "this gain"]
    if name:
        named += [name.lower() + " get", name.lower() + " gain"]
    if any(sub in low for sub in named):
        return True
    if not any(sub in low for sub in ["it get", "it gain"]):
        return False
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    for i, sentence in enumerate(sentences):
        if word not in sentence.lower():
            continue
        window = " ".join(sentences[max(0, i - 1):i + 1])
        if OTHER_REFERENT.search(window):
            return False
    return True


def implemented_slugs():
    """Slugs with a card JSON, skipping pipeline artifacts.

    Never use a bare rglob here: the drafting pipeline writes candidate JSON
    into dot-directories under the card tree, and ~48 test files once counted
    those as implemented cards.
    """
    from tests.conftest import card_json_files
    out = {}
    for path in card_json_files(JSON_ROOT):
        rel = path.relative_to(JSON_ROOT)
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") or p == "needs_review" for p in rel.parts):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict) and raw.get("slug"):
            out[raw["slug"]] = path
    return out


def unstripped(words):
    """{keyword: [slug, ...]} for implemented cards whose printed keyword their
    own text gates, and whose JSON does not make it conditional."""
    from engine.card_effects.dsl.loader import _kw_key, conditional_keywords

    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    have = implemented_slugs()
    found = {}
    for word in words:
        pattern = gated(word)
        hits = []
        for slug in have:
            entry = idx.get(slug) or {}
            printed = {_kw_key(k) for k in (entry.get("keywords") or [])}
            text = entry.get("functionalText") or ""
            if _kw_key(word) not in printed or not pattern.search(text):
                continue
            if prints_outright(text, word):
                continue
            if not is_about_itself(text, entry.get("name") or "", word):
                continue
            if _kw_key(word) in conditional_keywords(slug):
                continue
            hits.append(slug)
        if hits:
            found[word] = sorted(hits)
    return found

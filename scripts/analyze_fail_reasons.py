#!/usr/bin/env python3
"""Categorize WHY remaining unparsed cards fail to parse."""
from __future__ import annotations
import sys, re, msgpack
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

with open(ROOT / "card_data" / "slug_index.msgpack", "rb") as f:
    raw = msgpack.unpackb(f.read(), raw=False)
slug_index = raw.get("by_slug", raw)

from engine.card import Card
from engine.card_effects.text_trigger_parser import parse_functional_text
from engine.card_effects.triggers import CARD_TRIGGERS

unparsed = []
for slug, data in slug_index.items():
    ft = data.get("functional_text", "") or ""
    if not ft.strip() or slug in CARD_TRIGGERS:
        continue
    try:
        card = Card(slug=slug, name=data.get("name", ""), base_functional_text=ft,
                    types=data.get("types", []) or [], subtypes=data.get("subtypes", []) or [],
                    keywords=data.get("ability_keywords", []) or [])
        if not parse_functional_text(card):
            unparsed.append((slug, ft))
    except Exception:
        unparsed.append((slug, ft))

print(f"Total unparsed cards: {len(unparsed)}")

# === Categorize primary blocker ===
reasons = Counter()
examples: dict[str, list] = {}

def tag(reason, slug, ft):
    reasons[reason] += 1
    examples.setdefault(reason, [])
    if len(examples[reason]) < 5:
        examples[reason].append((slug, ft[:140]))

for slug, ft in unparsed:
    ftl = ft.lower()

    # Hard complex markers (choose, for each, equal to, search, reveal, transform, etc.)
    if re.search(r'\bchoose\b', ft, re.I):
        tag("choose", slug, ft); continue
    if re.search(r'\bfor each\b', ft, re.I):
        tag("for_each", slug, ft); continue
    if re.search(r'\bequal to\b', ft, re.I):
        tag("equal_to", slug, ft); continue
    if re.search(r'\bsearch your deck\b', ft, re.I):
        tag("search_deck", slug, ft); continue
    if re.search(r'\blook at the top\b', ft, re.I):
        tag("look_at_top", slug, ft); continue
    if re.search(r'\breveal\b', ft, re.I):
        tag("reveal", slug, ft); continue
    if re.search(r'\btransform\b', ft, re.I):
        tag("transform", slug, ft); continue
    if re.search(r'\btranscend\b', ft, re.I):
        tag("transcend", slug, ft); continue
    if re.search(r'\bgraft\b', ft, re.I):
        tag("graft", slug, ft); continue
    if re.search(r'\bcopy\b', ft, re.I):
        tag("copy", slug, ft); continue
    if re.search(r'\bexchange\b', ft, re.I):
        tag("exchange", slug, ft); continue
    if re.search(r'\btake control\b', ft, re.I):
        tag("take_control", slug, ft); continue
    if re.search(r'\bname a card\b', ft, re.I):
        tag("name_a_card", slug, ft); continue
    if re.search(r'\bput .+ into play\b', ft, re.I):
        tag("put_into_play", slug, ft); continue
    if re.search(r'\binstead\b', ft, re.I):
        tag("instead", slug, ft); continue
    if re.search(r'\bunless\b', ft, re.I):
        tag("unless", slug, ft); continue
    if re.search(r'\bbecomes?\b', ft, re.I):
        tag("becomes", slug, ft); continue

    # Activated abilities: **Action** — or **Instant** —
    if re.search(r'\*\*(?:once per turn )?(?:action|instant)\*\*\s*[-\u2013\u2014]', ft, re.I):
        tag("activated_ability", slug, ft); continue

    # "whenever" triggers (continuous, not one-shot)
    if re.search(r'\bwhenever\b', ft, re.I):
        tag("whenever_trigger", slug, ft); continue

    # Contract mechanic
    if re.search(r'\bcontract\b', ft, re.I):
        tag("contract", slug, ft); continue

    # "at the start/beginning of your turn"
    if re.search(r'at the (?:start|beginning) of', ft, re.I):
        tag("at_start_turn", slug, ft); continue

    # "at the end of"
    if re.search(r'at the end of', ft, re.I):
        tag("at_end_turn", slug, ft); continue

    # "you may" optional effects
    if re.search(r'\byou may\b', ft, re.I):
        tag("you_may_optional", slug, ft); continue

    # "then" sequencing
    if re.search(r'\bthen\b', ft, re.I):
        tag("then_clause", slug, ft); continue

    # Blood Debt / keyword-only remainder
    if re.search(r'\bblood debt\b', ft, re.I):
        tag("blood_debt", slug, ft); continue

    # Boost
    if re.search(r'\bboost\b', ft, re.I):
        tag("boost_kw", slug, ft); continue

    # Cost reduction
    if re.search(r'this costs .+ (?:less|more)', ft, re.I):
        tag("cost_reduction", slug, ft); continue

    # Additional cost
    if re.search(r'as an additional cost', ft, re.I):
        tag("additional_cost", slug, ft); continue

    # Multi-sentence with no recognized trigger
    if re.search(r'\.\s+[A-Z]', ft):
        tag("multi_sentence_no_trigger", slug, ft); continue

    tag("other_unknown", slug, ft)

print("\nWHY CARDS FAIL (primary reason):")
print(f"{'Reason':<35s} {'Count':>5s}  {'%':>6s}")
print("-" * 50)
for reason, count in reasons.most_common():
    pct = count / len(unparsed) * 100
    print(f"  {reason:<33s} {count:>5d}  ({pct:5.1f}%)")
print("-" * 50)
print(f"  {'TOTAL':<33s} {len(unparsed):>5d}")

# Print examples for each category
print("\n" + "=" * 70)
print("EXAMPLES PER CATEGORY")
print("=" * 70)
for reason, _ in reasons.most_common():
    print(f"\n--- {reason} ({reasons[reason]}) ---")
    for slug, ft_snip in examples[reason]:
        print(f"  {slug}: {ft_snip}")

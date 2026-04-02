#!/usr/bin/env python3
"""Quantify which remaining unparsed patterns are expandable."""
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
                    keywords=data.get("card_keywords", []) or [])
        if not parse_functional_text(card):
            unparsed.append((slug, ft))
    except Exception:
        unparsed.append((slug, ft))

expandable = Counter()
examples: dict[str, list] = {}

def tag(reason, slug, ft):
    expandable[reason] += 1
    examples.setdefault(reason, [])
    if len(examples[reason]) < 3:
        examples[reason].append((slug, ft[:150]))

KW_ONLY_RE = re.compile(
    r"^\*\*(?:Go again|Dominate|Overpower|Phantasm|Spectra|Blood Debt|Stealth|"
    r"Battleworn|Temper|Legendary|Ephemeral|Universal|Modular|Cloaked|"
    r"Ward \d+|Arcane Barrier \d+|Spellvoid \d+|Arcane Shelter \d+)\*\*\.?$", re.I)

for slug, ft in unparsed:
    # 1. Standalone keyword-only text (Arcane Barrier N, Ward N, etc.)
    if KW_ONLY_RE.match(ft.strip()):
        tag("EASY:keyword_only_text", slug, ft); continue

    # 2. Multi-para where ALL are either keyword-only or already-parseable
    paras = [p.strip() for p in ft.split("\n\n") if p.strip()]
    if len(paras) >= 2:
        all_simple = True
        for p in paras:
            if KW_ONLY_RE.match(p):
                continue
            # Try parsing this paragraph alone
            try:
                test_card = Card(slug=slug, name="test", base_functional_text=p)
                if parse_functional_text(test_card):
                    continue
            except Exception:
                pass
            all_simple = False
            break
        if all_simple:
            tag("EASY:multi_para_all_simple", slug, ft); continue

    # 3. 'If [condition], this gets +N{p}' (no trigger word, standalone)
    if re.match(r"^If .+?, this gets \+\d+\{p\}", ft, re.I) and not re.search(r"\bchoose|for each|equal to|search|reveal|transform|instead|unless\b", ft, re.I):
        tag("MED:if_gets_power", slug, ft); continue
    if re.match(r"^If .+?, this gets \*\*go again\*\*", ft, re.I) and not re.search(r"\bchoose|for each|equal to|search|reveal|transform|instead|unless\b", ft, re.I):
        tag("MED:if_gets_keyword", slug, ft); continue
    if re.match(r"^If .+?, this gets \+\d+\{d\}", ft, re.I) and not re.search(r"\bchoose|for each|equal to|search|reveal|transform|instead|unless\b", ft, re.I):
        tag("MED:if_gets_defense", slug, ft); continue
    if re.match(r"^If .+?, (?:draw|deal|create|gain|this gets)", ft, re.I) and not re.search(r"\bchoose|for each|equal to|search|reveal|transform|instead|unless\b", ft, re.I):
        tag("MED:if_then_effect", slug, ft); continue

    # 4. Blood Debt as standalone keyword paragraph
    if "**Blood Debt**" in ft:
        tag("EASY:blood_debt_paragraph", slug, ft); continue

    # 5. While-defended conditions
    if re.search(r"\bwhile .+ defended by (?:less|fewer) than \d+", ft, re.I):
        tag("MED:while_few_defenders", slug, ft); continue

    # 6. Activated abilities
    if re.search(r"\*\*(?:once per turn )?action\*\*\s*[-\u2013\u2014]", ft, re.I):
        tag("HARD:activated_action", slug, ft); continue
    if re.search(r"\*\*(?:once per turn )?instant\*\*\s*[-\u2013\u2014]", ft, re.I):
        tag("HARD:activated_instant", slug, ft); continue

    # 7. Whenever triggers
    if re.search(r"\bwhenever\b", ft, re.I):
        tag("HARD:whenever", slug, ft); continue

    # 8. you may (optional)
    if re.search(r"\byou may\b", ft, re.I):
        tag("HARD:you_may", slug, ft); continue

    # 9. at the start/end of turn
    if re.search(r"at the (?:start|beginning) of", ft, re.I):
        tag("MED:at_start_turn", slug, ft); continue
    if re.search(r"at the end of", ft, re.I):
        tag("MED:at_end_turn", slug, ft); continue

    # 10. Simple 'if' with known effect but parser missed
    if re.search(r"\bif\b", ft, re.I) and not re.search(r"\bchoose|for each|equal to|search|reveal|transform|instead|unless\b", ft, re.I):
        tag("MED:other_simple_if", slug, ft); continue

    # 11. choose/for each/search/reveal
    if re.search(r"\bchoose\b", ft, re.I):
        tag("HARD:choose", slug, ft); continue
    if re.search(r"\bfor each\b", ft, re.I):
        tag("HARD:for_each", slug, ft); continue
    if re.search(r"\bsearch\b", ft, re.I):
        tag("HARD:search", slug, ft); continue
    if re.search(r"\breveal\b", ft, re.I):
        tag("HARD:reveal", slug, ft); continue

    # 12. instead/unless/becomes/transform
    if re.search(r"\binstead|unless|becomes?\b", ft, re.I):
        tag("HARD:replacement_effect", slug, ft); continue
    if re.search(r"\btransform\b", ft, re.I):
        tag("HARD:transform", slug, ft); continue

    tag("OTHER", slug, ft)

print(f"Total unparsed: {len(unparsed)}")
print()

# Group by difficulty tier
tiers = {"EASY": 0, "MED": 0, "HARD": 0, "OTHER": 0}
print(f"{'Pattern':<45s} {'Count':>5s}  {'%':>6s}")
print("-" * 60)
for pat, count in expandable.most_common():
    pct = count / len(unparsed) * 100
    print(f"  {pat:<43s} {count:>5d}  ({pct:5.1f}%)")
    tier = pat.split(":")[0] if ":" in pat else "OTHER"
    tiers[tier] = tiers.get(tier, 0) + count

print("-" * 60)
print(f"\nBy difficulty tier:")
for tier, count in sorted(tiers.items()):
    pct = count / len(unparsed) * 100
    print(f"  {tier:<10s} {count:>5d}  ({pct:5.1f}%)")

# Show examples
print(f"\n{'='*70}")
print("EXAMPLES")
print("=" * 70)
for pat, _ in expandable.most_common():
    if pat.startswith("HARD"):
        continue
    print(f"\n--- {pat} ({expandable[pat]}) ---")
    for slug, snip in examples.get(pat, []):
        print(f"  {slug}: {snip}")

#!/usr/bin/env python3
"""Classify all cards in slug_index.msgpack by implementation status.

Categories:
  1. VANILLA       — no functional_text at all (pure stat-sticks)
  2. KEYWORD-ONLY  — functional_text contains only keyword abilities already
                     handled by build_keyword_triggers()
  3. IMPLEMENTED   — has a CARD_TRIGGERS entry (triggers.py or card_triggers_extended.py)
                     OR text_trigger_parser can fully parse all effects
  4. PARSER-EXPANDABLE — functional_text follows common patterns that could
                         be handled by expanding text_trigger_parser (no hand-coding)
  5. COMPLEX       — needs hand-coded trigger implementations

Output: per-category counts + card lists, sorted by type.
"""
from __future__ import annotations
import sys, os, re, json
from pathlib import Path
from collections import defaultdict

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import msgpack

# ---------------------------------------------------------------------------
# 1. Load slug index
# ---------------------------------------------------------------------------
SLUG_INDEX_PATH = ROOT / "card_data" / "slug_index.msgpack"
with open(SLUG_INDEX_PATH, "rb") as f:
    raw_index: dict = msgpack.unpackb(f.read(), raw=False)

# slug_index has top-level keys "by_slug" and "by_name"
slug_index: dict = raw_index.get("by_slug", raw_index)

print(f"Total cards in slug_index: {len(slug_index)}")

# ---------------------------------------------------------------------------
# 2. Collect implemented CARD_TRIGGERS slugs (without full engine import)
# ---------------------------------------------------------------------------

# Read triggers.py to extract CARD_TRIGGERS["slug"] assignments
triggers_path = ROOT / "engine" / "card_effects" / "triggers.py"
triggers_src = triggers_path.read_text(encoding="utf-8")
ct_pattern = re.compile(r'CARD_TRIGGERS\["([a-z0-9_]+)"\]')
triggers_slugs = set(ct_pattern.findall(triggers_src))

# Read card_triggers_extended.py — uses _register("slug", ...) pattern
ext_path = ROOT / "engine" / "card_effects" / "card_triggers_extended.py"
ext_src = ext_path.read_text(encoding="utf-8")
reg_pattern = re.compile(r'_register\("([a-z0-9_]+)"')
ext_slugs = set(reg_pattern.findall(ext_src))
# Also catch direct CARD_TRIGGERS["slug"] in extended
ext_slugs.update(ct_pattern.findall(ext_src))

all_implemented_slugs = triggers_slugs | ext_slugs
print(f"CARD_TRIGGERS entries: {len(triggers_slugs)} (triggers.py) + {len(ext_slugs)} (extended) = {len(all_implemented_slugs)} unique")

# ---------------------------------------------------------------------------
# 3. Known keywords handled by build_keyword_triggers()
# ---------------------------------------------------------------------------
HANDLED_KEYWORDS = {
    # Combat chain close triggers
    "battleworn", "blade break", "temper", "guardwell",
    # Triggered statics
    "phantasm", "spectra", "blood debt", "watery grave", "suspense",
    # Static/pass-through (no trigger needed, engine handles)
    "dominate", "overpower", "go again", "stealth",
    "legendary", "universal", "cloaked", "ephemeral",
    "pairs", "perched", "unlimited", "modular",
    "protect", "ambush", "meld",
    # Optional on-play
    "boost", "scrap", "beat chest",
    # Fusion variants
    "ice fusion", "lightning fusion", "earth fusion",
    "light fusion", "shadow fusion", "draconic fusion",
    # Numbered
    "piercing", "heave", "opt", "crank",
    # Card-specific keywords (pass in build_keyword_triggers)
    "transform", "charge", "mark", "the crowd cheers",
    "contract", "clash", "combo", "crush", "reprise", "surge", "rune gate",
    # Defense keywords (handled by engine, not triggers)
    "arcane barrier", "spellvoid", "ward", "quell", "arcane shelter",
}

# Regex to strip keyword numbers like "Ward 3" -> "ward"
def normalize_kw(kw: str) -> str:
    return re.sub(r'\s+\d+$', '', kw.lower().strip())

# ---------------------------------------------------------------------------
# 4. Text parser coverage check (simplified version of _has_complex_markers)
# ---------------------------------------------------------------------------
COMPLEX_MARKERS = [
    r'\bchoose\b',
    r'\bfor each\b',
    r'\bequal to\b',
    r'\bunless\b',
    r'\binstead\b',
    r'\bbecomes?\b',
    r'\bsearch your deck\b',
    r'\blook at the top\b',
    r'\breveal\b',
    r'\bany number\b',
    r'\bput .+ into play\b',
    r'\breturn .+ from .+ to\b',
    r'\bexchange\b',
    r'\bcopy\b',
    r'\bname a card\b',
    r'\btarget\b',
    r'\btake control\b',
    r'\btransform\b',
    r'\bflip\b',
    r'\bgraft\b',
    r'\btranscend\b',
]

SIMPLE_EFFECT_PATTERNS = [
    r'draw \d+ cards?',
    r'draw a card',
    r'deal \d+ arcane damage',
    r'deal \d+ damage',
    r'gets? \+\d+\{p\}',
    r'gets? \+\d+\{d\}',
    r'(?:gets?|gains?) \*\*go again\*\*',
    r'(?:gets?|gains?) \*\*dominate\*\*',
    r'gain \d+\{h\}',
    r'gain \d+ life',
    r'lose \d+\{h\}',
    r'discard \d+ cards?',
    r'discard a card',
    r'create \d+ [A-Z][a-z ]+ tokens?',
    r'create a [A-Z][a-z ]+ token',
    r'\*\*opt \d+\*\*',
    r'opt \d+',
    r'gain \d+ action points?',
    r'gain \{r\}',
    r'\*\*amp \d+\*\*',
    r'amp \d+',
    r'\*\*intimidate\*\*',
    r'intimidate',
    r'banish the top \d+ cards? of',
]

TRIGGER_PATTERNS = [
    r'when (?:this|[\w\' ,]+?) hits',
    r'when (?:this|[\w\' ,]+?) attacks',
    r'when (?:this|[\w\' ,]+?) defends',
    r'when (?:this|[\w\' ,]+?) enters the arena',
    r'when you play this',
]

LABEL_PATTERNS = [
    r'\*\*Crush\*\*\s*[-–—:]\s*',
    r'\*\*Reprise\*\*\s*[-–—:]\s*',
    r'\*\*Combo\*\*\s*[-–—:]\s*',
]

# "Parser-expandable" patterns — common structures that COULD be parsed
# with moderate regex expansion but aren't currently handled
EXPANDABLE_PATTERNS = [
    r'gain \d+ \{r\}',
    r'put \d+ \{p\} counter',
    r'put a \+1\{p\} counter',
    r'the next attack action card you play',
    r'your next attack this turn',
    r'destroy this',  # equipment activation cost
    r'banish .+ from your graveyard',
    r'return .+ from your graveyard to your hand',
    r'put .+ on the bottom of (?:your|their) deck',
    r'shuffle .+ into (?:your|their) deck',
    r'\bgains?\b.*\buntil end of turn\b',
    r'this gets \+\d+\{p\} for each',
    r'\bonce per turn\b',
    r'action\s*[-\xe2\x80\x93\xe2\x80\x94]\s*\{r\}.*:',  # activated ability pattern
    r'instant\s*[-\xe2\x80\x93\xe2\x80\x94]\s*\{r\}.*:',
    # Simple if-conditions
    r'if (?:this|[\w ]+) has hit',
    r'if you have dealt arcane damage',
    r'if you control',
    r'if there are \d+ or more',
    r'if you have (?:played|pitched)',
    r'when this deals damage',
    r'whenever you play',
    r'at the (?:start|beginning) of',
    r'at the end of',
    r'go again.*\n.*go again',  # multi-effect with go again
    r'create a .+ token',
    r'(?:opponent|defending hero) discards? a? ?(?:random )?cards?',
    r'\{p\} counters?',  # counter manipulation
    r'prevent the next \d+ damage',
    r'(?:attack|defense) reactions? cards?',
    r'lose \d+\{h\}',
    r'gain \d+\{h\}',
    r'banish .+ face (?:up|down)',
    r'play .+ from (?:your )?banish',
]


def has_complex_markers(text: str) -> bool:
    for p in COMPLEX_MARKERS:
        if re.search(p, text, re.I):
            return True
    return False


def is_fully_parseable(text: str) -> bool:
    """Check if the text_trigger_parser would fully handle this card."""
    if not text:
        return False
    # Must have a recognized trigger + all effects are simple
    has_trigger = False
    for tp in TRIGGER_PATTERNS:
        if re.search(tp, text, re.I):
            has_trigger = True
            break
    for lp in LABEL_PATTERNS:
        if re.search(lp, text, re.I):
            has_trigger = True
            break
    
    if not has_trigger:
        return False
    
    # Check if all non-trigger text matches simple effect patterns
    if has_complex_markers(text):
        return False
    
    # Check for at least one recognized effect
    for ep in SIMPLE_EFFECT_PATTERNS:
        if re.search(ep, text, re.I):
            return True
    return False


def is_expandable(text: str) -> bool:
    """Check if the card could be handled by expanding patterns (no hand-coding)."""
    if not text:
        return False
    # Has at least one expandable pattern AND no deeply complex logic
    expandable_count = 0
    for ep in EXPANDABLE_PATTERNS:
        if re.search(ep, text, re.I):
            expandable_count += 1
    
    # Check for deep complexity markers that make expansion impractical
    deep_complex = [
        r'\bchoose\b.*\bchoose\b',  # double choose
        r'\b(?:search|reveal).*(?:search|reveal)',  # double search
        r'\bfor each\b.*\bfor each\b',  # double for-each
        r'\btransform\b',
        r'\bequipped\b',
        r'\bput .+ into play\b',
        r'\bgraft\b',
        r'\binstant action\b',  # timing-specific
    ]
    
    deeply_complex = any(re.search(p, text, re.I) for p in deep_complex)
    
    return expandable_count > 0 and not deeply_complex


def keywords_only(text: str, keywords: list) -> bool:
    """Check if functional_text is fully explained by keywords alone."""
    if not text:
        return True
    
    # Strip out keyword mentions and see if anything substantive remains
    remaining = text
    for kw in keywords:
        # Remove bold keyword mentions like **Go Again**, **Dominate**
        remaining = re.sub(rf'\*\*{re.escape(kw)}\*\*', '', remaining, flags=re.I)
        # Remove plain keyword mentions
        remaining = re.sub(rf'\b{re.escape(kw)}\b', '', remaining, flags=re.I)
    
    # Remove formatting, punctuation, whitespace
    remaining = re.sub(r'[\s\*\-–—:,\.;\(\)\{\}0-9]+', '', remaining)
    # Remove common non-effect text
    remaining = re.sub(r'(?i)rdph', '', remaining)  # resource/defense/power/health markers
    
    return len(remaining.strip()) < 5  # allow tiny residual


# ---------------------------------------------------------------------------
# 5. Classify every card
# ---------------------------------------------------------------------------
categories = {
    "VANILLA": [],
    "KEYWORD-ONLY": [],
    "IMPLEMENTED": [],
    "PARSER-EXPANDABLE": [],
    "COMPLEX": [],
}

for slug, card_data in sorted(slug_index.items()):
    func_text = card_data.get("functional_text") or card_data.get("functionalText") or ""
    keywords = card_data.get("keywords") or card_data.get("card_keywords") or []
    card_types = card_data.get("types") or card_data.get("card_type") or []
    if isinstance(card_types, str):
        card_types = [card_types]
    
    type_label = "/".join(card_types) if card_types else "Unknown"
    name = card_data.get("name") or card_data.get("card_name") or slug
    
    entry = {"slug": slug, "name": name, "type": type_label, "keywords": keywords}
    
    # Category 1: No functional text at all
    if not func_text.strip():
        categories["VANILLA"].append(entry)
        continue
    
    # Category 3: Has CARD_TRIGGERS entry (checks both triggers.py and extended)
    if slug in all_implemented_slugs:
        categories["IMPLEMENTED"].append(entry)
        continue
    
    # Category 2: Keywords explain everything
    normalized_kws = [normalize_kw(kw) for kw in keywords]
    all_handled = all(normalize_kw(kw) in HANDLED_KEYWORDS for kw in keywords) if keywords else False
    if all_handled and keywords_only(func_text, keywords):
        categories["KEYWORD-ONLY"].append(entry)
        continue
    
    # Category 3b: text_trigger_parser can handle it (use actual parser)
    try:
        from engine.card import Card as _Card
        from engine.card_effects.text_trigger_parser import parse_functional_text as _parse
        _card = _Card(slug=slug, name=name, base_functional_text=func_text,
                      types=card_types, subtypes=card_data.get("subtypes") or [],
                      keywords=keywords)
        _trigs = _parse(_card)
        if _trigs:
            categories["IMPLEMENTED"].append(entry)
            continue
    except Exception:
        pass
    if is_fully_parseable(func_text):
        categories["IMPLEMENTED"].append(entry)
        continue
    
    # Category 4: Could be handled by expanding the parser
    if is_expandable(func_text):
        categories["PARSER-EXPANDABLE"].append(entry)
        continue
    
    # Category 5: Complex — needs hand-coded implementations
    categories["COMPLEX"].append(entry)

# ---------------------------------------------------------------------------
# 6. Print results
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("CARD CLASSIFICATION REPORT")
print("=" * 70)

total = len(slug_index)
for cat_name, cards in categories.items():
    pct = len(cards) / total * 100
    print(f"\n{'-' * 60}")
    print(f"  {cat_name}: {len(cards)} cards ({pct:.1f}%)")
    print(f"{'-' * 60}")
    
    # Group by type
    by_type = defaultdict(list)
    for c in cards:
        by_type[c["type"]].append(c)
    
    for typ in sorted(by_type.keys()):
        type_cards = by_type[typ]
        print(f"\n  [{typ}] ({len(type_cards)})")
        for c in sorted(type_cards, key=lambda x: x["slug"]):
            kw_str = f"  kw={','.join(c['keywords'])}" if c['keywords'] else ""
            print(f"    {c['slug']:<50s} {c['name']}{kw_str}")

print(f"\n{'=' * 70}")
print(f"SUMMARY")
print(f"{'=' * 70}")
for cat_name, cards in categories.items():
    pct = len(cards) / total * 100
    print(f"  {cat_name:<25s} {len(cards):>5d}  ({pct:.1f}%)")
print(f"  {'TOTAL':<25s} {total:>5d}")
print(f"{'=' * 70}")

#!/usr/bin/env python3
"""Analyze the PARSER-EXPANDABLE cards to find the most common patterns."""
from __future__ import annotations
import sys, re, json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import msgpack

with open(ROOT / "card_data" / "slug_index.msgpack", "rb") as f:
    slug_index = msgpack.unpackb(f.read(), raw=False)["by_slug"]

# Re-import classification logic from classify_cards to get PARSER-EXPANDABLE set
# (Inline the check to avoid import issues)

HANDLED_KEYWORDS = {
    "battleworn", "blade break", "temper", "guardwell",
    "phantasm", "spectra", "blood debt", "watery grave", "suspense",
    "dominate", "overpower", "go again", "stealth",
    "legendary", "universal", "cloaked", "ephemeral",
    "pairs", "perched", "unlimited", "modular",
    "protect", "ambush", "meld",
    "boost", "scrap", "beat chest",
    "ice fusion", "lightning fusion", "earth fusion",
    "light fusion", "shadow fusion", "draconic fusion",
    "piercing", "heave", "opt", "crank",
    "transform", "charge", "mark", "the crowd cheers",
    "contract", "clash", "combo", "crush", "reprise", "surge", "rune gate",
    "arcane barrier", "spellvoid", "ward", "quell", "arcane shelter",
}

# Read implemented slugs
triggers_src = (ROOT / "engine" / "card_effects" / "triggers.py").read_text("utf-8")
ext_src = (ROOT / "engine" / "card_effects" / "card_triggers_extended.py").read_text("utf-8")
ct_pat = re.compile(r'CARD_TRIGGERS\["([a-z0-9_]+)"\]')
reg_pat = re.compile(r'_register\("([a-z0-9_]+)"')
implemented = set(ct_pat.findall(triggers_src)) | set(reg_pat.findall(ext_src)) | set(ct_pat.findall(ext_src))

# Collect functional_text from non-implemented, non-vanilla, non-keyword-only cards
texts = []
for slug, card in slug_index.items():
    if slug in implemented:
        continue
    ft = card.get("functional_text") or ""
    if not ft.strip():
        continue
    texts.append((slug, ft))

# Pattern frequency analysis
pattern_counts = Counter()
pattern_examples = {}

PATTERNS_TO_COUNT = [
    ("if_condition", r'\bif\b'),
    ("when_hits", r'when (?:this|[\w\' ,]+?) hits'),
    ("when_attacks", r'when (?:this|[\w\' ,]+?) attacks'),
    ("when_defends", r'when (?:this|[\w\' ,]+?) defends'),
    ("when_play", r'when you play this'),
    ("when_enters_arena", r'enters the arena'),
    ("when_leaves_arena", r'leaves the arena'),
    ("on_hit_effect", r'(?:hit|hits)[,:]?\s+(?:draw|deal|gain|create|discard|banish|lose|opt|intimidate|dominate)'),
    ("crush_label", r'\*\*Crush\*\*'),
    ("reprise_label", r'\*\*Reprise\*\*'),
    ("combo_label", r'\*\*Combo\*\*'),
    ("surge_label", r'\*\*Surge\*\*'),
    ("rupture_label", r'\*\*Rupture\*\*'),
    ("channel_label", r'\*\*Channel\*\*'),
    ("once_per_turn", r'once per turn'),
    ("go_again_grant", r'(?:gets?|gains?) \*\*go again\*\*'),
    ("dominate_grant", r'(?:gets?|gains?) \*\*dominate\*\*'),
    ("overpower_grant", r'(?:gets?|gains?) \*\*overpower\*\*'),
    ("stealth_grant", r'(?:gets?|gains?) \*\*stealth\*\*'),
    ("draw_cards", r'draw (?:a|\d+) cards?'),
    ("deal_arcane", r'deal \d+ arcane damage'),
    ("deal_damage", r'deal \d+ damage'),
    ("power_bonus", r'gets? \+\d+\{p\}'),
    ("defense_bonus", r'gets? \+\d+\{d\}'),
    ("gain_life", r'gain \d+\{h\}'),
    ("lose_life", r'lose\s*\d+\{h\}'),
    ("create_token", r'create (?:a|\d+) .+? tokens?'),
    ("discard_cards", r'discard (?:a|\d+) cards?'),
    ("opt_effect", r'opt \d+'),
    ("amp_effect", r'amp \d+'),
    ("intimidate_effect", r'\bintimidated?\b'),
    ("banish_top", r'banish the top'),
    ("action_activate", r'action\s*[-\u2013\u2014]'),
    ("instant_activate", r'instant\s*[-\u2013\u2014]'),
    ("destroy_this", r'destroy (?:this|[\w ]+?):'),
    ("counter_put", r'put (?:a|\d+) .+? counters?'),
    ("counter_remove", r'remove (?:a|\d+) .+? counters?'),
    ("prevent_damage", r'prevent the next \d+ damage'),
    ("next_attack", r'(?:next|the next) attack'),
    ("this_turn", r'this turn'),
    ("end_of_turn", r'(?:end|close) of (?:the )?turn'),
    ("if_you_control", r'if you control'),
    ("if_you_have", r'if you have'),
    ("if_defended", r'if .+ defended'),
    ("if_4_or_more_damage", r'if .+ dealt? \d+ or more damage'),
    ("for_each", r'for each'),
    ("choose", r'\bchoose\b'),
    ("search_deck", r'search your deck'),
    ("look_at_top", r'look at the top'),
    ("reveal", r'\breveal\b'),
    ("transform", r'\btransform\b'),
    ("play_from_banish", r'play .+ from .+banish'),
    ("activated_ability", r'(?:action|instant)\s*[-\u2013\u2014]\s*(?:\{r\}|destroy)'),
    ("resource_cost_pattern", r'\{r\}.*:'),
    ("blood_debt_kw", r'\*\*Blood Debt\*\*'),
    ("ward_kw", r'\*\*Ward\b'),
    ("arcane_barrier_kw", r'\*\*Arcane Barrier\b'),
    ("then_clause", r'\bthen\b'),
    ("and_conjunction", r'\band\b'),
    ("multi_sentence", r'\.\s+[A-Z]'),  # multiple sentences
    ("newline_sep", r'\n\n'),  # paragraph breaks (multi-effect)
]

for slug, ft in texts:
    for name, pat in PATTERNS_TO_COUNT:
        if re.search(pat, ft, re.I):
            pattern_counts[name] += 1
            if name not in pattern_examples:
                pattern_examples[name] = []
            if len(pattern_examples[name]) < 3:
                pattern_examples[name].append(slug)

print(f"Analyzed {len(texts)} non-implemented cards with text\n")
print("PATTERN FREQUENCY (sorted by count):")
print("-" * 60)
for name, count in pattern_counts.most_common():
    pct = count / len(texts) * 100
    examples = pattern_examples.get(name, [])
    print(f"  {name:<30s} {count:>5d} ({pct:>5.1f}%)  e.g. {', '.join(examples[:3])}")

# Also analyze JUST the PARSER-EXPANDABLE vs COMPLEX split
print("\n\nMOST COMMON EFFECTS IN SIMPLEST UNIMPLEMENTED CARDS:")
print("-" * 60)
# Cards that have only 1 sentence (no multi-sentence, no paragraph)
simple_cards = [(s, ft) for s, ft in texts
                if not re.search(r'\.\s+[A-Z]', ft) and '\n\n' not in ft]
print(f"Single-sentence cards: {len(simple_cards)}")
simple_patterns = Counter()
for slug, ft in simple_cards:
    for name, pat in PATTERNS_TO_COUNT:
        if re.search(pat, ft, re.I):
            simple_patterns[name] += 1

for name, count in simple_patterns.most_common(20):
    print(f"  {name:<30s} {count:>5d}")

#!/usr/bin/env python3
"""Analyze pattern frequencies in cards the text_trigger_parser cannot handle."""
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

# Collect unparsed cards
unparsed = []
for slug, data in slug_index.items():
    ft = data.get("functional_text", "") or ""
    if not ft.strip():
        continue
    if slug in CARD_TRIGGERS:
        continue
    try:
        card = Card(slug=slug, name=data.get("name", ""), base_functional_text=ft,
                    types=data.get("types", []) or [], subtypes=data.get("subtypes", []) or [],
                    keywords=data.get("ability_keywords", []) or [])
        trigs = parse_functional_text(card)
        if not trigs:
            unparsed.append((slug, ft))
    except Exception:
        unparsed.append((slug, ft))

print(f"Total unparsed cards: {len(unparsed)}")
print()

# Pattern frequency analysis
patterns = [
    ("action_activate", r"\*\*(?:once per turn )?action\*\*\s*[-\u2013\u2014]"),
    ("instant_activate", r"\*\*(?:once per turn )?instant\*\*\s*[-\u2013\u2014]"),
    ("destroy_this_colon", r"destroy (?:this|[\w ]+?)\s*:"),
    ("once_per_turn", r"once per turn"),
    ("go_again_kw", r"\*\*go again\*\*"),
    ("dominate_kw", r"\*\*dominate\*\*"),
    ("overpower_kw", r"\*\*overpower\*\*"),
    ("choose", r"\bchoose\b"),
    ("for_each", r"\bfor each\b"),
    ("equal_to", r"\bequal to\b"),
    ("search_deck", r"\bsearch\b"),
    ("look_at_top", r"\blook at the top\b"),
    ("reveal", r"\breveal\b"),
    ("transform", r"\btransform\b"),
    ("put_into_play", r"\bput .+ into play\b"),
    ("unless", r"\bunless\b"),
    ("instead", r"\binstead\b"),
    ("becomes", r"\bbecomes?\b"),
    ("then_clause", r"\bthen\b"),
    ("copy", r"\bcopy\b"),
    ("exchange", r"\bexchange\b"),
    ("name_a_card", r"\bname a card\b"),
    ("take_control", r"\btake control\b"),
    ("transcend", r"\btranscend\b"),
    ("graft", r"\bgraft\b"),
    ("when_attacks", r"when .+? attacks"),
    ("when_hits", r"when .+? hits"),
    ("when_defends", r"when .+? defends"),
    ("when_you_play", r"when you play"),
    ("if_condition", r"\bif\b"),
    ("draw_card", r"draw (?:a|\d+) cards?"),
    ("deal_arcane", r"deal \d+ arcane damage"),
    ("deal_damage", r"deal \d+ damage"),
    ("power_bonus", r"gets? \+\d+\{p\}"),
    ("defense_bonus", r"gets? \+\d+\{d\}"),
    ("create_token", r"create (?:a|\d+|an) .+ tokens?"),
    ("gain_life", r"gain \d+\{h\}"),
    ("lose_life", r"lose \d+\{h\}"),
    ("discard_cards", r"discards? (?:a|\d+)"),
    ("banish", r"\bbanish\b"),
    ("return_to_hand", r"return .+ to .+ hand"),
    ("put_bottom", r"put .+ bottom"),
    ("shuffle_into", r"shuffle .+ into"),
    ("graveyard", r"\bgraveyard\b"),
    ("arsenal", r"\barsenal\b"),
    ("until_end_turn", r"until end of turn"),
    ("whenever", r"\bwhenever\b"),
    ("at_start_turn", r"at the (?:start|beginning) of"),
    ("at_end_turn", r"at the end of"),
    ("counters", r"\bcounters?\b"),
    ("galvanize", r"\*\*galvanize\*\*"),
    ("crush", r"\*\*crush\*\*"),
    ("reprise", r"\*\*reprise\*\*"),
    ("combo", r"\*\*combo\*\*"),
    ("surge", r"\*\*surge\*\*"),
    ("rupture", r"\*\*rupture\*\*"),
    ("freeze", r"\bfreeze\b"),
    ("charge", r"\bcharge\b"),
    ("resource_cost", r"\{r\}"),
    ("defense_reaction", r"defense reaction"),
    ("attack_reaction", r"attack reaction"),
    ("played_from_arsenal", r"played from arsenal"),
    ("was_last_attack", r"was the last .+ played"),
    ("double_paragraph", r"\n\n"),
    ("prevent_damage", r"prevent the next \d+"),
    ("opt", r"\bopt\b"),
    ("intimidate", r"\bintimidate\b"),
    ("amp", r"\bamp\b"),
    ("phantasm", r"\bphantasm\b"),
    ("spectra", r"\bspectra\b"),
    ("boost", r"\bboost\b"),
    ("heave", r"\bheave\b"),
    ("battleworn", r"\bbattleworn\b"),
    ("temper", r"\btemper\b"),
    ("modular", r"\bmodular\b"),
    ("ward", r"\bward\b"),
    ("blood_debt", r"\bblood debt\b"),
    ("instant_card", r"\binstant\b"),
    ("your_hero", r"your hero"),
    ("opposing_hero", r"opposing hero"),
    ("target_hero", r"target hero"),
    ("each_hero", r"each .* hero"),
    ("multi_sentence", r"\.\s+[A-Z]"),
]

counts = Counter()
for slug, ft in unparsed:
    for pname, pat in patterns:
        if re.search(pat, ft, re.I | re.MULTILINE):
            counts[pname] += 1

print("Pattern frequencies in UNPARSED cards:")
for pname, count in counts.most_common():
    pct = count / len(unparsed) * 100
    if count >= 10:
        print(f"  {pname:<30s} {count:>5d}  ({pct:.1f}%)")

# Show sample texts for top patterns that COULD be parseable
print("\n" + "=" * 70)
print("SAMPLES — Cards with trigger+effect but blocked by complexity filter:")
print("=" * 70)

# Cards with a recognizable trigger but blocked
blocked_by_then = []
blocked_by_choose = []
blocked_simple_if = []
has_trigger_but_fails = []

for slug, ft in unparsed:
    has_trigger = bool(re.search(r"when .+? (?:hits|attacks|defends)|when you play this", ft, re.I))
    has_effect = bool(re.search(r"draw|deal \d+|gets? \+\d+|\*\*go again\*\*|create .+ token|gain \d+|discard", ft, re.I))
    
    if has_trigger and has_effect:
        if re.search(r"\bthen\b", ft, re.I) and not re.search(r"\bchoose\b|\bfor each\b|\bsearch\b", ft, re.I):
            blocked_by_then.append((slug, ft))
        elif re.search(r"\bif\b", ft, re.I) and not re.search(r"\bchoose\b|\bfor each\b|\bsearch\b|\bequal to\b", ft, re.I):
            blocked_simple_if.append((slug, ft))
        else:
            has_trigger_but_fails.append((slug, ft))

print(f"\nCards with trigger+effect blocked by 'then': {len(blocked_by_then)}")
for slug, ft in blocked_by_then[:10]:
    print(f"  {slug}: {ft[:120]}")

print(f"\nCards with trigger+effect + simple 'if' (not choose/for each): {len(blocked_simple_if)}")
for slug, ft in blocked_simple_if[:10]:
    print(f"  {slug}: {ft[:120]}")

print(f"\nOther cards with trigger+effect that fail: {len(has_trigger_but_fails)}")
for slug, ft in has_trigger_but_fails[:10]:
    print(f"  {slug}: {ft[:120]}")

# Show multi-paragraph cards with standalone effects that fail
print(f"\n{'=' * 70}")
print("SAMPLES — Simple standalone effects that fail:")
print("=" * 70)

standalone_fails = []
for slug, ft in unparsed:
    paras = ft.strip().split("\n\n")
    if len(paras) >= 2:
        # Check if at least one paragraph is simple but parser still fails overall
        simple_count = 0
        complex_count = 0
        for p in paras:
            p = p.strip()
            if not p:
                continue
            if re.match(r"^\*\*(?:Go again|Dominate|Overpower)\*\*\.?$", p, re.I):
                simple_count += 1
            elif re.search(r"\bchoose\b|\bfor each\b|\bsearch\b|\btransform\b|\breveal\b|\blook at\b", p, re.I):
                complex_count += 1
            elif re.search(r"deal \d+|draw|gets? \+\d+|create .+ token|gain \d+", p, re.I):
                simple_count += 1
        if simple_count >= 1 and complex_count >= 1:
            standalone_fails.append((slug, ft, simple_count, complex_count))

print(f"Multi-para cards with mix of simple+complex paragraphs: {len(standalone_fails)}")
for slug, ft, sc, cc in standalone_fails[:15]:
    print(f"  {slug} (simple={sc}, complex={cc}): {ft[:120]}")

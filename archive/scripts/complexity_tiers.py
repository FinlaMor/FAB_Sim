"""Classify uncovered card effects by complexity tier for subtask-2-1.

Reads slug_index.json, identifies uncovered cards (same logic as gap_analysis.py),
then classifies each into Simple/Medium/Complex based on functional_text patterns.
"""
import json
import re
import os

SLUG_PATH = r"C:\Users\Joseph\Desktop\FAB_Sim\card_data\slug_index.json"
REPORT_PATH = "docs/reports/complexity_tier_analysis.md"


def get_uncovered_cards(by_slug):
    """Reproduce the gap_analysis.py logic to find uncovered cards."""
    with open("engine/card_effects/triggers.py", encoding="utf-8") as f:
        trig_content = f.read()
    card_trigger_slugs = set(re.findall(r'CARD_TRIGGERS\["([a-z0-9_]+)"\]', trig_content))

    with open("engine/card_effects/db/seed_data.sql", encoding="utf-8") as f:
        seed = f.read()
    db_slugs = set(re.findall(r"INSERT INTO card_triggers.*?VALUES \('([^']+)'", seed))
    custom_slugs = card_trigger_slugs | db_slugs

    # Keyword handling
    bkt_match = re.search(
        r'def build_keyword_triggers\(.*?\).*?:\n(.*?)(?=\ndef |\Z)',
        trig_content, re.DOTALL,
    )
    handled_keywords = set()
    passthrough_keywords = set()
    if bkt_match:
        bkt_body = bkt_match.group(1)
        for m in re.finditer(r'kw_base\s*==\s*"([^"]+)"', bkt_body):
            handled_keywords.add(m.group(1))
        for m in re.finditer(r'kw_base\.endswith\("([^"]+)"\)', bkt_body):
            handled_keywords.add(m.group(1))
        for m in re.finditer(r'kw_base\s+in\s+\(([^)]+)\)', bkt_body):
            for kw in re.findall(r'"([^"]+)"', m.group(1)):
                passthrough_keywords.add(kw)

    keyword_triggered_cards = set()
    for s, card in by_slug.items():
        for kw in (card.get("card_keywords") or []):
            kw_base = re.sub(r"\s+\d+$", "", kw.strip()).lower()
            if kw_base in handled_keywords or (
                kw_base.endswith("fusion") and "fusion" in handled_keywords
            ):
                keyword_triggered_cards.add(s)

    vanilla_cards = set()
    cards_needing_effects = set()
    for s, card in by_slug.items():
        ft = (card.get("functional_text_plain") or "").strip()
        kws = card.get("card_keywords") or []
        if not ft:
            vanilla_cards.add(s)
            continue
        remaining = ft
        for kw in kws:
            remaining = remaining.replace(kw, "")
        remaining = re.sub(r"(Legendary|Unlimited|Universal)", "", remaining)
        remaining = remaining.strip(" \n\t,.-;:()")
        if not remaining:
            vanilla_cards.add(s)
        else:
            cards_needing_effects.add(s)

    covered_by_custom = custom_slugs & set(by_slug.keys())
    uncovered = cards_needing_effects - covered_by_custom - keyword_triggered_cards
    return uncovered


# Patterns indicating complex effects (~60+ min each)
COMPLEX_PATTERNS = [
    r"choose\s+(one|a|an|up\s+to)",       # player choices
    r"\binstead\b",                         # replacement effects
    r"\bwhenever\b",                        # general triggered abilities
    r"for\s+each",                          # scaling effects
    r"search\s+your\s+deck",               # tutoring
    r"\btransform\b",                       # transform mechanic
    r"\btranscend\b",                       # transcend mechanic
    r"play\s+.*from\s+(your\s+)?banished",  # cross-zone play
    r"put\s+.*into\s+play",                # cheat into play
    r"gain\s+control",                      # control effects
    r"\bcopy\b",                            # copy effects
    r"prevent.*damage",                     # damage prevention
    r"can.t\s+be",                          # restrictions
    r"additional\s+cost",                   # cost modification
    r"reduce.*cost",                        # cost reduction
    r"play\s+this\s+as\s+an\s+instant",    # timing changes
    r"name\s+a\s+card",                     # naming effects
    r"exchange",                            # exchange effects
    r"each\s+player",                       # symmetric effects
    r"pay\s+.*life",                        # alternate costs
    r"lose\s+and\s+can.t\s+gain",           # ability removal
    r"remove\s+.*counters?\s+from\s+among",  # multi-card counter manipulation
    r"rather\s+than\s+pay",                  # alternate costs
    r"becomes?\s+the\s+chosen",              # becomes/shapeshifting
    r"equal\s+to\s+the\s+number",            # variable scaling
]

# Patterns indicating medium effects (~30 min each)
MEDIUM_PATTERNS = [
    r"create\s+.*token",                    # token creation
    r"put\s+.*counter",                     # counter manipulation
    r"banish\s+.*from",                     # banishing from zones
    r"return\s+.*from\s+graveyard",         # recursion
    r"\bif\b.*\bhas\b",                     # simple conditionals
    r"when\s+this\s+(attacks|hits|enters|leaves)",  # specific triggers
    r"at\s+the\s+(start|end)\s+of",         # phase triggers
    r"your\s+next\s+attack",               # next-attack buffs
    r"\breveal\b",                          # reveal effects
    r"the\s+next\s+card",                   # next-card effects
    r"cards?\s+in\s+your\s+(graveyard|banished|soul|pitch)",  # zone-counting
    r"destroyed\s+this\s+way",             # conditional on resolution
    r"\bif\b.*\bin\s+your\b",              # conditional zone checks
    r"then\s+(draw|deal|gain|create)",      # if-then effects
    r"attack\s+action\s+card",             # targeting specific types
]

# Simple patterns are the default — anything not matching complex or medium


def classify_card(slug, card):
    """Classify a card into simple/medium/complex based on functional_text."""
    ft = (card.get("functional_text_plain") or "").strip()
    ft_lower = ft.lower()
    lines_count = len([l for l in ft.split("\n") if l.strip()])

    # Check complex first
    for p in COMPLEX_PATTERNS:
        if re.search(p, ft_lower):
            return "complex"
    if lines_count >= 4:
        return "complex"

    # Check medium
    for p in MEDIUM_PATTERNS:
        if re.search(p, ft_lower):
            return "medium"
    if lines_count >= 3:
        return "medium"

    return "simple"


def main():
    with open(SLUG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    by_slug = data["by_slug"]

    uncovered = get_uncovered_cards(by_slug)
    print(f"Uncovered cards: {len(uncovered)}")

    tiers = {"simple": [], "medium": [], "complex": []}
    for s in sorted(uncovered):
        tier = classify_card(s, by_slug[s])
        tiers[tier].append(s)

    for tier_name, slugs in tiers.items():
        print(f"  {tier_name.capitalize()}: {len(slugs)}")

    # --- Dedup by base name (strip color suffixes) ---
    def base_name(slug):
        return re.sub(r"_(red|yellow|blue)$", "", slug)

    unique_bases = {"simple": set(), "medium": set(), "complex": set()}
    for tier_name, slugs in tiers.items():
        for s in slugs:
            unique_bases[tier_name].add(base_name(s))

    print("\nAfter color dedup (unique implementations needed):")
    for tier_name, bases in unique_bases.items():
        print(f"  {tier_name.capitalize()}: {len(bases)}")

    # --- Time estimates ---
    time_per = {"simple": 15, "medium": 30, "complex": 60}  # minutes
    total_minutes = 0
    print("\nEffort estimates:")
    for tier_name, bases in unique_bases.items():
        minutes = len(bases) * time_per[tier_name]
        total_minutes += minutes
        hours = minutes / 60
        print(f"  {tier_name.capitalize()}: {len(bases)} x {time_per[tier_name]} min = {hours:.0f} hours")
    total_hours = total_minutes / 60
    total_weeks = total_hours / 40
    print(f"  TOTAL: {total_hours:.0f} hours (~{total_weeks:.1f} developer-weeks)")

    # --- Generate report ---
    lines = []
    lines.append("# Card Effect Complexity Tier Analysis")
    lines.append("")
    lines.append("**Generated by**: `scripts/complexity_tiers.py`")
    lines.append(f"**Uncovered cards analyzed**: {len(uncovered)}")
    lines.append("")

    lines.append("## Methodology")
    lines.append("")
    lines.append("Cards are classified by analyzing their `functional_text_plain` against pattern sets:")
    lines.append("")
    lines.append("- **Simple** (~15 min each): Stat modifications (+N power/defense), draw/discard N cards,")
    lines.append("  gain/lose life, deal damage, gain resources, go again as text, opt N, intimidate.")
    lines.append("  These map directly to existing template functions in keywords.py (effect_draw,")
    lines.append("  effect_deal_damage, effect_gain_life, etc.).")
    lines.append("")
    lines.append("- **Medium** (~30 min each): Token creation, counter manipulation, banish-from-zone,")
    lines.append("  graveyard recursion, simple conditionals (if X has Y), specific triggers")
    lines.append("  (when this attacks/hits/enters), phase triggers, next-attack buffs, reveal effects,")
    lines.append("  zone-counting conditions. These require combining 2-3 existing primitives with")
    lines.append("  light conditional logic.")
    lines.append("")
    lines.append("- **Complex** (~60+ min each): Player choices (choose one/up to), replacement effects")
    lines.append("  (instead), general triggered abilities (whenever), scaling effects (for each),")
    lines.append("  deck searching/tutoring, transform/transcend, cross-zone play, cheat-into-play,")
    lines.append("  control-changing, copy effects, damage prevention, restriction effects (can't be),")
    lines.append("  cost modification, timing changes. These require new infrastructure or multi-step")
    lines.append("  agent interaction.")
    lines.append("")
    lines.append("Cards with 4+ lines of functional text are auto-classified as Complex;")
    lines.append("3 lines as Medium (multi-paragraph text correlates with implementation complexity).")
    lines.append("")

    lines.append("## Tier Breakdown")
    lines.append("")
    lines.append("| Tier | Cards | Unique (deduped) | Time/each | Total Hours |")
    lines.append("|------|-------|------------------|-----------|-------------|")
    for tier_name in ["simple", "medium", "complex"]:
        cards = len(tiers[tier_name])
        uniq = len(unique_bases[tier_name])
        tpe = time_per[tier_name]
        hrs = uniq * tpe / 60
        lines.append(f"| {tier_name.capitalize()} | {cards} | {uniq} | {tpe} min | {hrs:.0f} |")
    lines.append(f"| **Total** | **{len(uncovered)}** | **{sum(len(b) for b in unique_bases.values())}** | — | **{total_hours:.0f}** |")
    lines.append("")
    lines.append(f"**Total effort**: ~{total_hours:.0f} developer-hours (~{total_weeks:.1f} developer-weeks at 40 hr/wk)")
    lines.append("")

    # --- Sample cards per tier ---
    for tier_name in ["simple", "medium", "complex"]:
        slugs = tiers[tier_name]
        lines.append(f"## {tier_name.capitalize()} Tier — Sample Cards ({len(slugs)} total)")
        lines.append("")
        # Show 15 samples
        for s in slugs[:15]:
            card = by_slug[s]
            name = card.get("name", s)
            ft = (card.get("functional_text_plain") or "")[:200].replace("\n", " ↵ ")
            types = " / ".join(card.get("types", []))
            lines.append(f"1. **`{s}`** ({name}) [{types}]")
            lines.append(f"   > {ft}")
            lines.append("")

        if len(slugs) > 15:
            lines.append(f"*... and {len(slugs) - 15} more {tier_name} cards*")
            lines.append("")

    # --- Validation section ---
    lines.append("## Validation")
    lines.append("")
    lines.append("### Sample Verification (5 per tier)")
    lines.append("")
    for tier_name in ["simple", "medium", "complex"]:
        slugs = tiers[tier_name]
        lines.append(f"**{tier_name.capitalize()} tier:**")
        lines.append("")
        for s in slugs[:5]:
            card = by_slug[s]
            name = card.get("name", s)
            ft = (card.get("functional_text_plain") or "").replace("\n", " ↵ ")
            lines.append(f"- `{s}` ({name}): {ft[:150]}")
        lines.append("")

    report = "\n".join(lines)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport written to: {REPORT_PATH}")


if __name__ == "__main__":
    main()

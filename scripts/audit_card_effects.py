"""Audit all card slugs and classify their implementation status.

Reads slug_index.json, cross-references with CARD_TRIGGERS keys and keyword-system
handled keywords, and classifies each card into:
  (a) already_implemented - has CARD_TRIGGERS entry or is purely keyword-handled
  (b) simple_db - expressible via existing DB effect/condition types
  (c) template_expandable - needs new or existing template builders
  (d) complex_custom - needs custom Python function
  (e) missing_mechanic - requires engine mechanic not yet supported

Outputs classification to a JSON file.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
SLUG_PATH = os.environ.get("FAB_SLUG_PATH", str(_ROOT / "card_data" / "slug_index.json"))
OUTPUT_PATH = "docs/reports/card_classification.json"

# ---------------------------------------------------------------------------
# DB-expressible effect/condition types from schema.sql
# ---------------------------------------------------------------------------
DB_EFFECT_TYPES = {
    "gain_life", "lose_life", "deal_damage", "deal_arcane", "deal_physical",
    "draw", "discard", "create_token", "grant_go_again", "grant_keyword",
    "intimidate", "dominate", "mark", "amp", "gain_resources",
    "power_bonus", "set_flag", "put_counter", "remove_counter",
    "banish_top_deck", "reload", "opt", "charge",
}

DB_CONDITION_TYPES = {
    "none", "is_attacking", "is_defending", "player_is_active",
    "player_is_non_active", "health_more_than_opp", "coplayer_power_gte",
    "has_counter_lt", "has_counter_gte", "flag_set", "card_in_zone",
    "controller_has_card_type", "opponent_has_supertype",
    "attacking_hero_is", "defending_hero_is",
    "reprise_check", "crush_check", "combo_check", "surge_check",
    "rupture_check",
}

# ---------------------------------------------------------------------------
# Patterns for simple DB-expressible effects
# ---------------------------------------------------------------------------
SIMPLE_DB_PATTERNS = [
    # "Draw a card" / "Draw 2 cards"
    (r"\bdraw\s+(\d+\s+)?cards?\b", "draw"),
    # "Deal N damage" / "Deal N arcane damage"
    (r"\bdeal\s+\d+\s+arcane\s+damage\b", "deal_arcane"),
    (r"\bdeal\s+\d+\s+damage\b", "deal_damage"),
    # "Gain N life"
    (r"\bgain\s+\d+\s+life\b", "gain_life"),
    # "Lose N life"
    (r"\blose\s+\d+\s+life\b", "lose_life"),
    # "Gain go again"
    (r"\bgain\s+go\s+again\b", "grant_go_again"),
    # "Dominate"
    (r"\bdominate\b", "dominate"),
    # "Intimidate"
    (r"\bintimidate\b", "intimidate"),
    # "Opt N"
    (r"\bopt\s+\d+\b", "opt"),
    # "+N power" / "gets +N"
    (r"\+\d+\s*\{p\}|\+\d+\s+power\b", "power_bonus"),
    # "Create a ... token"
    (r"\bcreate\s+a?\s*\w+\s+token\b", "create_token"),
    # "Put a ... counter"
    (r"\bput\s+a\s+\w+\s+counter\b", "put_counter"),
    # "Amp"
    (r"\bamp\b", "amp"),
]

# ---------------------------------------------------------------------------
# Patterns for template-expandable effects (common patterns with variation)
# ---------------------------------------------------------------------------
TEMPLATE_PATTERNS = [
    r"\bon\s+hit[,:]\s*draw",               # on-hit-draw template
    r"\bwhen\s+this\s+attacks.*\+\d+",       # attack-power-buff template
    r"\bwhen\s+this\s+hits.*deal\s+\d+",     # on-hit-damage template
    r"\bif\s+.*\bin\s+your\s+(graveyard|banished|pitch)",  # zone-count conditional
    r"\bcrush\b.*draw",                       # crush-draw template
    r"\breprise\b.*draw",                     # reprise-draw template
    r"\bcombo\b.*draw",                       # combo-draw template
    r"\bsurge\b.*deal",                       # surge-deal template
    r"\brupture\b.*draw",                     # rupture-draw template
    r"\bon\s+play.*gain\s+go\s+again",        # on-play-go-again template
    r"\bwhen\s+this\s+enters\s+the\s+arena",  # enters-arena template
]

# ---------------------------------------------------------------------------
# Patterns for missing mechanics (engine doesn't support yet)
# ---------------------------------------------------------------------------
MISSING_MECHANIC_PATTERNS = [
    (r"\btransform\b", "transform"),
    (r"\btranscend\b", "transcend"),
    (r"\bgain\s+control\b", "gain_control"),
    (r"\bname\s+a\s+card\b", "name_a_card"),
    (r"\bexchange\b.*\bhand\b", "exchange_hands"),
    (r"\bbecomes?\s+the\s+chosen\b", "becomes_chosen"),
    (r"\bcopy\b.*\battack\b", "copy_attack"),
    (r"\bplay\s+this\s+as\s+an\s+instant\b", "instant_timing"),
    (r"\brather\s+than\s+pay\b", "alternate_cost"),
    (r"\bprevent.*damage\b", "damage_prevention"),
    (r"\bcan.t\s+be\b.*\btargeted\b", "targeting_restriction"),
    (r"\beach\s+player\b.*\bchoose\b", "multiplayer_choice"),
]

# ---------------------------------------------------------------------------
# Complex patterns (need custom Python)
# ---------------------------------------------------------------------------
COMPLEX_PATTERNS = [
    r"choose\s+(one|a|an|up\s+to)",
    r"\binstead\b",
    r"\bwhenever\b",
    r"for\s+each",
    r"search\s+your\s+deck",
    r"play\s+.*from\s+(your\s+)?banished",
    r"put\s+.*into\s+play",
    r"can.t\s+be",
    r"additional\s+cost",
    r"reduce.*cost",
    r"pay\s+.*life",
    r"lose\s+and\s+can.t\s+gain",
    r"remove\s+.*counters?\s+from\s+among",
    r"equal\s+to\s+the\s+number",
]


def load_implemented_slugs():
    """Load slugs that have CARD_TRIGGERS entries or DB seed_data rows."""
    with open("engine/card_effects/triggers.py", encoding="utf-8") as f:
        trig_content = f.read()
    card_trigger_slugs = set(
        re.findall(r'CARD_TRIGGERS\["([a-z0-9_]+)"\]', trig_content)
    )

    with open("engine/card_effects/db/seed_data.sql", encoding="utf-8") as f:
        seed = f.read()
    db_slugs = set(
        re.findall(r"INSERT INTO card_triggers.*?VALUES \('([^']+)'", seed)
    )

    return card_trigger_slugs, db_slugs


def load_handled_keywords(trig_content):
    """Extract keywords handled by build_keyword_triggers."""
    handled_keywords = set()
    passthrough_keywords = set()

    bkt_match = re.search(
        r'def build_keyword_triggers\(.*?\).*?:\n(.*?)(?=\ndef |\Z)',
        trig_content, re.DOTALL,
    )
    if bkt_match:
        bkt_body = bkt_match.group(1)
        for m in re.finditer(r'kw_base\s*==\s*"([^"]+)"', bkt_body):
            handled_keywords.add(m.group(1))
        for m in re.finditer(r'kw_base\.endswith\("([^"]+)"\)', bkt_body):
            handled_keywords.add(m.group(1))
        for m in re.finditer(r'kw_base\s+in\s+\(([^)]+)\)', bkt_body):
            for kw in re.findall(r'"([^"]+)"', m.group(1)):
                passthrough_keywords.add(kw)

    return handled_keywords, passthrough_keywords


def is_keyword_handled(card, handled_keywords):
    """Check if a card is fully handled by keyword triggers."""
    for kw in (card.get("ability_keywords") or []):
        kw_base = re.sub(r"\s+\d+$", "", kw.strip()).lower()
        if kw_base in handled_keywords or (
            kw_base.endswith("fusion") and "fusion" in handled_keywords
        ):
            return True
    return False


def is_vanilla(card):
    """Check if a card has no functional text beyond keywords."""
    ft = (card.get("functional_text_plain") or "").strip()
    kws = card.get("ability_keywords") or []
    if not ft:
        return True
    remaining = ft
    for kw in kws:
        remaining = remaining.replace(kw, "")
    remaining = re.sub(r"(Legendary|Unlimited|Universal)", "", remaining)
    remaining = remaining.strip(" \n\t,.-;:()")
    return not remaining


def classify_card(slug, card, ft_lower):
    """Classify an uncovered card into simple_db, template_expandable,
    complex_custom, or missing_mechanic."""
    # Check missing mechanics first
    for pattern, mechanic in MISSING_MECHANIC_PATTERNS:
        if re.search(pattern, ft_lower):
            return "missing_mechanic", mechanic

    # Check complex patterns
    for pattern in COMPLEX_PATTERNS:
        if re.search(pattern, ft_lower):
            return "complex_custom", None

    # Check template patterns
    for pattern in TEMPLATE_PATTERNS:
        if re.search(pattern, ft_lower):
            return "template_expandable", None

    # Check simple DB patterns
    for pattern, effect_type in SIMPLE_DB_PATTERNS:
        if re.search(pattern, ft_lower):
            return "simple_db", None

    # Multi-line functional text suggests complexity
    ft = (card.get("functional_text_plain") or "").strip()
    lines_count = len([line for line in ft.split("\n") if line.strip()])
    if lines_count >= 4:
        return "complex_custom", None
    if lines_count >= 3:
        return "template_expandable", None

    # Default: simple DB if short, template if medium
    if lines_count <= 1:
        return "simple_db", None
    return "template_expandable", None


def main():
    parser = argparse.ArgumentParser(
        description="Audit card slugs and classify implementation status."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print summary only, don't write output file.",
    )
    parser.add_argument(
        "--output", default=OUTPUT_PATH,
        help=f"Output JSON path (default: {OUTPUT_PATH})",
    )
    args = parser.parse_args()

    # Load card data
    with open(SLUG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    by_slug = data["by_slug"]
    total = len(by_slug)

    # Load implemented slugs
    card_trigger_slugs, db_slugs = load_implemented_slugs()
    custom_slugs = card_trigger_slugs | db_slugs

    # Load keyword handling
    with open("engine/card_effects/triggers.py", encoding="utf-8") as f:
        trig_content = f.read()
    handled_keywords, passthrough_keywords = load_handled_keywords(trig_content)

    # Classify each card
    classification = {
        "already_implemented": [],
        "simple_db": [],
        "template_expandable": [],
        "complex_custom": [],
        "missing_mechanic": [],
    }
    missing_mechanics_detail = {}  # mechanic -> list of slugs

    for slug, card in sorted(by_slug.items()):
        # (a) Already implemented via CARD_TRIGGERS or DB
        if slug in custom_slugs:
            classification["already_implemented"].append(slug)
            continue

        # (a) Purely keyword-handled
        if is_keyword_handled(card, handled_keywords):
            classification["already_implemented"].append(slug)
            continue

        # (a) Vanilla cards (no functional text)
        if is_vanilla(card):
            classification["already_implemented"].append(slug)
            continue

        # Classify remaining cards
        ft_lower = (card.get("functional_text_plain") or "").strip().lower()
        category, detail = classify_card(slug, card, ft_lower)
        classification[category].append(slug)

        if category == "missing_mechanic" and detail:
            missing_mechanics_detail.setdefault(detail, []).append(slug)

    # Build output
    output = {
        "total_cards": total,
        "summary": {
            cat: len(slugs) for cat, slugs in classification.items()
        },
        "missing_mechanics": {
            mechanic: len(slugs)
            for mechanic, slugs in sorted(
                missing_mechanics_detail.items(), key=lambda x: -len(x[1])
            )
        },
        "classification": classification,
    }

    # Print summary
    print(f"Total cards: {total}")
    print(f"\nClassification summary:")
    for cat, slugs in classification.items():
        pct = len(slugs) / total * 100 if total else 0
        print(f"  {cat}: {len(slugs)} ({pct:.1f}%)")

    if missing_mechanics_detail:
        print(f"\nMissing mechanics breakdown:")
        for mechanic, slugs in sorted(
            missing_mechanics_detail.items(), key=lambda x: -len(x[1])
        ):
            print(f"  {mechanic}: {len(slugs)} cards")

    # Color dedup stats
    def base_name(slug):
        return re.sub(r"_(red|yellow|blue)$", "", slug)

    for cat in ("simple_db", "template_expandable", "complex_custom"):
        bases = set(base_name(s) for s in classification[cat])
        print(f"\n  {cat} unique implementations (after color dedup): {len(bases)}")

    if args.dry_run:
        print("\n[dry-run] Skipping file output.")
        return

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nClassification written to {args.output}")


if __name__ == "__main__":
    main()

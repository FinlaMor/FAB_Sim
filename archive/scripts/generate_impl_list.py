#!/usr/bin/env python3
"""Generate a prioritized list of cards needing implementation.

Outputs: cards_to_implement.txt — organized by difficulty tier, with color
variants collapsed (red/yellow/blue = one implementation).
"""
from __future__ import annotations
import sys, os, re, json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import msgpack

# ── Load slug index ──────────────────────────────────────────────────────
with open(ROOT / "card_data" / "slug_index.msgpack", "rb") as f:
    raw = msgpack.unpackb(f.read(), raw=False)
slug_index = raw.get("by_slug", raw)

# ── Already-implemented slugs ────────────────────────────────────────────
triggers_src = (ROOT / "engine" / "card_effects" / "triggers.py").read_text("utf-8")
ext_src = (ROOT / "engine" / "card_effects" / "card_triggers_extended.py").read_text("utf-8")
ct_pat = re.compile(r'CARD_TRIGGERS\["([a-z0-9_]+)"\]')
reg_pat = re.compile(r'_register\("([a-z0-9_]+)"')
impl_slugs = set(ct_pat.findall(triggers_src)) | set(reg_pat.findall(ext_src)) | set(ct_pat.findall(ext_src))

from engine.card import Card
from engine.card_effects.text_trigger_parser import parse_functional_text

# ── Pattern detectors ────────────────────────────────────────────────────
ACTIVATED_RE = re.compile(r"\*\*(?:Action|Instant)\*\*\s*[-–—]\s*", re.I)
CHOOSE_RE = re.compile(r"\bchoose\b", re.I)
FOR_EACH_RE = re.compile(r"\bfor each\b", re.I)
INSTEAD_RE = re.compile(r"\binstead\b", re.I)
SEARCH_RE = re.compile(r"\b(?:search|look at the top|reveal)\b", re.I)
TRANSFORM_RE = re.compile(r"\b(?:transform|transcend|graft|flip)\b", re.I)
PUT_INTO_PLAY_RE = re.compile(r"\bput .+ into play\b", re.I)
AT_START_RE = re.compile(r"\bat the (?:start|beginning) of", re.I)
ONCE_PER_TURN_RE = re.compile(r"\bonce per turn\b", re.I)
TARGET_RE = re.compile(r"\btarget\b", re.I)
COUNTER_RE = re.compile(r"\bcounters?\b", re.I)
DESTROY_RE = re.compile(r"\bdestroy\b", re.I)
PLAY_FROM_RE = re.compile(r"\bplay .+ from (?:your )?(?:banish|graveyard|soul)", re.I)
RETURN_RE = re.compile(r"\breturn .+ from .+ to\b", re.I)
COPY_RE = re.compile(r"\bcopy\b", re.I)
NAME_CARD_RE = re.compile(r"\bname a card\b", re.I)
EXCHANGE_RE = re.compile(r"\bexchange\b", re.I)
YOU_MAY_RE = re.compile(r"\byou may\b", re.I)
COLOR_SUFFIX_RE = re.compile(r"_(red|yellow|blue)$")

SIMPLE_NEW_EFFECT_RE = re.compile(
    r"(?:gain \d+ \{r\}|put .+ on (?:top|bottom) of|shuffle .+ into|"
    r"banish .+ from your|return .+ from your graveyard to your hand|"
    r"prevent the next \d+ damage|put .+ counter)", re.I
)


def classify_difficulty(ft: str, types: list, kws: list) -> tuple[str, list[str]]:
    """Return (tier, [reason_tags]) for an unimplemented card."""
    tags = []
    for pat, tag in [
        (ACTIVATED_RE, "activated_ability"), (CHOOSE_RE, "choose"),
        (FOR_EACH_RE, "for_each"), (INSTEAD_RE, "replacement_effect"),
        (SEARCH_RE, "search_reveal"), (TRANSFORM_RE, "transform"),
        (PUT_INTO_PLAY_RE, "put_into_play"), (AT_START_RE, "start_of_turn"),
        (ONCE_PER_TURN_RE, "once_per_turn"), (TARGET_RE, "targeting"),
        (PLAY_FROM_RE, "play_from_zone"), (RETURN_RE, "return_to_zone"),
        (COPY_RE, "copy"), (NAME_CARD_RE, "name_card"),
        (EXCHANGE_RE, "exchange"), (YOU_MAY_RE, "you_may"),
        (COUNTER_RE, "counters"), (DESTROY_RE, "destroy"),
    ]:
        if pat.search(ft):
            tags.append(tag)

    hard_tags = {"transform", "copy", "name_card", "exchange", "put_into_play"}
    med_tags = {"activated_ability", "choose", "for_each", "replacement_effect",
                "search_reveal", "targeting", "play_from_zone"}

    if tags and hard_tags & set(tags):
        return "HARD", tags
    if len(tags) >= 3:
        return "HARD", tags
    if tags and med_tags & set(tags):
        return "MEDIUM", tags
    if tags:
        return "EASY", tags
    if SIMPLE_NEW_EFFECT_RE.search(ft):
        return "EASY", ["new_effect_primitive"]
    return "MEDIUM", ["unrecognized_pattern"]


# ── Collect unimplemented cards ──────────────────────────────────────────
needs_impl = []
for slug, cd in sorted(slug_index.items()):
    ft = cd.get("functional_text") or cd.get("functionalText") or ""
    if not ft.strip():
        continue
    if slug in impl_slugs:
        continue

    kws = cd.get("keywords") or cd.get("ability_keywords") or []
    types = cd.get("types") or cd.get("card_type") or []
    if isinstance(types, str):
        types = [types]
    name = cd.get("name") or cd.get("card_name") or slug
    subtypes = cd.get("subtypes") or []

    try:
        c = Card(slug=slug, name=name, base_functional_text=ft, types=types,
                 subtypes=subtypes, keywords=kws)
        if parse_functional_text(c):
            continue
    except Exception:
        pass

    tier, tags = classify_difficulty(ft, types, kws)
    needs_impl.append({
        "slug": slug, "name": name, "types": types,
        "keywords": kws, "functional_text": ft,
        "subtypes": subtypes, "tier": tier, "tags": tags,
        "base_slug": COLOR_SUFFIX_RE.sub("", slug),
    })

# ── Group color variants ─────────────────────────────────────────────────
base_groups: dict[str, list[dict]] = defaultdict(list)
for c in needs_impl:
    base_groups[c["base_slug"]].append(c)

# Use first variant's data as the representative
card_groups: list[dict] = []
for base_slug, variants in sorted(base_groups.items()):
    rep = variants[0]  # representative
    slugs = sorted(v["slug"] for v in variants)
    card_groups.append({
        "base_slug": base_slug,
        "slugs": slugs,
        "name": rep["name"],
        "types": rep["types"],
        "keywords": rep["keywords"],
        "functional_text": rep["functional_text"],
        "tier": rep["tier"],
        "tags": rep["tags"],
        "variant_count": len(variants),
    })

# ── Stats ────────────────────────────────────────────────────────────────
tier_counts = defaultdict(int)
tag_counts = defaultdict(int)
type_counts = defaultdict(int)
for cg in card_groups:
    tier_counts[cg["tier"]] += 1
    for t in cg["tags"]:
        tag_counts[t] += 1
    primary_type = cg["types"][0] if cg["types"] else "Unknown"
    type_counts[primary_type] += 1

# ── Build output ─────────────────────────────────────────────────────────
L = []  # output lines

L.append("=" * 80)
L.append("CARDS TO IMPLEMENT")
L.append(f"Generated: 2026-04-01")
L.append(f"")
L.append(f"Total unimplemented slugs : {len(needs_impl)}")
L.append(f"Unique cards (color-collapsed) : {len(card_groups)}")
L.append(f"Color variants (free once base done): {len(needs_impl) - len(card_groups)}")
L.append(f"Already implemented              : {4560 - len(needs_impl)} / 4560 "
         f"({(4560 - len(needs_impl))/4560*100:.1f}%)")
L.append("=" * 80)

L.append("")
L.append("DIFFICULTY BREAKDOWN (unique cards):")
for tier in ["EASY", "MEDIUM", "HARD"]:
    L.append(f"  {tier:<10s} {tier_counts[tier]:>5d}")
L.append(f"  {'TOTAL':<10s} {len(card_groups):>5d}")

L.append("")
L.append("BY CARD TYPE:")
for typ, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
    L.append(f"  {typ:<30s} {cnt:>5d}")

L.append("")
L.append("BY MECHANIC TAG (cards can have multiple):")
for tag, cnt in sorted(tag_counts.items(), key=lambda x: -x[1]):
    L.append(f"  {tag:<30s} {cnt:>5d}")

# ── Per-tier card lists ──────────────────────────────────────────────────
for tier in ["EASY", "MEDIUM", "HARD"]:
    tier_cards = [cg for cg in card_groups if cg["tier"] == tier]
    L.append("")
    L.append("=" * 80)
    L.append(f"  {tier} TIER — {len(tier_cards)} unique cards")
    L.append("=" * 80)

    # Group by primary type
    by_type: dict[str, list[dict]] = defaultdict(list)
    for cg in tier_cards:
        primary = cg["types"][0] if cg["types"] else "Unknown"
        by_type[primary].append(cg)

    for typ in sorted(by_type.keys()):
        type_cards = by_type[typ]
        L.append("")
        L.append(f"  [{typ}] ({len(type_cards)} cards)")
        L.append(f"  {'-' * 70}")

        for cg in sorted(type_cards, key=lambda x: x["base_slug"]):
            tag_str = ", ".join(cg["tags"])
            variant_note = ""
            if cg["variant_count"] > 1:
                variant_note = f"  ({cg['variant_count']} variants: {', '.join(cg['slugs'])})"
            L.append(f"    {cg['base_slug']}")
            L.append(f"      Name: {cg['name']}{variant_note}")
            L.append(f"      Tags: {tag_str}")
            ft_preview = cg["functional_text"].replace("\n", " | ")
            if len(ft_preview) > 200:
                ft_preview = ft_preview[:197] + "..."
            L.append(f"      Text: {ft_preview}")
            L.append("")

output = "\n".join(L)
out_path = ROOT / "cards_to_implement.txt"
out_path.write_text(output, encoding="utf-8")
print(f"Wrote {out_path}")
print(f"  {len(needs_impl)} slugs → {len(card_groups)} unique cards")
print()
print("DIFFICULTY BREAKDOWN (unique cards):")
for tier in ["EASY", "MEDIUM", "HARD"]:
    print(f"  {tier:<10s} {tier_counts[tier]:>5d}")
print(f"  {'TOTAL':<10s} {len(card_groups):>5d}")
print()
print("TOP MECHANIC TAGS:")
for tag, cnt in sorted(tag_counts.items(), key=lambda x: -x[1])[:15]:
    print(f"  {tag:<30s} {cnt:>5d}")

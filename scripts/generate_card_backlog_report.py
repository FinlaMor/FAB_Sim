#!/usr/bin/env python3
"""Generate a card implementation backlog report from slug_index.

Outputs:
  - docs/reports/card_backlog_report.md
  - docs/reports/card_backlog_report.csv
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import msgpack

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card, CardDB
from engine.deck import load_deck
from engine.card_effects import registry as registry_mod
from engine.card_effects import triggers as triggers_mod
from engine.card_effects.text_trigger_parser import parse_functional_text

SLUG_INDEX_MSGPACK = ROOT / "card_data" / "slug_index.msgpack"
DECKS_DIR = ROOT / "decks" / "generated"
REPORT_DIR = ROOT / "docs" / "reports"
REPORT_MD = REPORT_DIR / "card_backlog_report.md"
REPORT_CSV = REPORT_DIR / "card_backlog_report.csv"

COLOR_SUFFIX_RE = re.compile(r"_(red|yellow|blue)$")
WORDS_RE = re.compile(r"[a-z0-9]+")


@dataclass
class CardGroup:
    base_slug: str
    slugs: list[str]
    name: str
    types: list[str]
    sets: list[str]
    legal_heroes: list[str]
    legal_formats: list[str]
    keywords: list[str]
    has_functional_text: bool
    parseable_by_text_parser: bool
    implemented_by_registry: bool
    implemented_by_manual_trigger: bool
    in_generated_decks: bool
    priority_tier: str
    priority_score: int
    implementation_bucket: str


def _load_slug_index(path: Path) -> dict[str, dict]:
    with path.open("rb") as f:
        data = msgpack.unpack(f, raw=False)
    return data.get("by_slug", {})


def _slug_keyed_maps(mod) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    mod_vars = vars(mod)
    for name, value in mod_vars.items():
        if not (name.isupper() and isinstance(value, dict)):
            continue
        keys = {k for k in value.keys() if isinstance(k, str)}
        if keys:
            out[name] = keys
    return out


def _normalize_base_slug(slug: str) -> str:
    return COLOR_SUFFIX_RE.sub("", slug)


def _normalize_name_token(s: str) -> str:
    return "".join(ch.lower() for ch in s if ch.isalnum() or ch == " ")


def _deck_slug_candidates(card_name: str) -> set[str]:
    """Approximate possible slug names from a deck line name."""
    low = _normalize_name_token(card_name).replace(" ", "_")
    low = low.replace("__", "_")
    candidates = {low}
    for suffix in ("_red", "_yellow", "_blue"):
        candidates.add(f"{low}{suffix}")
    return candidates


def _cards_in_generated_decks(deck_dir: Path) -> tuple[set[str], set[str]]:
    if not deck_dir.exists():
        return set(), set()
    found_exact: set[str] = set()
    found_base: set[str] = set()
    card_db = CardDB(str(SLUG_INDEX_MSGPACK))
    for deck_path in sorted(deck_dir.glob("*.txt")):
        try:
            deck = load_deck(str(deck_path), card_db)
        except Exception:
            # Fallback to loose text parsing for malformed deck files.
            for raw in deck_path.read_text(encoding="utf-8").splitlines():
                m = re.match(r"^\s*(\d+)x\s+(.+?)(?:\s+\((red|yellow|blue)\))?\s*$", raw.strip(), re.I)
                if not m:
                    continue
                _, name, color = m.groups()
                cands = _deck_slug_candidates(name)
                if color:
                    cands = {_normalize_base_slug(c) + f"_{color.lower()}" for c in cands}
                found_exact.update(cands)
                found_base.update({_normalize_base_slug(c) for c in cands})
            continue

        hero = deck.get("hero")
        if hero:
            found_exact.add(hero)
            found_base.add(_normalize_base_slug(hero))
        for w in deck.get("weapons", []):
            if w:
                found_exact.add(w)
                found_base.add(_normalize_base_slug(w))
        for e in (deck.get("equipment") or {}).values():
            if e:
                found_exact.add(e)
                found_base.add(_normalize_base_slug(e))
        for c in deck.get("cards", []):
            if c:
                found_exact.add(c)
                found_base.add(_normalize_base_slug(c))
    return found_exact, found_base


def _text_parseable(slug: str, card_data: dict) -> bool:
    functional_text = (card_data.get("functionalText") or card_data.get("functional_text") or "").strip()
    if not functional_text:
        return False
    card = Card(
        slug=slug,
        raw_name=card_data.get("name") or slug,
        raw_types=card_data.get("types") or [],
        raw_subtypes=card_data.get("subtypes") or [],
        raw_card_keywords=card_data.get("keywords") or card_data.get("card_keywords") or [],
        raw_functional_text=functional_text,
        raw_type_text=card_data.get("typeText") or card_data.get("type_text"),
    )
    try:
        parsed = parse_functional_text(card)
    except Exception:
        return False
    return bool(parsed)


def _priority_score(
    *,
    in_generated_decks: bool,
    parseable: bool,
    has_text: bool,
    has_keywords: bool,
    is_token: bool,
    implemented: bool,
) -> int:
    if implemented:
        return -1
    score = 0
    if in_generated_decks:
        score += 100
    if has_text:
        score += 30
    if parseable:
        score += 25
    if not has_keywords and has_text:
        score += 15
    if is_token:
        score -= 10
    return score


def _priority_tier(score: int) -> str:
    if score >= 110:
        return "P0"
    if score >= 60:
        return "P1"
    if score >= 25:
        return "P2"
    return "P3"


def _impl_bucket(
    implemented: bool,
    parseable: bool,
    has_text: bool,
    has_keywords: bool,
) -> str:
    if implemented:
        return "implemented"
    if parseable:
        return "template_expandable"
    if has_text and not has_keywords:
        return "manual_custom"
    if has_text:
        return "manual_or_keyword_gap"
    return "vanilla_or_keyword_only"


def _format_list(items: Iterable[str], limit: int = 8) -> str:
    uniq = sorted({x for x in items if x})
    if len(uniq) <= limit:
        return ", ".join(uniq) if uniq else "—"
    return ", ".join(uniq[:limit]) + f", +{len(uniq)-limit} more"


def generate_report() -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    by_slug = _load_slug_index(SLUG_INDEX_MSGPACK)
    all_slugs = set(by_slug.keys())

    registry_maps = _slug_keyed_maps(registry_mod)
    trigger_maps = _slug_keyed_maps(triggers_mod)

    registry_covered = set().union(*(v for v in registry_maps.values())) & all_slugs
    manual_trigger_covered = trigger_maps.get("CARD_TRIGGERS", set()) & all_slugs
    all_covered = (registry_covered | manual_trigger_covered) & all_slugs

    deck_exact_slugs, deck_base_slugs = _cards_in_generated_decks(DECKS_DIR)

    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for slug, card in by_slug.items():
        groups[_normalize_base_slug(slug)].append((slug, card))

    report_rows: list[CardGroup] = []

    for base_slug, variants in sorted(groups.items()):
        slugs = sorted(s for s, _ in variants)
        rep_slug, rep = variants[0]
        rep_types = rep.get("types") or []
        rep_sets = rep.get("sets") or []
        rep_heroes = rep.get("legalHeroes") or rep.get("legal_heroes") or []
        rep_formats = rep.get("legalFormats") or rep.get("legal_formats") or []
        rep_keywords = rep.get("keywords") or rep.get("card_keywords") or []

        has_text = any((c.get("functionalText") or c.get("functional_text") or "").strip() for _, c in variants)
        parseable = any(_text_parseable(s, c) for s, c in variants if (c.get("functionalText") or c.get("functional_text")))

        implemented_by_registry = any(s in registry_covered for s in slugs)
        implemented_by_manual_trigger = any(s in manual_trigger_covered for s in slugs)
        implemented = implemented_by_registry or implemented_by_manual_trigger

        in_generated_decks = any(s in deck_exact_slugs for s in slugs) or (base_slug in deck_base_slugs)
        is_token = "Token" in rep_types

        score = _priority_score(
            in_generated_decks=in_generated_decks,
            parseable=parseable,
            has_text=has_text,
            has_keywords=bool(rep_keywords),
            is_token=is_token,
            implemented=implemented,
        )
        tier = _priority_tier(score)
        bucket = _impl_bucket(
            implemented=implemented,
            parseable=parseable,
            has_text=has_text,
            has_keywords=bool(rep_keywords),
        )

        report_rows.append(
            CardGroup(
                base_slug=base_slug,
                slugs=slugs,
                name=rep.get("name") or rep_slug,
                types=rep_types,
                sets=rep_sets,
                legal_heroes=rep_heroes,
                legal_formats=rep_formats,
                keywords=rep_keywords,
                has_functional_text=has_text,
                parseable_by_text_parser=parseable,
                implemented_by_registry=implemented_by_registry,
                implemented_by_manual_trigger=implemented_by_manual_trigger,
                in_generated_decks=in_generated_decks,
                priority_tier=tier,
                priority_score=score,
                implementation_bucket=bucket,
            )
        )

    remaining_rows = [r for r in report_rows if r.implementation_bucket != "implemented"]
    remaining_rows.sort(key=lambda r: (-r.priority_score, r.base_slug))

    # CSV output
    with REPORT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "base_slug",
                "variant_slugs",
                "name",
                "types",
                "sets",
                "legal_heroes",
                "legal_formats",
                "keywords",
                "implemented_by_registry",
                "implemented_by_manual_trigger",
                "has_functional_text",
                "parseable_by_text_parser",
                "in_generated_decks",
                "priority_tier",
                "priority_score",
                "implementation_bucket",
            ]
        )
        for row in remaining_rows:
            writer.writerow(
                [
                    row.base_slug,
                    "|".join(row.slugs),
                    row.name,
                    "|".join(row.types),
                    "|".join(row.sets),
                    "|".join(row.legal_heroes),
                    "|".join(row.legal_formats),
                    "|".join(row.keywords),
                    row.implemented_by_registry,
                    row.implemented_by_manual_trigger,
                    row.has_functional_text,
                    row.parseable_by_text_parser,
                    row.in_generated_decks,
                    row.priority_tier,
                    row.priority_score,
                    row.implementation_bucket,
                ]
            )

    # Markdown summary output
    total_groups = len(report_rows)
    total_remaining = len(remaining_rows)
    bucket_counts = Counter(r.implementation_bucket for r in remaining_rows)
    tier_counts = Counter(r.priority_tier for r in remaining_rows)
    type_counts = Counter((r.types[0] if r.types else "Unknown") for r in remaining_rows)
    set_counts = Counter((r.sets[0] if r.sets else "Unknown") for r in remaining_rows)
    hero_counts = Counter(h for r in remaining_rows for h in r.legal_heroes)

    p0 = [r for r in remaining_rows if r.priority_tier == "P0"][:150]
    p1 = [r for r in remaining_rows if r.priority_tier == "P1"][:150]

    lines: list[str] = []
    lines.append("# Card Backlog Report")
    lines.append("")
    lines.append("Generated by `scripts/generate_card_backlog_report.py`.")
    lines.append("")
    lines.append("## Coverage Summary")
    lines.append("")
    lines.append(f"- Total slugs in `slug_index`: **{len(all_slugs)}**")
    lines.append(f"- Unique color-collapsed card groups: **{total_groups}**")
    lines.append(f"- Remaining groups (not explicitly covered): **{total_remaining}**")
    lines.append(f"- Covered by registry maps (slug-keyed): **{len(registry_covered)}**")
    lines.append(f"- Covered by manual triggers (`CARD_TRIGGERS`): **{len(manual_trigger_covered)}**")
    lines.append("")
    lines.append("## Remaining by Implementation Bucket")
    lines.append("")
    for bucket, count in sorted(bucket_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- `{bucket}`: **{count}**")
    lines.append("")
    lines.append("## Remaining by Priority Tier")
    lines.append("")
    for tier in ("P0", "P1", "P2", "P3"):
        lines.append(f"- `{tier}`: **{tier_counts.get(tier, 0)}**")
    lines.append("")
    lines.append("## Top Remaining by Primary Type")
    lines.append("")
    for typ, count in type_counts.most_common(20):
        lines.append(f"- `{typ}`: **{count}**")
    lines.append("")
    lines.append("## Top Remaining by Set")
    lines.append("")
    for set_name, count in set_counts.most_common(20):
        lines.append(f"- `{set_name}`: **{count}**")
    lines.append("")
    lines.append("## Top Remaining by Legal Hero")
    lines.append("")
    for hero, count in hero_counts.most_common(20):
        lines.append(f"- `{hero}`: **{count}**")
    lines.append("")

    def _append_priority_block(title: str, rows: list[CardGroup]) -> None:
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| base_slug | name | types | set | legal heroes | bucket | score |")
        lines.append("|---|---|---|---|---|---:|---:|")
        for r in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{r.base_slug}`",
                        r.name.replace("|", "/"),
                        _format_list(r.types, 3).replace("|", "/"),
                        _format_list(r.sets, 2).replace("|", "/"),
                        _format_list(r.legal_heroes, 4).replace("|", "/"),
                        f"`{r.implementation_bucket}`",
                        str(r.priority_score),
                    ]
                )
                + " |"
            )
        lines.append("")

    _append_priority_block("P0 Queue (highest priority)", p0)
    _append_priority_block("P1 Queue", p1)

    lines.append("## Artifacts")
    lines.append("")
    lines.append(f"- Markdown report: `{REPORT_MD.relative_to(ROOT)}`")
    lines.append(f"- CSV report: `{REPORT_CSV.relative_to(ROOT)}`")
    lines.append("")

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")

    return REPORT_MD, REPORT_CSV


def main() -> None:
    md_path, csv_path = generate_report()
    print(md_path)
    print(csv_path)


if __name__ == "__main__":
    main()

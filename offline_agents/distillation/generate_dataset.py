"""
generate_dataset.py — Distillation: use Claude to generate training Q&A pairs from ref/ docs.

This script calls the Anthropic API to generate high-quality question/answer pairs
from every rules doc and every card in card_data/slug_index.json. The output is a
JSONL file of {"messages": [...]} records ready for torchtune.

Run:
    python -m offline_agents.distillation.generate_dataset
    python -m offline_agents.distillation.generate_dataset --rules-only
    python -m offline_agents.distillation.generate_dataset --cards-only
    python -m offline_agents.distillation.generate_dataset --resume   # skip already-done slugs

Outputs:
    offline_agents/distillation/data/rules_train.jsonl
    offline_agents/distillation/data/cards_train.jsonl
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time
import textwrap
from typing import Iterator

import anthropic

ROOT = pathlib.Path(__file__).resolve().parents[2]
REF_DIR = ROOT / "ref"
CARD_JSON = ROOT / "card_data" / "slug_index.json"
OUT_DIR = pathlib.Path(__file__).parent / "data"
OUT_DIR.mkdir(exist_ok=True)

RULES_OUT = OUT_DIR / "rules_train.jsonl"
CARDS_OUT = OUT_DIR / "cards_train.jsonl"

MODEL = "claude-haiku-4-5-20251001"   # cheapest capable model for distillation
CHUNK_SIZE = 1500                      # characters per rules chunk sent to Claude
QA_PER_CHUNK = 3                       # Q&A pairs to generate per chunk
CARDS_PER_BATCH = 10                   # cards per API call (batched for cost efficiency)
DELAY = 0.3                            # seconds between API calls (rate limit safety)

CLIENT = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        end = start + size
        if end < len(text):
            nl = text.rfind("\n", start, end)
            if nl > start + 200:
                end = nl
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - 100
    return chunks


def _call(system: str, user: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            msg = CLIENT.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return msg.content[0].text
        except anthropic.RateLimitError:
            wait = 2 ** attempt * 5
            print(f"  Rate limit — waiting {wait}s", file=sys.stderr)
            time.sleep(wait)
        except Exception as e:
            print(f"  API error: {e}", file=sys.stderr)
            if attempt == retries - 1:
                raise
            time.sleep(2)
    return ""


def _parse_qa_json(raw: str) -> list[dict]:
    """Extract JSON array from model output."""
    m = re.search(r'\[.*\]', raw, re.DOTALL)
    if not m:
        return []
    try:
        pairs = json.loads(m.group())
        return [p for p in pairs if isinstance(p, dict) and "question" in p and "answer" in p]
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# Rules distillation
# ---------------------------------------------------------------------------

RULES_SYSTEM = """You are an expert Flesh and Blood TCG rules teacher. Given a passage from the official Comprehensive Rules, generate {n} diverse question-and-answer pairs that test understanding of the rules in that passage.

Output ONLY a JSON array with this exact structure:
[
  {{"question": "...", "answer": "..."}},
  ...
]

Rules for generating pairs:
- Questions should be specific (mention card names, CR section numbers, exact conditions)
- Answers should be complete and cite the rule
- Cover edge cases, timing, and interaction questions
- Do NOT ask trivially obvious questions"""


def generate_rules_dataset(resume: bool = False) -> None:
    existing_ids: set[str] = set()
    if resume and RULES_OUT.exists():
        with RULES_OUT.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    existing_ids.add(rec.get("_id", ""))
                except Exception:
                    pass
        print(f"Resuming: {len(existing_ids)} existing rules examples")

    with RULES_OUT.open("a", encoding="utf-8") as out:
        for txt_file in sorted(REF_DIR.glob("*.txt")):
            text = txt_file.read_text(encoding="utf-8", errors="replace")
            chunks = _chunk_text(text)
            print(f"{txt_file.name}: {len(chunks)} chunks")
            for i, chunk in enumerate(chunks):
                chunk_id = f"{txt_file.stem}_{i}"
                if chunk_id in existing_ids:
                    continue
                system = RULES_SYSTEM.format(n=QA_PER_CHUNK)
                user = f"Rules passage:\n\n{chunk}"
                raw = _call(system, user)
                pairs = _parse_qa_json(raw)
                for qa in pairs:
                    record = {
                        "_id": chunk_id,
                        "_source": txt_file.name,
                        "messages": [
                            {"role": "system", "content": "You are an expert Flesh and Blood TCG rules enforcer with deep knowledge of the Comprehensive Rules."},
                            {"role": "user", "content": qa["question"]},
                            {"role": "assistant", "content": qa["answer"]},
                        ]
                    }
                    out.write(json.dumps(record) + "\n")
                out.flush()
                time.sleep(DELAY)
                if (i + 1) % 20 == 0:
                    print(f"  ... {i+1}/{len(chunks)} chunks done")


# ---------------------------------------------------------------------------
# Card distillation
# ---------------------------------------------------------------------------

CARDS_SYSTEM = """You are an expert Flesh and Blood TCG card implementation validator. Given official card data, generate question-and-answer pairs that test whether a Python implementation correctly captures the card's rules.

Output ONLY a JSON array:
[
  {{"question": "...", "answer": "..."}},
  ...
]

Include questions about:
- Exact trigger conditions and timing
- Whether effects are optional or mandatory
- Correct numeric values (damage, cost, draw count)
- Interaction with other keywords
- Edge cases (empty zones, multiple instances, etc.)"""


def _cards_to_text(cards: list[tuple[str, dict]]) -> str:
    lines = []
    for slug, data in cards:
        lines.append(f"--- {slug} ---")
        lines.append(f"Name: {data.get('name', slug)}")
        lines.append(f"Types: {', '.join(data.get('types', []))}")
        for f in ("pitch", "cost", "power", "defense", "arcane"):
            v = data.get(f)
            if v:
                lines.append(f"{f.title()}: {v}")
        kws = (data.get("card_keywords") or []) + (data.get("ability_and_effect_keywords") or [])
        if kws:
            lines.append(f"Keywords: {', '.join(kws)}")
        fx = data.get("functional_text", "")
        if fx:
            lines.append(f"Text: {fx}")
        lines.append("")
    return "\n".join(lines)


def generate_cards_dataset(resume: bool = False) -> None:
    data = json.loads(CARD_JSON.read_text(encoding="utf-8"))
    by_slug: dict = data.get("by_slug", data)
    slugs = list(by_slug.keys())

    existing_ids: set[str] = set()
    if resume and CARDS_OUT.exists():
        with CARDS_OUT.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    existing_ids.add(rec.get("_id", ""))
                except Exception:
                    pass
        print(f"Resuming: {len(existing_ids)} existing card batches")

    # Only process cards with functional text (the rest are uninteresting for implementation)
    slugs_with_text = [s for s in slugs if by_slug[s].get("functional_text", "").strip()]
    print(f"{len(slugs_with_text)} cards with functional text (out of {len(slugs)})")

    with CARDS_OUT.open("a", encoding="utf-8") as out:
        for batch_start in range(0, len(slugs_with_text), CARDS_PER_BATCH):
            batch_slugs = slugs_with_text[batch_start:batch_start + CARDS_PER_BATCH]
            batch_id = f"cards_{batch_start}"
            if batch_id in existing_ids:
                continue
            batch = [(s, by_slug[s]) for s in batch_slugs]
            cards_text = _cards_to_text(batch)
            raw = _call(CARDS_SYSTEM, f"Cards:\n\n{cards_text}")
            pairs = _parse_qa_json(raw)
            for qa in pairs:
                record = {
                    "_id": batch_id,
                    "messages": [
                        {"role": "system", "content": "You are an expert Flesh and Blood TCG card implementation validator."},
                        {"role": "user", "content": qa["question"]},
                        {"role": "assistant", "content": qa["answer"]},
                    ]
                }
                out.write(json.dumps(record) + "\n")
            out.flush()
            time.sleep(DELAY)
            if (batch_start // CARDS_PER_BATCH + 1) % 20 == 0:
                done = batch_start + CARDS_PER_BATCH
                print(f"  ... {done}/{len(slugs_with_text)} cards done")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def merge_datasets() -> None:
    """Merge rules + cards into a single combined_train.jsonl, stripping _id/_source."""
    combined = OUT_DIR / "combined_train.jsonl"
    n = 0
    with combined.open("w", encoding="utf-8") as out:
        for src in (RULES_OUT, CARDS_OUT):
            if not src.exists():
                continue
            with src.open(encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        clean = {"messages": rec["messages"]}
                        out.write(json.dumps(clean) + "\n")
                        n += 1
                    except Exception:
                        pass
    print(f"Merged {n} examples → {combined}")


if __name__ == "__main__":
    args = sys.argv[1:]
    resume = "--resume" in args
    rules_only = "--rules-only" in args
    cards_only = "--cards-only" in args

    if not cards_only:
        print("=== Generating rules Q&A dataset ===")
        generate_rules_dataset(resume=resume)
    if not rules_only:
        print("=== Generating cards Q&A dataset ===")
        generate_cards_dataset(resume=resume)

    print("=== Merging datasets ===")
    merge_datasets()
    print("Done.")

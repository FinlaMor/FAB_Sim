"""
validator.py — Validate card test gamestates via the fab-rules-validator agent.

Reads card_test_gamestates from the SQLite DB, batches them, calls
'claude -p' with a validation prompt, parses JSON results, and updates
the validation_result column for each card.

Usage:
    python -m data.card_test_gamestates.validator
    python -m data.card_test_gamestates.validator --batch-size 5 --limit 50
    python -m data.card_test_gamestates.validator --slug "pummel-red"
    python -m data.card_test_gamestates.validator --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field

from data.card_test_gamestates.db import (
    get_all_gamestates,
    get_db,
    get_gamestate,
    get_status_counts,
    init_db,
    update_validation_result,
)

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 10
DEFAULT_DELAY = 1.0  # seconds between API calls
MAX_RETRIES = 3
BACKOFF_BASE = 2.0  # exponential backoff base in seconds


@dataclass
class ValidationStats:
    """Tracks validation run statistics."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    batches_sent: int = 0
    retries: int = 0

    def summary(self) -> str:
        return (
            f"Validation complete: {self.total} cards processed — "
            f"{self.passed} passed, {self.failed} failed, "
            f"{self.errors} errors, {self.skipped} skipped "
            f"({self.batches_sent} batches, {self.retries} retries)"
        )


@dataclass
class CardRecord:
    """A lightweight holder for a DB row relevant to validation."""

    card_slug: str
    card_name: str
    original_gamestate: str
    post_gamestate: str


def _build_validation_prompt(cards: list[CardRecord]) -> str:
    """Construct a prompt asking fab-rules-validator to check state transitions."""
    card_blocks: list[str] = []
    for i, card in enumerate(cards, 1):
        card_blocks.append(
            f"### Card {i}: {card.card_slug} ({card.card_name})\n"
            f"**Before GameState:**\n```json\n{card.original_gamestate}\n```\n"
            f"**After GameState:**\n```json\n{card.post_gamestate}\n```"
        )

    cards_section = "\n\n".join(card_blocks)

    return (
        "You are validating Flesh and Blood card game state transitions.\n"
        "For each card below, determine whether the before→after GameState "
        "transition is rules-compliant. Check that costs were correctly paid, "
        "effects were correctly applied, zones were updated properly, and no "
        "rules were violated.\n\n"
        f"{cards_section}\n\n"
        "Respond with ONLY a JSON object in this exact format:\n"
        "```json\n"
        "{\n"
        '  "results": [\n'
        "    {\n"
        '      "card_slug": "<slug>",\n'
        '      "pass": true | false,\n'
        '      "reason": "<brief explanation>"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "```\n"
        "Return one entry per card in the same order. No extra text outside the JSON."
    )


def _call_claude(prompt: str) -> dict:
    """Call 'claude -p' via subprocess and parse JSON response."""
    result = subprocess.run(
        ["claude", "-p", "--output-format", "json"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"claude process exited with code {result.returncode}: {result.stderr.strip()}"
        )

    # The response from claude --output-format json wraps output in a JSON envelope.
    # Parse the outer envelope first, then extract the actual content.
    raw = result.stdout.strip()
    if not raw:
        raise RuntimeError("Empty response from claude")

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse claude JSON envelope: {exc}") from exc

    # Extract the text content from the envelope
    content = envelope.get("result", raw) if isinstance(envelope, dict) else raw

    # The content may contain a JSON block — extract it
    if isinstance(content, str):
        # Try to find JSON in markdown code fences
        if "```json" in content:
            start = content.index("```json") + len("```json")
            end = content.index("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            content = content[start:end].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Failed to parse validation response JSON: {exc}\nContent: {content[:500]}"
            ) from exc

    if isinstance(content, dict):
        return content

    raise RuntimeError(f"Unexpected response format: {type(content)}")


class Validator:
    """Validates card test gamestates against FAB rules using the fab-rules-validator agent."""

    def __init__(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
        delay: float = DEFAULT_DELAY,
        dry_run: bool = False,
    ) -> None:
        self.batch_size = batch_size
        self.delay = delay
        self.dry_run = dry_run
        self.stats = ValidationStats()

    def _load_cards(
        self, limit: int | None = None, slug: str | None = None
    ) -> list[CardRecord]:
        """Load card records from DB for validation."""
        init_db()
        if slug:
            row = get_gamestate(slug)
            if row is None:
                logger.error("Card slug %r not found in database", slug)
                return []
            return [
                CardRecord(
                    card_slug=row["card_slug"],
                    card_name=row["card_name"],
                    original_gamestate=row["original_gamestate"],
                    post_gamestate=row["post_gamestate"],
                )
            ]

        rows = get_all_gamestates()
        cards = [
            CardRecord(
                card_slug=r["card_slug"],
                card_name=r["card_name"],
                original_gamestate=r["original_gamestate"],
                post_gamestate=r["post_gamestate"],
            )
            for r in rows
            if r["status"] != "validated"
        ]
        if limit is not None:
            cards = cards[:limit]
        return cards

    def _validate_batch(self, batch: list[CardRecord]) -> dict:
        """Send a batch to claude for validation, with retry logic."""
        prompt = _build_validation_prompt(batch)

        if self.dry_run:
            logger.info("[DRY RUN] Would send prompt (%d chars) for %d cards:", len(prompt), len(batch))
            for card in batch:
                logger.info("  - %s", card.card_slug)
            return {"results": []}

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                result = _call_claude(prompt)
                self.stats.batches_sent += 1
                return result
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                last_error = exc
                self.stats.retries += 1
                if attempt < MAX_RETRIES - 1:
                    wait = BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        "Batch failed (attempt %d/%d): %s — retrying in %.1fs",
                        attempt + 1, MAX_RETRIES, exc, wait,
                    )
                    time.sleep(wait)

        logger.error("Batch failed after %d retries: %s", MAX_RETRIES, last_error)
        return {"error": str(last_error), "results": []}

    def _apply_results(self, batch: list[CardRecord], response: dict) -> None:
        """Parse response and update DB with validation results."""
        results = response.get("results", [])

        # Build a lookup by slug
        result_map: dict[str, dict] = {}
        for r in results:
            slug = r.get("card_slug", "")
            result_map[slug] = r

        for card in batch:
            entry = result_map.get(card.card_slug)
            self.stats.total += 1

            if entry is None:
                self.stats.errors += 1
                update_validation_result(
                    card.card_slug,
                    json.dumps({"pass": False, "reason": "No result returned from validator"}),
                )
                continue

            passed = entry.get("pass", False)
            if passed:
                self.stats.passed += 1
            else:
                self.stats.failed += 1

            update_validation_result(card.card_slug, json.dumps(entry))

    def run(self, limit: int | None = None, slug: str | None = None) -> ValidationStats:
        """Execute the full validation run."""
        cards = self._load_cards(limit=limit, slug=slug)
        if not cards:
            logger.info("No cards to validate.")
            return self.stats

        total_cards = len(cards)
        logger.info("Starting validation of %d cards (batch_size=%d)", total_cards, self.batch_size)

        for i in range(0, total_cards, self.batch_size):
            batch = cards[i : i + self.batch_size]
            batch_num = i // self.batch_size + 1
            total_batches = (total_cards + self.batch_size - 1) // self.batch_size
            logger.info(
                "Processing batch %d/%d (%d cards)...",
                batch_num, total_batches, len(batch),
            )

            response = self._validate_batch(batch)

            if not self.dry_run:
                self._apply_results(batch, response)
            else:
                self.stats.total += len(batch)
                self.stats.skipped += len(batch)

            # Rate limiting between batches
            if i + self.batch_size < total_cards and self.delay > 0:
                time.sleep(self.delay)

        logger.info(self.stats.summary())
        return self.stats


def main() -> None:
    """CLI entry point for the validator."""
    parser = argparse.ArgumentParser(
        description="Validate card test gamestates against FAB rules",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"Number of cards per validation prompt (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Total number of cards to validate (default: all)",
    )
    parser.add_argument(
        "--slug", type=str, default=None,
        help="Validate a single card by slug",
    )
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY,
        help=f"Delay in seconds between API calls (default: {DEFAULT_DELAY})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show prompts without calling the API",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    validator = Validator(
        batch_size=args.batch_size,
        delay=args.delay,
        dry_run=args.dry_run,
    )
    stats = validator.run(limit=args.limit, slug=args.slug)

    # Print summary
    print(f"\n{'='*60}")
    print(stats.summary())
    print(f"{'='*60}")

    # Show DB status counts
    try:
        counts = get_status_counts()
        if counts:
            print("\nDatabase status breakdown:")
            for status, count in sorted(counts.items()):
                print(f"  {status}: {count}")
    except Exception:
        pass


if __name__ == "__main__":
    main()

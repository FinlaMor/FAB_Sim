"""
batch_runner.py — Batch-generate before/after GameState snapshots for every card.

Usage:
    python -m data.card_test_gamestates.batch_runner
    python -m data.card_test_gamestates.batch_runner --limit 10
    python -m data.card_test_gamestates.batch_runner --slug "some-card-slug"
    python -m data.card_test_gamestates.batch_runner --dry-run
    python -m data.card_test_gamestates.batch_runner --force
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import sys

import config
from data.card_test_gamestates.db import get_db, init_db, insert_gamestate
from data.card_test_gamestates.gamestate_factory import GameStateFactory, serialize_gamestate
from engine.card import CardDB, _derive_category
from engine.actions import legal_actions, Action, ActionType
from engine.engine import apply_action
from engine.state import GameState, Step

logger = logging.getLogger(__name__)

# Card types where automated play-through is not yet supported.
# Mentor and Figment are now supported via arsenal and hand placement respectively.
UNSUPPORTED_TYPES: set[str] = set()


def _load_slugs() -> list[dict]:
    """Load all card entries from slug_index.json.

    The index is a dict with a 'by_slug' key mapping slug -> card_data.
    Returns a flat list of dicts, each with a 'slug' key added.
    """
    with open(config.SLUG_INDEX_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    by_slug = raw.get("by_slug", raw) if isinstance(raw, dict) else {}
    entries = []
    for slug, data in by_slug.items():
        entry = dict(data) if isinstance(data, dict) else {}
        entry["slug"] = slug
        entries.append(entry)
    return entries


def _is_unsupported(card_entry: dict) -> bool:
    """Check if a card has types that are known unsupported."""
    types = card_entry.get("types", [])
    return bool(UNSUPPORTED_TYPES & set(types))


def _determine_status(
    before: dict, after: dict, error: Exception | None, unsupported: bool
) -> tuple[str, str]:
    """Determine (db_status, detail_status) for a card run.

    Returns:
        db_status: one of 'generated', 'failed' (matching schema CHECK constraint)
        detail_status: descriptive label for logging/error_message
    """
    if unsupported:
        return "failed", "unsupported"
    if error is not None:
        return "failed", "error"
    if before == after:
        return "generated", "no_effect"
    return "generated", "success"


def _apply_card_to_state(state: GameState, slug: str, card_db: CardDB) -> str | None:
    """Apply the card identified by *slug* to *state* using the local engine.

    Uses legal_actions() to find an action that plays *slug*, then calls
    apply_action() to mutate the state in-place.

    Returns:
        None on success, or an error string describing what went wrong.

    Engine integration notes
    ------------------------
    The engine's apply_action() is synchronous and mutates state in-place.
    legal_actions() enumerates every legal move for the current priority player
    in the current step.  We search that list for any action whose card matches
    the target slug and call apply_action() for the first match found.

    Supported action types: PLAY_CARD, PLAY_ATTACK_REACTION, PLAY_DEFENSE_REACTION,
    PLAY_ARSENAL, DEFEND_CARDS, ACTIVATE_ITEM, ACTIVATE_EQUIPMENT, ACTIVATE_WEAPON,
    ACTIVATE_HERO, DISCARD_ACTIVATE, PLAY_BANISH.

    If no matching legal action is found (e.g. cost cannot be paid, card type not
    yet modelled) the function records a descriptive engine_error and returns it so
    the caller can store it in the error_message column.
    """
    try:
        actions = legal_actions(state, card_db)
    except Exception as exc:
        return f"legal_actions error: {type(exc).__name__}: {exc}"

    # For DEFEND_CARDS the card appears in action.card_list, not action.card.
    target_action: Action | None = None
    for action in actions:
        if action.card is not None and action.card.slug == slug:
            target_action = action
            break
        if action.type == ActionType.DEFEND_CARDS and action.card_list:
            for c in action.card_list:
                if c.slug == slug:
                    target_action = action
                    break
        if target_action is not None:
            break

    if target_action is None:
        # Gather available card slugs to provide a useful diagnostic.
        available = sorted({
            a.card.slug for a in actions if a.card is not None
        })
        return (
            f"engine_error: no legal action found for '{slug}' "
            f"at step {state.step}. "
            f"Legal card slugs: {available[:20]}"
        )

    # apply_action requires player_id to be set (normally done by get_player_decision)
    target_action.player_id = state.priority_player

    try:
        apply_action(state, target_action)
    except Exception as exc:
        return f"apply_action error: {type(exc).__name__}: {exc}"

    return None


def run_batch(
    slugs: list[dict],
    factory: GameStateFactory,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    single_slug: str | None = None,
) -> dict[str, int]:
    """Process cards and insert before/after gamestates into the DB.

    Returns:
        Dict of detail_status -> count.
    """
    counts: dict[str, int] = {
        "success": 0,
        "no_effect": 0,
        "error": 0,
        "unsupported": 0,
    }

    # Filter to single slug if requested
    if single_slug:
        slugs = [e for e in slugs if e.get("slug") == single_slug]
        if not slugs:
            logger.warning("Slug '%s' not found in index", single_slug)
            return counts

    if limit is not None:
        slugs = slugs[:limit]

    total = len(slugs)
    logger.info("Processing %d cards...", total)

    card_db = factory._card_db

    for i, entry in enumerate(slugs, start=1):
        slug = entry.get("slug", "")
        name = entry.get("name", slug)
        types = entry.get("types", [])
        category = _derive_category(entry)

        error_msg: str | None = None
        before_json = "{}"
        after_json = "{}"
        is_unsupported = _is_unsupported(entry)

        if is_unsupported:
            db_status, detail = "failed", "unsupported"
            error_msg = f"Unsupported card type(s): {types}"
        else:
            try:
                state = factory.create_gamestate(slug)
                before_dict = serialize_gamestate(state)
                before_json = json.dumps(before_dict, default=str)

                # Deep-copy the state so we can mutate it without affecting
                # the original snapshot.
                after_state = copy.deepcopy(state)

                # Apply the card action to produce the real post-gamestate.
                engine_error = _apply_card_to_state(after_state, slug, card_db)
                if engine_error:
                    error_msg = engine_error

                after_dict = serialize_gamestate(after_state)
                after_json = json.dumps(after_dict, default=str)

                db_status, detail = _determine_status(
                    before_dict, after_dict, None, False
                )
            except Exception as exc:
                db_status, detail = "failed", "error"
                error_msg = f"{type(exc).__name__}: {exc}"

        counts[detail] += 1

        if dry_run:
            logger.debug("[DRY-RUN] %s -> %s", slug, detail)
        else:
            try:
                insert_gamestate(
                    card_slug=slug,
                    card_name=name,
                    card_types=json.dumps(types),
                    card_category=category,
                    original_gamestate=before_json,
                    post_gamestate=after_json,
                    status=db_status,
                    error_message=error_msg,
                )
            except Exception as exc:
                logger.error("DB insert failed for %s: %s", slug, exc)

        if i % 100 == 0 or i == total:
            logger.info("Processed %d/%d cards...", i, total)

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-generate card test gamestates."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Log what would happen without writing to DB")
    parser.add_argument("--slug", type=str, default=None,
                        help="Process a single card slug for debugging")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N cards")
    parser.add_argument("--force", action="store_true",
                        help="Reinitialize DB before run")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

    # Initialize DB
    if not args.dry_run:
        init_db(force=args.force)

    slugs = _load_slugs()
    factory = GameStateFactory()

    counts = run_batch(
        slugs,
        factory,
        dry_run=args.dry_run,
        limit=args.limit,
        single_slug=args.slug,
    )

    # Summary
    total = sum(counts.values())
    logger.info("=" * 50)
    logger.info("Batch complete. %d cards processed.", total)
    for status, count in sorted(counts.items()):
        logger.info("  %-15s %d", status, count)
    logger.info("=" * 50)


if __name__ == "__main__":
    main()

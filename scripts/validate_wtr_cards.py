"""
validate_wtr_cards.py — Run the verification pass over all existing WTR JSON card effect files.

Usage:
    python scripts/validate_wtr_cards.py              # validate all WTR JSON files
    python scripts/validate_wtr_cards.py --set arc    # validate a different set
    python scripts/validate_wtr_cards.py --slug foo   # validate a single card
    python scripts/validate_wtr_cards.py --fix        # write corrected JSON back to disk
    python scripts/validate_wtr_cards.py --model qwen3-coder:30b  # use specific model

Exits with non-zero if any card fails validation.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"

# Dynamically import helpers from auto_implement_wtr.py to avoid duplication
spec = importlib.util.spec_from_file_location(
    "auto_implement_wtr", SCRIPTS_DIR / "auto_implement_wtr.py"
)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

build_dsl_reference = _mod.build_dsl_reference
build_verification_prompt = _mod.build_verification_prompt
run_claw = _mod.run_claw
COMMON_MISTAKES = _mod.COMMON_MISTAKES


def load_queue(set_code: str) -> dict[str, dict]:
    queue_path = ROOT / "engine" / "card_effects" / "json" / set_code / f"{set_code}_work_queue.json"
    if not queue_path.exists():
        print(f"WARNING: work queue not found at {queue_path}")
        return {}
    with queue_path.open(encoding="utf-8") as f:
        items = json.load(f)
    return {item["slug"]: item for item in items}


def validate_card(card: dict, json_content: str, dsl_ref: str,
                  model: str | None, verbose: bool) -> tuple[str, str]:
    """Returns ('ok', '') or ('fail', corrected_json_or_empty)."""
    prompt = build_verification_prompt(card, json_content, dsl_ref)
    output = run_claw(prompt, verbose=verbose, model=model)

    if output in ("CLAW_TIMEOUT",) or output.startswith("CLAW_ERROR"):
        return "error", ""

    cleaned = re.sub(r"```(?:json)?\s*", "", output)
    cleaned = re.sub(r"```\s*", "", cleaned).strip()

    if cleaned.upper().startswith("LOOKS_GOOD"):
        return "ok", ""

    match = re.search(r"\{[\s\S]+\}", cleaned)
    if not match:
        return "unclear", ""

    try:
        corrected = json.loads(match.group())
        return "corrected", json.dumps(corrected, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return "invalid_json", ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate WTR card effect JSON files.")
    parser.add_argument("--set", default="wtr", dest="set_code")
    parser.add_argument("--slug", default=None)
    parser.add_argument("--fix", action="store_true", help="Write corrected JSON back to disk.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    json_dir = ROOT / "engine" / "card_effects" / "json" / args.set_code
    dsl_ref = build_dsl_reference()
    queue_by_slug = load_queue(args.set_code)

    json_files = sorted(json_dir.glob("*.json"))
    # Skip the work queue file itself
    json_files = [f for f in json_files if "work_queue" not in f.name]
    if args.slug:
        json_files = [f for f in json_files if f.stem == args.slug]

    total = len(json_files)
    print(f"Validating {total} cards in {json_dir.name}/\n")

    results: dict[str, list[str]] = {"ok": [], "corrected": [], "error": [], "unclear": [], "invalid_json": []}
    fixes_written = 0

    for i, json_path in enumerate(json_files, 1):
        slug = json_path.stem
        json_content = json_path.read_text(encoding="utf-8")

        card = queue_by_slug.get(slug, {"slug": slug, "functional_text": None, "name": slug})
        print(f"[{i}/{total}] {slug}  ", end="", flush=True)

        status, corrected = validate_card(card, json_content, dsl_ref,
                                          model=args.model, verbose=args.verbose)
        print(status.upper())

        results[status].append(slug)

        if status == "corrected" and args.fix:
            json_path.write_text(corrected, encoding="utf-8")
            fixes_written += 1
            print(f"  -> wrote corrected JSON to {json_path.name}")

    print(f"\n{'='*60}")
    print(f"RESULTS ({total} cards):")
    print(f"  OK:          {len(results['ok'])}")
    print(f"  CORRECTED:   {len(results['corrected'])}" + (" (written)" if args.fix else " (use --fix to apply)"))
    print(f"  ERROR:       {len(results['error'])}")
    print(f"  UNCLEAR:     {len(results['unclear'])}")
    print(f"  INVALID_JSON:{len(results['invalid_json'])}")
    if fixes_written:
        print(f"  Fixes written: {fixes_written}")

    if results["corrected"]:
        print(f"\nCards needing correction:")
        for slug in results["corrected"]:
            print(f"  {slug}")

    if results["error"] or results["unclear"] or results["invalid_json"]:
        print(f"\nCards with validation errors:")
        for slug in results["error"] + results["unclear"] + results["invalid_json"]:
            print(f"  {slug}")
        sys.exit(1)


if __name__ == "__main__":
    main()

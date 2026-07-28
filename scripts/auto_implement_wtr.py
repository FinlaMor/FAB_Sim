"""
auto_implement_wtr.py — Drive claw-code to batch-generate JSON effect files for FAB cards.

Usage:
    python scripts/auto_implement_wtr.py                       # process all pending WTR cards
    python scripts/auto_implement_wtr.py --set arc             # process ARC set
    python scripts/auto_implement_wtr.py --dry-run             # print first 3 prompts, no claw-code calls
    python scripts/auto_implement_wtr.py --limit 10            # process up to 10 pending cards
    python scripts/auto_implement_wtr.py --slug alpha_rampage_red  # process a specific slug only
    python scripts/auto_implement_wtr.py --reset-failed            # re-queue all "failed" cards

After each card:
- "done"         -> JSON written to engine/card_effects/json/{set}/{slug}.json
                   + pytest tests appended to tests/test_{set}_generated.py
- "needs_review" -> {slug}.md written to engine/card_effects/json/{set}/needs_review/
- "failed"       -> logged; queue entry kept as "failed" for manual retry

Queue state is saved after every card — re-running the script resumes automatically.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # so the load gate can import engine.* in-process
CLAW_DIR = Path(os.environ.get("CLAW_DIR", str(Path(__file__).resolve().parent.parent.parent / "claw-code")))
CLAW_ENTRY = CLAW_DIR / "src" / "launch_claw.py"

# LLM backend config (set in main()). BACKEND selects how prompts are run:
#   "openai" -> POST to an OpenAI-compatible /chat/completions endpoint (llama.cpp
#               llama-server, Ollama, LM Studio, etc.), model chosen per role.
#   "claw"   -> shell out to claw-code (legacy).
BACKEND = "openai"
BASE_URL = os.environ.get("FAB_LLM_BASE_URL", "http://localhost:11434/v1")
LLM_TIMEOUT = int(os.environ.get("FAB_LLM_TIMEOUT", "600"))

SET_CODE = "wtr"
WTR_DIR = ROOT / "engine" / "card_effects" / "json" / "wtr"
QUEUE_PATH = WTR_DIR / "wtr_work_queue.json"
REVIEW_DIR = WTR_DIR / "needs_review"
TEST_OUTPUT = ROOT / "tests" / "test_wtr_generated.py"

DSL_DIR = ROOT / "engine" / "card_effects" / "dsl"

# ---------------------------------------------------------------------------
# DSL reference extraction
# ---------------------------------------------------------------------------

def _extract_types_from_source(path: Path, pattern: str) -> list[str]:
    """Parse a DSL source file for quoted type identifiers matching `pattern`."""
    try:
        text = path.read_text(encoding="utf-8")
        return re.findall(pattern, text)
    except FileNotFoundError:
        return []


def build_dsl_reference() -> str:
    """Return a compact DSL reference string for injection into prompts."""
    effect_types = _extract_types_from_source(
        DSL_DIR / "effect_types.py",
        r'if etype == "([A-Z_]+)"'
    )
    condition_types = _extract_types_from_source(
        DSL_DIR / "condition_types.py",
        r'if ctype == "([A-Z_]+)"'
    )
    cost_types = _extract_types_from_source(
        DSL_DIR / "cost_types.py",
        r'if ctype == "([A-Z_]+)"'
    )
    trigger_types = _extract_types_from_source(
        DSL_DIR / "trigger_types.py",
        r'"(ON_[A-Z_]+|START_OF[A-Z_]+|END_OF[A-Z_]+)":'
    )
    ability_types = ["PLAY", "TRIGGERED", "ATTACK_REACTION", "DEFENSE_REACTION", "ACTIVATE", "STATIC"]

    lines = [
        "=== DSL REFERENCE ===",
        "",
        "ABILITY TYPES:",
        "  " + ", ".join(ability_types),
        "",
        "TRIGGER TYPES (for TRIGGERED abilities):",
        "  " + ", ".join(trigger_types),
        "",
        "EFFECT TYPES:",
        textwrap.fill("  " + ", ".join(effect_types), width=100, subsequent_indent="  "),
        "",
        "CONDITION TYPES:",
        textwrap.fill("  " + ", ".join(condition_types), width=100, subsequent_indent="  "),
        "",
        "COST TYPES (for additional_cost / alternative_cost):",
        textwrap.fill("  " + ", ".join(cost_types), width=100, subsequent_indent="  "),
        "",
        "ADDITIONAL COSTS vs ALTERNATIVE COSTS — CRITICAL DISTINCTION:",
        "  additional_cost: MANDATORY extra cost that BLOCKS play if unpayable.",
        "    Use for: 'As an additional cost to play X, discard a random card.'",
        "    If the player CANNOT pay this cost (e.g. empty hand for DISCARD_RANDOM),",
        "    the card does NOT appear in legal actions. Never model these as effects.",
        "  alternative_cost: Pay INSTEAD of the normal resource cost.",
        "    Use for: 'Instead of its resource cost, you may remove 3 counters...'",
        "    Card is legal if EITHER the resource cost OR the alt cost is payable.",
        "",
        "Use ONLY type names that appear in the lists above or in the EXAMPLES",
        "below. The EXAMPLES are real cards and show correct params for each type.",
        "Never invent a type, trigger, or condition name.",
        "",
        "CONDITIONS ON EFFECTS: an effect object may have a 'conditions' key (list) to gate only that effect.",
        "CONDITIONS ON ABILITIES: an ability may have a 'conditions' key (list) — ALL must pass or nothing fires.",
        "=== END DSL REFERENCE ===",
    ]
    return "\n".join(lines)


def valid_type_names() -> set[str]:
    """The names the DSL actually dispatches on — the ground truth for what a card
    JSON may use. Covers both `etype == "X"` and `etype in ("X", "Y")` forms (and
    the ctype equivalents), so param-requiring effects like GAIN aren't missed the
    way an empty-params compile probe would miss them.
    """
    names: set[str] = set()
    for fname, var in (("effect_types.py", "etype"), ("condition_types.py", "ctype"),
                       ("cost_types.py", "ctype")):
        text = (DSL_DIR / fname).read_text(encoding="utf-8") if (DSL_DIR / fname).exists() else ""
        names |= set(re.findall(rf'{var} == "([A-Z_]+)"', text))
        for grp in re.findall(rf'{var} in \(([^)]*)\)', text):
            names |= set(re.findall(r'"([A-Z_]+)"', grp))
    # Triggers + ability types are also written as "type"/"trigger" in card JSON.
    names |= set(_extract_types_from_source(
        DSL_DIR / "trigger_types.py", r'"(ON_[A-Z_]+|START_OF[A-Z_]+|END_OF[A-Z_]+)"'))
    return names


# ---------------------------------------------------------------------------
# Example JSON files (embedded)
# ---------------------------------------------------------------------------

EXAMPLES = """
=== EXAMPLES ===

Example 1 — ON_ATTACK trigger (pack_hunt_red):
Card text: "When this attacks, intimidate."
{
  "slug": "pack_hunt_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [{"type": "INTIMIDATE"}]
    }
  ]
}

Example 1b — ON_HIT trigger (soulbead_strike_red):
Card text: "If Soulbead Strike hits, Soulbead Strike gains go again."
{
  "slug": "soulbead_strike_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "effects": [{"type": "GO_AGAIN"}]
    }
  ]
}

Example 2 — Conditional effect on a PLAY ability (scar_for_a_scar_red):
Card text: "If your hero has less life than an opposing hero, Scar for a Scar gains go again."
{
  "slug": "scar_for_a_scar_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {
          "type": "GO_AGAIN",
          "conditions": [{"type": "HEALTH_LT_OPP"}]
        }
      ]
    }
  ]
}

Example 3 — Attack Reaction with INJECT_TRIGGER (pummel_red):
Card text: "Target attack action card or [Hammer] or [Club] weapon attack gets +4{p}. If it hits, defending player discards a card."
{
  "slug": "pummel_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [
        {
          "type": "OR",
          "any": [
            {"type": "AND", "all": [{"type": "ATTACK_IS_NOT_WEAPON"}, {"type": "ATTACK_COST_GTE", "amount": 2}]},
            {"type": "AND", "all": [{"type": "ATTACK_IS_WEAPON"}, {"type": "WEAPON_SUBTYPE_IN", "values": ["Hammer", "Club"]}]}
          ]
        }
      ],
      "effects": [
        {"type": "MODIFY_ATTACK_POWER", "amount": 4},
        {
          "type": "INJECT_TRIGGER",
          "trigger": "ON_HIT",
          "effects": [{"type": "DISCARD", "player": "DEFENDING", "amount": 1}]
        }
      ]
    }
  ]
}

Example 4 — Next weapon attack buff (warriors_valor_red):
Card text: "Your next weapon attack this turn gets +3{p}. If it hits, it gains go again."
{
  "slug": "warriors_valor_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {"type": "NEXT_WEAPON_ATTACK_BONUS", "amount": 3, "hit_go_again": true}
      ]
    }
  ]
}

Example 5 — Combo trigger with INJECT_TRIGGER ON_HIT DRAW (whelming_gustwave_red):
Card text: "Combo - Surging Strike: Whelming Gustwave gets +1{p} and gains go again. If it hits, draw a card."
{
  "slug": "whelming_gustwave_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "effects": [
        {"type": "MODIFY_ATTACK_POWER", "amount": 1, "conditions": [{"type": "COMBO", "names": ["surging_strike"]}]},
        {"type": "GO_AGAIN", "conditions": [{"type": "COMBO", "names": ["surging_strike"]}]}
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [{"type": "COMBO", "names": ["surging_strike"]}],
      "effects": [{"type": "DRAW", "amount": 1}]
    }
  ]
}

Example — additional_cost: mandatory discard (alpha_rampage_red):
Card text: "As an additional cost to play Alpha Rampage, discard a random card."
NOTE: This is a COST not an effect. If hand is empty the card cannot be played at all.
{
  "slug": "alpha_rampage_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [{"type": "DISCARD_RANDOM", "amount": 1}]
    }
  ]
}

Example — additional_cost: reveal restriction (demolition_crew_red):
Card text: "As an additional cost to play Demolition Crew, reveal a card with cost 2 or greater from your hand."
{
  "slug": "demolition_crew_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [{"type": "REVEAL_CARD_COST_GTE", "amount": 2}],
      "effects": [{"type": "DOMINATE"}]
    }
  ]
}

Example — additional_cost: optional banish with conditional bonus (nimble_strike_red):
Card text: "As an additional cost to play Nimble Strike, you may banish a Nimblism card from your graveyard.
If you do, Nimble Strike gains +1 Power and Go Again."
{
  "slug": "nimble_strike_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {"type": "BANISH_NAMED_GRAVEYARD_OPTIONAL", "slug_contains": "nimblism", "flag": "banished_nimblism"}
      ],
      "effects": [
        {"type": "MODIFY_ATTACK_POWER", "amount": 1, "conditions": [{"type": "FLAG_SET", "flag": "banished_nimblism"}]},
        {"type": "GO_AGAIN", "conditions": [{"type": "FLAG_SET", "flag": "banished_nimblism"}]}
      ]
    }
  ]
}

Example — ATTACK_REACTION with class targeting condition (ancestral_empowerment_red):
Card text: "Target Ninja attack action card gains +1 Power. Draw a card."
{
  "slug": "ancestral_empowerment_red",
  "abilities": [
    {
      "ability_type": "ATTACK_REACTION",
      "conditions": [{"type": "ATTACK_CLASS_IN", "classes": ["Ninja"]}],
      "effects": [
        {"type": "MODIFY_ATTACK_POWER", "amount": 1},
        {"type": "DRAW", "amount": 1}
      ]
    }
  ]
}
Example — Crush mechanic (cartilage_crush_red):
Card text: "Crush — When this deals 4 or more damage to a hero, their first action during their next turn costs an additional {r}."
NOTE: "deals N or more damage" maps to ON_HIT trigger + CRUSH condition. Do NOT invent ON_DEAL_DAMAGE.
{
  "slug": "cartilage_crush_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_HIT",
      "conditions": [{"type": "CRUSH", "amount": 4}],
      "effects": [{"type": "SET_FLAG", "flag": "crush_cost_next_turn", "scope": "NEXT"}]
    }
  ]
}

Example — ON_ENTER_PLAY aura (blessing_of_deliverance_red):
Card text: "Go again. When Blessing of Deliverance enters the arena, if you have a card with cost 3 or greater in your pitch zone, gain 3 life."
{
  "slug": "blessing_of_deliverance_red",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "effects": [
        {
          "type": "GAIN_LIFE",
          "amount": 3,
          "conditions": [{"type": "CARD_IN_ZONE", "zone": "pitch", "filter_cost_gte": 3}]
        }
      ]
    }
  ]
}
=== END EXAMPLES ===
"""

COMMON_MISTAKES = """
=== COMMON MISTAKES — READ CAREFULLY BEFORE GENERATING ===

1. EFFECT TYPES ≠ CONDITION TYPES.
   These are effects, NOT conditions — never put them in a "conditions" array:
     DEAL_ARCANE, DEAL_DAMAGE, GAIN_LIFE, DRAW, DISCARD, NEXT_ATTACK_BONUS,
     MODIFY_ATTACK_POWER, GO_AGAIN, INTIMIDATE, DOMINATE, CREATE_TOKEN, SET_FLAG
   Only condition types (COMBO, CRUSH, FLAG_SET, HEALTH_LT_OPP, etc.) belong in conditions.

2. ONLY USE TRIGGER TYPES FROM THE LIST ABOVE.
   Valid triggers: ON_HIT, ON_ATTACK, ON_PLAY, ON_ENTER_PLAY, ON_DEFEND, ON_DEATH,
     START_OF_TURN, END_OF_TURN, ON_ACTIVATE, START_OF_COMBAT, END_OF_COMBAT.
   NEVER invent: ON_DEAL_DAMAGE, ON_ENTER_ARENA, ON_BLOCK, ON_CRUSH, ON_RESOLVE.

3. COMBO condition REQUIRES a "names" array.
   CORRECT:   {"type": "COMBO", "names": ["rising_knee_thrust"]}
   WRONG:     {"type": "COMBO"}   ← missing names, always fails

4. "If this deals N or more damage" = ON_HIT trigger + CRUSH condition.
   {"ability_type": "TRIGGERED", "trigger": "ON_HIT", "conditions": [{"type": "CRUSH", "amount": N}], ...}

5. COSTS vs EFFECTS — the most common error:
   "As an additional cost to play X, ..."  -> additional_cost array (NEVER an effect)
   "Instead of its cost, you may ..."      -> alternative_cost array
   "Discard a card." (no cost preamble)    -> DISCARD effect
   If the hand must be non-empty to play the card -> it is a COST, not an effect.

6. ONLY THESE KEYS ARE VALID on an ability object:
     ability_type, trigger, conditions, effects, additional_cost, alternative_cost, optional
   NEVER invent: end_of_turn_effect, cost, remove_trigger, set_flag (top-level), activate_cost.

7. STATIC ability_type is for always-on passive bonuses (e.g. "+1 power while condition").
   If the card says "When" / "If this hits" / "At the start of" -> use TRIGGERED, not STATIC.

8. SYMBOL MEANINGS (CR 1.12.4) — never confuse these:
   {r} = resource (use PAY_RESOURCES / GAIN_RESOURCES, amount = number of {r} symbols)
   {p} = power / physical damage (attack bonus or damage value)
   {h} = life / health
   {c} = chi
   {d} = defense value
   {i} = intellect
   {t} = tap
   {u} = untap
   EXAMPLE: "Action - {r}{r}: ..." costs 2 resources -> additional_cost: [{"type": "PAY_RESOURCES", "amount": 2}]
   NEVER use PAY_LIFE for {r} costs. NEVER use PAY_RESOURCES for {h} costs.

9. DESTROY_PERMANENT must specify WHAT to destroy:
   - Card destroys itself (equipment activated with "Destroy X: ..."):
     {"type": "DESTROY_PERMANENT", "target": "self"}
   - Destroy a permanent of a specific type:
     {"type": "DESTROY_PERMANENT", "permanent_type": "Landmark"}
   - Destroy a specific named card:
     {"type": "DESTROY_PERMANENT", "slug": "barkbone_strapping"}
   NEVER use bare {"type": "DESTROY_PERMANENT"} with no target — it is ambiguous.

   NOTE: dice-roll resource gain IS supported:
     {"type": "GAIN_RESOURCES_FROM_ROLL", "faces": 6, "divisor": 2}
     rolls a d6, divides result by 2 (floor), gains that many resources.

10. IF THE CARD CANNOT BE EXPRESSED WITH THE CURRENT DSL, say so explicitly.
   Do NOT invent new type names, trigger names, or condition names.
   Instead, output ONLY this JSON (no abilities array):
   {
     "slug": "<slug>",
     "unsupported": true,
     "reason": "<one sentence: what effect or mechanic is missing from the DSL>",
     "suggested_additions": ["<e.g. ON_ENTER_ARENA trigger>", "<e.g. LANDMARK effect>"]
   }
   Use this ONLY when the card genuinely cannot be modeled with available types.
   If the effect is complex but expressible, use the available types and model it.

=== END COMMON MISTAKES ===
"""


# ---------------------------------------------------------------------------
# Embedding-based dynamic few-shot examples from approved cards
# ---------------------------------------------------------------------------

_EMBED_CACHE: dict[str, list[float]] = {}  # slug -> embedding vector


def _get_embedding(text: str, model: str = "qwen3-embedding:4b") -> list[float] | None:
    """Call Ollama /api/embeddings and return the vector, or None on failure."""
    try:
        payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:11434/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("embedding")
    except Exception:
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_dynamic_examples(card: dict, queue: list[dict], n: int = 3,
                            embed_model: str = "qwen3-embedding:4b") -> str:
    """Return additional examples from approved cards, ranked by semantic similarity.

    Falls back to type-text matching if the approved pool is < 5 or embeddings fail.
    """
    approved = [c for c in queue if c.get("status") == "approved" and c["slug"] != card["slug"]]
    if len(approved) < 2:
        return ""

    if len(approved) >= 30:
        # Try embedding-based ranking
        target_text = (card.get("functional_text") or card.get("name") or card["slug"])
        target_vec = _get_embedding(target_text, embed_model)
        if target_vec:
            scored = []
            for c in approved:
                slug = c["slug"]
                if slug not in _EMBED_CACHE:
                    vec = _get_embedding(
                        c.get("functional_text") or c.get("name") or slug,
                        embed_model,
                    )
                    if vec:
                        _EMBED_CACHE[slug] = vec
                if slug in _EMBED_CACHE:
                    sim = _cosine_similarity(target_vec, _EMBED_CACHE[slug])
                    scored.append((sim, c))
            if scored:
                scored.sort(key=lambda x: x[0], reverse=True)
                ranked = [c for _, c in scored[:n]]
            else:
                ranked = approved[:n]
        else:
            ranked = approved[:n]
    else:
        # Simple type-text fallback
        target_type = (card.get("type_text") or "").split(" - ")[0].lower()
        ranked = sorted(
            approved,
            key=lambda c: 2 if (c.get("type_text") or "").split(" - ")[0].lower() == target_type else 0,
            reverse=True,
        )[:n]

    lines = ["=== ADDITIONAL EXAMPLES (from approved cards) ===", ""]
    for c in ranked:
        slug = c["slug"]
        json_path = WTR_DIR / f"{slug}.json"
        if not json_path.exists():
            continue
        lines.append(f"Card: {c['name']} ({slug})")
        lines.append(f"Type: {c.get('type_text', '')}")
        lines.append(f"Text: {(c.get('functional_text') or '(none)')[:200]}")
        lines.append("JSON:")
        lines.append(json_path.read_text(encoding="utf-8"))
        lines.append("")
    lines.append("=== END ADDITIONAL EXAMPLES ===")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Verification pass
# ---------------------------------------------------------------------------

def build_verification_prompt(card: dict, json_content: str, dsl_ref: str) -> str:
    return f"""\
You are a strict validator for a card game DSL. Check this JSON against the DSL reference.

{dsl_ref}

{STRUCTURAL_RULES}

Card text:
  slug: {card["slug"]}
  functional_text: {card.get("functional_text") or "(none)"}

Generated JSON:
{json_content}

VALIDATION CHECKS — fail if ANY of these are true:
1. An effect type appears inside a "conditions" array.
2. A trigger type is used that is NOT in the valid trigger list above.
3. A COMBO condition is missing its "names" array.
4. A card cost ("As an additional cost...") is modelled as an effect instead of additional_cost.
5. An invented top-level key appears on an ability (anything other than: ability_type, trigger, conditions, effects, additional_cost, alternative_cost, optional).
6. A condition type is used that is NOT in the valid condition list above.

If the JSON passes ALL checks, output exactly: LOOKS_GOOD
If any check fails, output ONLY the corrected JSON object (no explanation, no markdown fences).
"""


def run_verification_pass(card: dict, json_content: str, dsl_ref: str,
                          model: str | None, verbose: bool) -> str:
    """Run a second claw-code call to validate and optionally correct the JSON.
    Returns the final JSON string to write (may be same as input or corrected)."""
    prompt = build_verification_prompt(card, json_content, dsl_ref)
    output = run_llm(prompt, verbose=verbose, model=model)

    if output in ("CLAW_TIMEOUT",) or output.startswith("CLAW_ERROR"):
        print(f"  [verify] claw-code failed, keeping original")
        return json_content

    # Strip reasoning models' <think>...</think> before looking for the verdict/JSON.
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', output, flags=re.IGNORECASE)
    cleaned = re.sub(r'```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'```\s*', '', cleaned).strip()

    if "LOOKS_GOOD" in cleaned.upper()[:40]:
        print(f"  [verify] LOOKS_GOOD")
        return json_content

    match = re.search(r'\{[\s\S]+\}', cleaned)
    if not match:
        print(f"  [verify] no JSON in verification output, keeping original")
        return json_content

    try:
        corrected = json.loads(match.group())
        print(f"  [verify] corrections applied")
        return json.dumps(corrected, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        print(f"  [verify] corrected JSON invalid, keeping original")
        return json_content


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _card_text_index() -> dict[str, str]:
    """slug -> printed functional text, from the canonical slug_index."""
    try:
        idx = json.loads((ROOT / "card_data" / "slug_index.json").read_text(encoding="utf-8"))
        by = idx.get("by_slug", idx)
        return {s: (e.get("functionalText") or "") for s, e in by.items()}
    except Exception:
        return {}


def build_real_examples(n: int = 8) -> str:
    """Few-shot examples drawn from REAL committed card JSONs.

    Every committed card compiles, so every example uses valid, current type
    names — unlike hand-written examples, which drift from the DSL and teach the
    model non-loading types (the exact failure the load gate was catching). One
    small (=simple) card per ability_type, for a spread of patterns.
    """
    from engine.card_effects.dsl.loader import compile_card
    text_of = _card_text_index()
    by_type: dict[str, list] = {}
    json_root = ROOT / "engine" / "card_effects" / "json"
    for path in sorted(json_root.rglob("*.json")):
        rel = path.relative_to(json_root)
        if path.stem.endswith("_work_queue") or any(p.startswith(".") for p in rel.parts):
            continue
        if "needs_review" in rel.parts or rel.parts[0] == "tokens":
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        abilities = raw.get("abilities")
        if not abilities or not isinstance(abilities, list):
            continue
        try:
            compile_card(raw)  # only real, LOADING cards teach valid type usage
        except Exception:
            continue
        at = abilities[0].get("ability_type", "?")
        body = json.dumps(raw, ensure_ascii=False)
        by_type.setdefault(at, []).append((len(body), raw.get("slug", path.stem), path))

    order = ["TRIGGERED", "PLAY", "ATTACK_REACTION", "ACTIVATE", "STATIC_TRIGGERED",
             "INSTANT", "DEFENSE_REACTION", "MODAL", "STATIC", "WHILE_STATIC"]
    picks: list = []
    for at in order:
        for _sz, slug, path in sorted(by_type.get(at, []))[:1]:
            picks.append((slug, path))
        if len(picks) >= n:
            break

    lines = ["=== EXAMPLES — real implemented cards. Copy their structure and use "
             "ONLY type names that appear here or in the reference above. ===", ""]
    for slug, path in picks[:n]:
        lines.append(f"Card text: {text_of.get(slug) or '(vanilla / no text)'}")
        lines.append(path.read_text(encoding="utf-8").strip())
        lines.append("")
    lines.append("=== END EXAMPLES ===")
    return "\n".join(lines)


def validate_prompt_vocabulary(prompt: str) -> list[str]:
    """Return "type" names used in the prompt that the DSL does not dispatch on —
    i.e. names that would teach the model to emit non-loading JSON. A startup
    self-check so prompt/DSL drift can never silently return.
    """
    valid = valid_type_names()
    names = set(re.findall(r'"type":\s*"([A-Z_]+)"', prompt))
    return sorted(nm for nm in names if nm not in valid)


# Structural rules that name NO specific effect types (so they can't go stale).
# Concrete type usage is taught by build_real_examples() and the DSL reference.
STRUCTURAL_RULES = """
=== RULES ===
1. Only include abilities that DO something. A pure stat card (power/defense, no
   effect text) or a Specialization-only card outputs: {"slug": "<slug>", "abilities": []}
2. Use ONLY effect/condition/cost type names that appear in the DSL REFERENCE or
   the EXAMPLES above. NEVER invent a type, trigger, or condition name. If a card
   truly cannot be expressed with the available types, output exactly:
   NEEDS_NEW_DSL: <one-sentence reason>  and STOP.

3. THE COLON SPLITS COST : EFFECT.  In an activated/action line
   "[Prefix] - [costs]: [effect]", EVERYTHING BEFORE THE COLON (after an
   "Action -" / "Instant -" prefix) is a COST; everything AFTER the colon is the
   effect. Costs are NEVER effects.
   - {r} resource cost, e.g. "Action - {r}{r}: ..."  ->  "activation_cost": N
     (N = number of {r}). The engine charges it; do NOT also add a pay-resources effect.
   - Non-resource costs before the colon (destroy this, discard, pay {h}, remove a
     counter, ...) -> a "cost" array on the ability. "Destroy this" is
     {"type": "DESTROY_PERMANENT", "target": "self"} in "cost" — NEVER an effect.
   - The part AFTER the colon -> "effects".
   Example — "Action - Destroy this: Gain {r}. Go again":
     {"ability_type": "ACTIVATE", "activation_cost": 0,
      "cost": [{"type": "DESTROY_PERMANENT", "target": "self"}],
      "effects": [{"type": "GAIN", "asset": "RESOURCE_POINTS", "amount": 1}, {"type": "GO_AGAIN"}]}

4. ACTIVATED ability vs PLAY effect — decide by the card's type line:
   - Permanent types (Equipment, Item, Weapon, Aura, token) with an activated line
     "Action - ...:" / "Instant - ...:"  ->  "ability_type": "ACTIVATE". The card
     STAYS in play and is activated; use "activation_cost" for {r} and a "cost"
     array for other costs (rule 3).
   - Action / Attack cards played from hand  ->  "ability_type": "PLAY". The text
     is what happens WHEN PLAYED. Play-cost wording uses "additional_cost" /
     "alternative_cost" (below), NOT a "cost" array.

5. PLAY-cost wording (only for PLAY cards):
   - "As an additional cost to play X, ..." -> "additional_cost" array (unplayable if unpayable).
   - "Instead of paying its cost, you may ..." -> "alternative_cost" array.
   - "discard a card" with NO cost preamble and NO colon -> a normal effect.

6. "When/If this hits" -> a TRIGGERED ability with ON_HIT. "When this attacks" ->
   ON_ATTACK. Match the wording to a real trigger; do not invent one.
7. Slugs use underscores, never hyphens. Output ONLY the raw JSON object — no
   markdown fences, no prose. It must parse (no trailing commas; true/false).
=== END RULES ==="""


# Real, verified-passing tests (each confirmed under the gate's own harness),
# keyed by ability_type. Injected into the test prompt so the auditor copies a
# working pattern for THIS card's kind of ability — correct trigger event, real
# attribute names, real zones — instead of guessing.
GOLD_TESTS = {
    "ACTIVATE": '''def test_blossom_of_spring_activate():
    # "Action - Destroy this: Gain {r}. Go again" — activated ability fires on ON_ACTIVATE
    st = _make_state(); st.card_db = DB
    card = _card("blossom_of_spring")
    st.players[1].chest.add(card)
    before = st.players[1].resources
    dispatch(st, "ON_ACTIVATE", "blossom_of_spring", card=card, event=None)
    assert st.players[1].resources == before + 1''',
    "PLAY": '''def test_vigorous_windup_blue_play():
    # A play ability fires on ON_PLAY; assert the observable result (here a token in play)
    st = _make_state(); st.card_db = DB
    card = _card("vigorous_windup_blue")
    st.players[1].permanents.add(card)
    n0 = len(st.players[1].permanents.cards)
    dispatch(st, "ON_PLAY", "vigorous_windup_blue", card=card, event=None)
    assert len(st.players[1].permanents.cards) >= n0''',
    "TRIGGERED": '''def test_crown_of_dominion_on_equip():
    # "When you equip this, create a Gold token" — a TRIGGERED ability fires on its trigger
    st = _make_state(); st.card_db = DB
    card = _card("crown_of_dominion")
    st.players[1].head.add(card)
    dispatch(st, "ON_EQUIP", "crown_of_dominion", card=card, event=None)
    assert any(c.slug == "gold" for c in st.players[1].permanents.cards)''',
}

_GOLD_BY_ABILITY = {
    "ACTIVATE": "ACTIVATE", "ACTION": "ACTIVATE",
    "PLAY": "PLAY", "INSTANT": "PLAY",
    "ATTACK_REACTION": "PLAY", "DEFENSE_REACTION": "PLAY",
    "TRIGGERED": "TRIGGERED", "STATIC_TRIGGERED": "TRIGGERED",
    "STATIC": "TRIGGERED", "WHILE_STATIC": "TRIGGERED", "MODAL": "PLAY",
}


def _gold_test_for(json_content: str) -> str:
    """Pick the verified gold test whose ability_type matches the generated card."""
    try:
        at = (json.loads(json_content).get("abilities") or [{}])[0].get("ability_type", "")
    except Exception:
        at = ""
    return GOLD_TESTS[_GOLD_BY_ABILITY.get(at, "TRIGGERED")]


def build_implementation_prompt(card: dict, dsl_ref: str, queue: list[dict] | None = None,
                                embed_model: str = "qwen3-embedding:4b") -> str:
    card_block = json.dumps({k: v for k, v in card.items() if k != "status"}, indent=2, ensure_ascii=False)
    dynamic = build_dynamic_examples(card, queue or [], embed_model=embed_model) if queue else ""
    extra = f"\n{dynamic}\n" if dynamic else ""
    real_examples = build_real_examples()
    return f"""\
You are implementing a card effect JSON file for the Flesh and Blood trading card game simulator.

{dsl_ref}

{real_examples}
{extra}
{STRUCTURAL_RULES}

=== YOUR TASK ===

Generate a JSON effect file for this card (follow the RULES and EXAMPLES above):

{card_block}

Output the JSON now:
"""


def build_test_prompt(card: dict, json_content: str) -> str:
    gold = _gold_test_for(json_content)
    try:
        has_abilities = bool(json.loads(json_content).get("abilities"))
    except Exception:
        has_abilities = True
    rule5 = (
        '5. This card HAS abilities — test their effect(s). Do NOT write a '
        '"no abilities" test and do NOT assert `not card.abilities`.'
        if has_abilities else
        '5. This card has EMPTY abilities. Write EXACTLY ONE smoke test:\n'
        f'   assert get_card("{card["slug"]}").abilities == []'
    )
    return f"""\
You are writing pytest unit tests for a Flesh and Blood card simulator.

The card being tested is:
  slug: {card["slug"]}
  name: {card["name"]}
  type: {card["type_text"]}
  functional text: {card["functional_text"] or "(none)"}

The JSON effect definition is:
{json_content}

Below is a REAL, PASSING test for another card of the SAME kind of ability.
Write your test(s) the same way, adapted to {card["slug"]}: build a real state
with _make_state(), dispatch with the real signature
`dispatch(state, EVENT_TYPE, slug, card=<card>, event=None)`, and assert an
OBSERVABLE outcome. Do NOT invent a mock state dict. The harness already
provides _make_state, _card, DB, dispatch, get_card — do NOT redefine them.

REAL PASSING EXAMPLE (same ability_type):
{gold}

Write 1-2 FOCUSED tests on the card's PRIMARY, directly-observable effect (the
resource/life/token/zone change). Every test you write MUST pass. Do NOT assert
`GO_AGAIN` or other keyword grants (go again, dominate, intimidate): those apply
during the resolution flow, not from a bare dispatch, so `action_points`/etc.
will NOT change here — asserting them fails a correct card.

RULES:
1. Every test name starts with `test_{card["slug"]}_`.
2. Use the real API shown above: `_make_state()` for state (NOT a dict), the
   real `dispatch(state, EVENT_TYPE, slug, card=..., event=None)` signature, and
   the trigger from the card's JSON (ON_HIT, ON_PLAY, ON_ATTACK, ON_ACTIVATE, ...).
3. Assert OBSERVABLE state using the REAL attribute names (these exact spellings):
   - life: `st.players[p].health`   (there is NO 'life'/'hp' attribute)
   - resources: `st.players[p].resources`   (NOT resource_points)
   - action points: `st.players[p].action_points`;  chi: `st.players[p].chi`
   - zones are objects; use `.cards`: `st.players[p].graveyard.cards`,
     `.arsenal.cards`, `.banished.cards`, `.hand.cards`, `.chest.cards`,
     `.arms.cards`, `.weapon1.cards`, `.permanents.cards`
   Do NOT assert on internal registries or flags. Do NOT invent attribute names.
4. Fire the ability by its ability_type: TRIGGERED -> dispatch its trigger
   (ON_HIT/ON_ATTACK/ON_DEFEND/...); PLAY -> "ON_PLAY"; ACTIVATE/ACTION ->
   "ON_ACTIVATE"; DEFENSE_REACTION/ATTACK_REACTION -> "ON_PLAY". Match the
   card's JSON. Arsenal holds at most 1 card.
{rule5}
6. If you genuinely cannot write a correct test, output `NEEDS_NEW_DSL: <reason>` and stop.
7. Output ONLY valid Python — no markdown fences, no prose.

Output the test functions now:
"""


# ---------------------------------------------------------------------------
# claw-code runner
# ---------------------------------------------------------------------------

def run_openai_chat(prompt: str, model: str, verbose: bool = False,
                    retries: int = 2, temperature: float = 0.1) -> str:
    """Run a prompt against an OpenAI-compatible /chat/completions endpoint.

    Works with any server that speaks the OpenAI chat API — a standalone
    llama.cpp llama-server, Ollama, LM Studio, etc. Returns the assistant text,
    or a CLAW_TIMEOUT / CLAW_ERROR sentinel (shared with run_claw so the existing
    output parsers handle failures identically).
    """
    url = BASE_URL.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "stream": False,
    }).encode("utf-8")
    last_error = ""
    for attempt in range(1, retries + 2):
        try:
            if verbose:
                print(f"  [llm] attempt {attempt} model={model} -> {url}", file=sys.stderr)
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except urllib.error.URLError as e:
            last_error = str(getattr(e, "reason", e))
            if hasattr(e, "code") and getattr(e, "code", None):  # HTTP error, no point retrying fast-fail 4xx
                last_error = f"HTTP {e.code}: {last_error}"
            print(f"  [llm ERROR] attempt {attempt}: {last_error}", file=sys.stderr)
            if attempt <= retries:
                continue
            return f"CLAW_ERROR: {last_error}"
        except (KeyError, IndexError, ValueError) as e:
            return f"CLAW_ERROR: malformed response: {e}"
        except Exception as e:  # includes socket.timeout
            print(f"  [llm ERROR] attempt {attempt}: {e}", file=sys.stderr)
            if attempt <= retries:
                continue
            return f"CLAW_ERROR: {e}"
    return f"CLAW_ERROR: all attempts failed ({last_error})"


def run_llm(prompt: str, verbose: bool = False, model: str | None = None) -> str:
    """Dispatch a prompt to the configured backend (openai endpoint or claw-code)."""
    if BACKEND == "openai":
        if not model:
            return "CLAW_ERROR: openai backend requires an explicit model"
        return run_openai_chat(prompt, model=model, verbose=verbose)
    return run_claw(prompt, verbose=verbose, model=model)


# ---------------------------------------------------------------------------
# Execution gate — deterministic checks that the generated card actually works,
# so a card is only marked "done" if it loads and its test passes. This is the
# real signal; the LLM verification pass is advisory and can miss invented types.
# ---------------------------------------------------------------------------

def validate_card_loads(json_content: str) -> tuple[bool, str]:
    """Compile the generated JSON as the engine would at game start.

    compile_card raises ValueError on any unknown effect/condition/trigger type
    or malformed ability — exactly the invented-type errors an LLM produces
    (e.g. MAY_DESTROY_SILVERS_TO_EQUIP). Returns (ok, error_message).
    """
    from engine.card_effects.dsl.loader import compile_card
    try:
        raw = json.loads(json_content)
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}"
    try:
        compile_card(raw)
        return True, ""
    except Exception as e:  # ValueError (unknown type) and any structural error
        return False, f"{type(e).__name__}: {e}"


def run_generated_test(slug: str, test_code: str, verbose: bool = False) -> tuple[bool, str]:
    """Run the auditor's test in ISOLATION and report whether it passes.

    Writing to a throwaway file (not the shared test_{set}_generated.py) means a
    prior card's broken test cannot poison this card's gate, and only tests that
    actually pass get appended to the committed file. Returns (passed, output).
    """
    # The header MUST provide exactly the names the test-prompt example uses
    # (_make_state, _card, DB, dispatch, get_card) — extract_test_code strips the
    # model's own header, so the gate supplies the harness. Keep in sync with
    # build_test_prompt's example.
    header = (
        "import copy, sys\n"
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "sys.path.insert(0, str(ROOT))\n"
        "from engine.card import CardDB\n"
        "from engine.card_effects.dsl import dispatch, get_card\n"
        "from engine.card_effects.dsl.loader import load_all_cards\n"
        "from tests.conftest import _make_state\n"
        "load_all_cards()\n"
        "DB = CardDB()\n"
        "def _card(slug, owner=1):\n"
        "    c = copy.deepcopy(DB.get(slug)); c.owner = c.controller = owner\n"
        "    return c\n\n"
    )
    tmp = ROOT / "tests" / f"_gate_{slug}.py"
    tmp.write_text(header + test_code + "\n", encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(tmp), "-q", "-p", "no:randomly", "-x"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=180,
            encoding="utf-8", errors="replace",  # pytest output may carry cp1252 bytes on Windows
        )
        out = (result.stdout or "") + (result.stderr or "")
        if verbose:
            print(f"  [gate] pytest exit {result.returncode}", file=sys.stderr)
        return result.returncode == 0, out[-3000:]
    except subprocess.TimeoutExpired:
        return False, "pytest timed out (possible infinite loop in generated test)"
    except Exception as e:
        return False, f"pytest run error: {e}"
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def run_claw(prompt: str, verbose: bool = False, retries: int = 2,
             model: str | None = None) -> str:
    """Write prompt to a temp file and invoke claw-code one-shot. Returns stdout."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(prompt)
        prompt_file = f.name

    last_error = ""
    for attempt in range(1, retries + 2):
        try:
            cmd = [sys.executable, "-m", "src.main", "chat", "-f", prompt_file]
            if model:
                cmd += ["--model", model]
            if verbose:
                print(f"  [claw] Attempt {attempt}: {' '.join(cmd)}", file=sys.stderr)
            result = subprocess.run(
                cmd,
                cwd=str(CLAW_DIR),
                capture_output=True,
                text=True,
                timeout=360,
                encoding="utf-8",
            )
            if result.returncode != 0:
                last_error = result.stderr[:3000]
                print(f"  [claw ERROR] attempt {attempt} exit code {result.returncode}", file=sys.stderr)
                if verbose:
                    print(f"  [claw stderr] {last_error}", file=sys.stderr)
                if attempt <= retries:
                    print(f"  [claw] Retrying...", file=sys.stderr)
                    continue
                os.unlink(prompt_file)
                return f"CLAW_ERROR: exit {result.returncode}"
            if result.stderr.strip() and verbose:
                print(f"  [claw stderr] {result.stderr[:3000]}", file=sys.stderr)
            os.unlink(prompt_file)
            return result.stdout
        except subprocess.TimeoutExpired:
            print(f"  [claw] attempt {attempt} timed out", file=sys.stderr)
            if attempt <= retries:
                continue
            try:
                os.unlink(prompt_file)
            except OSError:
                pass
            return "CLAW_TIMEOUT"
        except Exception as e:
            try:
                os.unlink(prompt_file)
            except OSError:
                pass
            return f"CLAW_ERROR: {e}"
    return "CLAW_ERROR: all attempts failed"


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------

def _write_review_note(slug: str, reason: str, raw_output: str, label: str = "") -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{label}" if label else ""
    path = REVIEW_DIR / f"{slug}{suffix}.md"
    path.write_text(
        f"# {slug}{' — ' + label if label else ''} — Needs New DSL\n\n"
        f"**Reason:** {reason}\n\n"
        f"## Raw claw-code output\n\n```\n{raw_output}\n```\n",
        encoding="utf-8",
    )


def process_impl_output(slug: str, output: str, debug: bool = False) -> tuple[str, str]:
    """
    Parse claw-code implementation output.
    Returns (status, json_content_or_empty).
    status: "done" | "needs_review" | "failed"
    """
    if output in ("CLAW_TIMEOUT", ) or output.startswith("CLAW_ERROR"):
        print(f"  [ERROR] claw-code failed: {output[:200]}")
        return "failed", ""

    if debug or not output.strip():
        print(f"  [DEBUG raw output ({len(output)} chars)]:\n{output[:1000]}\n  [/DEBUG]")

    # Check for NEEDS_NEW_DSL flag
    if "NEEDS_NEW_DSL:" in output:
        reason = output.split("NEEDS_NEW_DSL:", 1)[1].strip().splitlines()[0]
        _write_review_note(slug, reason, output)
        return "needs_review", ""

    # Strip markdown fences if present (```json ... ``` or ``` ... ```)
    cleaned = re.sub(r'```(?:json)?\s*', '', output)
    cleaned = re.sub(r'```\s*', '', cleaned)

    # Try to extract JSON object from output
    match = re.search(r'\{[\s\S]+\}', cleaned)
    if not match:
        print(f"  [WARN] No JSON found in output for {slug}")
        print(f"  [WARN] First 500 chars of output: {repr(output[:500])}")
        return "failed", ""

    raw_json = match.group()
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        print(f"  [WARN] JSON parse error for {slug}: {e}")
        print(f"  [WARN] Raw JSON attempt: {raw_json[:300]}")
        return "failed", ""

    # Ensure slug matches
    if data.get("slug") != slug:
        print(f"  [WARN] slug mismatch: expected {slug}, got {data.get('slug')}")
        data["slug"] = slug  # fix silently

    out_path = WTR_DIR / f"{slug}.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Check for unsupported flag
    if data.get("unsupported"):
        reason = data.get("reason", "")
        suggestions = data.get("suggested_additions", [])
        print(f"  [UNSUPPORTED] {slug}: {reason}")
        if suggestions:
            print(f"  [UNSUPPORTED] suggested additions: {', '.join(suggestions)}")
        return "needs_dsl", json.dumps(data, indent=2, ensure_ascii=False)

    return "done", json.dumps(data, indent=2, ensure_ascii=False)


def extract_test_code(output: str) -> str:
    """Pull the test function(s) out of an LLM response. '' if none found."""
    # Strip <think>...</think> chain-of-thought and markdown fences.
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', output, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'```python\s*', '', cleaned)
    cleaned = re.sub(r'```\s*', '', cleaned).strip()
    match = re.search(r'((?:^|\n)(def test_[\s\S]+))', cleaned)
    return match.group(2).strip() if match else ''


def append_test(slug: str, code: str) -> None:
    """Append verified test code to the committed test_{set}_generated.py file."""
    if not TEST_OUTPUT.exists():
        # Same harness the gate runs tests under (build_test_prompt example +
        # run_generated_test header), so appended tests keep passing here.
        TEST_OUTPUT.write_text(
            f'"""Auto-generated pytest tests for {SET_CODE.upper()} card DSL implementations.\n'
            'Generated by scripts/auto_implement_wtr.py — do not edit manually.\n"""\n'
            "import copy, sys\n"
            "from pathlib import Path\n"
            "ROOT = Path(__file__).resolve().parent.parent\n"
            "sys.path.insert(0, str(ROOT))\n"
            "from engine.card import CardDB\n"
            "from engine.card_effects.dsl import dispatch, get_card\n"
            "from engine.card_effects.dsl.loader import load_all_cards\n"
            "from tests.conftest import _make_state\n"
            "load_all_cards()\n"
            "DB = CardDB()\n"
            "def _card(slug, owner=1):\n"
            "    c = copy.deepcopy(DB.get(slug)); c.owner = c.controller = owner\n"
            "    return c\n\n",
            encoding="utf-8",
        )
    with TEST_OUTPUT.open("a", encoding="utf-8") as f:
        f.write(f"\n# --- {slug} ---\n")
        f.write(code)
        f.write("\n")


def process_test_output(slug: str, output: str) -> None:
    """Legacy (ungated) path: extract and append without running. Kept for the
    claw backend / --no-gate use; the gated path in main() runs the test first."""
    if output in ("CLAW_TIMEOUT", ) or output.startswith("CLAW_ERROR"):
        print(f"  [TEST ERROR] test generation failed: {output[:80]}")
        return
    if "NEEDS_NEW_DSL:" in output:
        reason = output.split("NEEDS_NEW_DSL:", 1)[1].strip().splitlines()[0]
        _write_review_note(slug, reason, output, label="test")
        print(f"  [TEST REVIEW] {slug} -> needs_review/{slug}_test.md")
        return
    code = extract_test_code(output)
    if not code:
        print(f"  [TEST WARN] No recognisable test code for {slug}")
        return
    append_test(slug, code)
    print(f"  [TEST] tests appended -> tests/test_{SET_CODE}_generated.py")


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------

def load_queue() -> list[dict]:
    if not QUEUE_PATH.exists():
        print(f"ERROR: work queue not found at {QUEUE_PATH}")
        sys.exit(1)
    with QUEUE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue: list[dict]) -> None:
    QUEUE_PATH.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global BACKEND, BASE_URL, SET_CODE, WTR_DIR, QUEUE_PATH, REVIEW_DIR, TEST_OUTPUT
    parser = argparse.ArgumentParser(description="Batch-generate WTR JSON effect files via claw-code.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print first 3 prompts without calling claw-code.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after processing N pending cards.")
    parser.add_argument("--slug", default=None,
                        help="Process a specific slug only.")
    parser.add_argument("--reset-failed", action="store_true",
                        help="Reset all 'failed' cards back to 'pending' then run.")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show claw-code stderr and command details.")
    parser.add_argument("--skip-tests", action="store_true",
                        help="Skip the test generation step.")
    parser.add_argument("--skip-verify", action="store_true",
                        help="Skip the LLM verification pass after implementation.")
    parser.add_argument("--no-gate", action="store_true",
                        help="Disable the execution gate (load check + running the generated "
                             "test). By default a card is only marked 'done' if it compiles AND "
                             "its test passes; failures become needs_review / test_failed.")
    parser.add_argument("--debug", action="store_true",
                        help="Print raw claw-code output for every card.")
    parser.add_argument("--backend", choices=["openai", "claw"], default="openai",
                        help="LLM backend: 'openai' = OpenAI-compatible /chat/completions "
                             "endpoint (llama.cpp/Ollama/LM Studio); 'claw' = claw-code. Default: openai.")
    parser.add_argument("--base-url", default=BASE_URL, dest="base_url",
                        help=f"OpenAI-compatible API base URL (default: {BASE_URL}).")
    parser.add_argument("--model", default=None,
                        help="IMPLEMENTER model — writes the card JSON (e.g. fab-cards-ft:latest, qwen3-coder:30b).")
    parser.add_argument("--verify-model", "--audit-model", default=None, dest="verify_model",
                        help="AUDITOR model — verifies the JSON AND writes the test. MUST differ from "
                             "--model (e.g. fab-rules-ft:latest).")
    parser.add_argument("--embed-model", default="qwen3-embedding:4b", dest="embed_model",
                        help="Ollama embedding model for dynamic example selection (default: qwen3-embedding:4b).")
    parser.add_argument("--set", default="wtr", dest="set_code",
                        help="Set code to process (e.g. wtr, arc, cru). Default: wtr.")
    args = parser.parse_args()

    # Configure LLM backend
    BACKEND = args.backend
    BASE_URL = args.base_url
    if BACKEND == "openai":
        # Runnable defaults that honour the implementer/auditor split; override freely.
        if not args.model:
            args.model = "qwen2.5-coder:14b"
            print(f"[cfg] no --model given; implementer defaults to {args.model}")
        if not args.verify_model:
            args.verify_model = "fab-rules-ft:latest"
            print(f"[cfg] no --audit-model given; auditor defaults to {args.verify_model}")
        if args.verify_model == args.model:
            print(f"[cfg] WARNING: auditor model == implementer model ({args.model}); "
                  f"the design wants them separate so the auditor is an independent check.")
        print(f"[cfg] backend=openai base_url={BASE_URL}")
        print(f"[cfg] implementer={args.model}  auditor={args.verify_model}")

    # Remap paths based on --set
    SET_CODE = args.set_code.lower()
    WTR_DIR = ROOT / "engine" / "card_effects" / "json" / SET_CODE
    QUEUE_PATH = WTR_DIR / f"{SET_CODE}_work_queue.json"
    REVIEW_DIR = WTR_DIR / "needs_review"
    TEST_OUTPUT = ROOT / "tests" / f"test_{SET_CODE}_generated.py"

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    queue = load_queue()

    if args.reset_failed:
        for card in queue:
            if card["status"] == "failed":
                card["status"] = "pending"
        save_queue(queue)
        print(f"Reset failed cards to pending.")

    dsl_ref = build_dsl_reference()

    # Self-check: the assembled implementation prompt must not teach any type name
    # that the DSL can't compile, or the model will faithfully emit non-loading
    # JSON (the drift the load gate kept catching). Fail loudly rather than churn.
    _sample_card = {"slug": "_probe", "name": "probe", "type_text": "", "functional_text": ""}
    _stale = validate_prompt_vocabulary(build_implementation_prompt(_sample_card, dsl_ref))
    if _stale:
        print(f"[cfg] ERROR: prompt teaches {len(_stale)} type name(s) the DSL cannot "
              f"compile: {', '.join(_stale)}")
        print("[cfg] Fix the prompt/reference so it only uses real DSL types, then re-run.")
        sys.exit(2)
    print("[cfg] prompt vocabulary check: OK (all taught types compile)")

    pending = [c for c in queue if c["status"] == "pending"]
    if args.slug:
        pending = [c for c in pending if c["slug"] == args.slug]
        if not pending:
            # Also allow re-running a completed/failed card by slug
            pending = [c for c in queue if c["slug"] == args.slug]
            if pending:
                pending[0]["status"] = "pending"

    total = len(pending)
    limit = args.limit if args.limit else total
    print(f"Processing {min(total, limit)} / {total} pending cards.")
    print(f"Dry run: {args.dry_run}")

    processed = 0
    for card in pending:
        if processed >= limit:
            break

        slug = card["slug"]
        print(f"\n[{processed + 1}/{min(total, limit)}] {slug} — {card['name']}")
        print(f"  type: {card['type_text']}")
        if card["functional_text"]:
            print(f"  text: {card['functional_text'][:120]}")

        impl_prompt = build_implementation_prompt(card, dsl_ref, queue, embed_model=args.embed_model)

        if args.dry_run:
            if processed < 3:
                print("\n--- PROMPT PREVIEW (first 1500 chars) ---")
                print(impl_prompt[:1500])
                print("\n--- PROMPT PREVIEW (last 1500 chars) ---")
                print(impl_prompt[-1500:])
                print("--- END PREVIEW ---\n")
            processed += 1
            continue

        # Run implementation (implementer model)
        print(f"  [impl] generating via {BACKEND} model={args.model or 'default'}... (prompt {len(impl_prompt)} chars)")
        impl_output = run_llm(impl_prompt, verbose=args.verbose, model=args.model)
        status, json_content = process_impl_output(slug, impl_output, debug=args.debug)

        # Verification pass (auditor) — advisory LLM check for structural errors
        if status == "done" and not args.skip_verify:
            verify_model = args.verify_model or args.model
            print(f"  [verify] auditor ({verify_model or 'default'}) checking JSON...")
            json_content = run_verification_pass(card, json_content, dsl_ref,
                                                 model=verify_model, verbose=args.verbose)
            (WTR_DIR / f"{slug}.json").write_text(json_content, encoding="utf-8")

        # --- Execution gate 1: the card must actually compile/load ---
        # Deterministic: catches invented effect/condition/trigger types the LLM
        # verification can miss. One corrective retry feeds the exact error back
        # to the implementer before giving up.
        if status == "done" and not args.no_gate:
            ok, err = validate_card_loads(json_content)
            if not ok:
                print(f"  [gate] load FAILED: {err[:160]}")
                fix_prompt = (
                    impl_prompt
                    + f"\n\nYOUR PREVIOUS ATTEMPT FAILED TO LOAD with this error:\n{err}\n"
                      "Fix it using ONLY effect/condition/trigger types listed in the DSL "
                      "REFERENCE above. Do NOT invent type names. Output ONLY the corrected JSON."
                )
                fix_out = run_llm(fix_prompt, verbose=args.verbose, model=args.model)
                status, json_content = process_impl_output(slug, fix_out, debug=args.debug)
                ok, err = validate_card_loads(json_content) if status == "done" else (False, err)
                if ok and status == "done":
                    print(f"  [gate] load OK after retry")
                else:
                    _write_review_note(slug, f"load gate failed after retry: {err}",
                                       json_content or fix_out, label="loadgate")
                    status = "needs_review"
                    print(f"  [gate] load still failing -> needs_review")
            else:
                print(f"  [gate] load OK")

        # NOTE: the card's on-disk status is deliberately NOT written yet. It
        # stays at its previous value ('pending') all through the test gate, so
        # an interruption mid-gate leaves the card pending -> cleanly reprocessed
        # on resume, never a premature 'done'. The single authoritative write
        # happens once below, after the gate has decided the final status.
        print(f"  [load] {slug} -> {status}")

        # Test generation (auditor writes it — kept separate from the implementer)
        # + Execution gate 2: RUN the test in isolation. When the gate is on, a
        # card only KEEPS 'done' if a test was produced AND it passes — otherwise
        # 'done' would mean "compiles but was never behaviourally checked", which
        # defeats the gate. Downgrades (local only): no/failed test generation ->
        # needs_test; NEEDS_NEW_DSL -> needs_review; a test that ran but failed ->
        # test_failed.
        if status == "done" and not args.skip_tests:
            audit_model = args.verify_model or args.model
            print(f"  [test] auditor ({audit_model or 'default'}) writing test...")
            test_prompt = build_test_prompt(card, json_content)
            test_output = run_llm(test_prompt, verbose=args.verbose, model=audit_model)

            if test_output in ("CLAW_TIMEOUT",) or test_output.startswith("CLAW_ERROR"):
                if not args.no_gate:
                    status = "needs_test"
                print(f"  [test] generation failed ({test_output[:60]}) -> {status}")
            elif "NEEDS_NEW_DSL:" in test_output:
                process_test_output(slug, test_output)  # writes a review note
                if not args.no_gate:
                    status = "needs_review"
                print(f"  [test] auditor flagged NEEDS_NEW_DSL -> {status}")
            else:
                code = extract_test_code(test_output)
                if not code:
                    if not args.no_gate:
                        status = "needs_test"
                    print(f"  [test] no recognisable test code produced -> {status}")
                elif args.no_gate:
                    append_test(slug, code)
                    print(f"  [test] appended (gate disabled)")
                else:
                    passed, out = run_generated_test(slug, code, verbose=args.verbose)
                    if passed:
                        append_test(slug, code)
                        print(f"  [gate] test PASSED -> appended; {slug} verified done")
                    else:
                        _write_review_note(slug, "generated test did not pass",
                                           out + "\n\n--- TEST CODE ---\n" + code, label="testgate")
                        status = "test_failed"
                        print(f"  [gate] test FAILED -> status test_failed "
                              f"(JSON kept for review; test not appended)")

        # Single authoritative status write for this card, after the gate decided.
        card["status"] = status
        save_queue(queue)
        print(f"  [{status.upper()}] {slug}")

        processed += 1

    # Summary
    counts = {}
    for card in queue:
        counts[card["status"]] = counts.get(card["status"], 0) + 1
    print(f"\n=== Queue summary ===")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

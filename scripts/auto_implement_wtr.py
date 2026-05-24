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
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
CLAW_DIR = Path(os.environ.get("CLAW_DIR", str(Path(__file__).resolve().parent.parent.parent / "claw-code")))
CLAW_ENTRY = CLAW_DIR / "src" / "launch_claw.py"

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
        "ADDITIONAL COST EXAMPLES:",
        "  DISCARD_RANDOM: {amount: 1}  -- 'discard a random card as additional cost'",
        "  REVEAL_CARD_COST_GTE: {amount: 2}  -- 'reveal a card with cost 2 or greater'",
        "  REVEAL_CARD_COST_LTE: {amount: 1}  -- 'reveal a card with cost 1 or less'",
        "  BANISH_NAMED_GRAVEYARD_OPTIONAL: {slug_contains: 'nimblism', flag: 'banished_nimblism'}",
        "    -- optional banish from graveyard; sets turn flag if banished (for conditional bonus)",
        "  PUT_HAND_CARD_BOTTOM: {}  -- 'put a card from hand on bottom of deck'",
        "",
        "KEY EFFECT PARAMS:",
        "  DRAW: {amount: int}",
        "  DISCARD: {amount: int, player: SELF|OPPONENT, random: bool}",
        "  MODIFY_ATTACK_POWER: {amount: int}",
        "  GO_AGAIN: {}",
        "  GAIN_LIFE: {amount: int}",
        "  DEAL_DAMAGE: {amount: int, target: SELF|OPPONENT}",
        "  DEAL_ARCANE: {amount: int, target: SELF|OPPONENT}",
        "  CREATE_TOKEN: {token: str, count: int}",
        "  GAIN_RESOURCES: {amount: int}",
        "  NEXT_ATTACK_BONUS: {amount: int}",
        "  NEXT_WEAPON_ATTACK_BONUS: {amount: int, go_again: bool, hit_go_again: bool}",
        "  ALL_ATTACKS_BONUS: {amount: int}",
        "  ALL_ATTACKS_HIT_DRAW: {amount: int}",
        "  NEXT_ATTACK_HIT_DRAW: {amount: int}",
        "  NEXT_LOW_COST_ATTACK_BONUS: {amount: int}  -- cost<=1 attacks",
        "  NEXT_HIGH_COST_ATTACK_BONUS: {amount: int} -- cost>=2 attacks",
        "  BANISH: {amount: int, from_zone: TOP_DECK}",
        "  OPT: {amount: int}",
        "  RELOAD: {}",
        "  SEARCH_DECK: {filter_types: list, slug_contains: str}",
        "  RETURN_TO_HAND: {}",
        "  PUT_BOTTOM_DRAW: {}  -- put a hand card to bottom of deck, then draw",
        "  PUT_COUNTER: {counter_type: str, amount: int}",
        "  REMOVE_COUNTER: {counter_type: str, amount: int}",
        "  INTIMIDATE: {}",
        "  DOMINATE: {}",
        "  GRANT_KEYWORD: {keyword: str}",
        "  INJECT_TRIGGER: {trigger: str, conditions: [...], effects: [...]}",
        "  SET_FLAG: {flag: str, scope: CURRENT|NEXT}",
        "  GAIN_ACTION_POINTS: {amount: int}",
        "  DISCARD_RANDOM_CONDITIONAL: {amount: int, power_gte: int, ap_gain: int, draw: int, go_again: bool}",
        "  AMP: {amount: int}",
        "",
        "KEY CONDITION PARAMS:",
        "  COMBO: {names: [str]}  -- last chain link slug matches one of names",
        "  COMBO_CONTAINS: {substring: str}  -- last chain link slug contains substring",
        "  WEAPON_SUBTYPE_IN: {values: [str]}  -- e.g. [Hammer, Sword, Dagger]",
        "  ATTACK_COST_GTE: {amount: int}",
        "  COUNTER_GTE: {counter_type: str, min: int}",
        "  FLAG_SET: {flag: str}",
        "  HAS_KEYWORD: {keyword: str}",
        "  SURGE: {amount: int}",
        "  ATTACK_CLASS_IN: {classes: [str]}  -- e.g. [Ninja, Guardian]; checks attack_card.classes",
        "  OR: {any: [condition, ...]}",
        "  AND: {all: [condition, ...]}",
        "  NOT: {inner_type: str, ...params}",
        "",
        "CONDITIONS ON EFFECTS: an effect object may have a 'conditions' key (list) to gate only that effect.",
        "CONDITIONS ON ABILITIES: an ability may have a 'conditions' key (list) — ALL must pass or nothing fires.",
        "=== END DSL REFERENCE ===",
    ]
    return "\n".join(lines)


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

{COMMON_MISTAKES}

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
    output = run_claw(prompt, verbose=verbose, model=model)

    if output in ("CLAW_TIMEOUT",) or output.startswith("CLAW_ERROR"):
        print(f"  [verify] claw-code failed, keeping original")
        return json_content

    cleaned = re.sub(r'```(?:json)?\s*', '', output)
    cleaned = re.sub(r'```\s*', '', cleaned).strip()

    if cleaned.upper().startswith("LOOKS_GOOD"):
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

def build_implementation_prompt(card: dict, dsl_ref: str, queue: list[dict] | None = None,
                                embed_model: str = "qwen3-embedding:4b") -> str:
    card_block = json.dumps({k: v for k, v in card.items() if k != "status"}, indent=2, ensure_ascii=False)
    dynamic = build_dynamic_examples(card, queue or [], embed_model=embed_model) if queue else ""
    extra = f"\n{dynamic}\n" if dynamic else ""
    return f"""\
You are implementing a card effect JSON file for the Flesh and Blood trading card game simulator.

{dsl_ref}

{EXAMPLES}
{extra}
{COMMON_MISTAKES}

=== YOUR TASK ===

Generate a JSON effect file for this card:

{card_block}

RULES:
1. Only include abilities that actually DO something (trigger an effect, grant keywords, modify state).
   - Pure stat cards (just power/defense, no effect text) should output: {{"slug": "{card["slug"]}", "abilities": []}}
   - Cards that are "Specialization" only (restricted to a hero) but have no other effect also output empty abilities.
2. Use ONLY effect/condition/cost types listed in the DSL REFERENCE above.
3. CRITICAL — costs vs effects:
   - "As an additional cost to play X, ..." -> use "additional_cost" array on the ability (NEVER model as an effect).
     The card CANNOT be played if the cost is unsatisfiable (e.g. DISCARD_RANDOM when hand is empty).
   - "Instead of paying its cost, you may ..." -> use "alternative_cost" array on the ability.
   - If an effect says "discard a card" WITHOUT "as an additional cost", it IS an effect (use DISCARD effect type).
4. If you believe a new DSL type is genuinely required (not expressible with existing types), output this line and STOP:
   NEEDS_NEW_DSL: <brief reason>
5. Slugs use underscores (e.g. "alpha_rampage_red"), never hyphens.
6. Output ONLY the raw JSON object — no markdown fences, no explanation, no extra text.
7. The JSON must parse cleanly (no trailing commas, valid booleans as true/false).

Output the JSON now:
"""


def build_test_prompt(card: dict, json_content: str) -> str:
    return f"""\
You are writing pytest unit tests for a Flesh and Blood card simulator.

The card being tested is:
  slug: {card["slug"]}
  name: {card["name"]}
  type: {card["type_text"]}
  functional text: {card["functional_text"] or "(none)"}

The JSON effect definition is:
{json_content}

Write 1-3 pytest test functions that verify this card's effects work correctly.
Tests should import from engine modules and use the DSL dispatch system.
Use this import pattern at the top:

```python
import pytest, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.card_effects.dsl import dispatch, get_card
```

RULES:
1. Each test function name must start with `test_{card["slug"]}_`.
2. Tests should be self-contained — create minimal mock state objects if needed.
3. Focus on: ability fires on correct trigger, condition gates correctly, effect produces expected state change.
4. If the card has empty abilities (no effects), write one smoke test that confirms get_card returns None or has no abilities.
5. If you believe you cannot write a correct test without new infrastructure, output:
   NEEDS_NEW_DSL: <brief reason>
   and stop.
6. Output ONLY valid Python — no markdown fences, no extra explanation.

Output the test functions now:
"""


# ---------------------------------------------------------------------------
# claw-code runner
# ---------------------------------------------------------------------------

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


def process_test_output(slug: str, output: str) -> None:
    """Append generated test functions to test_wtr_generated.py, or write review note."""
    if output in ("CLAW_TIMEOUT", ) or output.startswith("CLAW_ERROR"):
        print(f"  [TEST ERROR] claw-code failed for test generation: {output[:80]}")
        return

    if "NEEDS_NEW_DSL:" in output:
        reason = output.split("NEEDS_NEW_DSL:", 1)[1].strip().splitlines()[0]
        _write_review_note(slug, reason, output, label="test")
        print(f"  [TEST REVIEW] {slug} -> needs_review/{slug}_test.md")
        return

    # Strip <think>...</think> blocks (qwen3 chain-of-thought)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', output, flags=re.IGNORECASE).strip()

    # Strip markdown fences if present
    cleaned = re.sub(r'```python\s*', '', cleaned)
    cleaned = re.sub(r'```\s*', '', cleaned)
    cleaned = cleaned.strip()

    # Extract from first def test_ found anywhere in the output
    match = re.search(r'((?:^|\n)(def test_[\s\S]+))', cleaned)
    code = match.group(2).strip() if match else ''

    if not code:
        print(f"  [TEST WARN] No recognisable test code for {slug}")
        return

    # Ensure output file has a header
    if not TEST_OUTPUT.exists():
        TEST_OUTPUT.write_text(
            f'"""Auto-generated pytest tests for {SET_CODE.upper()} card DSL implementations.\n'
            'Generated by scripts/auto_implement_wtr.py — do not edit manually.\n"""\n'
            "from __future__ import annotations\n"
            "import json, sys\n"
            "from pathlib import Path\n"
            "ROOT = Path(__file__).resolve().parent.parent\n"
            "sys.path.insert(0, str(ROOT))\n"
            "from engine.card_effects.dsl import dispatch, get_card\n\n",
            encoding="utf-8",
        )

    with TEST_OUTPUT.open("a", encoding="utf-8") as f:
        f.write(f"\n# --- {slug} ---\n")
        f.write(code)
        f.write("\n")

    print(f"  [TEST] tests appended -> tests/test_wtr_generated.py")


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
                        help="Skip the verification pass after implementation.")
    parser.add_argument("--debug", action="store_true",
                        help="Print raw claw-code output for every card.")
    parser.add_argument("--model", default=None,
                        help="Ollama model for implementation (e.g. qwen3-coder:30b).")
    parser.add_argument("--verify-model", default=None, dest="verify_model",
                        help="Ollama model for verification pass (e.g. fab-rules-ft:latest).")
    parser.add_argument("--embed-model", default="qwen3-embedding:4b", dest="embed_model",
                        help="Ollama embedding model for dynamic example selection (default: qwen3-embedding:4b).")
    parser.add_argument("--set", default="wtr", dest="set_code",
                        help="Set code to process (e.g. wtr, arc, cru). Default: wtr.")
    args = parser.parse_args()

    # Remap paths based on --set
    global SET_CODE, WTR_DIR, QUEUE_PATH, REVIEW_DIR, TEST_OUTPUT
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

        # Run implementation
        print(f"  [impl] calling claw-code... (prompt {len(impl_prompt)} chars)")
        impl_output = run_claw(impl_prompt, verbose=args.verbose, model=args.model)
        status, json_content = process_impl_output(slug, impl_output, debug=args.debug)

        # Run verification pass to catch structural errors
        if status == "done" and not args.skip_verify:
            verify_model = args.verify_model or args.model
            print(f"  [verify] checking JSON (model={verify_model or 'default'})...")
            json_content = run_verification_pass(card, json_content, dsl_ref,
                                                 model=verify_model, verbose=args.verbose)
            # Write the (possibly corrected) JSON back to disk
            out_path = WTR_DIR / f"{slug}.json"
            out_path.write_text(json_content, encoding="utf-8")

        card["status"] = status
        save_queue(queue)

        print(f"  [{status.upper()}] {slug}")

        # Run test generation if implementation succeeded
        if status == "done" and not args.skip_tests:
            print("  [test] calling claw-code for tests...")
            test_prompt = build_test_prompt(card, json_content)
            test_output = run_claw(test_prompt, verbose=args.verbose, model=args.model)
            process_test_output(slug, test_output)

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

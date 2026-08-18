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
import ast
import functools
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

# Windows redirects stdout as cp1252; printing a card name with a non-cp1252 char
# (curly apostrophes, accents — common after a card-data refresh) then crashes the
# whole run with UnicodeEncodeError. Force utf-8 with a safe fallback.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Run control (pause / resume / stop), driven by scripts/pipeline_gui.py
# ---------------------------------------------------------------------------
# A single JSON file the GUI writes and this script reads AT CARD BOUNDARIES
# only. Never mid-card: the queue is saved once per card, so a boundary is the
# one place where stopping loses nothing and a half-generated card can't be
# left behind. A file (rather than a signal or a pipe) means control also works
# when the run was started from a terminal, and survives the GUI being closed.
CONTROL_PATH = ROOT / ".pipeline_control.json"


def read_control() -> dict:
    """Current control state; missing/corrupt file means 'just keep going'."""
    try:
        return json.loads(CONTROL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def wait_while_paused(poll: float = 0.5) -> bool:
    """Block while paused. Returns False when the run should stop.

    Called at the top of each card. Prints a marker line on each transition so
    a watching UI can distinguish "finishing the current card" from "idle".
    """
    import time
    announced = False
    while True:
        control = read_control()
        if control.get("stop"):
            print("[control] STOPPED at card boundary — queue is saved, "
                  "re-run to resume", flush=True)
            return False
        if not control.get("paused"):
            if announced:
                print("[control] RESUMED", flush=True)
            return True
        if not announced:
            print("[control] PAUSED at card boundary — nothing is mid-flight, "
                  "your machine is free", flush=True)
            announced = True
        time.sleep(poll)
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


# Card text -> the primitive that already implements it. Every entry here is a
# defect class actually found in the corpus: the author invented a private flag
# (or a wrong ability_type) for a mechanic the DSL ALREADY expressed, because the
# prompt listed the type name among ~200 others with no hint of when to use it.
# Four whole mechanics needed NO new engine code once the right primitive was
# found — this block is what makes them findable.
PRIMITIVE_RECIPES = """
=== HOW TO SAY IT — text patterns and the primitive that implements them ===

NEVER invent a flag. If you are about to write {"type":"FLAG_SET","flag":"..."}
for a mechanic, the primitive almost certainly already exists below. A FLAG_SET
on a flag nothing sets is an ability that can NEVER fire.

"if you've <done X> this turn"          -> {"type":"EVENT_THIS_TURN","event":"<e>","qualifier":"<q>"}
    events: damage (qualifier = damage type), pitch (colour/class/talent),
            banish, draw, create (token slug or category), play (colour, type,
            subtype, class, talent, card name, attack_action, non_attack_action),
            transcend, graveyard (qualifier = a type, e.g. "instant")
    "ANOTHER blue card" -> add "count": 2 (this card's own play is recorded too)

"if you've destroyed a <thing> this turn"  -> {"type":"DESTROYED_THIS_TURN","name":"<thing>"}

"Combo - If <Card> was the last attack this combat chain"
                                        -> {"type":"LAST_CHAIN_ATTACK","name":"<Card Name>"}
    also takes talent / class / subtype / hit. NEVER the type "COMBO" — that is a
    different, older condition and your params will be silently ignored.

"Reprise - If the defending hero has defended with a card from their hand"
                                        -> {"type":"REPRISE"}

"Your next <arrow/dagger/sword/angel> attack this turn gets +N"
    -> {"type":"MODIFY_NEXT_ATTACK","mod":"add","amount":N,
        "filter":[{"type":"ATTACK_SUBTYPE_IN","subtypes":["Arrow"]}]}
    by class instead: {"type":"ATTACK_CLASS_IN","classes":["Brute"]}
    on a marked hero:  {"type":"OPPONENT_IS_MARKED"}
    NEVER a SET_FLAG + flag-gated STATIC: that buffs EVERY attack for the rest of
    the turn, not just the next one.

"weapons you control gain +N until end of turn"
    -> {"type":"MODIFY_ATTACKS_THIS_TURN","mod":"add","amount":N,
        "filter":[{"type":"ATTACK_IS_WEAPON"}]}

"while this has more {p} than its base {p}"  -> {"type":"ATTACK_POWER_GT_BASE"}

"X is the number of <Draconic> chain links you control"
    -> "amount": {"type":"COUNT_CHAIN_LINKS","talent":"Draconic"}
"X is the number of <doom> counters on this"
    -> "amount": {"type":"COUNT_COUNTERS","counter":"doom"}
    An unknown amount STRING resolves to 0, so the effect silently does nothing.

"... , instead <bigger effect>"          -> ONE {"type":"CONDITIONAL_EFFECT",
                                              "when":[...],"then":[...],"else":[...]}
    Two effects gated on the same condition give you BOTH (3 and 4 = 7).

=== ability_type — as fatal to get wrong as a dead flag ===
An Attack Action card ("Action - Attack") is NOT an ATTACK_REACTION.
A card that resolves when PLAYED is PLAY — INSTANT means an ACTIVATED ability
with instant timing ("Instant - Destroy this: ...") and fires on ON_ACTIVATE.
Reprise/Combo clauses belong on the SAME ability_type as the card's main effect.
=== END ===
"""


def build_dsl_reference() -> str:
    """Return a compact DSL reference string for injection into prompts."""
    # Both registration forms: `if etype == "X"` AND `if etype in ("X","Y")`.
    # Matching only `==` omitted 30 types the VALIDATOR accepts — including
    # EVENT_THIS_TURN, CONDITIONAL_EFFECT, OR and AND — so the model was told
    # its way of expressing "if you've done X this turn" did not exist, and
    # invented a flag instead. The prompt vocabulary and the validator
    # vocabulary must be the same set.
    def _types(fname: str, kind: str) -> list[str]:
        src = DSL_DIR / fname
        eq = _extract_types_from_source(src, rf'if {kind} == "([A-Z_0-9]+)"')
        tup: list[str] = []
        for group in _extract_types_from_source(src, rf'if {kind} in \(([^)]*)\)'):
            tup += re.findall(r'"([A-Z_0-9]+)"', group)
        seen, out = set(), []
        for t in eq + tup:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    effect_types = _types("effect_types.py", "etype")
    condition_types = _types("condition_types.py", "ctype")
    cost_types = _types("cost_types.py", "ctype")
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
        PRIMITIVE_RECIPES,
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
        json_path = _card_out_dir(slug) / f"{slug}.json"
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


@functools.lru_cache(maxsize=1)
def _slug_index_by_slug() -> dict:
    try:
        idx = json.loads((ROOT / "card_data" / "slug_index.json").read_text(encoding="utf-8"))
        return idx.get("by_slug", idx)
    except Exception:
        return {}


def _card_set_folder(slug: str, default: str) -> str:
    """The set folder a card must be filed under — one of its REAL printed set
    codes (HNT012 -> hnt), matching tests/test_card_json_hygiene.py. A card's
    print set is NOT its class or the work-queue's name (e.g. the "fsa" product
    queue holds cards whose set code is AUR), so writing to json/<queue>/ files
    them wrong. Prefer the active --set when the card was actually printed there
    (keeps a set's own cards together); otherwise pick a deterministic printed
    code. Falls back to `default` for unknown slugs (e.g. engine tokens)."""
    entry = _slug_index_by_slug().get(slug) or {}
    codes = sorted({
        "".join(ch for ch in ident if ch.isalpha()).lower()
        for ident in (entry.get("setIdentifiers") or [])
    })
    if not codes:
        return default
    return default if default in codes else codes[0]


def _card_out_dir(slug: str) -> Path:
    """Directory the card's JSON belongs in, created if needed."""
    d = ROOT / "engine" / "card_effects" / "json" / _card_set_folder(slug, SET_CODE)
    d.mkdir(parents=True, exist_ok=True)
    return d


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
        # Skip cards whose whole implementation is one bare keyword grant. They
        # win the "smallest" contest for their ability_type and so ship in every
        # prompt, while teaching nothing but "emit this keyword" — the pen run
        # copied the smallest STATIC_TRIGGERED card (an ON_DEFEND INTIMIDATE)
        # onto 13 unrelated Blade Break cards. A slightly larger example that
        # actually demonstrates structure is worth far more.
        _effs = [e for ab in abilities for e in (ab.get("effects") or [])]
        if len(_effs) == 1 and set(_effs[0]) <= {"type"}:
            continue
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
7. IMPLEMENT EVERY CLAUSE. Each sentence/clause of the functional text must appear
   as an effect (or cost). Do NOT stop after the first verb. Watch for CONSEQUENT
   clauses joined by "If you do" / "then" / ". " — the payload after them is
   usually the real effect and is the most commonly dropped part.
   Example — "you may destroy this. If you do, deal 1 arcane damage to them":
     BOTH must appear -> a DESTROY_PERMANENT (target self) AND a DEAL_ARCANE (or
     the DSL's arcane-damage effect) to the opponent. Missing the damage clause
     is WRONG. Count the distinct game actions in the text and match your effect
     list to that count.
8. Slugs use underscores, never hyphens. Output ONLY the raw JSON object — no
   markdown fences, no prose. It must parse (no trailing commas; true/false).
9. "INSTEAD" / "If X, instead Y" is a MUTUALLY-EXCLUSIVE choice, not two things.
   The base case must ALWAYS happen when the condition is false. Two ways:
   (a) one effect with CONDITIONAL_EFFECT {"when":[<cond>], "then":[<Y>], "else":[<X>]};
   (b) OR two effects: <X> gated on NOT the condition, <Y> gated on the condition.
   NEVER gate the WHOLE ability on the condition (that zeroes the default case —
   e.g. "deal 3, instead 4 if starfall" must still deal 3 without starfall), and
   NEVER emit both an always-on <X> and an always-on <Y> (that does X+Y).
   Example — "Deal 3 arcane; if you rolled a 6 this turn, instead deal 5":
     {"ability_type":"PLAY","effects":[{"type":"CONDITIONAL_EFFECT",
       "when":[{"type":"FLAG_SET","flag":"ROLLED_6"}],
       "then":[{"type":"DEAL_ARCANE","amount":5}],
       "else":[{"type":"DEAL_ARCANE","amount":3}]}]}
10. "You may X. If you do, Y." is a MAY block — put BOTH X and Y inside one
    {"type":"MAY","effects":[<X>,<Y>]}. Declining runs neither, so "if you do"
    falls out for free. NEVER emit X and Y unconditionally, and NEVER model "you
    may" as always-happening.
11. Only use JSON KEYS that appear in the DSL REFERENCE / EXAMPLES. Invented keys
    like "additional_effects", "alternative_effects", "additional_cost" on a
    non-PLAY-cost, etc. are SILENTLY IGNORED — the clause then does nothing. If a
    branch/extra effect is needed, put it in "effects" (with per-effect
    "conditions"), not a made-up key.
12. "create a <token> under their control" / "under another hero's control" ->
    add "player":"OPPONENT" to CREATE_TOKEN. Default (no player) creates it under
    YOU. Match the controller named in the text.
13. ability_type INSTANT is ONLY for ACTIVATED abilities on a permanent that STAY
    in play ("Instant - {cost}: effect"). A played instant-speed ACTION card
    (type line says Instant but there is NO "Instant -  ... :" activated cost) is
    ability_type PLAY — its effect resolves when played. (INSTANT fires on
    activation, never on play, so a played card with ability_type INSTANT does
    NOTHING.)
14. LISTS ARE LISTS. Sub-effects always go in a LIST key, never a singular one.
    Write "effects":[{...}] on MAY, "modifications":[{...}] on APPLY_CONTINUOUS,
    "on_success":[{...}] on PAY_OR_DAMAGE/ROLL, "on_failure":[{...}] on
    PAY_OR_ELSE. A singular "effect":{...} is a DIFFERENT key — the whole clause
    is dropped and the ability does nothing.
15. GAIN: "asset" vs "keyword" are NOT interchangeable. Resources, life, action
    points and chi are ASSETS -> {"type":"GAIN","asset":"ACTION_POINTS",
    "amount":N} (assets: RESOURCE_POINTS, LIFE_POINTS, ACTION_POINTS, CHI_POINTS).
    "keyword" grants a COMBAT KEYWORD to the current attack (go again, dominate).
    Using "keyword":"ACTION_POINTS" silently grants a nonsense keyword and gains
    nothing.
16. WHO PAYS decides the effect type. "<they> do X unless they pay {r}" targets
    the OPPONENT -> {"type":"PAY_OR_ELSE","player":"OPPONENT","resources":N,
    "on_failure":[<X with "player":"OPPONENT">]}. PAY_OR_DAMAGE is only for "deals
    N damage to YOU unless YOU pay". Getting this backwards makes the wrong player
    pay.
17. Amounts that are a NUMBER must be a number. "resource"/"resources"/
    "resource_cost" hold a QUANTITY (2), not a resource NAME ("RESOURCE_POINTS").
    If you name the resource, the quantity must be in "amount".
18. A filter you write must be a filter the condition READS. Class/talent/color
    filters on CARD_IN_ZONE are "card_class"; keyword filters are "keywords":[...];
    attacker-vs-defender on IN_COMBAT is "combat_role":"ATTACKER"/"DEFENDER". An
    unread filter key makes the condition TOO PERMISSIVE (it fires when it should
    not) rather than failing loudly — so prefer a key from the REFERENCE over one
    that merely reads well.
19. IMPLEMENT ONLY WHAT THE TEXT SAYS. Never add an ability the card does not
    have. A card whose whole text is a keyword (e.g. "**Blade Break**") gets
    {"abilities": []} — it does NOT get an ON_DEFEND ability granting some other
    keyword. 27 cards were found granting an INTIMIDATE they never had, all of
    them Blade Break equipment. If you catch yourself adding an effect no clause
    asked for, delete it.
20. A NAMED KEYWORD MECHANIC HAS A KEYWORD EFFECT — never hand-roll it with
    SET_FLAG. "the crowd cheers you" -> {"type":"CROWD_CHEER"} and the check
    "if you've been cheered this turn" -> {"type":"IS_CHEERED"}; likewise
    CROWD_BOO / IS_BOOED, MARK / OPPONENT_IS_MARKED. A private
    SET_FLAG/FLAG_SET pair is invisible to every other card and to replacement
    effects: 8 cards invented FOUR different spellings of the cheer flag, two of
    them checking a flag no card ever set, so those abilities could never fire.
    "Whenever the crowd cheers you, X" is a TRIGGER: ability_type TRIGGERED with
    "trigger":"ON_CHEER" (ON_BOO for boos) — not a condition on some other event.
21. "YOUR NEXT <thing> THIS TURN" IS ONE-SHOT. Use
    {"type":"MODIFY_NEXT_ATTACK","mod":"add","amount":N,"filter":[...]} for power
    and {"type":"GRANT_NEXT_ATTACK","keyword":"GO_AGAIN","filter":[...]} for a
    keyword; both are consumed by the FIRST attack matching "filter". A SET_FLAG
    plus a flag-gated STATIC applies to EVERY attack for the rest of the turn,
    which is not what "next" means and is worse than omitting the clause. Put the
    restriction ("your next WEAPON attack") in "filter", not in the static's
    conditions.
22. ONE SLUG, ONE FILE, RIGHT FOLDER. The loader REJECTS a slug defined by more
    than one JSON file — both copies stop working, so never create a second file
    for a card that already exists; edit the existing one. Choose the folder from
    the card's setIdentifiers, never from its class or from the set you happen to
    be working on.
23. **NEVER INVENT A FLAG.** This is the single most common way a card ends up
    doing nothing. FLAG_SET compiles to `flag in player.current_turn_effects`, so
    a flag NOTHING WRITES is permanently false and the ability it gates CAN NEVER
    FIRE — while the card loads, passes its tests and looks finished. 167 invented
    flags across 195 cards were found this way.
    A FLAG_SET is legitimate in exactly two cases:
      (a) the SAME card sets it earlier with SET_FLAG (a two-part combo), or
      (b) it is one of the engine's own markers, which are LOWERCASE:
          "boosted_this_turn", "cranked_this_turn", "played_lightning",
          "crowd_booed", "crowd_cheered", "fused_<slug>", "DIE_ROLLED_SIX",
          "destroyed_this_turn:<name>".
    Writing BOOSTED_THIS_TURN or FUSED instead of the lowercase engine marker is
    the same bug — the case must match exactly. If the state you need is not in
    that list and your card does not set it itself, the mechanic does not exist:
    output NEEDS_NEW_DSL rather than inventing a flag name that reads plausibly.
24. "IF YOU HAVE DESTROYED A <thing> THIS TURN" has a generic condition — do not
    invent MIGHT_TOKEN_DESTROYED_THIS_TURN or ITEM_DESTROYED_THIS_TURN. Use
    {"type":"DESTROYED_THIS_TURN","name":"might"}. "name" matches the destroyed
    card's slug, type OR subtype ("might", "item", "aura", "lightning flow"), so
    pick whichever the text names. Add "player":"OPPONENT" when the text says
    someone ELSE destroyed it ("if the attack's controller has destroyed ...").
25. "THIS MAY ONLY DEFEND ... IF <x>" is a defend-LEGALITY restriction, not a
    triggered ability — a trigger fires too late, once the card is already
    defending. Use an ability with "ability_type":"DEFEND_RESTRICTION" carrying
    "conditions" and NO effects; the card is simply not offered as a defender
    while they are unmet.
=== END RULES ==="""


# Real, verified-passing tests (each confirmed under the gate's own harness),
# keyed by ability_type. Injected into the test prompt so the auditor copies a
# working pattern for THIS card's kind of ability — correct trigger event, real
# attribute names, real zones — instead of guessing.
GOLD_TESTS = {
    "ACTIVATE": '''def test_blossom_of_spring_activate():
    # "Action - Destroy this: Gain {r}. Go again" — activate() runs the REAL flow,
    # so both the effect AND the "Destroy this" cost are checkable.
    st = _make_state(); st.card_db = DB
    card = _card("blossom_of_spring")
    st.players[1].chest.add(card)
    before = st.players[1].resources
    activate(st, card)
    assert st.players[1].resources == before + 1      # the effect (after the colon)
    assert card not in st.players[1].chest.cards       # the "Destroy this" cost was paid''',
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
    "COMBAT": '''def test_hunters_klaive_on_hit_marks():
    # "When this hits a hero, mark them." attack() sets up a REAL combat (this card
    # attacking the opponent hero); hit() lands the hit so ON_HIT fires.
    st = _make_state(); st.card_db = DB
    card = _card("hunters_klaive")
    st.players[1].weapon1.add(card)
    attack(st, card)
    hit(st)
    assert st.players[2].class_counters.get("marked", 0) >= 1''',
}

_GOLD_BY_ABILITY = {
    "ACTIVATE": "ACTIVATE", "ACTION": "ACTIVATE",
    "PLAY": "PLAY", "INSTANT": "PLAY",
    "ATTACK_REACTION": "PLAY", "DEFENSE_REACTION": "PLAY",
    "TRIGGERED": "TRIGGERED", "STATIC_TRIGGERED": "TRIGGERED",
    "STATIC": "TRIGGERED", "WHILE_STATIC": "TRIGGERED", "MODAL": "PLAY",
}


def _gold_test_for(json_content: str, card: dict | None = None) -> str:
    """Pick the verified gold test that best matches the generated card. Anything
    that resolves through combat gets the combat example (real attack + hit):
    a combat trigger (ON_HIT/ON_ATTACK/ON_DEFEND) on ANY ability_type, or an
    Attack card whose whole effect (e.g. a conditional power pump) is observed
    mid-combat. Everything else keys off ability_type."""
    try:
        ab = (json.loads(json_content).get("abilities") or [{}])[0]
        at = ab.get("ability_type", "")
        trig = (ab.get("trigger") or "").upper()
    except Exception:
        at, trig = "", ""
    if trig in ("ON_HIT", "ON_ATTACK", "ON_DEFEND"):
        return GOLD_TESTS["COMBAT"]
    # An Attack action/weapon whose effect (often a STATIC/WHILE power pump) is
    # only observable once it is attacking -> use the combat pattern.
    type_text = ((card or {}).get("type_text") or "")
    if "Attack" in type_text:
        return GOLD_TESTS["COMBAT"]
    return GOLD_TESTS[_GOLD_BY_ABILITY.get(at, "TRIGGERED")]


def build_implementation_prompt(card: dict, dsl_ref: str, queue: list[dict] | None = None,
                                embed_model: str = "qwen3-embedding:4b") -> str:
    card_block = json.dumps({k: v for k, v in card.items() if k != "status"}, indent=2, ensure_ascii=False)
    dynamic = build_dynamic_examples(card, queue or [], embed_model=embed_model) if queue else ""
    extra = f"\n{dynamic}\n" if dynamic else ""

    # Prefer THIS CARD's reference logic over generic few-shot examples.
    #
    # The examples are chosen as the SMALLEST loading card per ability_type, so
    # the same handful ships in every prompt — and the smallest STATIC_TRIGGERED
    # card in the corpus grants INTIMIDATE, which a 14B copied onto 13 unrelated
    # Blade Break cards in the pen run. A minimal example is maximally copyable,
    # which is precisely the problem: the demonstration outweighs the prose rule
    # forbidding it.
    #
    # Talishar's own per-card logic is keyed by the same slug and is specific to
    # THIS card, so it cannot teach another card's shape. It covers ~80% of the
    # remaining corpus (though only ~13% of pen/sup, the newest sets). Where it
    # exists it replaces the examples; otherwise we fall back to them.
    talishar = _talishar_reference(card["slug"])
    if talishar and talishar.strip():
        grounding = f"""=== REFERENCE IMPLEMENTATION (Talishar) ===

Talishar is a different, independently written FAB engine (PHP). Below is ITS
logic for THIS EXACT CARD. Use it to understand WHAT THE CARD DOES — which
clauses exist, what is optional, who chooses, what is a cost vs an effect.

Do NOT translate it line by line, and do NOT copy its structure: it is another
engine with different primitives, and it is a second opinion, not ground truth
(Talishar's own README disclaims correctness). Where it disagrees with the
printed card text, THE PRINTED TEXT WINS.

{talishar.strip()}

=== END REFERENCE ===
"""
    else:
        grounding = build_real_examples()

    return f"""\
You are implementing a card effect JSON file for the Flesh and Blood trading card game simulator.

{dsl_ref}

{grounding}
{extra}
{STRUCTURAL_RULES}

=== YOUR TASK ===

Generate a JSON effect file for this card (follow the RULES and EXAMPLES above):

{card_block}

Output the JSON now:
"""


def _talishar_reference(slug: str) -> str:
    """Talishar's own logic for this slug, as a prompt-ready 'second opinion' block
    (empty if the local backend is absent or has no per-card logic). Grounds the
    auditor's test in reference behaviour — e.g. reveals a persistent combat-chain
    effect our impl modelled as a one-shot ON_HIT. Not authoritative (Talishar's
    README disclaims it); a divergence is a review signal, not proof."""
    try:
        import talishar_reference as _T
        return _T.reference_text(slug)
    except Exception:
        return ""


def build_test_prompt(card: dict, json_content: str) -> str:
    gold = _gold_test_for(json_content, card)
    tal = _talishar_reference(card["slug"])
    tal_block = (
        "\nTALISHAR REFERENCE — how the Talishar engine implements this card (a\n"
        "SECOND OPINION on the intended behaviour; may have bugs, not authoritative).\n"
        "Use it to assert the RIGHT observable outcome; if our JSON clearly\n"
        "contradicts it, still test what the CARD TEXT says:\n"
        f"{tal}\n"
    ) if tal else ""
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
provides _make_state, _card, DB, dispatch, get_card, activate(state, card),
attack(state, card), hit(state), stock_deck(state, pid, n=20),
give_token(state, pid, slug, n=1) and set_turn_flag(state, pid, "marker")
— do NOT redefine them. Use stock_deck before
any "top of deck" effect (the deck starts EMPTY) and give_token for
"if you control a X token" preconditions (slugs are lowercase: 'might', 'gold').

To stage TURN STATE ("if you've attacked this turn", "if an attack action was
played this turn") use `set_turn_flag(st, 1, "did_this_turn:attack")`. There is
NO `st.flags` and NO `st.players[p].flags` dict — inventing one is the single
most common way these tests fail. Turn state lives in
`st.players[p].current_turn_effects`, a list of lowercase string markers.

`_card` and `stock_deck` accept attribute overrides for preconditions:
`_card("x", cost=3)`, `stock_deck(st, 1, n=1, color="yellow")`.

REAL PASSING EXAMPLE (same ability_type):
{gold}
{tal_block}
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
   ONLY reference the card under test: the sole slug you may pass to `_card(...)`
   or `get_card(...)` is "{card["slug"]}". Do NOT invent, name, or `_card()` any OTHER
   card (no "lightning_strike", no helper attacks) — those slugs may not exist
   and will raise. Set up preconditions ONLY with the provided helpers
   (give_token, stock_deck) or by appending to a real zone (e.g.
   `st.players[1].arsenal.cards.append(_card("{card["slug"]}"))`). NEVER invent a
   Player/GameState attribute to set up state (no `might_token_count`, no
   `st.tokens`, no `.max_health`) — that raises AttributeError and proves nothing.
3. Assert OBSERVABLE state using the REAL attribute names (these exact spellings):
   - life: `st.players[p].health`   (there is NO 'life'/'hp' attribute)
   - resources: `st.players[p].resources`   (NOT resource_points)
   - action points: `st.players[p].action_points`;  chi: `st.players[p].chi`
   - zones are objects; use `.cards`: `st.players[p].graveyard.cards`,
     `.arsenal.cards`, `.banished.cards`, `.hand.cards`, `.chest.cards`,
     `.arms.cards`, `.weapon1.cards`, `.permanents.cards`
   - TOKENS (gold, might, seismic_surge, ...) live in `st.players[p].permanents.cards`
     — check them there (`any(c.slug == "gold" for c in st.players[p].permanents.cards)`).
     There is NO `st.tokens` / `st.players[p].tokens` count attribute.
   Do NOT assert on internal registries or flags. Do NOT invent attribute names.
   ASSERT RELATIVE DELTAS, never absolute totals. Capture the observable value
   FIRST, THEN fire the ability, THEN assert the change — order matters:
     `before = len(st.players[2].deck.cards)`  # capture BEFORE firing
     `attack(st, card); hit(st)`               # now fire
     `assert len(st.players[2].deck.cards) == before - 1`
   Capturing `before` AFTER the action makes the delta impossible to observe. Do
   NOT hardcode an absolute number (`== 9`, `== 40`, deck `== 19`) — you do not
   know the starting value and it will be wrong even for a correct card.
4. Fire the ability by its ability_type:
   - ACTIVATE / ACTION -> `activate(st, card)`. This runs the REAL activation
     flow, so it PAYS the card's cost array (e.g. "Destroy this") AND runs the
     effects. You can assert BOTH (the effect, and that the cost happened, e.g.
     the card left its zone).
   - TRIGGERED with a COMBAT trigger (ON_HIT / ON_ATTACK) -> set up a real attack:
     `attack(st, card)` (the card attacks the opponent hero; returns st.combat,
     assert `st.combat.attack_power` for pumps), then `hit(st)` to land the hit
     so ON_HIT fires.
   - Other TRIGGERED -> `dispatch(st, "<TRIGGER>", "<slug>", card=card, event=None)`
     with the trigger from the JSON (ON_EQUIP / ON_ENTER_PLAY / START_OF_TURN / ...).
   - PLAY / INSTANT / ATTACK_REACTION / DEFENSE_REACTION -> `dispatch(st,
     "ON_PLAY", "<slug>", card=card, event=None)`.
   Arsenal holds at most 1 card.
{rule5}
6. If you genuinely cannot write a correct test, output `NEEDS_NEW_DSL: <reason>` and stop.
7. Output ONLY valid Python — no markdown fences, no prose.

Output the test functions now:
"""


# ---------------------------------------------------------------------------
# claw-code runner
# ---------------------------------------------------------------------------

def run_openai_chat(prompt: str, model: str, verbose: bool = False,
                    retries: int = 2, temperature: float = 0.1,
                    seed: int | None = None) -> str:
    """Run a prompt against an OpenAI-compatible /chat/completions endpoint.

    Works with any server that speaks the OpenAI chat API — a standalone
    llama.cpp llama-server, Ollama, LM Studio, etc. Returns the assistant text,
    or a CLAW_TIMEOUT / CLAW_ERROR sentinel (shared with run_claw so the existing
    output parsers handle failures identically).

    `seed` pins sampling so best-of-N auditor attempts draw DIFFERENT candidates
    (each attempt passes a distinct seed); omit it for a single non-pinned call.
    """
    url = BASE_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "stream": False,
    }
    if seed is not None:
        payload["seed"] = seed
    body = json.dumps(payload).encode("utf-8")
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


def run_llm(prompt: str, verbose: bool = False, model: str | None = None,
            temperature: float = 0.1, seed: int | None = None) -> str:
    """Dispatch a prompt to the configured backend (openai endpoint or claw-code).

    `temperature`/`seed` only affect the openai backend; claw ignores them."""
    if BACKEND == "openai":
        if not model:
            return "CLAW_ERROR: openai backend requires an explicit model"
        return run_openai_chat(prompt, model=model, verbose=verbose,
                               temperature=temperature, seed=seed)
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


# The behavioural-test harness, shared verbatim by the execution gate
# (run_generated_test) and the committed test file (append_test) so a test that
# passes the gate passes identically once committed. Provides the exact names the
# test-prompt example uses.
GATE_HARNESS = (
    "import copy, sys\n"
    "from pathlib import Path\n"
    "ROOT = Path(__file__).resolve().parents[1]\n"
    "sys.path.insert(0, str(ROOT))\n"
    "from engine.card import CardDB, Card\n"
    "from engine.card_effects.dsl import dispatch, get_card\n"
    "from engine.card_effects.dsl.loader import load_all_cards\n"
    "from tests.conftest import _make_state as _base_make_state\n"
    "load_all_cards()\n"
    "DB = CardDB()\n"
    "def _make_state(*a, **k):\n"
    "    # Wrap the real _make_state to PRE-STOCK both decks — the base state\n"
    "    # starts with EMPTY decks, so any 'draw a card' / 'banish the top card'\n"
    "    # effect silently no-ops and a correct card fails its assertion. 20\n"
    "    # dummy cards per deck make those effects observable by default.\n"
    "    st = _base_make_state(*a, **k)\n"
    "    st.card_db = DB\n"
    "    for pid in (1, 2):\n"
    "        if len(st.players[pid].deck.cards) == 0:\n"
    "            for _ in range(20):\n"
    "                c = Card(slug='dummy_card', name='dummy', types=['Action']); c.owner = c.controller = pid\n"
    "                st.players[pid].deck.cards.append(c)\n"
    "    return st\n"
    "def _card(slug, owner=1, **overrides):\n"
    "    # Tolerate a slug that isn't a real card: the auditor sometimes builds a\n"
    "    # generic setup/opponent card via _card('some_slug'). DB.get returns None\n"
    "    # for those, and None.owner crashes the whole test (zero signal). Fall\n"
    "    # back to a bare Card so the test can still exercise the card UNDER TEST.\n"
    "    #\n"
    "    # **overrides sets attributes on the built card (_card('x', cost=3),\n"
    "    # pitch=1, power=4, defense=2, types=[...]). The auditor writes these to\n"
    "    # express a legitimate precondition ('a card costing 3 in hand'); before\n"
    "    # they were accepted the call raised TypeError and the sample was lost\n"
    "    # for a reason unrelated to the card under test.\n"
    "    base = DB.get(slug)\n"
    "    if base is None:\n"
    "        c = Card(slug=slug, name=slug, types=['Action'], owner=owner, controller=owner)\n"
    "    else:\n"
    "        c = copy.deepcopy(base); c.owner = c.controller = owner\n"
    "    _ALIAS = {'attack_power': 'power', 'attack': 'power', 'base_attack': 'base_power',\n"
    "              'defense_value': 'defense', 'pitch_power': 'pitch', 'pitch_value': 'pitch'}\n"
    "    for k, v in overrides.items():\n"
    "        setattr(c, _ALIAS.get(k, k), v)\n"
    "    return c\n"
    "def activate(state, card, player_id=1):\n"
    "    # Real activation flow: pays the ability's cost array (e.g. 'Destroy this')\n"
    "    # AND runs its effects. Use this for ACTIVATE/ACTION cards.\n"
    "    from engine.actions import Action, ActionType\n"
    "    from engine.play import apply_action\n"
    "    p = state.players[player_id]; p.action_points = max(1, p.action_points)\n"
    "    apply_action(state, Action(type=ActionType.ACTIVATE_CARD, player_id=player_id, card=card))\n"
    "def attack(state, card, attacker=1):\n"
    "    # Real combat: `card` attacks the opponent HERO. Fires ON_ATTACK and\n"
    "    # recomputes attack_power. Returns state.combat (assert .attack_power for\n"
    "    # pumps). NOTE: for a hero attack the engine leaves combat.attack_target\n"
    "    # None (it is set only when the attack targets a permanent/ally); the\n"
    "    # ATTACK_TARGET_IS_HERO condition relies on that, and 'defending hero'\n"
    "    # effects resolve via the controller's opponent, not attack_target — so\n"
    "    # do NOT set attack_target here.\n"
    "    from engine.state import CombatState\n"
    "    import engine.engine as _E\n"
    "    bp = getattr(card, 'power', None) or getattr(card, 'base_power', None) or 0\n"
    "    state.combat = CombatState(attacker_id=attacker, link_id=1, attack_power=bp, attack_card=card, keywords=[])\n"
    "    state.combat.base_attack_power = bp\n"
    "    dispatch(state, 'ON_ATTACK', card.slug, card=card, event=None)\n"
    "    _E._recalculate_attack_power(state)\n"
    "    return state.combat\n"
    "def hit(state, damage=None, **kw):\n"
    "    # The current attack hits -> fires ON_HIT for the attacking card.\n"
    "    # `damage`/`amount` set the attack's power first, so a test for an\n"
    "    # 'if this deals 4 or more damage' clause can stage that precondition\n"
    "    # instead of raising TypeError on an unexpected kwarg.\n"
    "    dmg = damage if damage is not None else kw.get('amount')\n"
    "    if dmg is not None:\n"
    "        state.combat.attack_power = dmg\n"
    "    ac = state.combat.attack_card; state.combat.hit = True\n"
    "    dispatch(state, 'ON_HIT', ac.slug, card=ac, event=None)\n"
    "def stock_deck(state, pid, n=20, **attrs):\n"
    "    # Add more dummy cards to a deck (decks are pre-stocked with 20 already).\n"
    "    # **attrs set attributes on each stocked card (color='yellow', pitch=3,\n"
    "    # card_type='Arrow'), so 'reveal a yellow card' style preconditions are\n"
    "    # expressible; unknown kwargs used to raise TypeError and lose the sample.\n"
    "    _ALIAS = {'card_type': 'types', 'type': 'types', 'pitch_power': 'pitch'}\n"
    "    for _ in range(n):\n"
    "        c = Card(slug='dummy_card', name='dummy', types=['Action']); c.owner = c.controller = pid\n"
    "        for k, v in attrs.items():\n"
    "            k = _ALIAS.get(k, k)\n"
    "            setattr(c, k, [v] if k == 'types' and isinstance(v, str) else v)\n"
    "        state.players[pid].deck.cards.append(c)\n"
    "    return state.players[pid].deck.cards\n"
    "def set_turn_flag(state, pid, marker):\n"
    "    # Stage a turn-scoped precondition the REAL way. The engine has no\n"
    "    # `state.flags` / `player.flags` dict (44 + 18 recorded gate failures\n"
    "    # invented one); turn state lives in `player.current_turn_effects` as\n"
    "    # lowercase string markers written by the canonical keyword functions.\n"
    "    state.players[pid].current_turn_effects.append(str(marker).lower())\n"
    "def give_token(state, pid, slug, n=1):\n"
    "    # Put n copies of a token under a player via the real create path, so\n"
    "    # 'if you control a X token' conditions see them. Slugs are LOWERCASE\n"
    "    # ('might', 'gold', 'seismic_surge'). Do NOT invent a *_token_count attr.\n"
    "    if getattr(state, 'card_db', None) is None: state.card_db = DB\n"
    "    from engine.effect_keywords import create_token\n"
    "    create_token(state, pid, slug, n)\n\n"
)


def run_generated_test(slug: str, test_code: str, verbose: bool = False) -> tuple[bool, str]:
    """Run the auditor's test in ISOLATION and report whether it passes.

    Writing to a throwaway file (not the shared test_{set}_generated.py) means a
    prior card's broken test cannot poison this card's gate, and only tests that
    actually pass get appended to the committed file. Returns (passed, output).
    """
    # GATE_HARNESS supplies exactly the names the test-prompt example uses
    # (_make_state, _card, DB, dispatch, get_card, activate/attack/hit, ...) —
    # extract_test_code strips the model's own header. The SAME constant is
    # written to the committed test file (append_test), so a test that passes the
    # gate passes identically there.
    header = GATE_HARNESS
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

_BOLD_KW = re.compile(r"\*\*.*?\*\*")


def _is_noop_stub(card: dict, json_content: str) -> bool:
    """True if the impl is effectively a NO-OP the implementer punted on. Mirrors
    the json-hygiene suite so such a card is rejected by the gate (never a false
    'done' with a vacuous test, never a live 'candidate' that does nothing). Two
    forms:
      (1) empty abilities for a card whose text is not purely keywords
          (test_card_with_functional_text_implements_something), and
      (2) any ability with no effects/modes/options — a cost with no payload
          (test_every_ability_has_effects). COST_MODIFIER/REPLACEMENT are exempt."""
    try:
        d = json.loads(json_content)
    except Exception:
        return False
    abilities = d.get("abilities") or []
    # (1) empty abilities but the card has real (non-keyword) rules text
    if not abilities and not d.get("setup"):
        prose = _BOLD_KW.sub("", card.get("functional_text") or "").strip(" \n\t-—,.")
        return bool(prose)
    # (2) an ability that resolves to nothing (only a cost, no effect)
    for ab in abilities:
        atype = (ab.get("ability_type") or "").upper()
        if atype in ("COST_MODIFIER", "REPLACEMENT"):
            continue
        if not (ab.get("effects") or ab.get("modes") or ab.get("options")):
            return True
    return False


def _quarantine_card_json(slug: str) -> None:
    """Move a non-'done' card's JSON OUT of the live corpus. The pipeline writes
    the card JSON to its real set folder before the gate runs, so a card that
    fails the load gate (won't compile) would break load_all_cards() and the
    engine, and a test_failed card would sit in the corpus UNVERIFIED. Keep only
    'done' cards live; park the rest as <slug>.json.quarantine next to the review
    note (the loader globs *.json exactly, so .json.quarantine is ignored) so the
    impl is preserved for a later fix/re-run without polluting anything."""
    src = _card_out_dir(slug) / f"{slug}.json"
    if not src.exists():
        return
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    dest = REVIEW_DIR / f"{slug}.json.quarantine"
    try:
        src.replace(dest)
    except OSError:
        src.unlink(missing_ok=True)


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

    out_path = _card_out_dir(slug) / f"{slug}.json"
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
    """Pull the test function(s) out of an LLM response. '' if none found.

    The extracted text is SYNTAX-VALIDATED before being returned. The model
    routinely appends a prose paragraph after the final test (or leaves a string
    literal unterminated), which made the whole file a SyntaxError and burned the
    sample for a reason unrelated to the card — 21 of the 823 recorded test-gate
    failures are exactly that. When the block does not parse, drop trailing
    top-level statements one at a time and keep the longest prefix of whole test
    functions that does parse, so a good first test is not lost to bad trailing
    output.
    """
    # Strip <think>...</think> chain-of-thought and markdown fences.
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', output, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'```python\s*', '', cleaned)
    cleaned = re.sub(r'```\s*', '', cleaned).strip()
    match = re.search(r'((?:^|\n)(def test_[\s\S]+))', cleaned)
    if not match:
        return ''
    code = match.group(2).strip()
    return _largest_parsing_prefix(code)


def _largest_parsing_prefix(code: str) -> str:
    """The longest prefix of `code` that is valid Python AND ends on a complete
    test function. Returns '' if not even the first function parses."""
    if _parses(code):
        return code
    # Drop trailing LINES until what remains parses. This keeps the longest good
    # prefix in every case: a prose paragraph after the last test costs only the
    # prose, while an unterminated string mid-function falls back to the whole
    # functions before it. (Working per whole-function instead would throw away a
    # good second test just because prose followed it.)
    lines = code.splitlines()
    for cut in range(len(lines), 0, -1):
        candidate = "\n".join(lines[:cut]).rstrip()
        if candidate and _parses(candidate) and re.search(r'(?m)^def test_', candidate):
            return candidate
    return ''


def _parses(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def _is_vacuous_test(code: str) -> bool:
    """True if `code` would pass without proving anything about the card.

    Guards the repair loop: showing the model its failing test invites the
    cheapest possible 'fix' — delete the assertion, or assert something
    trivially true — which would mark the card verified on no evidence. A real
    behavioural test must assert against live game state (`st.` / `state.`) or
    the card object, so a block whose every assert is a literal/constant is
    rejected even though pytest is happy with it.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False  # a syntax error is reported by the gate, not here
    asserts = [n for n in ast.walk(tree) if isinstance(n, ast.Assert)]
    if not asserts:
        return True
    for node in asserts:
        for sub in ast.walk(node.test):
            # A Name/Attribute reference means the assertion reads something
            # from the running state rather than comparing two constants.
            if isinstance(sub, (ast.Attribute, ast.Call)):
                return False
            if isinstance(sub, ast.Name) and sub.id not in ("True", "False", "None"):
                return False
    return True


def append_test(slug: str, code: str) -> None:
    """Append verified test code to the committed test_{set}_generated.py file."""
    docstring = (
        f'"""Auto-generated pytest tests for {SET_CODE.upper()} card DSL implementations.\n'
        'Generated by scripts/auto_implement_wtr.py — do not edit manually.\n"""\n'
    )
    if not TEST_OUTPUT.exists():
        # Same harness the gate runs tests under (build_test_prompt example +
        # run_generated_test header), so appended tests keep passing here.
        TEST_OUTPUT.write_text(docstring + GATE_HARNESS, encoding="utf-8")
    else:
        # The committed file embeds a COPY of the harness from whenever it was
        # created. When the harness gains a helper (set_turn_flag, kwargs on
        # _card/stock_deck), a test that passes the gate would NameError/TypeError
        # here — verified-then-broken, the worst outcome. Refresh the stale header
        # in place, keeping every already-appended test below it.
        existing = TEST_OUTPUT.read_text(encoding="utf-8")
        marker = "\n# --- "
        idx = existing.find(marker)
        header, body = (existing[:idx], existing[idx:]) if idx != -1 else (existing, "")
        if header != docstring + GATE_HARNESS:
            TEST_OUTPUT.write_text(docstring + GATE_HARNESS + body, encoding="utf-8")
            print(f"  [test] refreshed stale harness header in {TEST_OUTPUT.name}")
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
    parser.add_argument("--auditor-samples", type=int, default=3, dest="auditor_samples",
                        help="Best-of-N: the auditor gets up to N seeded attempts to write a "
                             "passing test; the first that clears the gate wins (early-exit). "
                             "Beats a stochastic 14B's run-to-run variance. Default: 3, set 1 to disable.")
    parser.add_argument("--set", default="wtr", dest="set_code",
                        help="Set code to process (e.g. wtr, arc, cru). Default: wtr.")
    args = parser.parse_args()

    # Configure LLM backend
    BACKEND = args.backend
    BASE_URL = args.base_url
    if BACKEND == "openai":
        # Runnable defaults that honour the implementer/auditor split; override freely.
        if not args.model:
            # 30B (MoE, ~3B active) measured FASTER than the 14B — 5.64 vs
            # 5.42 tok/s — while loading 95% vs 75% and giving the first
            # non-zero verification rate. See docs/model_comparison_2026-08.md.
            args.model = "qwen3-coder-30b-ctx8k:latest"
            print(f"[cfg] no --model given; implementer defaults to {args.model}")
        if not args.verify_model:
            args.verify_model = "qwen3-coder-30b-ctx8k:latest"
            print(f"[cfg] no --audit-model given; auditor defaults to {args.verify_model}")
        if args.verify_model == args.model:
            # Same weights is allowed: each call is a stateless /chat/completions
            # with no shared context, so the auditor is already a separate
            # instance (the point of implementer/auditor separation). Identical
            # weights only costs error DEcorrelation, which an A/B test found not
            # worth chasing via persona/temperature (it added hallucinated attrs).
            print(f"[cfg] NOTE: auditor == implementer ({args.model}); calls are still "
                  f"independent (stateless), same weights though.")
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
        # Card boundary: the only safe place to pause or stop. The previous
        # card's status is already written and the next has not started.
        if not wait_while_paused():
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
            (_card_out_dir(slug) / f"{slug}.json").write_text(json_content, encoding="utf-8")

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

        # --- Execution gate 1b: reject no-op stubs. A card with real (non-keyword)
        # text but empty abilities compiles fine, but it implements NOTHING — the
        # auditor then "verifies" it with a vacuous `assert abilities == []`. Catch
        # it here (same rule as the json-hygiene suite) so it can't reach 'done'.
        if status == "done" and not args.no_gate and _is_noop_stub(card, json_content):
            _write_review_note(slug, "empty abilities but card has non-keyword text "
                               "(implementer punted on the effect)", json_content, label="loadgate")
            status = "needs_review"
            print(f"  [gate] no-op stub (text unimplemented) -> needs_review")

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
            test_prompt = build_test_prompt(card, json_content)
            # Best-of-N: a stochastic 14B writes a correct test only some of the
            # time (right trigger, right ordering, real attributes). Give it up to
            # N SEEDED attempts and keep the FIRST that passes the gate — turning
            # run-to-run variance into a reliable pass when ANY sample is correct.
            # Early-exit means an easy card still costs one call.
            #
            # TEMPERATURE LADDER (measured): each successive attempt is WARMER.
            # Attempt 0 runs CRISP (temp 0.1) so a card that passes near-greedily
            # never regresses; each retry steps up (0.1 -> 0.45 -> 0.8 -> capped
            # 1.0) for more diversity to rescue a variance card. A flat warm temp
            # was tried and lost a reliably-passing card (aether_crackers), so
            # quality-first-then-progressively-diversify beats uniform sampling.
            n = max(1, args.auditor_samples)
            passed_code = None
            last_run_out = ""     # gate output of the last test we actually ran
            saw_needs_dsl = False
            last_gen_err = ""
            repair_ctx = ""       # previous attempt's code + real pytest error
            for i in range(n):
                temp = round(min(0.1 + 0.35 * i, 1.0), 2)
                seed = (1000 + i) if n > 1 else None
                tag = f" [{i + 1}/{n}]" if n > 1 else ""
                print(f"  [test] auditor ({audit_model or 'default'}){tag} "
                      f"writing test (t={temp})...")
                # REPAIR LOOP: after a failed attempt, show the model its own code
                # and the ACTUAL pytest output instead of re-rolling blind. Most
                # gate failures are a wrong attribute/signature the traceback names
                # outright (211 of 823 recorded failures are AttributeError, 62 of
                # them an invented `.flags`), which a blind re-roll reproduces and
                # a shown traceback usually fixes in one step.
                out = run_llm(test_prompt + repair_ctx, verbose=args.verbose,
                              model=audit_model, temperature=temp, seed=seed)
                if out == "CLAW_TIMEOUT" or out.startswith("CLAW_ERROR"):
                    last_gen_err = out
                    continue
                if "NEEDS_NEW_DSL:" in out:
                    saw_needs_dsl = True
                    process_test_output(slug, out)  # writes a review note
                    continue
                code = extract_test_code(out)
                if not code:
                    continue
                if args.no_gate:
                    passed_code = code
                    break
                passed, run_out = run_generated_test(slug, code, verbose=args.verbose)
                if passed and _is_vacuous_test(code):
                    # A test that passes while asserting nothing about game state is
                    # worse than no test: it marks the card 'done' (verified) on no
                    # evidence. Treat it as a failure and demand a real assertion.
                    passed = False
                    run_out = ("The test passed but asserts nothing observable about "
                               "game state, so it proves nothing. Assert a real "
                               "state change (health/resources/zone contents).")
                    print(f"  [gate]{tag} vacuous test (no state assertion) — rejected")
                if passed:
                    passed_code = code
                    break
                last_run_out = run_out + "\n\n--- TEST CODE ---\n" + code
                if i + 1 < n:
                    print(f"  [gate]{tag} did not pass — retrying with the error fed back")
                    repair_ctx = f"""

=== YOUR PREVIOUS ATTEMPT FAILED — FIX IT ===

You wrote this test:

{code}

Running it produced:

{run_out[-1500:]}

Fix the cause. If the traceback says an attribute does not exist, you INVENTED it
— use only the real names listed above (there is no `state.flags`, no
`player.flags`, no `.max_health`; use `set_turn_flag(st, pid, "marker")` to stage
turn state). If a helper rejected a keyword argument, check its real signature.

Do NOT weaken the test to make it pass: keep asserting a real, observable state
change. Deleting the assertion or asserting something trivially true is a
FAILURE, not a fix. Output ONLY the corrected Python.
"""

            if passed_code is not None:
                append_test(slug, passed_code)
                print(f"  [gate] test PASSED -> appended; {slug} verified done"
                      if not args.no_gate else "  [test] appended (gate disabled)")
            elif args.no_gate:
                print(f"  [test] no test code produced (gate disabled; status kept {status})")
            elif last_run_out:
                # CANDIDATE tier: the impl LOADS and is not a no-op stub (it cleared
                # gate 1 + 1b to reach here), the auditor just couldn't produce a
                # PASSING test — usually a false negative (correct impl, wrong test)
                # on a complex card. Keep the impl live/usable but unverified; the
                # note records the failing test for a later verification pass.
                _write_review_note(slug, f"no generated test passed (best of {n})",
                                   last_run_out, label="testgate")
                status = "candidate"
                print(f"  [gate] no sample passed after {n} -> candidate (unverified)")
            elif saw_needs_dsl:
                status = "needs_review"
                print(f"  [test] auditor flagged NEEDS_NEW_DSL -> needs_review")
            else:
                # Loaded + non-stub but no test code produced at all -> candidate.
                status = "candidate"
                print(f"  [test] no usable test produced ({last_gen_err[:50]}) -> candidate (unverified)")

        # Corpus tiers: 'done' (loaded + behaviourally verified) and 'candidate'
        # (loaded + non-stub, unverified) both stay LIVE in their set folder so the
        # cards are playable. Only genuinely-broken results (load-gate failure,
        # no-op stub, NEEDS_NEW_DSL, no JSON) are quarantined out of the corpus.
        # --no-gate keeps the old write-everything behaviour.
        if not args.no_gate and status not in ("done", "candidate"):
            _quarantine_card_json(slug)

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

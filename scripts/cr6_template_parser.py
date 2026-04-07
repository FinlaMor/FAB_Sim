"""cr6_template_parser.py — Classify card functional_text against CR section 6 effect templates
and check whether the existing keyword parsers (text_trigger_parser.py patterns) would capture
each paragraph.

CR Section 6 template categories:
  6.1  discrete              — direct one-time state change (default on-play)
  6.2  continuous            — modifies state for a duration: "while X", "gets +N until end of turn"
  6.4.7  self_replacement    — [EFFECT]. [CONDITION], instead [MODIFICATION]
  6.4.8  identity_replacement — As [CONDITION] [MODIFICATION]  /  [CONDITION] as/with [MODIFICATION]
  6.4.9  standard_replacement — (If / The next) [CONDITION], instead [MODIFICATION]  (continuous repl.)
  6.4.10_fixed  prevention_fixed   — [CONDITION], prevent [N] damage
  6.4.10_shield prevention_shield  — prevent the next [N] damage
  6.4.11 outcome_replacement — after-event "instead"; shares surface syntax with 6.4.9
  6.6.2  inline_triggered    — When [single-sentence condition] [effect]  (one-shot trigger)
  6.6.3  delayed_triggered   — The next time / contains trigger phrasing mid-sentence
  6.6.4  static_triggered    — Whenever / When (persistent) / At [time]
  keyword_only               — paragraph is a standalone keyword with no added effect text

Parser result categories:
  captured         — parser would generate a TriggerDef for this paragraph
  keyword_system   — handled by the keyword registration system (not text_trigger_parser.py)
  too_complex      — _has_complex_markers blocked it
  no_effect_match  — trigger detected but effect text was unparseable
  no_trigger_match — paragraph not matched by any trigger/if/standalone pattern
  no_text          — card has no functional text

Usage:
    python scripts/cr6_template_parser.py [--output OUTPUT_FILE]

Outputs:
    cr6_template_report.csv  (per-paragraph rows)
    Prints summary to stdout
"""

from __future__ import annotations

import re
import csv
import sys
import os
import argparse
from collections import Counter, defaultdict
from typing import Optional

# ---------------------------------------------------------------------------
# Path setup — run from FAB_Sim root or pass --root
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Load card data
# ---------------------------------------------------------------------------
def load_cards(msgpack_path: str) -> dict[str, dict]:
    try:
        import msgpack
    except ImportError:
        raise SystemExit("msgpack not installed. Run: pip install msgpack")
    with open(msgpack_path, "rb") as f:
        data = msgpack.unpackb(f.read(), raw=False)
    return data.get("by_slug", {})


# ===========================================================================
# CR Section 6 Template Classification
# ===========================================================================

# --- Trigger word detection -------------------------------------------------

_STATIC_TRIGGER_RE = re.compile(
    r'^(?:'
    r'whenever\b'
    r'|when\b(?!\s+this\s+chain\s+link)'   # "when" but not "when this chain link resolves" (resolution step phrase)
    r'|at the (?:start|end|beginning)\b'
    r'|the (?:first|second|third|fourth|next) time\b'  # ordinal triggers
    r')',
    re.I,
)

_DELAYED_TRIGGER_RE = re.compile(
    r'\b(?:when(?:ever)?|at the (?:start|end|beginning)|the next time)\b',
    re.I,
)

_THE_NEXT_TIME_RE = re.compile(r'^the next time\b', re.I)

# --- Replacement effect detection -------------------------------------------

_INSTEAD_RE = re.compile(r'\binstead\b', re.I)
_PREVENT_RE = re.compile(r'\bprevent(?:s)?\b', re.I)
_PREVENT_NEXT_RE = re.compile(r'\bprevent(?:s)? the next\b', re.I)
_AS_IDENTITY_RE = re.compile(r'^as\b', re.I)
_IF_OR_NEXT_RE = re.compile(r'^(?:if\b|the next\b)', re.I)

# --- Continuous effect detection --------------------------------------------

_WHILE_RE = re.compile(r'^while\b', re.I)
_GETS_UNTIL_RE = re.compile(r'\bgets?\s+[+\-]\d+\{[pd]\}.*\buntil\b', re.I)
_HAS_WHILE_RE = re.compile(r'\bhas\b.*\bwhile\b|\bwhile\b.*\bhas\b', re.I)
_STATIC_GRANT_RE = re.compile(
    r'^(?:cards? you play|attacks? you (?:make|play)|(?:your )?(?:attacks?|cards?))\b.*\b(?:gets?|gains?|have|has)\b',
    re.I,
)

# --- Keyword-only paragraph -------------------------------------------------

_KEYWORD_ONLY_RE = re.compile(
    r'^\*\*(?:'
    r'Go again|Dominate|Overpower|Phantasm|Spectra|Stealth|'
    r'Blood Debt|Battleworn|Temper|Legendary|Ephemeral|'
    r'Universal|Modular|Cloaked|Blade Break|Guardwell|'
    r'Galvanize|Intimidate|Heave|Boost|Wager|Freeze|'
    r'(?:Ice|Lightning|Earth|Elemental) Fusion|'
    r'[\w\' ]+ Specialization|'
    r'Arcane Barrier \d+|Ward \d+|Spellvoid \d+|Arcane Shelter \d+'
    r')\*\*\.?$',
    re.I,
)

# --- Label keyword patterns -------------------------------------------------

_LABEL_KEYWORD_RE = re.compile(
    r'\*\*(?:Crush|Reprise|Combo|Surge|Rupture|Boost|Opt|Amp)\*\*\s*[-\u2013\u2014:]',
    re.I,
)

# --- Additional cost lines --------------------------------------------------

_COST_LINE_RE = re.compile(r'^as an additional cost to (?:play|activate)', re.I)


def classify_cr6_template(paragraph: str) -> str:
    """Return the best-matching CR section 6 template label for a paragraph."""
    p = paragraph.strip()
    if not p:
        return "empty"

    # --- Keyword-only ---
    if _KEYWORD_ONLY_RE.match(p):
        return "keyword_only"

    # --- Additional cost — not a CR6 effect at all ---
    if _COST_LINE_RE.match(p):
        return "cost_restriction"

    # --- Triggered effects (6.6.x) --- check before replacement ---
    if _STATIC_TRIGGER_RE.match(p) or _THE_NEXT_TIME_RE.match(p):
        # Distinguish static (6.6.4) vs inline (6.6.2) vs delayed (6.6.3)
        # "The next time" = delayed-triggered (6.6.3)
        if _THE_NEXT_TIME_RE.match(p):
            return "6.6.3_delayed_triggered"
        # "Whenever" = definitely static-triggered (persistent)
        if re.match(r'^whenever\b', p, re.I):
            return "6.6.4_static_triggered"
        # "When" could be static or inline; can't fully distinguish from text alone.
        # Per 6.6.2, inline-triggered is a *discrete* effect that generates as it resolves.
        # Heuristic: if the paragraph references "this chain link" or "this turn" after
        # "when" it's more likely inline; persistent is more likely static.
        # We classify "When" starters as static_triggered (the most common case).
        if re.match(r'^at\b', p, re.I):
            return "6.6.4_static_triggered"
        return "6.6.4_static_triggered"

    # --- Delayed triggered — trigger word mid-sentence (6.6.3) ---
    # e.g. "Deal 3 arcane damage. The next time you draw..."
    # e.g. "Create a Runechant. When it leaves the arena, ..."
    if _DELAYED_TRIGGER_RE.search(p):
        # Only if it doesn't start with a trigger word (already handled above)
        return "6.6.3_delayed_triggered"

    # --- Label keyword triggers ---
    if _LABEL_KEYWORD_RE.search(p):
        # These trigger on specific events (crush, reprise, etc.) — they are
        # effectively static-triggered or delayed-triggered, but expressed via labels.
        return "6.6.4_label_triggered"

    # --- Prevention effects (6.4.10) --- check before other replacements ---
    if _PREVENT_RE.search(p):
        if _PREVENT_NEXT_RE.search(p):
            return "6.4.10_prevention_shield"
        return "6.4.10_prevention_fixed"

    # --- Identity-replacement (6.4.8): "As [CONDITION] [MODIFICATION]" ---
    if _AS_IDENTITY_RE.match(p):
        return "6.4.8_identity_replacement"

    # --- Self-replacement (6.4.7): [EFFECT]. [CONDITION], instead [MOD]
    # Signature: has "instead" and is NOT at the start of the paragraph
    # (the "instead" is embedded after a preceding effect).
    if _INSTEAD_RE.search(p):
        # Standard-replacement (6.4.9): starts with If/The next + instead
        if _IF_OR_NEXT_RE.match(p):
            return "6.4.9_standard_replacement"
        # Self-replacement: "instead" appears mid-paragraph after a prior effect
        # Heuristic: if there's a sentence boundary before "instead"
        before_instead = p[:_INSTEAD_RE.search(p).start()]
        if re.search(r'[.!?]\s*\w', before_instead) or re.search(r',\s*\w+.*,', before_instead):
            return "6.4.7_self_replacement"
        # Otherwise treat as standard-replacement (If-less form)
        return "6.4.9_standard_replacement"

    # --- Continuous effects (6.2) ---
    if _WHILE_RE.match(p) or _GETS_UNTIL_RE.search(p) or _STATIC_GRANT_RE.match(p):
        return "6.2_continuous"

    # --- Discrete effect (6.1) — everything remaining ---
    return "6.1_discrete"


# ===========================================================================
# Parser Coverage Check  (re-implements text_trigger_parser.py logic)
# ===========================================================================

# --- Complex markers (from text_trigger_parser._has_complex_markers) --------

_COMPLEX_PATTERNS = [
    re.compile(r'\bchoose\b', re.I),
    re.compile(r'\bfor each\b', re.I),
    re.compile(r'\bequal to\b', re.I),
    re.compile(r'\bunless\b', re.I),
    re.compile(r'\binstead\b', re.I),
    re.compile(r'\bbecomes?\b', re.I),
    re.compile(r'\bsearch your deck\b', re.I),
    re.compile(r'\blook at the top\b', re.I),
    re.compile(r'\breveal\b', re.I),
    re.compile(r'\bany number\b', re.I),
    re.compile(r'\bput .+ into play\b', re.I),
    re.compile(r'\btransform\b', re.I),
    re.compile(r'\btranscend\b', re.I),
    re.compile(r'\bgraft\b', re.I),
    re.compile(r'\btake control\b', re.I),
    re.compile(r'\bname a card\b', re.I),
    re.compile(r'\bcopy\b', re.I),
    re.compile(r'\bexchange\b', re.I),
]

def _has_complex_markers(text: str) -> bool:
    return any(p.search(text) for p in _COMPLEX_PATTERNS)


# --- Effect patterns (from text_trigger_parser._EFFECT_PATTERNS) ------------

_EFFECT_PATTERNS = [
    re.compile(r'draw (\d+|a|an|one|two|three) cards?', re.I),
    re.compile(r'deal (\d+) arcane damage', re.I),
    re.compile(r'deal (\d+) damage', re.I),
    re.compile(r'(?:the )?next (?:\w+ )?attack (?:action card )?(?:you play )?this (?:turn|combat chain) (?:gets?|gains?) \+(\d+)\{p\}', re.I),
    re.compile(r'(?:this |it )(?:gets?|has) \+(\d+)\{p\}', re.I),
    re.compile(r'(?:gets?|has) \+(\d+)\{p\}', re.I),
    re.compile(r'(?:this |it )(?:gets?|has) \+(\d+)\{d\}', re.I),
    re.compile(r'(?:gets?|has) \+(\d+)\{d\}', re.I),
    re.compile(r'(?:this |it )?(?:gets?|gains?|has) \*\*go again\*\*', re.I),
    re.compile(r'(?:this |it )?(?:gets?|gains?|has) \*\*dominate\*\*', re.I),
    re.compile(r'(?:this |it )?(?:gets?|gains?|has) \*\*overpower\*\*', re.I),
    re.compile(r'gain (\d+)\{h\}', re.I),
    re.compile(r'gain (\d+) life', re.I),
    re.compile(r'(?:they |the (?:attacking|defending|opposing) hero )?loses? (\d+)\{h\}', re.I),
    re.compile(r'(?:they |the (?:attacking|defending|opposing) hero )?discards? (\d+|a|an) (?:random )?cards?', re.I),
    re.compile(r'create (\d+|a|an|two|three) ([A-Z][a-z][a-z A-Z]*?) tokens?', re.I),
    re.compile(r'\*\*opt (\d+)\*\*', re.I),
    re.compile(r'\bopt (\d+)\b', re.I),
    re.compile(r'gain (\d+) action points?', re.I),
    re.compile(r'gain (\{r\})+', re.I),
    re.compile(r'\*\*amp (\d+)\*\*', re.I),
    re.compile(r'\bamp (\d+)\b', re.I),
    re.compile(r'\*\*intimidate\*\*', re.I),
    re.compile(r'\bintimidate\b(?! you)', re.I),
    re.compile(r'banish the top (\d+|a|an) cards? of', re.I),
    re.compile(r'prevent the next (\d+) damage', re.I),
    re.compile(r'put (\d+|a|an) \+1\{p\} counters? on (?:this|it)', re.I),
    re.compile(r'(?:the )?next (?:\w+ )?attack (?:action card )?(?:you play )?this (?:turn|combat chain) (?:gets?|gains?) \*\*go again\*\*', re.I),
    re.compile(r'(?:the )?next (?:\w+ )?attack (?:action card )?(?:you play )?this (?:turn|combat chain) (?:gets?|gains?) \*\*dominate\*\*', re.I),
    re.compile(r'(?:the )?next (?:\w+ )?attack (?:action card )?(?:you play )?this (?:turn|combat chain) (?:gets?|gains?) \*\*overpower\*\*', re.I),
]

def _effect_parseable(text: str) -> bool:
    """Return True if any effect pattern matches the text."""
    # Remove trailing period
    text = text.rstrip('. ')
    return any(p.search(text) for p in _EFFECT_PATTERNS)


def _effect_parseable_compound(text: str) -> bool:
    """Check compound effects (comma/and-separated)."""
    if _effect_parseable(text):
        return True
    parts = re.split(r',\s+(?:and\s+)?|\s+and\s+', text)
    if len(parts) < 2:
        return False
    return all(_effect_parseable(p.strip()) for p in parts if p.strip())


# --- Trigger patterns (from text_trigger_parser._TRIGGER_PATTERNS) ----------

_TRIGGER_PATTERNS = [
    re.compile(r'when(?:ever)? (?:this|[\w\' ,]+?) hits(?: a hero)?', re.I),
    re.compile(r'if (?:this|[\w\' ,]+?) hits', re.I),
    re.compile(r'when(?:ever)? (?:this|[\w\' ,]+?) attacks(?: a hero)?', re.I),
    re.compile(r'when(?:ever)? (?:this|[\w\' ,]+?) defends', re.I),
    re.compile(r'when(?:ever)? (?:this|[\w\' ,]+?) enters the arena', re.I),
    re.compile(r'when(?:ever)? (?:this|[\w\' ,]+?) leaves the arena', re.I),
    re.compile(r'when(?:ever)? you play this', re.I),
    re.compile(r'when(?:ever)? (?:this|[\w\' ,]+?) deals damage', re.I),
    re.compile(r'when(?:ever)? you attack with', re.I),
]

# --- Label keyword patterns (from text_trigger_parser._LABEL_PATTERNS) ------

_LABEL_PATTERNS_CHECK = [
    re.compile(r'\*\*Crush\*\*\s*[-\u2013\u2014:]\s*(.+?)(?:\.|$)', re.I | re.S),
    re.compile(r'\*\*Reprise\*\*\s*[-\u2013\u2014:]\s*(.+?)(?:\.|$)', re.I | re.S),
    re.compile(r'\*\*Combo\*\*\s*[-\u2013\u2014:]\s*(.+?)(?:\.|$)', re.I | re.S),
    re.compile(r'\*\*Surge\*\*\s*[-\u2013\u2014:]\s*(.+?)(?:\.|$)', re.I | re.S),
    re.compile(r'\*\*Rupture\*\*\s*[-\u2013\u2014:]\s*(.+?)(?:\.|$)', re.I | re.S),
]

# --- If-condition patterns (from text_trigger_parser._IF_CONDITION_PATTERNS) ---

_IF_CONDITION_PATTERNS_CHECK = [
    re.compile(r'if you have (?:less|fewer) \{h\} than', re.I),
    re.compile(r'if you have more \{h\} than', re.I),
    re.compile(r'if (?:this|[\w ]+?) is played from arsenal', re.I),
    re.compile(r'if (?:this|[\w ]+?) was played from arsenal', re.I),
    re.compile(r'if there (?:are|is) (\d+) or more (\w+) cards? in your pitch zone', re.I),
    re.compile(r'if there (?:are|is) (\d+) or more (\w+) cards? in your banished zone', re.I),
    re.compile(r'if there is a card with (\d+) or more \{p\} in your pitch zone', re.I),
    re.compile(r"if you(?:'ve| have) been cheered this turn", re.I),
    re.compile(r'if you control (?:a|an) ([A-Z][a-z][a-z A-Z]*?) token', re.I),
    re.compile(r'if (?:this|it) is defended by fewer than (\d+) non-equipment cards?', re.I),
    re.compile(r'if you have no cards in hand', re.I),
    re.compile(r"if you(?:'ve| have) discarded a card with (\d+) or more \{p\} this turn", re.I),
    re.compile(r"if you(?:'ve| have) controlled a (\w[\w ]*?) token this turn", re.I),
    re.compile(r'if [\w\' ]+ was (?:\*\*)?fused(?:\*\*)?', re.I),
    re.compile(r'if [\w\' ]+ was (?:\*\*)?charged(?:\*\*)?', re.I),
    re.compile(r"if you(?:'ve| have) dealt arcane damage this turn", re.I),
    re.compile(r"if you(?:'ve| have) intimidated", re.I),
    re.compile(r'if (?:this|it) has \*\*stealth\*\*', re.I),
    re.compile(r'if (?:this|it) is attacking a hero', re.I),
    re.compile(r'if you control (\d+) or more (\w[\w ]*?) (?:chain links?|cards?)', re.I),
    re.compile(r"if you(?:'ve| have) played (?:a|an|another) (\w[\w ]*?) card this turn", re.I),
    re.compile(r'if (?:this|it|[\w\' ]+) has (\d+) or more \{p\}', re.I),
    re.compile(r'if (?:this|it|[\w\' ]+) has \{p\} greater than its base \{p\}', re.I),
    re.compile(r'if you have (?:a|an) (\w+) card in your pitch zone', re.I),
    re.compile(r"if you(?:'ve| have) drawn a card this turn", re.I),
    re.compile(r"if you(?:'ve| have) banished a card with (\d+) or more \{p\} this turn", re.I),
    re.compile(r"if you(?:'ve| have) created (?:a card|an? \w[\w ]*? token) this turn", re.I),
    re.compile(r"if you(?:'ve| have) \*\*boosted\*\* (\d+) or more times? this turn", re.I),
    re.compile(r'if you have a card in your arsenal', re.I),
    re.compile(r'(?:while|if) [\w\' ]+ is defended by (?:less|fewer) than (\d+) non-equipment cards?', re.I),
    re.compile(r'if (?:this|it) is (\w+)', re.I),
]

_SKIPPABLE_RE = re.compile(r'^as an additional cost to (?:play|activate)', re.I)
_STANDALONE_GO_AGAIN_RE = re.compile(r'^\*\*Go again\*\*\.?$', re.I)


def check_parser_coverage(paragraph: str) -> tuple[str, str]:
    """
    Return (result_code, detail) where result_code is one of:
      'captured_label'      — matched by a label keyword pattern with parseable effect
      'captured_trigger'    — matched by a trigger pattern with parseable effect
      'captured_if_cond'    — matched by an if-condition pattern with parseable effect
      'captured_standalone' — matched as a standalone effect
      'keyword_only'        — keyword-only paragraph (handled by keyword system)
      'standalone_go_again' — standalone **Go again** paragraph
      'skipped_cost'        — additional cost line (skipped)
      'too_complex'         — has complex markers that block parsing
      'trigger_no_effect'   — trigger matched but effect text unparseable
      'if_cond_no_effect'   — if-condition matched but effect text unparseable
      'label_no_effect'     — label keyword matched but effect text unparseable
      'not_captured'        — nothing matched
    """
    p = paragraph.strip()
    if not p:
        return ("empty", "")

    # Skippable cost lines
    if _SKIPPABLE_RE.match(p):
        return ("skipped_cost", "")

    # Standalone **Go again**
    if _STANDALONE_GO_AGAIN_RE.match(p):
        return ("standalone_go_again", "")

    # Keyword-only paragraph
    if _KEYWORD_ONLY_RE.match(p):
        return ("keyword_only", "")

    # Phase A: Label keyword patterns
    for pat in _LABEL_PATTERNS_CHECK:
        m = pat.search(p)
        if m:
            effect_text = m.group(1).strip()
            if _has_complex_markers(effect_text):
                return ("too_complex", f"label complex: {effect_text[:60]}")
            if _effect_parseable_compound(effect_text):
                return ("captured_label", pat.pattern[:40])
            return ("label_no_effect", f"effect: {effect_text[:60]}")

    # Phase B: Trigger patterns
    for trig_pat in _TRIGGER_PATTERNS:
        m = trig_pat.search(p)
        if m:
            effect_text = p[m.end():].strip().lstrip(',').strip()
            # Strip embedded if-clause
            for if_pat in _IF_CONDITION_PATTERNS_CHECK:
                if_m = if_pat.search(effect_text)
                if if_m:
                    effect_text = effect_text[if_m.end():].strip().lstrip(',').strip()
                    break
            # Strip "you may" / "if you do"
            you_may_m = re.match(r'you may\b\s*', effect_text, re.I)
            if you_may_m:
                effect_text = effect_text[you_may_m.end():].strip()
            if_you_do_m = re.search(r'\bif you do,?\s*', effect_text, re.I)
            if if_you_do_m:
                effect_text = effect_text[if_you_do_m.end():].strip()
            # Check complexity
            if _has_complex_markers(effect_text):
                return ("too_complex", f"trigger complex: {effect_text[:60]}")
            if _effect_parseable_compound(effect_text):
                return ("captured_trigger", trig_pat.pattern[:60])
            return ("trigger_no_effect", f"effect: {effect_text[:60]}")

    # Phase B.3: If-condition patterns (no trigger word)
    if not re.search(r'^when(?:ever)? ', p, re.I):
        for if_pat in _IF_CONDITION_PATTERNS_CHECK:
            if_m = if_pat.search(p)
            if if_m:
                effect_text = p[if_m.end():].strip().lstrip(',').strip()
                you_may_m = re.match(r'you may\b\s*', effect_text, re.I)
                if you_may_m:
                    effect_text = effect_text[you_may_m.end():].strip()
                if_you_do_m = re.search(r'\bif you do,?\s*', effect_text, re.I)
                if if_you_do_m:
                    effect_text = effect_text[if_you_do_m.end():].strip()
                if _has_complex_markers(effect_text):
                    return ("too_complex", f"if-cond complex: {effect_text[:60]}")
                if _effect_parseable_compound(effect_text):
                    return ("captured_if_cond", if_pat.pattern[:60])
                return ("if_cond_no_effect", f"effect: {effect_text[:60]}")

    # Phase B.4: Standalone effect
    if not re.search(r'^(?:when(?:ever)? |if |\*\*(?:crush|reprise|combo|surge|rupture)\*\*)', p, re.I):
        if not _has_complex_markers(p):
            # Must be single sentence
            if not re.search(r'\.\s+[A-Z]', p):
                text = p
                you_may_m = re.match(r'^you may\b\s*', text, re.I)
                if you_may_m:
                    text = text[you_may_m.end():].strip()
                if_you_do_m = re.search(r'\bif you do,?\s*', text, re.I)
                if if_you_do_m:
                    text = text[if_you_do_m.end():].strip()
                if _effect_parseable(text):
                    return ("captured_standalone", "")

    if _has_complex_markers(p):
        return ("too_complex", "")

    return ("not_captured", "")


# ===========================================================================
# Main
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="CR6 template parser for FAB cards")
    parser.add_argument("--msgpack", default=os.path.join(ROOT, "card_data", "slug_index.msgpack"))
    parser.add_argument("--output", default=os.path.join(ROOT, "card_data", "cr6_template_report.csv"))
    parser.add_argument("--summary-only", action="store_true", help="Print summary without writing CSV")
    args = parser.parse_args()

    print(f"Loading cards from {args.msgpack} ...")
    cards = load_cards(args.msgpack)
    print(f"  {len(cards)} cards loaded")

    rows = []
    template_counts: Counter = Counter()
    parser_counts: Counter = Counter()
    # cross-tab: template -> parser_result -> count
    cross: dict[str, Counter] = defaultdict(Counter)
    # cards with no text
    no_text_count = 0

    for slug, card in sorted(cards.items()):
        name = card.get("name", slug)
        ft = card.get("functional_text", "") or ""

        if not ft.strip():
            no_text_count += 1
            rows.append({
                "slug": slug,
                "name": name,
                "para_index": 0,
                "cr_template": "no_text",
                "parser_result": "no_text",
                "detail": "",
                "paragraph": "",
            })
            template_counts["no_text"] += 1
            parser_counts["no_text"] += 1
            cross["no_text"]["no_text"] += 1
            continue

        paragraphs = [p.strip() for p in re.split(r'\n\n+', ft) if p.strip()]

        for i, para in enumerate(paragraphs):
            cr_template = classify_cr6_template(para)
            parser_result, detail = check_parser_coverage(para)

            rows.append({
                "slug": slug,
                "name": name,
                "para_index": i,
                "cr_template": cr_template,
                "parser_result": parser_result,
                "detail": detail,
                "paragraph": para[:200],
            })
            template_counts[cr_template] += 1
            parser_counts[parser_result] += 1
            cross[cr_template][parser_result] += 1

    # --- Write CSV ---
    if not args.summary_only:
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["slug", "name", "para_index", "cr_template", "parser_result", "detail", "paragraph"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nCSV written to {args.output}")

    total_paras = len(rows)
    total_cards = len(cards)

    print(f"\n{'='*72}")
    print(f"  CR SECTION 6 TEMPLATE REPORT  ({total_cards} cards, {total_paras} paragraphs)")
    print(f"{'='*72}")

    print(f"\n{'-'*72}")
    print(f"  TEMPLATE DISTRIBUTION")
    print(f"{'-'*72}")
    template_order = [
        "no_text",
        "keyword_only",
        "cost_restriction",
        "6.1_discrete",
        "6.2_continuous",
        "6.4.7_self_replacement",
        "6.4.8_identity_replacement",
        "6.4.9_standard_replacement",
        "6.4.10_prevention_fixed",
        "6.4.10_prevention_shield",
        "6.6.3_delayed_triggered",
        "6.6.4_static_triggered",
        "6.6.4_label_triggered",
    ]
    for tmpl in template_order:
        count = template_counts.get(tmpl, 0)
        if count:
            pct = 100.0 * count / total_paras
            print(f"  {tmpl:<40} {count:5d}  ({pct:5.1f}%)")
    # Anything not in the order list
    for tmpl, count in sorted(template_counts.items()):
        if tmpl not in template_order:
            pct = 100.0 * count / total_paras
            print(f"  {tmpl:<40} {count:5d}  ({pct:5.1f}%)")

    print(f"\n{'-'*72}")
    print(f"  PARSER COVERAGE")
    print(f"{'-'*72}")
    coverage_order = [
        "captured_label",
        "captured_trigger",
        "captured_if_cond",
        "captured_standalone",
        "standalone_go_again",
        "keyword_only",
        "skipped_cost",
        "too_complex",
        "trigger_no_effect",
        "if_cond_no_effect",
        "label_no_effect",
        "not_captured",
        "no_text",
        "empty",
    ]
    captured_total = sum(parser_counts.get(k, 0) for k in [
        "captured_label", "captured_trigger", "captured_if_cond", "captured_standalone",
        "standalone_go_again", "keyword_only", "skipped_cost",
    ])
    for result in coverage_order:
        count = parser_counts.get(result, 0)
        if count:
            pct = 100.0 * count / total_paras
            print(f"  {result:<40} {count:5d}  ({pct:5.1f}%)")

    text_paras = total_paras - no_text_count
    if text_paras:
        pct_captured = 100.0 * captured_total / text_paras
        print(f"\n  OVERALL CAPTURE RATE (non-empty cards): {pct_captured:.1f}%")

    print(f"\n{'-'*72}")
    print(f"  CROSS-TAB: template vs parser result")
    print(f"{'-'*72}")
    # Only show templates that exist in the data
    active_templates = [t for t in template_order if template_counts.get(t, 0) > 0]
    # Collect all unique parser results
    all_results = sorted({r for counts in cross.values() for r in counts})
    # Header
    hdr = f"  {'Template':<40}"
    for r in all_results:
        hdr += f"  {r[:16]:>16}"
    print(hdr)
    for tmpl in active_templates:
        row_str = f"  {tmpl:<40}"
        for r in all_results:
            cnt = cross[tmpl].get(r, 0)
            row_str += f"  {cnt:>16}"
        print(row_str)

    # --- Sample uncaptured paragraphs by template ---
    print(f"\n{'-'*72}")
    print(f"  SAMPLE NOT-CAPTURED PARAGRAPHS (up to 5 per template)")
    print(f"{'-'*72}")
    samples: dict[str, list] = defaultdict(list)
    for row in rows:
        if row["parser_result"] in ("not_captured", "trigger_no_effect", "if_cond_no_effect", "label_no_effect"):
            tmpl = row["cr_template"]
            if len(samples[tmpl]) < 5:
                samples[tmpl].append(row)

    for tmpl in template_order:
        if tmpl in samples:
            print(f"\n  [{tmpl}]")
            for row in samples[tmpl]:
                print(f"    {row['slug']}: {row['paragraph'][:120]}")


if __name__ == "__main__":
    os.chdir(ROOT)
    main()

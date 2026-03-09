"""
card_agent.py — Offline card implementation validator agent.

Backends (in priority order):
  1. Ollama local model (fab-cards-ft if fine-tuned, else any available model)
  2. Anthropic Claude API (fallback when Ollama unavailable)

Usage:
    from offline_agents.agents.card_agent import CardAgent
    agent = CardAgent()
    result = agent.validate("etchings_of_arcana", code_snippet)
    result = agent.sniff_test_all()   # breadth-first scan of all registered cards
"""
from __future__ import annotations

import json
import pathlib
import textwrap
from typing import Optional

from offline_agents.rag.retriever import Retriever

ROOT = pathlib.Path(__file__).resolve().parents[2]
CARD_JSON = ROOT / "card_data" / "slug_index.json"

SYSTEM_PROMPT = """You are an expert Flesh and Blood TCG card implementation validator. You cross-reference card implementations against official card text and CR rules to find bugs, missing effects, wrong values, and corner cases.

When validating a card:
- Check damage/cost/draw numbers against the card's functional text
- Check trigger conditions and event types
- Check keyword handling (go again, dominate, intimidate, etc.)
- Flag optional vs mandatory effects
- Note any missing on_play / on_hit / on_defend triggers
- Cite the card's functional text when flagging an issue

Be concise. List issues in priority order: Critical > Major > Minor."""


class CardAgent:
    """RAG-augmented card implementation validator."""

    def __init__(
        self,
        ollama_model: str = "fab-cards-ft",  # falls back to qwen2.5:7b if not found
        fallback_model: str = "claude-sonnet-4-6",
    ):
        self.ollama_model = ollama_model
        self.fallback_model = fallback_model
        self._retriever: Optional[Retriever] = None
        self._card_db: Optional[dict] = None
        self._ollama_available: Optional[bool] = None
        self._ollama_model_available: Optional[bool] = None

    @property
    def retriever(self) -> Retriever:
        if self._retriever is None:
            self._retriever = Retriever()
        return self._retriever

    @property
    def card_db(self) -> dict:
        if self._card_db is None:
            data = json.loads(CARD_JSON.read_text(encoding="utf-8"))
            self._card_db = data.get("by_slug", data)
        return self._card_db

    def get_card_text(self, slug: str) -> str:
        """Return the official card text for a given slug."""
        card = self.card_db.get(slug)
        if not card:
            return f"(Card '{slug}' not found in database)"
        lines = [
            f"Name: {card.get('name', slug)}",
            f"Types: {', '.join(card.get('types', []))}",
        ]
        for f in ("pitch", "cost", "power", "defense", "health", "arcane"):
            v = card.get(f)
            if v:
                lines.append(f"{f.title()}: {v}")
        kws = (card.get("card_keywords") or []) + (card.get("ability_and_effect_keywords") or [])
        if kws:
            lines.append(f"Keywords: {', '.join(kws)}")
        fx = card.get("functional_text", "")
        if fx:
            lines.append(f"Text: {fx}")
        return "\n".join(lines)

    def _check_ollama(self) -> tuple[bool, bool]:
        if self._ollama_available is not None:
            return self._ollama_available, self._ollama_model_available
        try:
            import ollama
            models = ollama.list()
            available = [m.model for m in models.models]
            running = True
            has_model = any(
                self.ollama_model in m or m.startswith(self.ollama_model)
                for m in available
            )
            if not has_model and available:
                # Prefer qwen2.5:7b as fallback, otherwise use first available
                preferred = next((m for m in available if "qwen2.5" in m), None)
                self.ollama_model = preferred or available[0]
                has_model = True
        except Exception:
            running = False
            has_model = False
        self._ollama_available = running
        self._ollama_model_available = has_model
        return running, has_model

    def _query(self, prompt: str, context: str) -> str:
        ollama_running, ollama_has_model = self._check_ollama()
        if ollama_running and ollama_has_model:
            import ollama
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{context}\n\n---\n\n{prompt}"},
            ]
            response = ollama.chat(model=self.ollama_model, messages=messages)
            return response.message.content
        # Fallback to Claude
        import anthropic
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=self.fallback_model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"{context}\n\n---\n\n{prompt}"}],
        )
        return message.content[0].text

    def validate(self, slug: str, implementation: str) -> str:
        """
        Validate a card implementation against its official text.

        Args:
            slug: The card's slug (e.g. 'etchings_of_arcana_yellow')
            implementation: The Python code implementing this card's triggers/effects.
        Returns:
            Validation report string.
        """
        card_text = self.get_card_text(slug)
        rag_context = ""
        if self.retriever.is_ready():
            # Search for card name + any keywords it uses
            card_name = self.card_db.get(slug, {}).get("name", slug)
            rag_context = self.retriever.query_all(card_name, n_rules=4, n_cards=2)

        context = f"## Official Card Text\n{card_text}"
        if rag_context:
            context += f"\n\n{rag_context}"

        prompt = (
            f"Validate this implementation of '{slug}' against the official card text above.\n\n"
            f"```python\n{implementation}\n```\n\n"
            "List any bugs, wrong values, missing effects, or incorrect trigger conditions."
        )
        return self._query(prompt, context)

    def sniff_test_all(self, triggers_file: Optional[pathlib.Path] = None,
                       registry_file: Optional[pathlib.Path] = None) -> str:
        """
        Quick breadth-first sniff test of all card implementations.
        Reads triggers.py and registry.py, builds a summary prompt, queries the agent.
        """
        triggers_file = triggers_file or (ROOT / "engine" / "card_effects" / "triggers.py")
        registry_file = registry_file or (ROOT / "engine" / "card_effects" / "registry.py")

        triggers_src = triggers_file.read_text(encoding="utf-8", errors="replace") if triggers_file.exists() else ""
        registry_src = registry_file.read_text(encoding="utf-8", errors="replace") if registry_file.exists() else ""

        # Grab a sample of card entries for RAG context
        rag_context = ""
        if self.retriever.is_ready():
            rag_context = self.retriever.query_all(
                "card triggers effects damage arcane go again", n_rules=4, n_cards=4)

        context = rag_context
        prompt = textwrap.dedent(f"""
            Perform a quick breadth-first sniff test of all card implementations below.
            For each suspected bug, return: card slug | file+line | issue | correct behavior.
            Group by severity: Critical / Major / Minor.
            Be concise — scan for obvious problems, don't deep-dive every card.

            ## triggers.py (truncated to 8000 chars)
            ```python
            {triggers_src[:8000]}
            ```

            ## registry.py (truncated to 4000 chars)
            ```python
            {registry_src[:4000]}
            ```
        """).strip()
        return self._query(prompt, context)

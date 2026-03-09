"""
rules_agent.py — Offline FAB rules enforcement agent.

Backends (in priority order):
  1. Ollama local model (fab-rules-ft if fine-tuned, else any available model)
  2. Anthropic Claude API (fallback when Ollama unavailable)

Usage:
    from offline_agents.agents.rules_agent import RulesAgent
    agent = RulesAgent()
    answer = agent.ask("Does CR 4.4.3c apply to all players or just the active player?")
"""
from __future__ import annotations

import os
import textwrap
from typing import Optional

from offline_agents.rag.retriever import Retriever

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert Flesh and Blood TCG rules enforcer. You have deep knowledge of the official Comprehensive Rules (CR) and all set release notes. When answering questions about rules or reviewing code implementations:
- Always cite the specific CR section or release note
- Be precise about timing, costs, and optional vs mandatory effects
- Flag any implementation that deviates from the official rules
- If uncertain, say so and explain what the rules text actually states

You will be given relevant rules excerpts and card data as context. Use them."""

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class RulesAgent:
    """
    RAG-augmented rules agent. Retrieves relevant rules context then queries
    either a local Ollama model or the Anthropic API.
    """

    def __init__(
        self,
        ollama_model: str = "fab-rules-ft",  # falls back to qwen2.5:7b if not found
        fallback_model: str = "claude-sonnet-4-6",
        n_rules: int = 6,
        n_cards: int = 3,
    ):
        self.n_rules = n_rules
        self.n_cards = n_cards
        self.ollama_model = ollama_model
        self.fallback_model = fallback_model
        self._retriever: Optional[Retriever] = None
        self._ollama_available: Optional[bool] = None
        self._ollama_model_available: Optional[bool] = None

    @property
    def retriever(self) -> Retriever:
        if self._retriever is None:
            self._retriever = Retriever()
        return self._retriever

    def _check_ollama(self) -> tuple[bool, bool]:
        """Returns (ollama_running, model_available)."""
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
            if not has_model:
                # Prefer qwen2.5:7b as fallback, otherwise use first available
                preferred = next((m for m in available if "qwen2.5" in m), None)
                self.ollama_model = preferred or (available[0] if available else None)
                has_model = self.ollama_model is not None
        except Exception:
            running = False
            has_model = False
        self._ollama_available = running
        self._ollama_model_available = has_model
        return running, has_model

    def _query_ollama(self, prompt: str, context: str) -> str:
        import ollama
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{context}\n\n---\n\n{prompt}"},
        ]
        response = ollama.chat(model=self.ollama_model, messages=messages)
        return response.message.content

    def _query_claude(self, prompt: str, context: str) -> str:
        import anthropic
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=self.fallback_model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"{context}\n\n---\n\n{prompt}"}],
        )
        return message.content[0].text

    def ask(self, question: str, extra_context: str = "") -> str:
        """
        Ask a rules question. Retrieves relevant context, then queries the best
        available backend.

        Args:
            question: The rules question or implementation to review.
            extra_context: Optional additional context (e.g. code snippet).
        Returns:
            The agent's answer as a string.
        """
        # Retrieve relevant rules + card context
        rag_context = ""
        if self.retriever.is_ready():
            rag_context = self.retriever.query_all(
                question, n_rules=self.n_rules, n_cards=self.n_cards)

        context_parts = []
        if rag_context:
            context_parts.append(rag_context)
        if extra_context:
            context_parts.append(f"## Additional Context\n{extra_context}")
        context = "\n\n".join(context_parts)

        # Choose backend
        ollama_running, ollama_has_model = self._check_ollama()
        if ollama_running and ollama_has_model:
            return self._query_ollama(question, context)
        return self._query_claude(question, context)

    def review_code(self, code: str, question: str = "") -> str:
        """Review a code implementation for rules compliance."""
        prompt = question or "Review this implementation for FAB rules compliance. Flag any deviations."
        return self.ask(prompt, extra_context=f"```python\n{code}\n```")

"""
rules_agent.py — Offline FAB rules enforcement agent.

Backends (in priority order):
    1. Local merged Transformers model (models/fab-rules-ft/merged, if available)
    2. Ollama local model (fab-rules-ft if fine-tuned, else any available model)
    3. Anthropic Claude API (fallback when local models unavailable)

Usage:
        from offline_agents.agents.rules_agent import RulesAgent
        agent = RulesAgent()
        answer = agent.ask("Does CR 4.4.3c apply to all players or just the active player?")
"""
from __future__ import annotations

import pathlib
from typing import Optional

from offline_agents.agents.local_transformers_backend import LocalTransformersBackend
from offline_agents.rag.retriever import Retriever

ROOT = pathlib.Path(__file__).resolve().parents[2]

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
        ollama_model: str = "fab-rules-ft-q4ks",  # falls back to qwen2.5:7b if not found
        fallback_model: str = "claude-sonnet-4-6",
        n_rules: int = 6,
        n_cards: int = 3,
        use_rag: bool = True,
        prefer_ollama: bool = False,
        ollama_num_gpu: int = 16,
        ollama_num_ctx: int = 4096,
    ):
        self.n_rules = n_rules
        self.n_cards = n_cards
        self.use_rag = use_rag
        self.prefer_ollama = prefer_ollama
        self.ollama_model = ollama_model
        self.fallback_model = fallback_model
        self.ollama_num_gpu = ollama_num_gpu
        self.ollama_num_ctx = ollama_num_ctx
        self.last_backend: Optional[str] = None
        self._retriever: Optional[Retriever] = None
        self._local_backend: Optional[LocalTransformersBackend] = None
        self._local_model_available: Optional[bool] = None
        self._ollama_available: Optional[bool] = None
        self._ollama_model_available: Optional[bool] = None

    @property
    def retriever(self) -> Retriever:
        if self._retriever is None:
            self._retriever = Retriever()
        return self._retriever

    @property
    def local_backend(self) -> LocalTransformersBackend:
        if self._local_backend is None:
            self._local_backend = LocalTransformersBackend(
                ROOT / "models" / "fab-rules-ft" / "merged",
                SYSTEM_PROMPT,
            )
        return self._local_backend

    def _check_local_model(self) -> bool:
        if self._local_model_available is None:
            self._local_model_available = self.local_backend.is_available()
        return self._local_model_available

    def _query_local_model(self, prompt: str, context: str) -> str:
        self.last_backend = "local-transformers"
        return self.local_backend.generate(prompt, context)

    def _check_ollama(self) -> tuple[bool, bool]:
        """Returns (ollama_running, model_available)."""
        if self._ollama_available is not None:
            return self._ollama_available, self._ollama_model_available
        try:
            import ollama
            models = ollama.list()
            available = [m.model for m in models.models]
            running = True
            matches = [
                model_name
                for model_name in available
                if model_name == self.ollama_model
                or model_name.startswith(f"{self.ollama_model}:")
                or self.ollama_model in model_name
            ]
            has_model = bool(matches)
            if has_model:
                self.ollama_model = matches[0]
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
        response = ollama.chat(
            model=self.ollama_model,
            messages=messages,
            options={
                "num_gpu": self.ollama_num_gpu,
                "num_ctx": self.ollama_num_ctx,
            },
        )
        self.last_backend = "ollama"
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
        self.last_backend = "claude"
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
        if self.use_rag and self.retriever.is_ready():
            rag_context = self.retriever.query_all(
                question, n_rules=self.n_rules, n_cards=self.n_cards)

        context_parts = []
        if rag_context:
            context_parts.append(rag_context)
        if extra_context:
            context_parts.append(f"## Additional Context\n{extra_context}")
        context = "\n\n".join(context_parts)

        # Choose backend
        if self.prefer_ollama:
            ollama_running, ollama_has_model = self._check_ollama()
            if ollama_running and ollama_has_model:
                return self._query_ollama(question, context)

            if self._check_local_model():
                try:
                    return self._query_local_model(question, context)
                except Exception:
                    self._local_model_available = False
        else:
            if self._check_local_model():
                try:
                    return self._query_local_model(question, context)
                except Exception:
                    self._local_model_available = False

            ollama_running, ollama_has_model = self._check_ollama()
            if ollama_running and ollama_has_model:
                return self._query_ollama(question, context)

        return self._query_claude(question, context)

    def review_code(self, code: str, question: str = "") -> str:
        """Review a code implementation for rules compliance."""
        prompt = question or "Review this implementation for FAB rules compliance. Flag any deviations."
        return self.ask(prompt, extra_context=f"```python\n{code}\n```")

"""
card_agent.py — Offline card implementation validator agent.

Backends (in priority order):
    1. Local merged Transformers model (models/fab-cards-ft/merged, if available)
    2. Ollama local model (fab-cards-ft if fine-tuned, else any available model)
    3. Anthropic Claude API (fallback when local models unavailable)

Usage:
    from offline_agents.agents.card_agent import CardAgent
    agent = CardAgent()
    result = agent.ask("When does Big Bully's effect trigger?", slug="big_bully")
    result = agent.validate("etchings_of_arcana", code_snippet)
    result = agent.sniff_test_all()   # breadth-first scan of all registered cards
"""
from __future__ import annotations

import json
import pathlib
import re
import textwrap
from typing import Optional

from offline_agents.agents.local_transformers_backend import LocalTransformersBackend
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
        ollama_model: str = "fab-cards-ft-q4ks",  # falls back to qwen2.5:7b if not found
        fallback_model: str = "claude-sonnet-4-6",
        use_rag: bool = True,
        prefer_ollama: bool = False,
        ollama_num_gpu: int = 16,
        ollama_num_ctx: int = 4096,
    ):
        self.use_rag = use_rag
        self.prefer_ollama = prefer_ollama
        self.ollama_model = ollama_model
        self.fallback_model = fallback_model
        self.ollama_num_gpu = ollama_num_gpu
        self.ollama_num_ctx = ollama_num_ctx
        self.last_backend: Optional[str] = None
        self._retriever: Optional[Retriever] = None
        self._card_db: Optional[dict] = None
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
                ROOT / "models" / "fab-cards-ft" / "merged",
                SYSTEM_PROMPT,
            )
        return self._local_backend

    def _check_local_model(self) -> bool:
        if self._local_model_available is None:
            self._local_model_available = self.local_backend.is_available()
        return self._local_model_available

    @property
    def card_db(self) -> dict:
        if self._card_db is None:
            data = json.loads(CARD_JSON.read_text(encoding="utf-8"))
            self._card_db = data.get("by_slug", data)
        return self._card_db

    @staticmethod
    def _normalize_lookup(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")

    def resolve_card_slugs(self, identifier: str) -> list[str]:
        """Resolve a shorthand slug or card name to one or more DB slugs."""
        # Direct key check first — preserves slugs with double underscores (e.g. burn_up__shock_red)
        if identifier in self.card_db:
            return [identifier]

        normalized = self._normalize_lookup(identifier)
        if not normalized:
            return []

        if normalized in self.card_db:
            return [normalized]

        exact_name_matches = sorted(
            slug
            for slug, card in self.card_db.items()
            if self._normalize_lookup(card.get("name", "")) == normalized
        )
        if exact_name_matches:
            return exact_name_matches

        prefix_matches = sorted(
            slug for slug in self.card_db if slug.startswith(f"{normalized}_")
        )
        if prefix_matches:
            return prefix_matches

        return []

    def resolve_card_slug(self, identifier: str) -> Optional[str]:
        matches = self.resolve_card_slugs(identifier)
        return matches[0] if matches else None

    def _format_card_entry(self, slug: str, card: dict) -> str:
        lines = [
            f"Slug: {slug}",
            f"Name: {card.get('name', slug)}",
            f"Types: {', '.join(card.get('types', []))}",
        ]
        for field_name in ("pitch", "cost", "power", "defense", "health", "arcane"):
            value = card.get(field_name)
            if value:
                lines.append(f"{field_name.title()}: {value}")
        keywords = (card.get("card_keywords") or []) + (card.get("ability_and_effect_keywords") or [])
        if keywords:
            lines.append(f"Keywords: {', '.join(keywords)}")
        functional_text = card.get("functional_text", "")
        if functional_text:
            lines.append(f"Text: {functional_text}")
        return "\n".join(lines)

    def get_card_text(self, slug: str) -> str:
        """Return the official card text for a given slug."""
        matches = self.resolve_card_slugs(slug)
        if not matches:
            return f"(Card '{slug}' not found in database)"

        if len(matches) == 1:
            resolved_slug = matches[0]
            return self._format_card_entry(resolved_slug, self.card_db[resolved_slug])

        sections = [f"Matched slugs: {', '.join(matches)}"]
        for resolved_slug in matches:
            sections.append(self._format_card_entry(resolved_slug, self.card_db[resolved_slug]))
        return "\n\n".join(sections)

    def _check_ollama(self) -> tuple[bool, bool]:
        if self._ollama_available is not None:
            return self._ollama_available, self._ollama_model_available
        try:
            import ollama

            models = ollama.list()
            available = [model.model for model in models.models]
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
            if not has_model and available:
                preferred = next((model_name for model_name in available if "qwen2.5" in model_name), None)
                self.ollama_model = preferred or available[0]
                has_model = True
        except Exception:
            running = False
            has_model = False
        self._ollama_available = running
        self._ollama_model_available = has_model
        return running, has_model

    def _query_local_model(self, prompt: str, context: str) -> str:
        self.last_backend = "local-transformers"
        return self.local_backend.generate(prompt, context)

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

    def _query(self, prompt: str, context: str) -> str:
        if self.prefer_ollama:
            ollama_running, ollama_has_model = self._check_ollama()
            if ollama_running and ollama_has_model:
                return self._query_ollama(prompt, context)

            if self._check_local_model():
                try:
                    return self._query_local_model(prompt, context)
                except Exception:
                    self._local_model_available = False
        else:
            if self._check_local_model():
                try:
                    return self._query_local_model(prompt, context)
                except Exception:
                    self._local_model_available = False

            ollama_running, ollama_has_model = self._check_ollama()
            if ollama_running and ollama_has_model:
                return self._query_ollama(prompt, context)

        return self._query_claude(prompt, context)

    def ask(self, question: str, slug: Optional[str] = None) -> str:
        """Ask a direct card question with optional official card text context."""
        context_parts = []
        resolved_slug = self.resolve_card_slug(slug) if slug else None
        if slug:
            if resolved_slug is None:
                return f"Card '{slug}' not found in database."
            context_parts.append(f"## Official Card Text\n{self.get_card_text(resolved_slug)}")

        rag_context = ""
        if self.use_rag and self.retriever.is_ready():
            rag_query = question
            if resolved_slug:
                card_name = self.card_db.get(resolved_slug, {}).get("name", slug)
                rag_query = f"{card_name}\n{question}"
            rag_context = self.retriever.query_all(rag_query, n_rules=4, n_cards=3)

        if rag_context:
            context_parts.append(rag_context)

        return self._query(question, "\n\n".join(context_parts))

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
        resolved_slug = self.resolve_card_slug(slug)
        rag_context = ""
        if self.use_rag and self.retriever.is_ready() and resolved_slug:
            card_name = self.card_db.get(resolved_slug, {}).get("name", slug)
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

    def sniff_test_all(
        self,
        triggers_file: Optional[pathlib.Path] = None,
        registry_file: Optional[pathlib.Path] = None,
    ) -> str:
        """
        Quick breadth-first sniff test of all card implementations.
        Reads triggers.py and registry.py, builds a summary prompt, queries the agent.
        """
        triggers_file = triggers_file or (ROOT / "engine" / "card_effects" / "triggers.py")
        registry_file = registry_file or (ROOT / "engine" / "card_effects" / "registry.py")

        triggers_src = triggers_file.read_text(encoding="utf-8", errors="replace") if triggers_file.exists() else ""
        registry_src = registry_file.read_text(encoding="utf-8", errors="replace") if registry_file.exists() else ""

        rag_context = ""
        if self.use_rag and self.retriever.is_ready():
            rag_context = self.retriever.query_all(
                "card triggers effects damage arcane go again",
                n_rules=4,
                n_cards=4,
            )

        context = rag_context
        prompt = textwrap.dedent(
            f"""
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
            """
        ).strip()
        return self._query(prompt, context)

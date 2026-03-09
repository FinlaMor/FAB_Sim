"""
retriever.py — Query the ChromaDB vector store for relevant context.

Usage:
    from offline_agents.rag.retriever import Retriever
    r = Retriever()
    docs = r.query_rules("What does Arcane Barrier do?", n=5)
    docs = r.query_cards("Etchings of Arcana", n=3)
    docs = r.query_all("How does amp interact with Arcane Barrier?", n=8)
"""
from __future__ import annotations

import pathlib
from functools import cached_property
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

ROOT = pathlib.Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "offline_agents" / "rag" / "chroma_db"
EMBED_MODEL = "all-MiniLM-L6-v2"


class Retriever:
    """Thin wrapper around ChromaDB that returns plain text context strings."""

    def __init__(self, db_path: str | pathlib.Path = DB_PATH):
        self._db_path = str(db_path)
        ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
        self._client = chromadb.PersistentClient(path=self._db_path)
        self._ef = ef
        # Lazily loaded collections
        self._rules_col: Optional[chromadb.Collection] = None
        self._cards_col: Optional[chromadb.Collection] = None

    def _rules(self) -> chromadb.Collection:
        if self._rules_col is None:
            self._rules_col = self._client.get_collection(
                "fab_rules", embedding_function=self._ef)
        return self._rules_col

    def _cards(self) -> chromadb.Collection:
        if self._cards_col is None:
            self._cards_col = self._client.get_collection(
                "fab_cards", embedding_function=self._ef)
        return self._cards_col

    def query_rules(self, query: str, n: int = 6) -> list[str]:
        """Return top-N rules text chunks relevant to the query."""
        results = self._rules().query(query_texts=[query], n_results=n)
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        out = []
        for doc, meta in zip(docs, metas):
            source = meta.get("source", "?")
            out.append(f"[{source}]\n{doc}")
        return out

    def query_cards(self, query: str, n: int = 4) -> list[str]:
        """Return top-N card descriptions relevant to the query."""
        results = self._cards().query(query_texts=[query], n_results=n)
        docs = results.get("documents", [[]])[0]
        return docs

    def query_all(self, query: str, n_rules: int = 5, n_cards: int = 3) -> str:
        """Return a combined context string from rules + cards, ready to inject into a prompt."""
        rule_chunks = self.query_rules(query, n=n_rules)
        card_chunks = self.query_cards(query, n=n_cards)

        sections = []
        if rule_chunks:
            sections.append("## Relevant Rules\n" + "\n\n".join(rule_chunks))
        if card_chunks:
            sections.append("## Relevant Cards\n" + "\n\n".join(card_chunks))
        return "\n\n".join(sections)

    def is_ready(self) -> bool:
        """Return True if the DB has been built and both collections exist."""
        try:
            self._rules()
            self._cards()
            return True
        except Exception:
            return False

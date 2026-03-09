"""
embedder.py — Build and persist the ChromaDB vector store from FAB rules + card data.

Run this once (or whenever source docs change):
    python -m offline_agents.rag.embedder

Collections created:
    fab_rules  — chunked ref/*.txt documents (rules, release notes, glossary)
    fab_cards  — one document per card from card_data/slug_index.json
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import textwrap

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parents[2]
REF_DIR = ROOT / "ref"
CARD_JSON = ROOT / "card_data" / "slug_index.json"
DB_PATH = ROOT / "offline_agents" / "rag" / "chroma_db"

EMBED_MODEL = "all-MiniLM-L6-v2"   # fast, 384-dim, CPU-friendly (~80 MB)
CHUNK_SIZE = 600          # characters per chunk
CHUNK_OVERLAP = 100       # overlap between consecutive chunks


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping character chunks, splitting on newlines where possible."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        if end < len(text):
            # Try to break at a newline near the end of the window
            nl = text.rfind("\n", start, end)
            if nl > start + overlap:
                end = nl
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks


# ---------------------------------------------------------------------------
# Ingest rules docs
# ---------------------------------------------------------------------------

def _ingest_rules(collection: chromadb.Collection) -> int:
    """Embed all ref/*.txt files into the rules collection."""
    total = 0
    for txt_file in sorted(REF_DIR.glob("*.txt")):
        text = txt_file.read_text(encoding="utf-8", errors="replace")
        chunks = _chunk_text(text)
        ids = [f"{txt_file.stem}__chunk_{i}" for i in range(len(chunks))]
        metas = [{"source": txt_file.name, "chunk": i} for i in range(len(chunks))]
        # Add in batches of 100 to avoid memory spikes
        for batch_start in range(0, len(chunks), 100):
            collection.add(
                documents=chunks[batch_start:batch_start + 100],
                ids=ids[batch_start:batch_start + 100],
                metadatas=metas[batch_start:batch_start + 100],
            )
        total += len(chunks)
        print(f"  {txt_file.name}: {len(chunks)} chunks")
    return total


# ---------------------------------------------------------------------------
# Ingest card data
# ---------------------------------------------------------------------------

def _card_to_text(slug: str, data: dict) -> str:
    """Render a card dict to a plain-text description suitable for embedding."""
    parts = [
        f"Card: {data.get('name', slug)} (slug: {slug})",
        f"Types: {', '.join(data.get('types', []))}",
    ]
    for field in ("pitch", "cost", "power", "defense", "health", "intelligence", "arcane"):
        val = data.get(field)
        if val:
            parts.append(f"{field.title()}: {val}")
    kws = data.get("card_keywords", []) + data.get("ability_and_effect_keywords", []) + data.get("granted_keywords", [])
    if kws:
        parts.append(f"Keywords: {', '.join(kws)}")
    fx = data.get("functional_text", "")
    if fx:
        parts.append(f"Text: {fx}")
    abilities = data.get("abilities_and_effects", [])
    if abilities:
        parts.append(f"Abilities: {'; '.join(str(a) for a in abilities)}")
    return "\n".join(parts)


def _ingest_cards(collection: chromadb.Collection) -> int:
    """Embed all cards from slug_index.json into the cards collection."""
    data = json.loads(CARD_JSON.read_text(encoding="utf-8"))
    by_slug: dict = data.get("by_slug", data)  # handle both wrapped and flat formats
    slugs = list(by_slug.keys())
    print(f"  {len(slugs)} cards found")

    batch_docs, batch_ids, batch_metas = [], [], []

    def flush():
        if batch_docs:
            collection.add(documents=batch_docs, ids=batch_ids, metadatas=batch_metas)
            batch_docs.clear(); batch_ids.clear(); batch_metas.clear()

    for slug, card_data in by_slug.items():
        text = _card_to_text(slug, card_data)
        batch_docs.append(text)
        batch_ids.append(slug)
        types = card_data.get("types", [])
        batch_metas.append({
            "slug": slug,
            "name": card_data.get("name", slug),
            "types": ",".join(types),
        })
        if len(batch_docs) >= 100:
            flush()
    flush()
    return len(slugs)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_db(reset: bool = False) -> chromadb.ClientAPI:
    """Build (or rebuild) the ChromaDB vector store. Returns the client."""
    ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    client = chromadb.PersistentClient(path=str(DB_PATH))

    if reset:
        for name in ("fab_rules", "fab_cards"):
            try:
                client.delete_collection(name)
            except Exception:
                pass

    print("=== Ingesting rules docs ===")
    rules_col = client.get_or_create_collection("fab_rules", embedding_function=ef)
    existing_rules = rules_col.count()
    if existing_rules > 0 and not reset:
        print(f"  fab_rules already has {existing_rules} chunks — skipping (use --reset to rebuild)")
    else:
        n = _ingest_rules(rules_col)
        print(f"  Total rules chunks: {n}")

    print("=== Ingesting card data ===")
    cards_col = client.get_or_create_collection("fab_cards", embedding_function=ef)
    existing_cards = cards_col.count()
    if existing_cards > 0 and not reset:
        print(f"  fab_cards already has {existing_cards} cards — skipping (use --reset to rebuild)")
    else:
        n = _ingest_cards(cards_col)
        print(f"  Total cards: {n}")

    print("=== Done ===")
    return client


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    build_db(reset=reset)

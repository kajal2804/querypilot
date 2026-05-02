"""
agents/vector_store.py — Vector RAG Fallback
---------------------------------------------
Stores successful Q&A pairs in ChromaDB (local, no server needed).
When Groq is rate-limited or SQL generation fails, this is queried
for the most similar past question and its cached answer is returned.

Flow:
  Successful query → store(question, answer, sql, tables)
  Groq fails (429 / error) → search(question) → return best match
"""

import os
import chromadb
from chromadb.utils import embedding_functions

# Local persistent ChromaDB (stored in .chromadb/ inside project)
_DB_PATH    = os.path.join(os.path.dirname(__file__), "..", ".chromadb")
_COLLECTION = "query_cache"

# Use local sentence-transformers embeddings — no API key needed
_EMBED_FN = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

_SIMILARITY_THRESHOLD = 0.92   # cosine distance below this = good match


class VectorStore:
    """
    Singleton-style wrapper around a ChromaDB collection.
    Persists to disk so cached answers survive restarts.
    """

    def __init__(self):
        self._client     = chromadb.PersistentClient(path=_DB_PATH)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION,
            embedding_function=_EMBED_FN,
            metadata={"hnsw:space": "cosine"},
        )

    # ── write ─────────────────────────────────────────────────────────────────

    def store(self, question: str, answer: str, sql: str, tables: list[str]) -> None:
        """Save a successful Q&A pair."""
        import hashlib, json
        doc_id = hashlib.md5(question.lower().strip().encode()).hexdigest()
        self._collection.upsert(
            ids       = [doc_id],
            documents = [question],
            metadatas = [{
                "answer": answer,
                "sql":    sql,
                "tables": json.dumps(tables),
            }],
        )

    # ── read ──────────────────────────────────────────────────────────────────

    def search(self, question: str, n_results: int = 1) -> dict | None:
        """
        Find the most similar cached question.
        Returns the cached result dict or None if no good match found.
        """
        count = self._collection.count()
        if count == 0:
            return None

        results = self._collection.query(
            query_texts = [question],
            n_results   = min(n_results, count),
        )

        if not results["ids"][0]:
            return None

        distance = results["distances"][0][0]   # cosine distance (lower = more similar)
        if distance > (1 - _SIMILARITY_THRESHOLD):
            return None   # not similar enough

        import json
        meta = results["metadatas"][0][0]
        return {
            "answer":           meta["answer"],
            "sql":              meta["sql"],
            "tables":           json.loads(meta.get("tables", "[]")),
            "similarity_score": round(1 - distance, 3),
            "matched_question": results["documents"][0][0],
        }

    def clear(self) -> None:
        """Delete all cached entries."""
        self._client.delete_collection(_COLLECTION)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION,
            embedding_function=_EMBED_FN,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        return self._collection.count()

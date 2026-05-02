"""
agents/doc_store.py — Document Knowledge Base
----------------------------------------------
Ingests PDF and plain-text files into a ChromaDB collection.
Supports semantic search so the /ask pipeline can pull relevant
document context when the question cannot be fully answered by SQL.

Supported file types: .pdf, .txt, .md
"""

import os
import re
import hashlib
import chromadb
from chromadb.utils import embedding_functions

_DB_PATH    = os.path.join(os.path.dirname(__file__), "..", ".chromadb")
_COLLECTION = "documents"
_CHUNK_SIZE = 500    # characters per chunk
_CHUNK_OVERLAP = 50

_EMBED_FN = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)


class DocStore:
    """
    Manages a ChromaDB collection of document chunks.
    Each document is split into overlapping chunks for better retrieval.
    """

    def __init__(self):
        self._client     = chromadb.PersistentClient(path=_DB_PATH)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION,
            embedding_function=_EMBED_FN,
            metadata={"hnsw:space": "cosine"},
        )

    # ── ingest ────────────────────────────────────────────────────────────────

    def ingest_file(self, file_path: str, filename: str) -> dict:
        """
        Read a PDF or text file, chunk it, and store in ChromaDB.
        Returns {"chunks": int, "filename": str, "error": None | str}
        """
        ext = os.path.splitext(filename)[1].lower()
        try:
            if ext == ".pdf":
                text = _extract_pdf(file_path)
            elif ext in (".txt", ".md"):
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            else:
                return {"chunks": 0, "filename": filename,
                        "error": f"Unsupported file type: {ext}"}

            if not text.strip():
                return {"chunks": 0, "filename": filename,
                        "error": "File appears to be empty or unreadable."}

            chunks = _chunk_text(text, _CHUNK_SIZE, _CHUNK_OVERLAP)
            self._store_chunks(chunks, filename)
            return {"chunks": len(chunks), "filename": filename, "error": None}

        except Exception as exc:
            return {"chunks": 0, "filename": filename, "error": str(exc)}

    def ingest_text(self, text: str, source_name: str) -> dict:
        """Ingest raw text directly (for internal notes)."""
        chunks = _chunk_text(text, _CHUNK_SIZE, _CHUNK_OVERLAP)
        self._store_chunks(chunks, source_name)
        return {"chunks": len(chunks), "filename": source_name, "error": None}

    # ── search ────────────────────────────────────────────────────────────────

    def search(self, query: str, n_results: int = 3) -> list[dict]:
        """
        Return the top-N most relevant document chunks for the query.
        Each result: {"text": str, "source": str, "score": float}
        """
        count = self._collection.count()
        if count == 0:
            return []

        results = self._collection.query(
            query_texts = [query],
            n_results   = min(n_results, count),
        )

        out = []
        for i, doc in enumerate(results["documents"][0]):
            distance = results["distances"][0][i]
            score    = round(1 - distance, 3)
            if score < 0.3:   # too dissimilar — skip
                continue
            out.append({
                "text":   doc,
                "source": results["metadatas"][0][i].get("source", "unknown"),
                "score":  score,
            })
        return out

    def list_documents(self) -> list[str]:
        """Return unique source file names that have been ingested."""
        if self._collection.count() == 0:
            return []
        results = self._collection.get(include=["metadatas"])
        sources = {m["source"] for m in results["metadatas"]}
        return sorted(sources)

    def count(self) -> int:
        return self._collection.count()

    # ── internal ──────────────────────────────────────────────────────────────

    def _store_chunks(self, chunks: list[str], source: str) -> None:
        ids       = []
        documents = []
        metadatas = []
        for i, chunk in enumerate(chunks):
            uid = hashlib.md5(f"{source}:{i}:{chunk[:40]}".encode()).hexdigest()
            ids.append(uid)
            documents.append(chunk)
            metadatas.append({"source": source, "chunk_index": i})
        self._collection.upsert(ids=ids, documents=documents, metadatas=metadatas)


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_pdf(file_path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(file_path)
    pages  = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks, breaking at sentence boundaries."""
    text   = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not text:
        return []
    chunks = []
    start  = 0
    while start < len(text):
        end   = min(start + size, len(text))
        chunk = text[start:end]
        # Try to end at a sentence boundary
        if end < len(text):
            last_period = max(chunk.rfind(". "), chunk.rfind("\n"))
            if last_period > size // 2:
                end   = start + last_period + 1
                chunk = text[start:end]
        stripped = chunk.strip()
        if len(stripped) > 30:
            chunks.append(stripped)
        next_start = end - overlap
        if next_start <= start:   # guard against infinite loop
            next_start = end
        start = next_start
        if start >= len(text):
            break
    return chunks

from __future__ import annotations

import hashlib
import math
from typing import Any

from .config import CHROMA_DIR


def entry_text(entry: dict[str, Any]) -> str:
    return " ".join(
        [
            entry.get("category", ""),
            entry.get("title", ""),
            entry.get("content", ""),
            " ".join(entry.get("tags", [])),
        ]
    ).strip()


class HashEmbeddingFunction:
    """Small local embedding function for Chroma; avoids hosted embedding APIs."""

    def __call__(self, input: list[str]) -> list[list[float]]:
        vectors = []
        for text in input:
            vector = [0.0] * 128
            for token in text.lower().split():
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = digest[0] % len(vector)
                vector[index] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class ChromaRAGStore:
    def __init__(self) -> None:
        self.available = False
        self.collection = None
        try:
            import chromadb

            CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            self.collection = client.get_or_create_collection(
                name="autonova_business_kb",
                embedding_function=HashEmbeddingFunction(),
            )
            self.available = True
        except Exception:
            self.available = False

    def sync(self, entries: list[dict[str, Any]]) -> None:
        if not self.available or self.collection is None:
            return
        ids = [entry["id"] for entry in entries]
        documents = [entry_text(entry) for entry in entries]
        metadatas = [
            {
                "category": entry.get("category", ""),
                "title": entry.get("title", ""),
                "updated_at": entry.get("updated_at", ""),
            }
            for entry in entries
        ]
        if ids:
            self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def search(self, query: str, entries_by_id: dict[str, dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
        if not self.available or self.collection is None:
            return []
        result = self.collection.query(query_texts=[query], n_results=limit)
        ids = result.get("ids", [[]])[0]
        return [entries_by_id[item_id] for item_id in ids if item_id in entries_by_id]


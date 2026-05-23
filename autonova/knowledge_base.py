from __future__ import annotations

import re
from typing import Any

from .config import KNOWLEDGE_PATH
from .rag_store import ChromaRAGStore
from .storage import now_iso, read_json, write_json


TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


class KnowledgeBase:
    def __init__(self) -> None:
        self.entries = read_json(KNOWLEDGE_PATH, [])
        self.rag = ChromaRAGStore()
        self.rag.sync(self.entries)

    def save(self) -> None:
        write_json(KNOWLEDGE_PATH, self.entries)

    def list(self) -> list[dict[str, Any]]:
        return self.entries

    def add(self, category: str, title: str, content: str, tags: list[str] | None = None) -> dict[str, Any]:
        entry = {
            "id": f"kb-{len(self.entries) + 1:03d}",
            "category": category.strip() or "note",
            "title": title.strip() or "Untitled",
            "content": content.strip(),
            "tags": tags or [],
            "updated_at": now_iso(),
        }
        self.entries.append(entry)
        self.save()
        self.rag.sync([entry])
        return entry

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        by_id = {entry["id"]: entry for entry in self.entries}
        rag_matches = self.rag.search(query, by_id, limit)
        if rag_matches:
            return rag_matches

        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        scored = []
        for entry in self.entries:
            haystack = " ".join(
                [
                    entry.get("category", ""),
                    entry.get("title", ""),
                    entry.get("content", ""),
                    " ".join(entry.get("tags", [])),
                ]
            )
            entry_tokens = _tokens(haystack)
            score = len(query_tokens & entry_tokens)
            title_bonus = len(query_tokens & _tokens(entry.get("title", ""))) * 2
            if score or title_bonus:
                scored.append((score + title_bonus, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

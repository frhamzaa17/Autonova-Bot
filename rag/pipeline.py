from __future__ import annotations

from llm.ollama_client import generate_response
from rag.knowledge_base import retrieve_context


def answer_query(query: str, tenant_id: str | None = None, memory: str | None = None) -> str:
    context, has_context = retrieve_context(query, tenant_id=tenant_id)
    parts = []
    if memory:
        parts.append(f"Recent conversation:\n{memory}")
    if has_context:
        parts.append(f"Company knowledge base:\n{context}")
    return generate_response(query, "\n\n".join(parts) if parts else None)

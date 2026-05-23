from __future__ import annotations

from llm.ollama_client import generate_response
from rag.knowledge_base import retrieve_context


def answer_query(query: str) -> str:
    context, has_context = retrieve_context(query)
    return generate_response(query, context if has_context else None)

from __future__ import annotations

from llm.ollama_client import generate_response
from rag.business_queries import answer_pending_rent, answer_property_count
from rag.document_queries import answer_document_count, answer_document_records, answer_full_document_query
from rag.knowledge_base import retrieve_context
from utils.web_search import answer_with_web, wants_web_search


def answer_query(
    query: str,
    tenant_id: str | None = None,
    memory: str | None = None,
    preferred_file: str | None = None,
) -> str:
    document_count = answer_document_count(query, tenant_id=tenant_id, preferred_file=preferred_file)
    if document_count:
        return document_count

    document_records = answer_document_records(query, tenant_id=tenant_id, preferred_file=preferred_file)
    if document_records:
        return document_records

    document_answer = answer_full_document_query(query, tenant_id=tenant_id, preferred_file=preferred_file)
    if document_answer:
        return document_answer

    for deterministic in (answer_pending_rent, answer_property_count):
        deterministic_answer = deterministic(query, tenant_id=tenant_id)
        if deterministic_answer:
            return deterministic_answer

    context, has_context = retrieve_context(query, tenant_id=tenant_id)
    if wants_web_search(query):
        try:
            answer, _sources = answer_with_web(query, context if has_context else None)
            return answer
        except Exception as exc:
            return f"I could not use web search for this request: {exc}"

    parts = []
    if memory:
        parts.append(f"Recent conversation:\n{memory}")
    if has_context:
        parts.append(f"Company knowledge base:\n{context}")
    return generate_response(query, "\n\n".join(parts) if parts else None)

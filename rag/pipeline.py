from __future__ import annotations

import re

from llm.ollama_client import generate_response
from rag.business_queries import answer_pending_rent, answer_property_count
from rag.document_queries import (
    answer_document_count,
    answer_document_records,
    answer_full_document_query,
    is_document_scoped_query,
)
from rag.knowledge_base import retrieve_context
from rag.structured_store import answer_structured_query, structured_context, structured_documents
from utils.web_search import answer_with_web, wants_web_search


CASUAL_CHAT_RE = re.compile(
    r"^\s*(hi|hello|hey|good\s+(morning|afternoon|evening)|how\s+are\s+you|how'?s\s+it\s+going|"
    r"what'?s\s+up|thanks?|thank\s+you|ok|okay|cool|great|nice)\s*[!.?]*\s*$",
    re.I,
)
FOLLOWUP_DETAIL_RE = re.compile(
    r"^\s*(give|show|list|tell\s+me)?\s*(me\s+)?(more\s+)?(details?|them|these|those|records?|list)\s*[.!?]*\s*$",
    re.I,
)
LOCAL_KNOWLEDGE_RE = re.compile(
    r"\b(this|that|uploaded|local|knowledge\s+base|kb|document|pdf|file|sheet|spreadsheet|docx|excel|"
    r"from\s+(?:my|our|the)\s+(?:data|file|document|kb|knowledge\s+base)|"
    r"agreement|tenant|rent|property|contact|question|record|table|row|paragraph|section)\b",
    re.I,
)
EXPLICIT_WEB_RE = re.compile(
    r"\b(web|online|internet|latest|current|today|recent|news|look\s+up|search\s+(?:the\s+)?web|google|scrape)\b",
    re.I,
)
GENERAL_INFO_RE = re.compile(
    r"\b(how\s+to|what\s+is|who\s+is|where\s+is|when\s+is|why\s+does|explain|guide|tutorial|steps?|"
    r"strategy|strategies|best\s+way|best|learn|analy[sz]e|analysis|evaluate|research|compare|forecast|outlook|"
    r"meaning|definition|overview|tips?|examples?|tell\s+me\s+about|recommend|suggest)\b",
    re.I,
)
LOCAL_OPERATION_RE = re.compile(
    r"\b(how\s+many|count|number\s+of|total|sum|average|avg|highest|lowest|max|min|list|show|give|details?|"
    r"which|who|find|search|expire|expires|expiring|pending|due|rent|tenant|agreement|property|contact|record|table|row)\b",
    re.I,
)
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "what", "when", "where", "which", "who",
    "how", "why", "are", "is", "was", "were", "will", "would", "could", "should", "give", "show",
    "tell", "more", "details", "about", "into", "your", "you", "me", "my", "our", "their", "there",
}


def _contextualize_followup(query: str, memory: str | None) -> str:
    if not memory or not FOLLOWUP_DETAIL_RE.match(query):
        return query
    recent = memory.lower()[-2500:]
    if "expiring soon" in recent or "agreement(s) expire" in recent or "expire within" in recent:
        return "list expiring soon agreements with full details"
    if "renewal" in recent and ("pipeline" in recent or "proposed" in recent):
        return "list renewal pipeline actions with full details"
    if "contact" in recent or "phone" in recent or "email" in recent:
        return "list contact records with full details"
    if "table row" in recent or "structured table" in recent:
        return "show table rows"
    if "agreement" in recent or "tenant" in recent or "rent" in recent:
        return "list agreements with full details"
    if "document" in recent or "structured" in recent:
        return "summarize structured form"
    return query


def _query_tokens(query: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(query.lower()) if len(token) > 2 and token not in STOPWORDS}


def _local_relevance_score(query: str, tenant_id: str | None) -> int:
    query_tokens = _query_tokens(query)
    if not query_tokens:
        return 0

    best = 0
    for document in structured_documents(tenant_id):
        doc_text = f"{document.get('file_name', '')} {document.get('document_type', '')}"
        doc_tokens = _query_tokens(doc_text)
        best = max(best, len(query_tokens & doc_tokens) * 2)
        for record in document.get("records", [])[:1000]:
            haystack = " ".join(str(value) for key, value in record.items() if key != "source_file")
            record_tokens = _query_tokens(haystack)
            overlap = len(query_tokens & record_tokens)
            if overlap:
                best = max(best, overlap)
            for value in record.values():
                if isinstance(value, str) and len(value) >= 4 and value.lower() in query.lower():
                    best = max(best, 5)
    return best


def _has_strong_local_entity(query: str, tenant_id: str | None) -> bool:
    lower = query.lower()
    if re.search(r"\b[A-Z]{1,5}-\d{2,}\b|\b[A-Z]{2,}\d{4,}\b", query):
        return True
    for document in structured_documents(tenant_id):
        file_name = str(document.get("file_name", "")).lower()
        if file_name and file_name in lower:
            return True
        for record in document.get("records", [])[:1000]:
            for field in ("tenant", "name", "agreement_id", "property_id", "reference_id", "email", "phone"):
                value = str(record.get(field, "")).strip()
                if len(value) >= 4 and value.lower() in lower:
                    return True
    return False


def _should_use_web_before_local(query: str, document_scoped: bool, tenant_id: str | None) -> bool:
    if document_scoped:
        return False
    if EXPLICIT_WEB_RE.search(query):
        return True

    local_score = _local_relevance_score(query, tenant_id)
    strong_local_entity = _has_strong_local_entity(query, tenant_id)
    explicit_local = bool(LOCAL_KNOWLEDGE_RE.search(query))
    local_operation = bool(LOCAL_OPERATION_RE.search(query))
    general_info = bool(GENERAL_INFO_RE.search(query))

    if general_info and not strong_local_entity and not document_scoped:
        return True
    if explicit_local and local_operation and not general_info:
        return False
    if local_operation and local_score >= 1 and not general_info:
        return False
    if local_score >= 5 and not general_info:
        return False
    if wants_web_search(query):
        return True
    if general_info and local_score < 5:
        return True
    return False


def answer_query(
    query: str,
    tenant_id: str | None = None,
    memory: str | None = None,
    preferred_file: str | None = None,
) -> str:
    query = _contextualize_followup(query, memory)
    if CASUAL_CHAT_RE.match(query):
        return generate_response(query)

    document_scoped = is_document_scoped_query(query)
    document_preference = preferred_file if document_scoped else None
    web_first = _should_use_web_before_local(query, document_scoped, tenant_id)

    for deterministic in (answer_pending_rent, answer_property_count):
        deterministic_answer = deterministic(query, tenant_id=tenant_id)
        if deterministic_answer:
            return deterministic_answer

    if web_first:
        try:
            answer, _sources = answer_with_web(query, None)
            return answer
        except Exception as exc:
            return f"I could not use web search for this request: {exc}"

    structured_answer = answer_structured_query(query, tenant_id=tenant_id)
    if structured_answer:
        return structured_answer

    decoded_context = structured_context(query, tenant_id=tenant_id)
    context, has_context = retrieve_context(query, tenant_id=tenant_id)
    combined_context = "\n\n".join(part for part in [decoded_context, context] if part)
    has_combined_context = bool(combined_context)
    if wants_web_search(query):
        try:
            answer, _sources = answer_with_web(query, combined_context if has_combined_context else None)
            return answer
        except Exception as exc:
            return f"I could not use web search for this request: {exc}"

    if has_combined_context and not document_scoped:
        parts = []
        if memory:
            parts.append(f"Recent conversation:\n{memory}")
        parts.append(f"Structured and semantic knowledge base:\n{combined_context}")
        return generate_response(query, "\n\n".join(parts))

    document_count = answer_document_count(query, tenant_id=tenant_id, preferred_file=document_preference)
    if document_count:
        return document_count

    document_records = answer_document_records(query, tenant_id=tenant_id, preferred_file=document_preference)
    if document_records:
        return document_records

    document_answer = answer_full_document_query(query, tenant_id=tenant_id, preferred_file=document_preference)
    if document_answer:
        return document_answer

    parts = []
    if memory:
        parts.append(f"Recent conversation:\n{memory}")
    if has_combined_context:
        parts.append(f"Structured and semantic knowledge base:\n{combined_context}")
    return generate_response(query, "\n\n".join(parts) if parts else None)

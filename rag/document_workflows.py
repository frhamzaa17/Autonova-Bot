from __future__ import annotations

import re
from pathlib import Path

from docs.document_ops import create_document_bundle
from llm.ollama_client import generate_response
from rag.document_queries import MAX_FULL_CONTEXT_CHARS, _text_for_file, target_document


OUTPUT_RE = re.compile(
    r"\b(generate|create|make|prepare|provide|share|send|return|draft|write)\b.*\b(document|docx|pdf|file|report|summary|notes|list)\b"
    r"|\b(document|docx|pdf|file|report)\b.*\b(generate|create|make|prepare|provide|share|send|return|draft|write)\b",
    re.I,
)
SOURCE_RE = re.compile(r"\b(this|that|uploaded|last|same|pdf|document|file|sheet|spreadsheet|docx|excel|source)\b", re.I)
NEW_DOC_ONLY_RE = re.compile(r"\b(agreement|contract|letter|proposal|deed|notice|invoice)\b", re.I)


def wants_source_document_bundle(instruction: str, preferred_file: str | None = None) -> bool:
    if not OUTPUT_RE.search(instruction):
        return False
    if SOURCE_RE.search(instruction):
        return True
    if preferred_file and not NEW_DOC_ONLY_RE.search(instruction):
        return True
    return False


def _stem_for_instruction(instruction: str) -> str:
    lower = instruction.lower()
    if "summary" in lower:
        return "document_summary"
    if "report" in lower:
        return "document_report"
    if "notes" in lower:
        return "document_notes"
    if "list" in lower:
        return "document_list"
    return "generated_from_document"


def create_source_document_bundle(
    instruction: str,
    tenant_id: str,
    preferred_file: str | None = None,
) -> tuple[str, list[Path]] | None:
    source = target_document(instruction, tenant_id=tenant_id, preferred_file=preferred_file)
    if not source:
        return None

    try:
        text = _text_for_file(source)
    except Exception:
        return None
    if not text.strip():
        return None

    truncated = len(text) > MAX_FULL_CONTEXT_CHARS
    context = text[:MAX_FULL_CONTEXT_CHARS]
    prompt = (
        "Create a polished, complete business-style document from the uploaded source according to the user's request. "
        "Use only the supplied source content and preserve important names, numbers, dates, headings, clauses, rows, and labels. "
        "Do not mention internal implementation details. "
        "If the request asks for extraction, selection, classification, summary, notes, a list, or a report, format the output as a clean document with headings. "
        "If the source content is insufficient for part of the request, state that briefly inside the document."
    )
    if truncated:
        prompt += " The source was too large for one request, so use the visible extracted content and mention that limitation briefly."

    document_text = generate_response(
        f"{prompt}\n\nUser request:\n{instruction}",
        f"Source file: {source.name}\n\nExtracted source content:\n{context}",
    )
    files = create_document_bundle(document_text, _stem_for_instruction(instruction), tenant_id)
    return f"I created the document from {source.name}. I have attached it here.", files

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2

from docs.document_ops import create_pdf, process_uploaded_document, update_rent_tracker_pdf
from llm.ollama_client import generate_response
from rag.document_queries import _text_for_file
from rag.knowledge_base import ingest_file
from utils.config import load_settings, tenant_generated_dir, tenant_uploads_dir


ACTION_RE = re.compile(
    r"\b(update|edit|rewrite|revise|modify|change|correct|fill|replace|mark|record|set|prepare\s+updated|make\s+changes?)\b",
    flags=re.I,
)
IMPLICIT_ACTION_RE = re.compile(
    r"\b(update|edit|rewrite|revise|modify|change|correct|fill|replace|make\s+changes?)\b",
    flags=re.I,
)
DOCUMENT_RE = re.compile(r"\b(pdf|docx|xlsx|document|file|agreement|contract|letter|report|proposal|sheet|spreadsheet|tracker|form)\b", flags=re.I)
SUPPORTED_SUFFIXES = {".pdf", ".docx", ".xlsx", ".txt", ".md"}


@dataclass(frozen=True)
class DocumentActionResult:
    summary: str
    files: list[Path]
    ingested_chunks: int | None = None
    ingest_error: str | None = None


def is_document_action_request(instruction: str) -> bool:
    if instruction.strip().endswith("?") and re.match(r"\s*(what|who|which|how|does|is|has|did|was)\b", instruction, flags=re.I):
        return False
    return bool(ACTION_RE.search(instruction) and DOCUMENT_RE.search(instruction))


def _tokens(text: str) -> set[str]:
    tokens = {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 1}
    singulars = {token[:-1] for token in tokens if len(token) > 3 and token.endswith("s")}
    return tokens | singulars


def _candidate_documents(tenant_id: str) -> list[Path]:
    settings = load_settings()
    roots = [tenant_uploads_dir(settings, tenant_id), tenant_generated_dir(settings, tenant_id)]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES)
    return sorted(files, key=lambda item: item.stat().st_mtime, reverse=True)


def _in_workspace(path: Path, tenant_id: str) -> bool:
    settings = load_settings()
    roots = [tenant_uploads_dir(settings, tenant_id), tenant_generated_dir(settings, tenant_id)]
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return any(root.resolve() in resolved.parents or resolved == root.resolve() for root in roots)


def _resolve_document(instruction: str, chat_state: dict, tenant_id: str) -> Path | None:
    candidates = _candidate_documents(tenant_id)
    if not candidates:
        return None

    lower = instruction.lower()
    if re.search(r"\b(last|previous|that|this|same)\s+(document|file|pdf|docx|sheet|spreadsheet|agreement)?\b", lower):
        for key in ("last_uploaded_file", "last_document_path"):
            raw = chat_state.get(key)
            if raw:
                path = Path(raw)
                if path.exists() and _in_workspace(path, tenant_id) and path.suffix.lower() in SUPPORTED_SUFFIXES:
                    return path

    explicit_suffixes = set()
    if re.search(r"\bpdf\b", lower):
        explicit_suffixes.add(".pdf")
    if re.search(r"\bdocx|word\b", lower):
        explicit_suffixes.add(".docx")
    if re.search(r"\bxlsx|excel|sheet|spreadsheet\b", lower):
        explicit_suffixes.add(".xlsx")
    if explicit_suffixes:
        candidates = [path for path in candidates if path.suffix.lower() in explicit_suffixes]
        if not candidates:
            return None

    for path in candidates:
        if path.name.lower() in lower or path.stem.lower() in lower:
            return path

    query_tokens = _tokens(instruction)
    scored: list[tuple[int, Path]] = []
    settings = load_settings()
    for path in candidates:
        name_tokens = _tokens(path.stem.replace("_", " "))
        score = len(query_tokens & name_tokens) * 3
        if settings.uploads_dir in path.parents:
            score += 2
        if "current" in path.stem.lower() and query_tokens & {"current", "last", "previous", "that", "this", "updated"}:
            score += 2
        if path.suffix.lower() in explicit_suffixes:
            score += 3
        if "sheet" in query_tokens or "spreadsheet" in query_tokens:
            if path.suffix.lower() == ".xlsx":
                score += 2
        if score:
            scored.append((score, path))
    if scored:
        scored.sort(key=lambda item: (item[0], item[1].stat().st_mtime), reverse=True)
        return scored[0][1]

    for key in ("last_uploaded_file", "last_document_path"):
        raw = chat_state.get(key)
        if raw:
            path = Path(raw)
            if path.exists() and _in_workspace(path, tenant_id) and path.suffix.lower() in SUPPORTED_SUFFIXES:
                return path
    return None


def _rewrite_text_document(path: Path, instruction: str, tenant_id: str) -> Path:
    original = _text_for_file(path)
    revised = generate_response(
        (
            "Edit this business document according to the instruction. "
            "Return the complete revised document text only. Preserve all unchanged details, names, figures, "
            "dates, headings, numbering, rows, tables, and clauses. Do not add commentary. "
            "If the requested edit is ambiguous, make the smallest reasonable change and preserve everything else."
        )
        + f"\n\nInstruction:\n{instruction}",
        f"Original complete extracted document {path.name}:\n{original[:90000]}",
    )
    suffix = "pdf" if path.suffix.lower() == ".pdf" else "txt"
    if suffix == "pdf":
        return create_pdf(revised, f"{path.stem}_updated", tenant_id)
    output = tenant_generated_dir(load_settings(), tenant_id) / f"{path.stem}_updated.txt"
    output.write_text(revised, encoding="utf-8")
    return output


def _ingest_output(path: Path, tenant_id: str) -> tuple[int | None, str | None, Path | None]:
    settings = load_settings()
    current_copy = tenant_uploads_dir(settings, tenant_id) / f"{path.stem}_current{path.suffix}"
    try:
        copy2(path, current_copy)
        return ingest_file(current_copy, tenant_id), None, current_copy
    except Exception as exc:
        return None, str(exc), current_copy if current_copy.exists() else None


def perform_document_action(instruction: str, chat_state: dict, tenant_id: str) -> DocumentActionResult | None:
    rent_update = update_rent_tracker_pdf(instruction, tenant_id)
    if rent_update:
        output, summary = rent_update
        chunks, ingest_error, _current_copy = _ingest_output(output, tenant_id)
        return DocumentActionResult(summary=summary, files=[output], ingested_chunks=chunks, ingest_error=ingest_error)

    implicit_edit = bool(IMPLICIT_ACTION_RE.search(instruction)) and not re.match(
        r"\s*(what|who|which|how|does|is|has|did|was|why)\b",
        instruction,
        flags=re.I,
    )
    if not is_document_action_request(instruction) and not implicit_edit:
        return None

    target = _resolve_document(instruction, chat_state, tenant_id)
    if not target:
        return DocumentActionResult(
            summary="I understood this as a document action, but I could not identify which document to update. Upload the file or mention its filename.",
            files=[],
        )

    if target.suffix.lower() in {".pdf", ".txt", ".md"}:
        output = _rewrite_text_document(target, instruction, tenant_id)
    else:
        output = process_uploaded_document(target, instruction, tenant_id=tenant_id)
        if not output:
            return DocumentActionResult(summary=f"I could not edit {target.name}; this file type is not supported yet.", files=[])

    chunks, ingest_error, _current_copy = _ingest_output(output, tenant_id)
    summary = f"Updated {target.name} according to your instruction."
    return DocumentActionResult(summary=summary, files=[output], ingested_chunks=chunks, ingest_error=ingest_error)

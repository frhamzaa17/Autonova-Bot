from __future__ import annotations

import re
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from utils.config import Settings, load_settings, safe_workspace_id
from rag.ocr import IMAGE_EXTENSIONS, is_image_file, extract_image_text


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".xlsx"} | IMAGE_EXTENSIONS
TOKEN_RE = re.compile(r"[a-z0-9]+")


def _embeddings(settings: Settings) -> OllamaEmbeddings:
    return OllamaEmbeddings(model=settings.ollama_embedding_model, base_url=settings.ollama_url)


def _load_file(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if is_image_file(path):
        text = extract_image_text(path)
        return [Document(page_content=text, metadata={"source": str(path), "kind": "ocr_image"})] if text else []
    if suffix in {".txt", ".md"}:
        return TextLoader(str(path), encoding="utf-8").load()
    if suffix == ".pdf":
        return PyPDFLoader(str(path)).load()
    if suffix == ".docx":
        return Docx2txtLoader(str(path)).load()
    if suffix == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(path, data_only=False)
        docs = []
        for sheet in workbook.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                values = [str(value) for value in row if value is not None]
                if values:
                    rows.append(" | ".join(values))
            if rows:
                docs.append(Document(page_content="\n".join(rows), metadata={"source": str(path), "sheet": sheet.title}))
        return docs
    return []


def _collection_name(tenant_id: str | None = None) -> str:
    if not tenant_id:
        return "local_knowledge"
    safe = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in tenant_id)
    return f"local_knowledge_{safe}"[:63]


def _vector_store(settings: Settings, tenant_id: str | None = None) -> Chroma:
    return Chroma(
        collection_name=_collection_name(tenant_id),
        persist_directory=str(settings.chroma_dir),
        embedding_function=_embeddings(settings),
    )


def _tokens(text: str) -> set[str]:
    tokens = set(TOKEN_RE.findall(text.lower()))
    if {"property", "properties", "prop"} & tokens:
        tokens.update({"property", "properties", "prop", "listing", "listings", "portfolio"})
    if {"tenant", "tenants", "rent", "rental"} & tokens:
        tokens.update({"tenant", "tenants", "rent", "rental", "agreement", "lease"})
    if {"client", "clients", "contact", "contacts"} & tokens:
        tokens.update({"client", "clients", "contact", "contacts", "directory"})
    return tokens


def _candidate_files(settings: Settings, tenant_id: str | None = None) -> list[Path]:
    if tenant_id:
        workspace = safe_workspace_id(tenant_id)
        roots = [settings.uploads_dir / workspace, settings.data_dir / workspace]
    else:
        roots = [settings.uploads_dir, settings.data_dir]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(path)
    return files


def _lexical_context(query: str, settings: Settings, tenant_id: str | None = None, limit: int = 3, max_chars: int = 2200) -> str:
    query_tokens = _tokens(query)
    if not query_tokens:
        return ""

    scored: list[tuple[int, Path, str]] = []
    for path in _candidate_files(settings, tenant_id):
        try:
            docs = _load_file(path)
        except Exception:
            continue
        text = "\n".join(doc.page_content for doc in docs if doc.page_content.strip())
        if not text:
            continue
        haystack = f"{path.stem} {path.name} {text}"
        haystack_tokens = _tokens(haystack)
        score = len(query_tokens & haystack_tokens)
        filename_score = len(query_tokens & _tokens(path.stem)) * 3
        if score or filename_score:
            scored.append((score + filename_score, path, text[:max_chars]))

    scored.sort(key=lambda item: item[0], reverse=True)
    return "\n\n".join(
        f"Source: {path}\n{text}"
        for _score, path, text in scored[:limit]
    )


def ingest_data_folder(settings: Settings | None = None, tenant_id: str | None = None) -> int:
    settings = settings or load_settings()
    docs: list[Document] = []
    root = settings.data_dir / safe_workspace_id(tenant_id) if tenant_id else settings.data_dir
    if not root.exists():
        return 0
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            docs.extend(_load_file(path))

    if not docs:
        return 0

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=160)
    chunks = splitter.split_documents(docs)
    store = _vector_store(settings, tenant_id)
    store.add_documents(chunks)
    return len(chunks)


def ingest_file(path: Path, tenant_id: str) -> int:
    settings = load_settings()
    docs = _load_file(path)
    if not docs:
        return 0
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=160)
    chunks = splitter.split_documents(docs)
    store = _vector_store(settings, tenant_id)
    store.add_documents(chunks)
    return len(chunks)


def retrieve_context(query: str, min_relevance: float = 0.25, k: int = 6, tenant_id: str | None = None) -> tuple[str, bool]:
    settings = load_settings()
    store = _vector_store(settings, tenant_id)
    contexts: list[str] = []
    try:
        results = store.similarity_search_with_relevance_scores(query, k=k)
    except Exception:
        results = []
    relevant = [(doc, score) for doc, score in results if score >= min_relevance]

    lexical = _lexical_context(query, settings, tenant_id)
    if lexical:
        contexts.append(lexical)

    if relevant:
        contexts.append(
            "\n\n".join(
                f"Source: {doc.metadata.get('source', 'unknown')}\n{doc.page_content}"
                for doc, _score in relevant
            )
        )

    context = "\n\n".join(contexts)
    return context, bool(context)

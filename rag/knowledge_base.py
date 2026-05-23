from __future__ import annotations

from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from utils.config import Settings, load_settings


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def _embeddings(settings: Settings) -> OllamaEmbeddings:
    return OllamaEmbeddings(model=settings.ollama_embedding_model, base_url=settings.ollama_url)


def _load_file(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return TextLoader(str(path), encoding="utf-8").load()
    if suffix == ".pdf":
        return PyPDFLoader(str(path)).load()
    if suffix == ".docx":
        return Docx2txtLoader(str(path)).load()
    return []


def _vector_store(settings: Settings) -> Chroma:
    return Chroma(
        collection_name="local_knowledge",
        persist_directory=str(settings.chroma_dir),
        embedding_function=_embeddings(settings),
    )


def ingest_data_folder(settings: Settings | None = None) -> int:
    settings = settings or load_settings()
    docs: list[Document] = []
    for path in settings.data_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            docs.extend(_load_file(path))

    if not docs:
        return 0

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=160)
    chunks = splitter.split_documents(docs)
    store = _vector_store(settings)
    store.add_documents(chunks)
    return len(chunks)


def retrieve_context(query: str, min_relevance: float = 0.35, k: int = 4) -> tuple[str, bool]:
    settings = load_settings()
    store = _vector_store(settings)
    results = store.similarity_search_with_relevance_scores(query, k=k)
    relevant = [(doc, score) for doc, score in results if score >= min_relevance]
    if not relevant:
        return "", False

    context = "\n\n".join(
        f"Source: {doc.metadata.get('source', 'unknown')}\n{doc.page_content}"
        for doc, _score in relevant
    )
    return context, True

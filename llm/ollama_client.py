from __future__ import annotations

import requests

from utils.config import load_settings


def _available_models(ollama_url: str) -> set[str]:
    response = requests.get(f"{ollama_url}/api/tags", timeout=10)
    response.raise_for_status()
    return {model["name"] for model in response.json().get("models", [])}


def select_model() -> str:
    settings = load_settings()
    models = _available_models(settings.ollama_url)
    if settings.ollama_model in models:
        return settings.ollama_model
    if settings.ollama_fallback_model in models:
        return settings.ollama_fallback_model
    for model in models:
        if model.startswith("llama3") or model.startswith("mistral"):
            return model
    raise RuntimeError("No llama3 or mistral model found. Run: ollama pull llama3.2")


def generate_response(query: str, context: str | None = None) -> str:
    settings = load_settings()
    model = select_model()
    system = (
        "You are a local AI assistant. Use the supplied knowledge base context first. "
        "If context is present, prioritize it over general knowledge. "
        "Answer only from the supplied context when it is present. "
        "For numbers, totals, statuses, tables, payments, inventories, dates, names, and lists, compute directly from the context. "
        "If the context is incomplete or conflicting, say exactly what is missing or conflicting instead of guessing. "
        "Do not invent records, amounts, names, statuses, or source files. "
        "Do not expose internal file paths, raw JSON, source rows, source labels, or implementation details unless the user explicitly asks for sources. "
        "Answer conversationally and directly. "
        "Do not claim external web access."
    )
    prompt = query if not context else f"Knowledge base context:\n{context}\n\nUser query:\n{query}"
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    response = requests.post(f"{settings.ollama_url}/api/chat", json=payload, timeout=120)
    response.raise_for_status()
    return response.json()["message"]["content"].strip()

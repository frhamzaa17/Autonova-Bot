from __future__ import annotations

import json
import os
from typing import Any

import requests


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")


def ollama_status() -> dict[str, Any]:
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        response.raise_for_status()
        models = [item.get("name") for item in response.json().get("models", [])]
        return {
            "available": True,
            "url": OLLAMA_URL,
            "model": OLLAMA_MODEL,
            "models": models,
            "selected_model_present": OLLAMA_MODEL in models,
        }
    except Exception as exc:
        return {
            "available": False,
            "url": OLLAMA_URL,
            "model": OLLAMA_MODEL,
            "error": str(exc),
        }


def generate_with_ollama(prompt: str, context_entries: list[dict[str, Any]] | None = None) -> str | None:
    status = ollama_status()
    if not status.get("available"):
        return None

    context = "\n".join(
        f"- {item.get('title')} ({item.get('category')}): {item.get('content')}"
        for item in (context_entries or [])
    )
    system = (
        "You are AutoNova's private real-estate business assistant. "
        "Use the provided business knowledge first. If the answer is not in the knowledge, say what is missing. "
        "Be concise, operational, and careful with prices, names, and next actions."
    )
    full_prompt = f"""{system}

Business knowledge:
{context or "No matching local knowledge entries were found."}

User request:
{prompt}

Answer:"""
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": full_prompt, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("response", "")).strip() or None


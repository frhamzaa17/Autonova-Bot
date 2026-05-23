from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass

import requests

from utils.config import Settings


REQUIRED_IMPORTS = {
    "telegram": "python-telegram-bot",
    "chromadb": "chromadb",
    "langchain": "langchain",
    "langchain_chroma": "langchain-chroma",
    "langchain_community": "langchain-community",
    "langchain_ollama": "langchain-ollama",
    "whisper": "openai-whisper",
    "docx": "python-docx",
    "openpyxl": "openpyxl",
    "pypdf": "pypdf",
    "dotenv": "python-dotenv",
    "requests": "requests",
}


@dataclass
class CheckResult:
    ok: bool
    lines: list[str]
    missing_commands: list[str]


def run_doctor(settings: Settings) -> CheckResult:
    lines: list[str] = []
    missing: list[str] = []

    py_ok = sys.version_info >= (3, 10)
    lines.append(f"Python: {sys.version.split()[0]} {'OK' if py_ok else 'MISSING'}")
    if not py_ok:
        missing.append("winget install Python.Python.3.11")

    missing_packages = []
    for module, package in REQUIRED_IMPORTS.items():
        try:
            importlib.import_module(module)
        except Exception:
            missing_packages.append(package)
    if missing_packages:
        lines.append("Python packages: MISSING " + ", ".join(missing_packages))
        missing.append("python -m pip install -r requirements.txt")
    else:
        lines.append("Python packages: OK")

    ffmpeg_ok = shutil.which("ffmpeg") is not None
    lines.append(f"FFmpeg: {'OK' if ffmpeg_ok else 'MISSING'}")
    if not ffmpeg_ok:
        missing.append("winget install Gyan.FFmpeg")

    ollama_cli_ok = shutil.which("ollama") is not None
    lines.append(f"Ollama CLI: {'OK' if ollama_cli_ok else 'MISSING'}")
    if not ollama_cli_ok:
        missing.append("winget install Ollama.Ollama")

    models: list[str] = []
    ollama_api_ok = False
    try:
        response = requests.get(f"{settings.ollama_url}/api/tags", timeout=5)
        response.raise_for_status()
        models = [item["name"] for item in response.json().get("models", [])]
        ollama_api_ok = True
    except requests.RequestException:
        pass

    lines.append(f"Ollama API: {'OK' if ollama_api_ok else 'MISSING'}")
    if not ollama_api_ok:
        missing.append("ollama serve")

    has_llm = any(model.startswith(("llama3", "mistral")) for model in models)
    lines.append(f"Ollama models: {', '.join(models) if models else 'none'}")
    if not has_llm:
        missing.append("ollama pull llama3.2")
        missing.append("ollama pull mistral")

    if settings.ollama_embedding_model not in models:
        lines.append(f"Embedding model: MISSING {settings.ollama_embedding_model}")
        missing.append(f"ollama pull {settings.ollama_embedding_model}")
    else:
        lines.append(f"Embedding model: OK {settings.ollama_embedding_model}")

    return CheckResult(ok=not missing, lines=lines, missing_commands=missing)

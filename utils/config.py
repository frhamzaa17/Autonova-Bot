from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    allowed_telegram_user_ids: set[int]
    ollama_url: str
    ollama_model: str
    ollama_fallback_model: str
    ollama_embedding_model: str
    data_dir: Path
    chroma_dir: Path
    uploads_dir: Path
    generated_dir: Path
    whisper_model: str
    image_backend: str
    stable_diffusion_model: str
    allow_image_external_fallback: bool


def _user_ids(value: str) -> set[int]:
    ids: set[int] = set()
    for raw in value.split(","):
        raw = raw.strip()
        if raw:
            ids.add(int(raw))
    return ids


def load_settings() -> Settings:
    load_dotenv(BASE_DIR / ".env")
    settings = Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        allowed_telegram_user_ids=_user_ids(os.getenv("ALLOWED_TELEGRAM_USER_IDS", "")),
        ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:latest"),
        ollama_fallback_model=os.getenv("OLLAMA_FALLBACK_MODEL", "mistral"),
        ollama_embedding_model=os.getenv("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large:latest"),
        data_dir=BASE_DIR / os.getenv("DATA_DIR", "data"),
        chroma_dir=BASE_DIR / os.getenv("CHROMA_DIR", "workspace/chroma"),
        uploads_dir=BASE_DIR / os.getenv("UPLOADS_DIR", "workspace/uploads"),
        generated_dir=BASE_DIR / os.getenv("GENERATED_DIR", "workspace/generated"),
        whisper_model=os.getenv("WHISPER_MODEL", "base"),
        image_backend=os.getenv("IMAGE_BACKEND", "auto"),
        stable_diffusion_model=os.getenv("STABLE_DIFFUSION_MODEL", ""),
        allow_image_external_fallback=os.getenv("ALLOW_IMAGE_EXTERNAL_FALLBACK", "false").lower()
        in {"1", "true", "yes"},
    )
    for directory in (
        settings.data_dir,
        settings.chroma_dir,
        settings.uploads_dir,
        settings.generated_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return settings

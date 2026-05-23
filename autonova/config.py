from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
WORKSPACE_DIR = ROOT_DIR / "workspace"
UPLOAD_DIR = WORKSPACE_DIR / "uploads"
GENERATED_DIR = WORKSPACE_DIR / "generated"
CHROMA_DIR = WORKSPACE_DIR / "chroma"

KNOWLEDGE_PATH = DATA_DIR / "knowledge_base.json"
LOG_PATH = DATA_DIR / "conversation_logs.jsonl"
TASKS_PATH = DATA_DIR / "tasks.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_USER_IDS = {
    user_id.strip()
    for user_id in os.getenv("ALLOWED_TELEGRAM_USER_IDS", "").split(",")
    if user_id.strip()
}


def ensure_directories() -> None:
    for path in (DATA_DIR, WORKSPACE_DIR, UPLOAD_DIR, GENERATED_DIR, CHROMA_DIR):
        path.mkdir(parents=True, exist_ok=True)

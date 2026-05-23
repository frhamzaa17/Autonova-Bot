from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import LOG_PATH, TASKS_PATH, ensure_directories


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def read_json(path: Path, default: Any) -> Any:
    ensure_directories()
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    ensure_directories()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def append_log(source: str, message: str, response: str, meta: dict[str, Any] | None = None) -> None:
    ensure_directories()
    row = {
        "timestamp": now_iso(),
        "source": source,
        "message": message,
        "response": response,
        "meta": meta or {},
    }
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_logs(limit: int = 100) -> list[dict[str, Any]]:
    ensure_directories()
    if not LOG_PATH.exists():
        return []
    rows = []
    with LOG_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[-limit:]


def add_task(text: str, source: str) -> dict[str, Any]:
    tasks = read_json(TASKS_PATH, [])
    task = {
        "id": len(tasks) + 1,
        "created_at": now_iso(),
        "source": source,
        "status": "open",
        "text": text,
    }
    tasks.append(task)
    write_json(TASKS_PATH, tasks)
    return task


from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.config import load_settings


def _path(name: str) -> Path:
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / name


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def read_json(name: str, default: Any) -> Any:
    path = _path(name)
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(name: str, payload: Any) -> None:
    with _path(name).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def add_task(text: str, source: str) -> dict[str, Any]:
    tasks = read_json("tasks.json", [])
    task = {
        "id": len(tasks) + 1,
        "created_at": now_iso(),
        "source": source,
        "status": "open",
        "text": text,
    }
    tasks.append(task)
    write_json("tasks.json", tasks)
    return task


def add_knowledge(text: str, source: str) -> dict[str, Any]:
    entries = read_json("knowledge_notes.json", [])
    entry = {
        "id": len(entries) + 1,
        "created_at": now_iso(),
        "source": source,
        "text": text,
    }
    entries.append(entry)
    write_json("knowledge_notes.json", entries)
    return entry


def tenant_for_chat(chat_id: int) -> str:
    state = get_chat_state(chat_id)
    return state.get("tenant_id") or f"telegram_{chat_id}"


def set_tenant_for_chat(chat_id: int, company_name: str) -> dict[str, Any]:
    safe = "".join(char if char.isalnum() else "_" for char in company_name.strip().lower())
    safe = "_".join(part for part in safe.split("_") if part)
    return update_chat_state(chat_id, {"tenant_id": safe or f"telegram_{chat_id}", "company_name": company_name.strip()})


def get_chat_state(chat_id: int) -> dict[str, Any]:
    states = read_json("conversation_state.json", {})
    return states.get(str(chat_id), {})


def update_chat_state(chat_id: int, updates: dict[str, Any]) -> dict[str, Any]:
    states = read_json("conversation_state.json", {})
    state = states.get(str(chat_id), {})
    state.update(updates)
    state["updated_at"] = now_iso()
    states[str(chat_id)] = state
    write_json("conversation_state.json", states)
    return state


def append_chat_history(chat_id: int, role: str, content: str, limit: int = 1000) -> list[dict[str, str]]:
    states = read_json("conversation_state.json", {})
    state = states.get(str(chat_id), {})
    history = state.get("history", [])
    history.append({"role": role, "content": content[:2000]})
    state["history"] = history[-limit:]
    state["updated_at"] = now_iso()
    states[str(chat_id)] = state
    write_json("conversation_state.json", states)
    return state["history"]


def conversation_context(chat_id: int, limit: int = 8) -> str:
    history = get_chat_state(chat_id).get("history", [])[-limit:]
    if not history:
        return ""
    return "\n".join(f"{item['role']}: {item['content']}" for item in history)

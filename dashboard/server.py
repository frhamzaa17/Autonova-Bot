from __future__ import annotations

import cgi
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import shutil
from collections import Counter
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests

from rag.knowledge_base import ingest_file, knowledge_files, remove_knowledge_file
from rag.structured_store import upsert_document
from utils.config import load_settings, safe_workspace_id, tenant_generated_dir, tenant_uploads_dir
from utils.storage import now_iso, read_json, write_json


BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
SUPPORTED_UPLOADS = {".pdf", ".docx", ".xlsx", ".txt", ".md", ".jpg", ".jpeg", ".png", ".webp"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
DOCUMENT_SUFFIXES = {".pdf", ".docx", ".xlsx", ".txt", ".md"}
USERS_FILE = "dashboard_users.json"
SESSIONS: dict[str, dict] = {}
ONBOARDING_STEPS = (
    "Register company profile",
    "Upload business documents",
    "Review structured knowledge",
    "Use assistant with workspace data",
)


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 220_000)
    return f"pbkdf2_sha256${salt}${base64.b64encode(digest).decode('ascii')}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt, expected = stored.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = _hash_password(password, salt).split("$", 2)[2]
    return hmac.compare_digest(candidate, expected)


def _new_link_code() -> str:
    return secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:10]


def _load_users() -> list[dict]:
    load_settings()
    users = read_json(USERS_FILE, [])
    if users:
        changed = False
        for user in users:
            if user.get("role") == "user" and not user.get("telegram_link_code"):
                user["telegram_link_code"] = _new_link_code()
                changed = True
        if changed:
            write_json(USERS_FILE, users)
        return users
    username = os.getenv("DASHBOARD_ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.getenv("DASHBOARD_ADMIN_PASSWORD", "").strip() or secrets.token_urlsafe(12)
    admin = {
        "id": secrets.token_hex(8),
        "username": username.lower(),
        "password_hash": _hash_password(password),
        "role": "admin",
        "workspace": "all",
        "company_name": "AutoNova Admin",
        "contact_name": "Administrator",
        "email": "",
        "status": "active",
        "created_at": now_iso(),
        "onboarding": {"step": 4, "steps": list(ONBOARDING_STEPS)},
    }
    write_json(USERS_FILE, [admin])
    if not os.getenv("DASHBOARD_ADMIN_PASSWORD", "").strip():
        settings = load_settings()
        bootstrap = settings.data_dir / "dashboard_admin_bootstrap.txt"
        bootstrap.write_text(
            f"Dashboard admin bootstrap login\nusername: {username}\npassword: {password}\n",
            encoding="utf-8",
        )
        print(f"Dashboard admin bootstrap credentials saved to {bootstrap}")
    return [admin]


def _save_users(users: list[dict]) -> None:
    write_json(USERS_FILE, users)


def _public_user(user: dict, include_link_code: bool = False) -> dict:
    payload = {
        "id": user.get("id"),
        "username": user.get("username"),
        "role": user.get("role", "user"),
        "workspace": user.get("workspace", "default"),
        "company_name": user.get("company_name", ""),
        "contact_name": user.get("contact_name", ""),
        "email": user.get("email", ""),
        "status": user.get("status", "active"),
        "onboarding": user.get("onboarding", {"step": 1, "steps": list(ONBOARDING_STEPS)}),
    }
    if include_link_code and user.get("role") == "user":
        payload["telegram_link_code"] = user.get("telegram_link_code", "")
        payload["telegram_linked"] = bool(user.get("telegram_user_id"))
    return payload


def _cookie_value(header: str | None, name: str) -> str:
    for part in (header or "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


def _states() -> dict[str, dict]:
    return read_json("conversation_state.json", {})


def _workspace_ids() -> list[str]:
    settings = load_settings()
    workspaces: set[str] = set()
    for root in (settings.uploads_dir, settings.generated_dir, settings.structured_dir):
        if root.exists():
            workspaces.update(path.name for path in root.iterdir() if path.is_dir())
    workspaces.update(state.get("tenant_id", "") for state in _states().values())
    return sorted(workspace for workspace in workspaces if workspace and workspace != "default")


def _registrations() -> list[dict]:
    return [
        _public_user(user)
        for user in _load_users()
        if user.get("role") == "user"
    ]


def _onboarding_for_user(user: dict, document_count: int, query_count: int) -> dict:
    if user.get("role") == "admin":
        return {"step": 4, "steps": list(ONBOARDING_STEPS)}
    step = 1
    if document_count:
        step = 3
    if query_count:
        step = 4
    stored = user.get("onboarding", {})
    return {"step": max(int(stored.get("step", 1) or 1), step), "steps": list(ONBOARDING_STEPS)}


def _workspace_states(workspace: str | None = None) -> list[tuple[str, dict]]:
    selected = safe_workspace_id(workspace) if workspace else None
    return [
        (chat_id, state)
        for chat_id, state in _states().items()
        if not selected or safe_workspace_id(state.get("tenant_id")) == selected
    ]


def _activities(workspace: str | None = None, limit: int = 120) -> list[dict]:
    activities: list[dict] = []
    for chat_id, state in _workspace_states(workspace):
        tenant = safe_workspace_id(state.get("tenant_id"))
        history = state.get("history", [])
        updated_at = state.get("updated_at", "")
        for index, item in enumerate(history):
            activities.append(
                {
                    "workspace": tenant,
                    "chat_id": chat_id,
                    "role": item.get("role", "unknown"),
                    "content": item.get("content", ""),
                    "timestamp": updated_at,
                    "order": index,
                }
            )
    activities.sort(key=lambda item: (item["timestamp"], item["order"]), reverse=True)
    return activities[:limit]


def _file_payload(path: Path, category: str, document_type: str | None = None, record_count: int = 0) -> dict:
    try:
        size = path.stat().st_size
        updated_at = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        size = 0
        updated_at = ""
    return {
        "name": path.name,
        "category": category,
        "type": document_type or path.suffix.lower().lstrip(".") or "file",
        "records": record_count,
        "size": size,
        "updated_at": updated_at,
    }


def _document_payload(workspace: str) -> list[dict]:
    files = []
    for item in knowledge_files(workspace):
        category = "generated_document" if _is_generated_path(item.path, workspace) else "uploaded"
        files.append(_file_payload(item.path, category, item.document_type, item.record_count))
    return sorted(files, key=lambda item: item["updated_at"], reverse=True)


def _is_generated_path(path: Path, workspace: str | None = None) -> bool:
    settings = load_settings()
    roots = [settings.generated_dir / safe_workspace_id(workspace)] if workspace else [settings.generated_dir]
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return any(root.exists() and (resolved == root.resolve() or root.resolve() in resolved.parents) for root in roots)


def _generated_files(workspace: str | None = None) -> list[Path]:
    settings = load_settings()
    roots = [settings.generated_dir / safe_workspace_id(workspace)] if workspace else [settings.generated_dir]
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(path for path in root.rglob("*") if path.is_file())
    return files


def _generated_payload(workspace: str | None = None) -> list[dict]:
    files = []
    known = {(item.get("category"), item.get("name")) for item in _document_payload(workspace) if workspace}
    for path in _generated_files(workspace):
        suffix = path.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            files.append(_file_payload(path, "generated_image", "image"))
        elif suffix in DOCUMENT_SUFFIXES and ("generated_document", path.name) not in known:
            files.append(_file_payload(path, "generated_document", "generated_document"))
    return sorted(files, key=lambda item: item["updated_at"], reverse=True)


def _managed_file_path(workspace: str, name: str, category: str = "") -> Path | None:
    settings = load_settings()
    roots: list[Path]
    if category.startswith("generated"):
        roots = [tenant_generated_dir(settings, workspace)]
    elif category == "uploaded":
        roots = [tenant_uploads_dir(settings, workspace), settings.data_dir / safe_workspace_id(workspace)]
    else:
        roots = [tenant_uploads_dir(settings, workspace), tenant_generated_dir(settings, workspace), settings.data_dir / safe_workspace_id(workspace)]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.name == name:
                return path
    return None


def _daily_analytics(workspace: str | None = None) -> list[dict]:
    today = date.today()
    days = [(today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]
    queries: Counter[str] = Counter()
    for _chat_id, state in _workspace_states(workspace):
        day = str(state.get("updated_at", ""))[:10]
        queries[day] += sum(1 for item in state.get("history", []) if item.get("role") == "user")

    edits: Counter[str] = Counter()
    images: Counter[str] = Counter()
    for path in _generated_files(workspace):
        try:
            day = datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
        except OSError:
            continue
        lower = path.name.lower()
        if "edited" in lower:
            edits[day] += 1
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            images[day] += 1

    return [{"date": day, "queries": queries[day], "edits": edits[day], "images": images[day]} for day in days]


def _ollama_status() -> dict:
    settings = load_settings()
    try:
        response = requests.get(f"{settings.ollama_url.rstrip('/')}/api/tags", timeout=2)
        response.raise_for_status()
        models = [model.get("name", "") for model in response.json().get("models", [])]
        return {"name": "Ollama", "status": "healthy", "detail": f"{len(models)} model(s) available"}
    except Exception:
        return {"name": "Ollama", "status": "offline", "detail": settings.ollama_url}


def _integration_payload() -> list[dict]:
    settings = load_settings()
    return [
        _ollama_status(),
        {
            "name": "Telegram Bot",
            "status": "configured" if settings.telegram_bot_token else "missing",
            "detail": "Token configured" if settings.telegram_bot_token else "TELEGRAM_BOT_TOKEN is missing",
        },
        {
            "name": "Tavily Web Search",
            "status": "configured" if settings.allow_web_search and settings.tavily_api_key else "disabled",
            "detail": "External search enabled" if settings.allow_web_search and settings.tavily_api_key else "Enable ALLOW_WEB_SEARCH and add TAVILY_API_KEY",
        },
        {
            "name": "ChromaDB",
            "status": "healthy" if settings.chroma_dir.exists() else "missing",
            "detail": str(settings.chroma_dir),
        },
        {
            "name": "OCR",
            "status": "configured" if shutil.which("tesseract") else "missing",
            "detail": shutil.which("tesseract") or "Tesseract is not on PATH",
        },
        {
            "name": "Voice Transcription",
            "status": "configured" if shutil.which("ffmpeg") else "missing",
            "detail": shutil.which("ffmpeg") or "FFmpeg is not on PATH",
        },
    ]


def _overview(workspace: str | None, user: dict) -> dict:
    role = user.get("role", "user")
    if role == "admin":
        selected = None if workspace == "all" else safe_workspace_id(workspace)
    else:
        selected = safe_workspace_id(user.get("workspace"))
    documents = []
    generated_documents = []
    generated_images = []
    if selected:
        all_documents = _document_payload(selected)
        documents = [item for item in all_documents if item.get("category") == "uploaded"]
        generated = _generated_payload(selected)
        generated_documents = [item for item in all_documents if item.get("category") == "generated_document"]
        generated_documents.extend(item for item in generated if item["category"] == "generated_document")
        generated_images = [item for item in generated if item["category"] == "generated_image"]
    elif role == "admin":
        for tenant in _workspace_ids():
            all_documents = _document_payload(tenant)
            documents.extend({**item, "workspace": tenant} for item in all_documents if item.get("category") == "uploaded")
            generated_documents.extend({**item, "workspace": tenant} for item in all_documents if item.get("category") == "generated_document")
            generated = _generated_payload(tenant)
            generated_documents.extend({**item, "workspace": tenant} for item in generated if item["category"] == "generated_document")
            generated_images.extend({**item, "workspace": tenant} for item in generated if item["category"] == "generated_image")

    activities = _activities(selected)
    generated = _generated_files(selected)
    image_count = sum(1 for path in generated if path.suffix.lower() in IMAGE_SUFFIXES)
    edit_count = sum(1 for path in generated if "edited" in path.name.lower())
    query_count = sum(1 for item in activities if item["role"] == "user")
    onboarding = _onboarding_for_user(user, len(documents), query_count)
    payload = {
        "role": role,
        "workspace": selected or "all",
        "user": _public_user(user, include_link_code=True),
        "workspaces": ["all", *_workspace_ids()] if role == "admin" else [safe_workspace_id(user.get("workspace"))],
        "stats": {
            "queries": query_count,
            "documents": len(documents),
            "edits": edit_count,
            "images": image_count,
        },
        "documents": documents,
        "generated_documents": generated_documents,
        "generated_images": generated_images,
        "activities": activities,
        "analytics": _daily_analytics(selected),
        "onboarding": onboarding,
    }
    if role == "admin":
        payload["integrations"] = _integration_payload()
        payload["registrations"] = _registrations()
    return payload


class Handler(BaseHTTPRequestHandler):
    server_version = "AutoNovaDashboard/1.0"

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _set_session_cookie(self, token: str) -> None:
        self.send_header("Set-Cookie", f"autonova_session={token}; HttpOnly; SameSite=Strict; Path=/")

    def _clear_session_cookie(self) -> None:
        self.send_header("Set-Cookie", "autonova_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")

    def _current_user(self) -> dict | None:
        token = _cookie_value(self.headers.get("Cookie"), "autonova_session")
        session = SESSIONS.get(token)
        if not session:
            return None
        users = _load_users()
        return next((user for user in users if user.get("id") == session.get("user_id") and user.get("status") == "active"), None)

    def _require_user(self) -> dict | None:
        user = self._current_user()
        if not user:
            self._send_json({"error": "Authentication required"}, 401)
            return None
        return user

    def _allowed_workspace(self, requested: str | None, user: dict) -> str | None:
        if user.get("role") == "admin":
            workspace = requested or "all"
            return None if workspace == "all" else safe_workspace_id(workspace)
        return safe_workspace_id(user.get("workspace"))

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def _send_file(self, path: Path, content_type: str | None = None) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"error": "Not found"}, 404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path in {"/", "/index.html"}:
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/api/session":
            user = self._current_user()
            self._send_json({"authenticated": bool(user), "user": _public_user(user, include_link_code=True) if user else None})
            return
        if parsed.path == "/api/overview":
            user = self._require_user()
            if not user:
                return
            workspace = query.get("workspace", ["all" if user.get("role") == "admin" else user.get("workspace", "default")])[0]
            self._send_json(_overview(workspace, user))
            return
        if parsed.path == "/api/document":
            user = self._require_user()
            if not user:
                return
            settings = load_settings()
            requested = query.get("workspace", [user.get("workspace", "default")])[0]
            workspace = self._allowed_workspace(requested, user)
            if not workspace:
                self._send_json({"error": "Choose one workspace"}, 400)
                return
            name = Path(unquote(query.get("name", [""])[0])).name
            category = query.get("category", [""])[0]
            path = _managed_file_path(workspace, name, category)
            if not path:
                self._send_json({"error": "Not found"}, 404)
                return
            self._send_file(path)
            return
        self._send_json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/login":
            payload = self._read_json_body()
            username = str(payload.get("username", "")).strip().lower()
            password = str(payload.get("password", ""))
            user = next((item for item in _load_users() if item.get("username") == username), None)
            if not user or user.get("status") != "active" or not _verify_password(password, user.get("password_hash", "")):
                self._send_json({"error": "Invalid login"}, 401)
                return
            token = secrets.token_urlsafe(32)
            SESSIONS[token] = {"user_id": user["id"], "created_at": now_iso()}
            body = _json_bytes({"ok": True, "user": _public_user(user, include_link_code=True)})
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._set_session_cookie(token)
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/logout":
            token = _cookie_value(self.headers.get("Cookie"), "autonova_session")
            if token:
                SESSIONS.pop(token, None)
            body = _json_bytes({"ok": True})
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._clear_session_cookie()
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/register":
            payload = self._read_json_body()
            company = str(payload.get("company_name", "")).strip()
            email = str(payload.get("email", "")).strip().lower()
            password = str(payload.get("password", ""))
            contact = str(payload.get("contact_name", "")).strip()
            if not company or not email or len(password) < 8:
                self._send_json({"error": "Company, email, and an 8+ character password are required"}, 400)
                return
            users = _load_users()
            username = email
            if any(user.get("username") == username for user in users):
                self._send_json({"error": "An account already exists for this email"}, 409)
                return
            workspace = safe_workspace_id(company)
            existing_workspaces = {user.get("workspace") for user in users}
            base = workspace
            suffix = 2
            while workspace in existing_workspaces:
                workspace = f"{base}_{suffix}"
                suffix += 1
            user = {
                "id": secrets.token_hex(8),
                "username": username,
                "password_hash": _hash_password(password),
                "role": "user",
                "workspace": workspace,
                "company_name": company,
                "contact_name": contact,
                "email": email,
                "status": "active",
                "created_at": now_iso(),
                "telegram_link_code": _new_link_code(),
                "onboarding": {"step": 1, "steps": list(ONBOARDING_STEPS)},
            }
            users.append(user)
            _save_users(users)
            self._send_json({"ok": True, "user": _public_user(user)}, 201)
            return
        if parsed.path != "/api/documents":
            self._send_json({"error": "Not found"}, 404)
            return
        user = self._require_user()
        if not user:
            return
        requested = parse_qs(parsed.query).get("workspace", [user.get("workspace", "default")])[0]
        workspace = self._allowed_workspace(requested, user)
        if not workspace:
            self._send_json({"error": "Choose one workspace"}, 400)
            return
        content_type, params = cgi.parse_header(self.headers.get("Content-Type", ""))
        if content_type != "multipart/form-data":
            self._send_json({"error": "Expected multipart file upload"}, 400)
            return
        params["boundary"] = params["boundary"].encode()
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"}, keep_blank_values=True)
        upload = form["file"] if "file" in form else None
        if upload is None or not getattr(upload, "filename", ""):
            self._send_json({"error": "Choose a file to upload"}, 400)
            return
        name = Path(upload.filename).name
        if Path(name).suffix.lower() not in SUPPORTED_UPLOADS:
            self._send_json({"error": f"Unsupported file type: {Path(name).suffix}"}, 400)
            return
        settings = load_settings()
        path = tenant_uploads_dir(settings, workspace) / name
        path.write_bytes(upload.file.read())
        decoded = upsert_document(path, workspace)
        ingest_error = ""
        try:
            ingest_file(path, workspace)
        except Exception as exc:
            ingest_error = str(exc)
        self._send_json(
            {
                "ok": True,
                "name": name,
                "records": int((decoded or {}).get("summary", {}).get("record_count") or 0),
                "ingest_error": ingest_error,
            },
            201,
        )

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/documents":
            self._send_json({"error": "Not found"}, 404)
            return
        user = self._require_user()
        if not user:
            return
        query = parse_qs(parsed.query)
        requested = query.get("workspace", [user.get("workspace", "default")])[0]
        workspace = self._allowed_workspace(requested, user)
        if not workspace:
            self._send_json({"error": "Choose one workspace"}, 400)
            return
        name = Path(unquote(query.get("name", [""])[0])).name
        if not name:
            self._send_json({"error": "Document name is required"}, 400)
            return
        category = query.get("category", [""])[0]
        if category.startswith("generated"):
            path = _managed_file_path(workspace, name, category)
            if not path:
                self._send_json({"error": "Document not found"}, 404)
                return
            try:
                path.unlink()
            except OSError as exc:
                self._send_json({"error": str(exc)}, 500)
                return
            self._send_json({"ok": True, "removed": name})
            return
        result = remove_knowledge_file(name, workspace)
        if not result.removed_files and not result.structured_removed:
            self._send_json({"error": "Document not found"}, 404)
            return
        self._send_json({"ok": True, "removed": name})

    def log_message(self, format: str, *args) -> None:
        return


def run_dashboard(host: str = "127.0.0.1", port: int = 8765) -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"AutoNova dashboard running at http://{host}:{port}")
    server.serve_forever()

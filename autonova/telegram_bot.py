from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests

from .assistant import Assistant
from .config import ALLOWED_USER_IDS, TELEGRAM_TOKEN, UPLOAD_DIR, ensure_directories
from .storage import append_log
from .transcription import transcribe_voice


class TelegramBot:
    def __init__(self, token: str = TELEGRAM_TOKEN) -> None:
        if not token:
            raise RuntimeError("Set TELEGRAM_BOT_TOKEN before running the Telegram bot.")
        self.token = token
        self.api = f"https://api.telegram.org/bot{token}"
        self.assistant = Assistant()

    def request(self, method: str, **payload: Any) -> dict:
        response = requests.post(f"{self.api}/{method}", json=payload, timeout=30)
        response.raise_for_status()
        return response.json()

    def send_message(self, chat_id: int, text: str) -> None:
        limit = 3900
        for start in range(0, len(text), limit):
            self.request("sendMessage", chat_id=chat_id, text=text[start:start + limit])

    def send_document(self, chat_id: int, path: Path) -> None:
        with path.open("rb") as handle:
            response = requests.post(
                f"{self.api}/sendDocument",
                data={"chat_id": chat_id},
                files={"document": (path.name, handle)},
                timeout=60,
            )
            response.raise_for_status()

    def send_photo(self, chat_id: int, image_url: str) -> None:
        self.request("sendPhoto", chat_id=chat_id, photo=image_url)

    def download_file(self, file_id: str, filename: str) -> Path:
        ensure_directories()
        file_info = self.request("getFile", file_id=file_id)["result"]
        url = f"https://api.telegram.org/file/bot{self.token}/{file_info['file_path']}"
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        path = UPLOAD_DIR / filename
        path.write_bytes(response.content)
        return path

    def allowed(self, user_id: int) -> bool:
        return not ALLOWED_USER_IDS or str(user_id) in ALLOWED_USER_IDS

    def handle_update(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat", {})
        user = message.get("from", {})
        chat_id = chat.get("id")
        user_id = user.get("id")
        if not chat_id or not user_id:
            return
        if not self.allowed(user_id):
            self.send_message(chat_id, "This bot is private. Ask the admin to add your Telegram user ID.")
            return

        text = message.get("text") or message.get("caption") or ""
        attachment = None
        if "document" in message:
            doc = message["document"]
            attachment = self.download_file(doc["file_id"], doc.get("file_name", "upload.bin"))
        elif "voice" in message:
            voice = message["voice"]
            attachment = self.download_file(voice["file_id"], f"voice_{voice['file_unique_id']}.ogg")
            transcript = transcribe_voice(attachment)
            if not transcript:
                append_log("telegram", "[voice note]", "Voice note received but local Whisper is not installed.", {"user_id": user_id})
                self.send_message(chat_id, "Voice note received. Install local Whisper to enable private transcription, or send the instruction as text.")
                return
            text = transcript
            attachment = None

        result = self.assistant.handle(text, source=f"telegram:{user_id}", attachment=attachment)
        self.send_message(chat_id, result["text"])
        for image_url in result.get("images", []):
            self.send_photo(chat_id, image_url)
        for file_path in result.get("files", []):
            self.send_document(chat_id, Path(file_path))

    def run(self) -> None:
        offset = None
        self.request("getMe")
        print("Telegram bot is running. Press Ctrl+C to stop.")
        while True:
            payload = {"timeout": 25, "allowed_updates": ["message", "edited_message"]}
            if offset is not None:
                payload["offset"] = offset
            updates = self.request("getUpdates", **payload).get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    self.handle_update(update)
                except Exception as exc:
                    print(f"Update failed: {exc}")
            time.sleep(1)

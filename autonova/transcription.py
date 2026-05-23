from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import GENERATED_DIR, ensure_directories


def transcribe_voice(path: Path) -> str | None:
    """Use local Whisper CLI when installed; never sends audio to a hosted API."""
    whisper = shutil.which("whisper")
    if not whisper:
        return None
    ensure_directories()
    subprocess.run(
        [
            whisper,
            str(path),
            "--model",
            "base",
            "--language",
            "en",
            "--output_format",
            "txt",
            "--output_dir",
            str(GENERATED_DIR),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    transcript = GENERATED_DIR / f"{path.stem}.txt"
    if transcript.exists():
        return transcript.read_text(encoding="utf-8", errors="ignore").strip()
    return None


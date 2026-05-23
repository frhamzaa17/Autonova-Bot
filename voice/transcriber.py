from __future__ import annotations

import subprocess
from pathlib import Path

import whisper

from utils.config import load_settings


def ogg_to_wav(input_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def transcribe_audio(audio_path: Path) -> str:
    settings = load_settings()
    wav_path = audio_path.with_suffix(".wav")
    if audio_path.suffix.lower() == ".ogg":
        audio_path = ogg_to_wav(audio_path, wav_path)
    model = whisper.load_model(settings.whisper_model)
    result = model.transcribe(str(audio_path), fp16=False)
    return result.get("text", "").strip()

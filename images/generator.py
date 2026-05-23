from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

import requests

from utils.config import load_settings


def _safe_name(prompt: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", prompt.strip())[:60].strip("_")
    return safe or "generated_image"


def _stable_diffusion(prompt: str) -> Path | None:
    settings = load_settings()
    if not settings.stable_diffusion_model:
        return None
    try:
        from diffusers import StableDiffusionPipeline
        import torch
    except ImportError:
        return None

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipe = StableDiffusionPipeline.from_pretrained(settings.stable_diffusion_model)
    pipe = pipe.to(device)
    image = pipe(prompt).images[0]
    output = settings.generated_dir / f"{_safe_name(prompt)}.png"
    image.save(output)
    return output


def generate_image(prompt: str) -> Path | str:
    settings = load_settings()
    local_image = _stable_diffusion(prompt)
    if local_image:
        return local_image

    if not settings.allow_image_external_fallback:
        raise RuntimeError(
            "Local Stable Diffusion is unavailable and external image fallback is disabled. "
            "Set ALLOW_IMAGE_EXTERNAL_FALLBACK=true to use Pollinations."
        )

    url = f"https://image.pollinations.ai/prompt/{quote(prompt)}"
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    output = settings.generated_dir / f"{_safe_name(prompt)}.jpg"
    output.write_bytes(response.content)
    return output

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

import requests

from utils.config import load_settings, tenant_generated_dir


def _safe_name(prompt: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", prompt.strip())[:60].strip("_")
    return safe or "generated_image"


def _output_dir(tenant_id: str | None = None) -> Path:
    settings = load_settings()
    return tenant_generated_dir(settings, tenant_id) if tenant_id else settings.generated_dir


def _stable_diffusion(prompt: str, tenant_id: str | None = None) -> Path | None:
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
    output = _output_dir(tenant_id) / f"{_safe_name(prompt)}.png"
    image.save(output)
    return output


def generate_image(prompt: str, tenant_id: str | None = None) -> Path | str:
    settings = load_settings()
    local_image = _stable_diffusion(prompt, tenant_id)
    if local_image:
        return local_image

    if not settings.allow_image_external_fallback:
        raise RuntimeError(
            "Local Stable Diffusion is unavailable and external image fallback is disabled. "
            "Set ALLOW_IMAGE_EXTERNAL_FALLBACK=true to use Pollinations."
        )

    # ✅ Updated to new endpoint
    url = f"https://gen.pollinations.ai/image/{quote(prompt)}?model=flux&nologo=true"

    headers = {}
    api_key = getattr(settings, "pollinations_api_key", None)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        raise RuntimeError(
            "POLLINATIONS_API_KEY is not set. Get a free key at https://enter.pollinations.ai"
        )

    response = requests.get(url, headers=headers, timeout=90)
    response.raise_for_status()
    output = _output_dir(tenant_id) / f"{_safe_name(prompt)}.jpg"
    output.write_bytes(response.content)
    return output
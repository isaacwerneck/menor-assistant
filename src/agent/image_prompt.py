"""Traduz briefings livres em instruções para o modelo visual local.

Separado do orquestrador: nunca baixa modelos nem executa uma ação externa.
Se o Ollama falhar, conserva o briefing original sem inventar adequação.
"""
import json
import os

import requests

from src.agent.artifacts import requested_size


def adapt(brief):
    if os.environ.get("MENOR_IMAGE_PROMPT_ADAPTER", "1") != "1":
        return brief
    system = (
        "You write prompts for a local Stable Diffusion 1.5 image model. "
        "Translate the user's exact image request from any language into clear "
        "English image instructions. Preserve the subject, colors, composition, "
        "style and requested dimensions. Do not replace characters with textures, "
        "carvings, icons, backgrounds or abstract patterns unless explicitly asked. "
        "For tiny pixel-art sprites, describe a single complete recognizable "
        "character on a plain background with clear silhouette and distinct colors, "
        "without letters. Never claim you generated or reviewed an image. "
        'Return ONLY JSON {"prompt":"English image prompt"} (max 1200 chars).'
    )
    try:
        with requests.post(
            os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat",
            json={
                "model": os.environ.get("MENOR_IMAGE_PROMPT_MODEL")
                         or os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": brief},
                ],
                "stream": False, "format": "json",
                "options": {"temperature": 0, "num_predict": 260},
            }, timeout=(4, 35),
        ) as response:
            response.raise_for_status()
            result = json.loads(response.json()["message"]["content"])
        prompt = result.get("prompt")
        if not isinstance(prompt, str) or not 12 <= len(prompt.strip()) <= 1200:
            return brief
        size = requested_size(brief)
        translated = prompt.strip()
        if size and requested_size(translated) != size:
            translated += f", final output {size[0]}x{size[1]} pixels"
        return translated
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return brief

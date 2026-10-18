"""Integração opcional com serviço de imagens; jamais finge que gerou uma arte.

O proprietário configura MENOR_IMAGE_API_KEY no ambiente do serviço. As
imagens ficam fora do repositório, em ~/menor-data/media/images/.
"""
import base64
import binascii
import io
import os
import re
import secrets

import requests
from PIL import Image, UnidentifiedImageError

from src.memory.store import BrainStore

API_URL = "https://api.openai.com/v1/images"
MAX_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 24_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class ImageUnavailable(RuntimeError):
    pass


def configured():
    return bool(os.environ.get("MENOR_IMAGE_API_KEY", "").strip())


def _verify_image(data):
    if not isinstance(data, bytes) or not 16 <= len(data) <= MAX_BYTES:
        raise ValueError("Imagem ausente ou grande demais (máximo 12 MB).")
    try:
        with Image.open(io.BytesIO(data)) as picture:
            if picture.format not in ("PNG", "JPEG", "WEBP"):
                raise ValueError("Somente PNG, JPEG ou WEBP.")
            if picture.width * picture.height > MAX_PIXELS:
                raise ValueError("Resolução de imagem excedida.")
            picture.verify()
        return data
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as error:
        raise ValueError("Arquivo não é uma imagem válida.") from error


def _folder():
    store = BrainStore()
    # Pasta media está fora do cérebro, mas dentro da raiz privada menor-data.
    store._require_directory(store.data_dir)
    media = store.data_dir / "media"
    store._require_directory(media)
    target = media / "images"
    store._require_directory(target)
    return target


def _save(data):
    data = _verify_image(data)
    name = secrets.token_hex(16)
    dest = _folder() / f"{name}.png"
    # Normaliza formato antes de servir como PNG.
    with Image.open(io.BytesIO(data)) as source:
        buf = io.BytesIO()
        source.convert("RGB").save(buf, format="PNG")
    encoded = buf.getvalue()
    if len(encoded) > MAX_BYTES:
        raise ValueError("Imagem produzida ultrapassa o limite de armazenamento.")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(dest, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return {"id": name, "url": f"/images/files/{name}", "size": len(encoded)}


def file_path(image_id):
    if not isinstance(image_id, str) or not re.fullmatch(r"[0-9a-f]{32}", image_id):
        raise ValueError("ID inválido.")
    path = _folder() / f"{image_id}.png"
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError("Imagem não encontrada.")
    return path


def _request(endpoint, **kwargs):
    key = os.environ.get("MENOR_IMAGE_API_KEY", "").strip()
    if not key:
        raise ImageUnavailable("Motor de imagens não configurado neste servidor.")
    try:
        response = requests.post(
            f"{API_URL}/{endpoint}",
            headers={"Authorization": f"Bearer {key}"},
            timeout=(10, 180), **kwargs,
        )
        response.raise_for_status()
        items = response.json().get("data")
        if not isinstance(items, list) or not items:
            raise ImageUnavailable("Motor de imagens não retornou uma imagem.")
        encoded = items[0].get("b64_json")
        if not isinstance(encoded, str):
            raise ImageUnavailable("Motor não retornou imagem codificada.")
        return _save(base64.b64decode(encoded, validate=True))
    except (requests.RequestException, KeyError, TypeError, ValueError, binascii.Error) as error:
        raise ImageUnavailable("Motor de imagens falhou; nada foi gerado.") from error


def generate(prompt):
    prompt = _prompt(prompt)
    result = _request(
        "generations", json={"model": os.environ.get("MENOR_IMAGE_MODEL", "gpt-image-1"),
                             "prompt": prompt, "size": "1024x1024", "n": 1},
    )
    return {"status": "completed", "kind": "generate", "prompt": prompt, **result}


def edit(prompt, raw):
    prompt = _prompt(prompt)
    raw = _verify_image(raw)
    # Enviar PNG de verdade, independentemente da origem JPEG/WEBP.
    with Image.open(io.BytesIO(raw)) as image:
        target = io.BytesIO()
        image.convert("RGB").save(target, "PNG")
        payload = target.getvalue()
    if len(payload) > MAX_BYTES:
        raise ValueError("Imagem convertida excede o limite de 12 MB.")
    result = _request(
        "edits", data={"model": os.environ.get("MENOR_IMAGE_MODEL", "gpt-image-1"),
                       "prompt": prompt, "size": "1024x1024", "n": "1"},
        files={"image": ("original.png", payload, "image/png")},
    )
    return {"status": "completed", "kind": "edit", "prompt": prompt, **result}


def _prompt(prompt):
    if not isinstance(prompt, str) or not 6 <= len(prompt.strip()) <= 2000:
        raise ValueError("Descreva a imagem em 6 a 2000 caracteres.")
    return prompt.strip()

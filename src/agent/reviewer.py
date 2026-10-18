"""Revisor técnico de resultados dos subagentes.

O verificador não faz avaliações estéticas; confirma que a saída é real,
legível, tem dimensão mínima e está dentro do armazenamento privado.
"""
from PIL import Image

from src.tools import images


def review_image(result):
    if not isinstance(result, dict) or result.get("status") != "completed":
        return {"passed": False, "reason": "Sem conclusão confirmada."}
    try:
        path = images.file_path(result["id"])
        with Image.open(path) as picture:
            picture.verify()
        with Image.open(path) as picture:
            width, height = picture.size
        if width < 256 or height < 256:
            return {"passed": False, "reason": "Imagem menor que 256 pixels."}
        if path.stat().st_size > images.MAX_BYTES:
            return {"passed": False, "reason": "Imagem acima do limite."}
    except (KeyError, OSError, ValueError, TypeError):
        return {"passed": False, "reason": "Arquivo de imagem inválido ou ausente."}
    return {"passed": True, "width": width, "height": height, "reason": "Arquivo válido."}

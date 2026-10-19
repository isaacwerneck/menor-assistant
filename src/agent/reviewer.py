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
        if not 16 <= width <= 4096 or not 16 <= height <= 4096:
            return {"passed": False, "reason": "Dimensão inválida."}
        from src.agent.artifacts import requested_size
        expected = requested_size(result.get("prompt", ""))
        if expected and expected != (width, height):
            return {"passed": False, "reason": "O PNG não tem a resolução solicitada."}
        if path.stat().st_size > images.MAX_BYTES:
            return {"passed": False, "reason": "Imagem acima do limite."}
    except (KeyError, OSError, ValueError, TypeError):
        return {"passed": False, "reason": "Arquivo de imagem inválido ou ausente."}
    return {
        "passed": True, "width": width, "height": height,
        "reason": "Integridade e resolução verificadas; conteúdo visual não avaliado.",
        "content_verified": False,
    }

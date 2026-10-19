"""Auditoria objetiva de sprites: integridade, grade, paleta e transparência.

Métricas técnicas NÃO comprovam personagem, acessórios, cores solicitadas
ou fidelidade visual ao prompt.
"""
from src.tools.file_analysis import service

VERSION = "1.0.0"
FORMATS = frozenset(("png", "gif", "webp", "jpeg", "bmp"))


def audit(file_id, *, expected_size=(32, 32), root=None):
    """Avalia recibo do worker isolado, sem abrir pixels no processo da API."""
    if (not isinstance(expected_size, (list, tuple)) or len(expected_size) != 2
            or any(type(size) is not int or not 16 <= size <= 256 for size in expected_size)):
        raise ValueError("Tamanho do sprite deve estar entre 16 e 256 pixels em cada eixo.")
    receipt = service.inspect(file_id, root=root)
    if receipt["status"] != "executed":
        return {
            "tool": "sprites.audit", "version": VERSION,
            "status": "failed", "technical_verified": False, "content_verified": False,
            "reason": "Integridade da imagem não foi comprovada.",
        }
    source = receipt["file"]
    if source["format"] not in FORMATS:
        return {
            "tool": "sprites.audit", "version": VERSION,
            "status": "unsupported", "technical_verified": False, "content_verified": False,
            "reason": "Auditoria de sprites requer imagem.",
        }
    image = receipt["content"][0]
    width, height = image["width"], image["height"]
    size_matches = [width, height] == list(expected_size)
    return {
        "tool": "sprites.audit", "version": VERSION, "status": "executed",
        "file_id": source["file_id"], "sha256": source["sha256"],
        "format": source["format"], "actual_size": [width, height],
        "expected_size": list(expected_size), "size_matches": size_matches,
        "technical_verified": True, "content_verified": False,
        "metrics": image.get("sprite_metrics"),
        "semantic_checks": {
            "recognizable_character": "not_evaluated",
            "requested_colors": "not_evaluated",
            "requested_accessories": "not_evaluated",
            "pixel_art_style": "not_evaluated",
        },
        "limitations": [
            "Paleta reduzida e tamanho correto não provam aderência ao briefing.",
            "Dimensões podem resultar de pós-processamento sem personagem reconhecível.",
            "Para qualidade estética, usar benchmarks independentes e revisão humana.",
        ],
    }

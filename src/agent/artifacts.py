"""Requisitos verificáveis de imagem, separados da escolha de modelo ou intenção.

Um arquivo tecnicamente válido não significa que a cena solicitada foi atendida.
"""
import re

SIZES = re.compile(r"(?<!\d)(\d{2,4})\s*[x×]\s*(\d{2,4})(?!\d)", re.I)


def requested_size(prompt):
    if not isinstance(prompt, str):
        raise ValueError("Prompt inválido.")
    dimensions = SIZES.search(prompt)
    if not dimensions:
        return None
    width, height = map(int, dimensions.groups())
    if not 16 <= width <= 2048 or not 16 <= height <= 2048:
        raise ValueError("Tamanho solicitado deve ficar entre 16 e 2048 pixels.")
    return width, height


def format_image(picture, prompt):
    """Converte saída do gerador para dimensões solicitadas; não avalia a cena."""
    from PIL import Image

    dimensions = requested_size(prompt)
    if not dimensions:
        return picture.convert("RGB"), {"requested_size": None, "postprocessed": False}
    if picture.size == dimensions:
        return picture.convert("RGB"), {
            "requested_size": list(dimensions), "postprocessed": False,
        }
    # Tamanho pequeno exige uma grade real de pixels, não só CSS em 512x512.
    small = max(dimensions) <= 128
    resampling = Image.Resampling.BOX if small else Image.Resampling.LANCZOS
    output = picture.convert("RGB").resize(dimensions, resampling)
    if small:
        # Paleta discreta, sem dither: grid utilizável para sprites pequenos.
        output = output.quantize(colors=32, dither=Image.Dither.NONE).convert("RGB")
    return output, {"requested_size": list(dimensions), "postprocessed": True}


def artifact_receipt(produced):
    """Informação para o próximo turno; não guarda imagem binária no histórico."""
    if not isinstance(produced, dict):
        raise ValueError("Resultado inválido.")
    from src.tools import images
    from PIL import Image

    image_id = produced["id"]
    with Image.open(images.file_path(image_id)) as source:
        width, height = source.size
    review = produced.get("review", {})
    visual = review.get("visual_review", {}) if isinstance(review, dict) else {}
    return {
        "kind": "image",
        "id": image_id,
        "url": produced["url"],
        "prompt": str(produced.get("prompt", ""))[:1000],
        "actual_size": [width, height],
        "requested_size": produced.get("requested_size"),
        "worker": produced.get("worker", "unknown"),
        "file_verified": bool(review.get("passed")),
        "content_verified": review.get("content_verified") is True,
        "content_description": str(visual.get("description", ""))[:500],
        "vision_model_assessment": visual.get("model_matches_brief")
                                   if visual.get("available") else None,
        "limitation": (
            "Arquivo válido não confirma que o tema, as cores ou o estilo pedidos aparecem na imagem."
        ),
    }


def describe_artifact(receipt):
    if not isinstance(receipt, dict) or receipt.get("kind") != "image":
        return "Não encontrei um artefato recente verificável nesta conversa."
    width, height = receipt.get("actual_size", ["?", "?"])
    description = receipt.get("content_description", "")
    critic = ("O modelo visual local descreveu: " + description[:400] + ". "
              if description else "")
    return (
        f"Eu gerei um PNG de {width}×{height} pixels com o subagente "
        f"{receipt.get('worker', 'local')}. Pedido: {receipt.get('prompt', '')[:350]}. "
        + critic + "O arquivo existe, mas sua integridade não comprova a cena, "
        "as cores ou o estilo. Se ficou diferente, precisamos corrigir a ferramenta; "
        "não vou afirmar que está certo sem avaliação confiável."
    )

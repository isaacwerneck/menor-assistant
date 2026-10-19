"""Delegação de imagens ao worker local e verificação técnica independente."""
from src.agent.reviewer import review_image
from src.agent.vision_review import inspect as visual_inspect
from src.agent.skills import capability_status
from src.tools import images, local_images
import os
import requests

MAX_ATTEMPTS = 2


def generate_image(prompt, missions=None):
    """Gera e verifica artefato; não usa provedor remoto nem finge sucesso."""
    prompt = images._prompt(prompt)
    if images.provider() != "local":
        raise images.ImageUnavailable("Este executor é exclusivo para subagentes locais.")
    skill = capability_status("images.generate", missions)
    if not skill["ready"]:
        raise images.ImageUnavailable(
            "Modelo local não instalado ou ainda não verificado. "
            "Posso ajudar a preparar essa ferramenta."
        )
    reasons = []
    model_prompt = prompt
    for attempt in range(MAX_ATTEMPTS):
        try:
            produced = local_images.generate(model_prompt)
            # A descrição de entrada é a fonte para conferir dimensões e intenção.
            produced["prompt"] = prompt
            verdict = review_image(produced)
            if not verdict["passed"]:
                reasons.append(verdict["reason"][:140])
                continue
            visual = {"available": False, "reason": "Revisão visual não configurada."}
            if os.environ.get("MENOR_VISION_MODEL", "").strip():
                try:
                    visual = visual_inspect(produced["id"], prompt)
                except (requests.RequestException, ValueError, OSError) as error:
                    visual = {"available": False, "reason": type(error).__name__}
            verdict["visual_review"] = visual
            verdict["content_verified"] = False  # um modelo avaliador não fornece prova
            if visual.get("available") and visual.get("model_matches_brief") is False:
                reasons.append("Modelo visual avaliou que a cena não corresponde ao pedido.")
                if attempt + 1 < MAX_ATTEMPTS:
                    issues = visual.get("issues", [])[:2]
                    model_prompt = prompt + ". Corrija os seguintes problemas visuais: " + "; ".join(issues)
                    continue
            return {
                **produced,
                "review": verdict,
                "worker": "openvino-sd15-int8",
                "attempts": attempt + 1,
                "requested_size": produced.get("requested_size"),
            }
        except (RuntimeError, ValueError, OSError, ImportError) as error:
            reasons.append(type(error).__name__)
            continue
    raise images.ImageUnavailable(
        "O subagente não passou na revisão técnica após duas tentativas. "
        "Não vou apresentar a imagem como concluída."
    )

"""Delegação de imagens ao worker local e verificação técnica independente."""
from src.agent.reviewer import review_image
from src.agent.skills import capability_status
from src.tools import images, local_images

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
    for _ in range(MAX_ATTEMPTS):
        try:
            produced = local_images.generate(prompt)
            verdict = review_image(produced)
        except (RuntimeError, ValueError, OSError, ImportError) as error:
            reasons.append(type(error).__name__)
            continue
        if verdict["passed"]:
            return {
                **produced,
                "review": verdict,
                "worker": "openvino-sd15-int8",
                "attempts": len(reasons) + 1,
            }
        reasons.append(verdict["reason"][:140])
    raise images.ImageUnavailable(
        "O subagente não passou na revisão técnica após duas tentativas. "
        "Não vou apresentar a imagem como concluída."
    )

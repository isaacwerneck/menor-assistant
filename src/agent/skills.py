"""Registro de skills: o que existe, o que foi testado e o que falta criar.

Estado derivado do cérebro e do runtime local; não confundir 'planejado'
com 'instalado'. O modelo de linguagem não pode marcar uma skill como pronta.
"""
from src.agent.missions import CAPABILITIES, MissionStore
from src.tools import local_images

DESCRIPTIONS = {
    "images.generate": "Gerar imagens locais a partir de um texto",
    "images.edit": "Editar fotos usando um modelo local",
    "programming": "Construir e testar código em um ambiente isolado",
    "design": "Criar e revisar materiais visuais",
    "music": "Criar áudio e música localmente",
    "web": "Pesquisar e navegar com ferramentas autorizadas",
}
LABELS = {
    "images.generate": "Subagente de imagens",
    "images.edit": "Subagente de edição",
    "programming": "Subagente programador",
    "design": "Subagente de design",
    "music": "Subagente de música",
    "web": "Subagente pesquisador",
}


def _mission_state(mission):
    if not mission:
        return "missing"
    return {
        "gathering": "planning", "awaiting_approval": "awaiting_approval",
        "queued": "queued", "installing": "installing",
        "needs_test": "testing", "ready": "ready",
        "blocked": "blocked", "failed": "failed",
        "cancelled": "missing",
    }[mission["status"]]


def catalog(missions=None):
    """Um único retrato do catálogo local, sem baixar ou executar modelos."""
    missions = missions if missions is not None else MissionStore()
    latest = {}
    for mission in missions.list(limit=50):
        cap = mission.get("capability")
        if cap in CAPABILITIES and cap not in latest and mission["status"] != "cancelled":
            latest[cap] = mission
    image_runtime = local_images.status(missions.store)
    result = []
    for capability in sorted(CAPABILITIES):
        mission = latest.get(capability)
        ready = (
            capability == "images.generate"
            and image_runtime["ready"]
            and mission is not None
            and mission["status"] == "ready"
            and isinstance(mission.get("result"), dict)
            and mission["result"].get("verified") is True
        )
        state = "ready" if ready else _mission_state(mission)
        if state == "ready" and not ready:
            state = "needs_verification"
        result.append({
            "capability": capability,
            "name": LABELS[capability],
            "description": DESCRIPTIONS[capability],
            "status": state,
            "ready": bool(ready),
            "mission_id": mission["id"] if mission else None,
            "worker": "openvino-sd15-int8" if capability == "images.generate" else None,
            "offline": capability == "images.generate",
        })
    return result


def capability_status(capability, missions=None):
    if capability not in CAPABILITIES:
        raise ValueError("Capacidade desconhecida.")
    return next(item for item in catalog(missions) if item["capability"] == capability)

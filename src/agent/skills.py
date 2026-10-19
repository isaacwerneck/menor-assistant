"""Registro de skills: o que existe, o que foi testado e o que falta criar.

Estado derivado do cérebro e do runtime local; não confundir 'planejado'
com 'instalado'. O modelo de linguagem não pode marcar uma skill como pronta.
"""
from src.agent.missions import CAPABILITIES, MissionStore
from src.tools import local_images
from src.memory.store import _write_lock

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
    verified = {}
    for mission in missions.list(limit=50, statuses={"ready"}):
        if isinstance(mission.get("result"), dict) and mission["result"].get("verified") is True:
            verified.setdefault(mission["capability"], mission)
    image_runtime = local_images.status(missions.store)
    result = []
    for capability in sorted(CAPABILITIES):
        mission = verified.get(capability) if image_runtime["ready"] else None
        mission = mission or latest.get(capability)
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
            "quality_status": "not_evaluated_for_specific_styles",
            "mission_id": mission["id"] if mission else None,
            "worker": "openvino-sd15-int8" if capability == "images.generate" else None,
            "offline": capability == "images.generate",
        })
    return result


def capability_status(capability, missions=None):
    if capability not in CAPABILITIES:
        raise ValueError("Capacidade desconhecida.")
    return next(item for item in catalog(missions) if item["capability"] == capability)


def document_verified_skill(mission, store):
    """Só documenta uma skill após teste positivo do artefato local."""
    if mission.get("capability") != "images.generate":
        raise ValueError("Skill não suportada para documentação.")
    if mission.get("status") != "ready" or not mission.get("approval"):
        raise ValueError("Missão não foi aprovada e concluída.")
    proof = mission.get("result")
    if not isinstance(proof, dict) or proof.get("verified") is not True:
        raise ValueError("Subagente não passou no teste.")
    if proof.get("worker") != "openvino-sd15-int8":
        raise ValueError("Worker desconhecido.")
    relative = "ferramentas/imagens/geracao_local.md"
    content = (
        "# Skill: geração de imagens local\n\n"
        "Estado: testada (arquivo gerado e tecnicamente verificado).\n"
        "Subagente: OpenVINO Stable Diffusion 1.5 INT8, CPU.\n"
        "Provedor: local (sem API de outra IA durante a inferência).\n"
        f"Missão de origem: {mission['id']}\n\n"
        "## Como usar\n\n"
        "Peça uma imagem no chat e descreva a cena e o estilo.\n"
        "O Menor chama o worker local e revisa tecnicamente o arquivo antes de entregar.\n\n"
        "## Limitações\n\n"
        "- Não há revisão estética ou semântica visual automática nesta versão.\n"
        "- CPU pode ser lenta, principalmente com imagens maiores.\n"
        "- Edição de fotos locais não faz parte desta skill.\n"
        "- Se o runtime for removido, o catálogo indicará indisponibilidade.\n"
    )
    with _write_lock:
        store.write_note(relative, content)
    return relative

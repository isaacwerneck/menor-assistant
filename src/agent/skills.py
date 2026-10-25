"""Registro de skills: o que existe, o que foi testado e o que falta criar.

Estado derivado do cérebro e do runtime local; não confundir 'planejado'
com 'instalado'. O modelo de linguagem não pode marcar uma skill como pronta.
"""
from typing import Any, Dict, List
from src.tools import local_images
from src.memory.store import _write_lock

CAPABILITIES = {"images.generate", "images.edit", "programming", "design", "music", "web"}

DESCRIPTIONS = {
    "images.generate": "Gerar imagens locais a partir de um texto",
    "images.edit": "Editar fotos usando um modelo local",
    "programming": "Construir e testar código com ferramentas reais do SO",
    "design": "Curador visual de referências e geração de interfaces web",
    "music": "Criar áudio e música localmente",
    "web": "Pesquisar e navegar na internet e bases de conhecimento (CRAG)",
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
    }.get(mission.get("status", "missing"), "missing")


def catalog(missions=None) -> List[Dict[str, Any]]:
    """Um único retrato do catálogo local, sem baixar ou executar modelos."""
    latest = {}
    verified = {}
    if missions is not None:
        try:
            for mission in missions.list(limit=50):
                cap = mission.get("capability")
                if cap in CAPABILITIES and cap not in latest and mission.get("status") != "cancelled":
                    latest[cap] = mission
            for mission in missions.list(limit=50, statuses={"ready"}):
                if isinstance(mission.get("result"), dict) and mission["result"].get("verified") is True:
                    verified.setdefault(mission.get("capability"), mission)
        except Exception:
            pass

    try:
        image_runtime = local_images.status()
    except Exception:
        image_runtime = {"ready": False}

    result = []
    # No Menor v2, programming, web e design são capacidades nativas operacionais
    v2_native_ready = {
        "programming": True,
        "web": True,
        "design": True,
    }

    for capability in sorted(CAPABILITIES):
        mission = verified.get(capability) if image_runtime.get("ready") else None
        mission = mission or latest.get(capability)

        if capability in v2_native_ready:
            ready = True
            state = "ready"
        elif capability == "images.generate":
            has_verified_proof = bool(
                mission is None or (
                    mission.get("status") == "ready"
                    and isinstance(mission.get("result"), dict)
                    and mission["result"].get("verified") is True
                )
            )
            ready = bool(image_runtime.get("ready") and has_verified_proof)
            if ready:
                state = "ready"
            elif not image_runtime.get("ready"):
                state = "awaiting_setup"
            else:
                state = _mission_state(mission)
        else:
            ready = bool(mission and mission.get("status") == "ready")
            state = "ready" if ready else _mission_state(mission)

        worker_desc = None
        if capability == "images.generate":
            worker_desc = "openvino-sd15-int8"
        elif capability in v2_native_ready:
            worker_desc = "python-native-v2"

        quality = "verified_native" if capability in v2_native_ready else "not_evaluated_for_specific_styles"
        result.append({
            "capability": capability,
            "name": LABELS.get(capability, capability),
            "description": DESCRIPTIONS.get(capability, ""),
            "status": state,
            "ready": bool(ready),
            "quality_status": quality,
            "mission_id": mission["id"] if mission and "id" in mission else None,
            "worker": worker_desc,
            "offline": capability in ("images.generate", "programming"),
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

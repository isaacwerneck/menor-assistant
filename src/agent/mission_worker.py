"""Worker de missão: executa apenas modelos pré-aprovados após consentimento.

Processo unitário, invocado por timer systemd. Não executa shell nem scripts
escolhidos pelo Qwen. Máximo de duas tentativas por missão.
"""

from src.agent.missions import MissionStore
from src.agent.reviewer import review_image
from src.agent.skills import document_verified_skill
from src.tools import local_images


def run_once(store=None):
    missions = store if store is not None else MissionStore()
    for mission in missions.list(limit=50):
        if mission["status"] not in ("queued", "installing"):
            continue
        mission_id = mission["id"]
        if mission["attempts"] >= 2:
            if mission["status"] == "installing":
                missions.transition(mission_id, "installing", "failed", {
                    "error": "Tentativas esgotadas; precisa de revisão.",
                })
            continue
        if mission["status"] == "installing":
            missions.transition(mission_id, "installing", "queued")
        if not mission["approval"] or mission["capability"] != "images.generate":
            missions.transition(mission_id, "queued", "blocked", {
                "error": "Executor não aprovado para esta capacidade.",
            })
            continue
        missions.transition(mission_id, "queued", "installing")
        try:
            missions.stage(mission_id, "preparing")
            local_images.ensure_runtime_approved()
            missions.stage(mission_id, "downloading")
            install = local_images.install_approved()
            if not install["ready"]:
                raise local_images.LocalImageUnavailable(
                    "Runtime OpenVINO indisponível; instale as dependências opcionais."
                )
            # Um agente revisor independente testa o artefato; no máximo 2 tentativas.
            missions.stage(mission_id, "testing")
            for _ in range(2):
                proof = local_images.generate("Uma esfera azul sobre fundo branco", steps=6)
                verdict = review_image(proof)
                if verdict["passed"]:
                    result = {
                        "worker": "openvino-sd15-int8",
                        "test_image": proof["url"],
                        "verified": True,
                        "review": verdict,
                    }
                    ready = {**missions.get(mission_id), "status": "ready", "result": result}
                    document_verified_skill(ready, missions.store)
                    return missions.transition(mission_id, "installing", "ready", result)
            raise local_images.LocalImageUnavailable("Imagem não passou na revisão técnica.")
        except (OSError, ValueError, RuntimeError, ImportError) as error:
            return missions.transition(mission_id, "installing", "failed", {
                "error": type(error).__name__,
                "verified": False,
            })
    return {"status": "idle"}


def main():
    result = run_once()
    print("Menor worker: " + result.get("status", "idle"))


if __name__ == "__main__":
    main()

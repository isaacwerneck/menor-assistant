"""Máquina de estados persistente para missões delegadas a subagentes.

Criação, planejamento e aprovação são operações separadas. Nenhuma
missão pode instalar modelos ou executar código sem aprovação explícita.
"""

import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timezone

from src.agent.model_catalog import discover
from src.agent.planner import explain as explain_plan, plan
from src.memory.store import BrainStore

_LOCK = threading.RLock()
VALID_ID = re.compile(r"^[0-9a-f]{32}$")
STATES = {
    "gathering", "awaiting_approval", "queued", "installing",
    "needs_test", "ready", "blocked", "failed", "cancelled",
}
CAPABILITIES = {"images.generate", "images.edit", "programming", "design", "music", "web"}
MAX_TASK_BYTES = 16 * 1024


def _timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MissionStore:
    def __init__(self, store=None):
        self.store = store if store is not None else BrainStore()

    def _root(self):
        return self.store._directories(("missoes",))

    def _path(self, mission_id):
        if not isinstance(mission_id, str) or not VALID_ID.fullmatch(mission_id):
            raise ValueError("ID de missão inválido.")
        return self._root() / (mission_id + ".json")

    def _write(self, obj):
        path = self._path(obj["id"])
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("Missão tem caminho inválido.")
        obj["updated_at"] = _timestamp()
        data = json.dumps(obj, ensure_ascii=False, indent=2)
        if len(data.encode("utf-8")) > MAX_TASK_BYTES:
            raise ValueError("Missão ultrapassou o limite de armazenamento.")
        fd, temporary = tempfile.mkstemp(dir=self._root(), prefix=".mission-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if path.is_symlink():
                raise ValueError("Missão não pode ser link simbólico.")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def get(self, mission_id):
        with _LOCK:
            path = self._path(mission_id)
            if path.is_symlink() or not path.is_file():
                raise LookupError("Missão não encontrada.")
            if path.stat().st_size > MAX_TASK_BYTES:
                raise ValueError("Missão inválida.")
            result = json.loads(path.read_text(encoding="utf-8"))
            if result.get("id") != mission_id or result.get("status") not in STATES:
                raise ValueError("Missão inválida.")
            return result

    def list(self, limit=20, statuses=None, oldest_first=False):
        if not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ValueError("Limite inválido.")
        if statuses is not None and not set(statuses).issubset(STATES):
            raise ValueError("Filtro de estados inválido.")
        with _LOCK:
            items = []
            for path in self._root().iterdir():
                if path.is_symlink() or not path.is_file() or not VALID_ID.fullmatch(path.stem):
                    continue
                try:
                    item = self.get(path.stem)
                    if statuses is None or item["status"] in statuses:
                        items.append(item)
                except (ValueError, LookupError, OSError, json.JSONDecodeError):
                    continue
            return sorted(items, key=lambda x: x["updated_at"], reverse=not oldest_first)[:limit]

    def begin(self, capability, goal):
        if capability not in CAPABILITIES:
            raise ValueError("Capacidade desconhecida.")
        if not isinstance(goal, str) or not 8 <= len(goal.strip()) <= 600:
            raise ValueError("Descreva o objetivo em 8 a 600 caracteres.")
        question = (
            "Como você quer que essa ferramenta funcione? "
            "Me diga entradas, resultado esperado e algum exemplo."
        )
        obj = {
            "id": uuid.uuid4().hex, "capability": capability, "goal": goal.strip(),
            "requirements": "", "status": "gathering", "question": question,
            "approval": False, "plan": {}, "result": None,
            "attempts": 0, "created_at": _timestamp(),
        }
        with _LOCK:
            self._write(obj)
        return obj

    def detail(self, mission_id, requirements):
        if not isinstance(requirements, str) or not 8 <= len(requirements.strip()) <= 1200:
            raise ValueError("Explique a ferramenta em 8 a 1200 caracteres.")
        with _LOCK:
            obj = self.get(mission_id)
            if obj["status"] != "gathering":
                raise ValueError("Missão não está coletando requisitos.")
            capability = obj["capability"]
            candidates = discover(capability)
            obj["requirements"] = requirements.strip()
            proposal = plan(obj["goal"], obj["requirements"], capability)
            obj["plan"] = {
                **proposal,
                "candidates": candidates,
                "preferred": candidates[0]["id"] if candidates else None,
                "requires_approval": True,
            }
            if capability == "images.generate":
                from src.tools.local_images import preflight
                obj["plan"]["preflight"] = preflight(self.store)
            obj["status"] = "awaiting_approval"
            if candidates and not obj["plan"]["preflight"]["enough_disk"]:
                obj["question"] = (
                    "Encontrei o modelo local, mas não há 5 GB livres em disco. "
                    "Precisamos liberar espaço antes do download."
                )
            elif candidates:
                obj["question"] = (
                    "O catálogo sugere Stable Diffusion 1.5 com OpenVINO para teste local. "
                    "A instalação reserva 5 GB em disco; desempenho e qualidade precisam de teste. "
                    "Posso instalar e testar o subagente?"
                )
            else:
                obj["question"] = (
                    "Ainda não tenho instalador aprovado para essa capacidade. "
                    "Quer que eu registre o plano e prepare uma proposta de implementação?"
                )
            self._write(obj)
            return obj

    def explain(self, mission_id, message):
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 8000:
            raise ValueError("Pergunta inválida.")
        mission = self.get(mission_id)
        if mission["status"] != "awaiting_approval":
            raise ValueError("Missão não está aguardando autorização.")
        normalized = re.sub(r"\s+", " ", message.casefold()).strip(" ?!.")
        if "aprova" in normalized or "autoriza" in normalized:
            return (
                "A autorização pendente é para baixar o modelo de imagens e instalar "
                "as dependências locais no servidor, conforme o plano. "
                "Até agora nada foi instalado por esta missão. "
                "Você pode tirar dúvidas ou dizer 'eu aprovo' para prosseguir."
            )
        return explain_plan(mission, message)

    def decide(self, mission_id, approved):
        if not isinstance(approved, bool):
            raise ValueError("A decisão precisa ser explícita.")
        with _LOCK:
            obj = self.get(mission_id)
            if obj["status"] != "awaiting_approval":
                raise ValueError("Missão não está aguardando autorização.")
            obj["approval"] = approved
            if not approved:
                obj["status"] = "cancelled"
                obj["question"] = "Entendi. Não instalei nada."
            elif obj["capability"] == "images.generate" and obj["plan"]["preferred"]:
                from src.tools.local_images import preflight
                if preflight(self.store)["enough_disk"]:
                    obj["status"] = "queued"
                    obj["question"] = "Autorizado. Vou baixar e preparar o modelo local."
                else:
                    obj["status"] = "blocked"
                    obj["question"] = (
                        "Autorizei o pedido, mas não há espaço suficiente em disco. "
                        "Nenhum download foi iniciado."
                    )
                    obj["result"] = {"error": "insufficient_disk", "verified": False}
            else:
                obj["status"] = "blocked"
                obj["question"] = (
                    "Plano autorizado, mas falta um executor seguro para criar "
                    "essa ferramenta. Não vou fingir que ela está instalada."
                )
            self._write(obj)
            return obj

    def stage(self, mission_id, value):
        """Atualiza a etapa da operação sem mudar a autorização da missão."""
        if value not in ("preparing", "downloading", "testing"):
            raise ValueError("Etapa desconhecida.")
        with _LOCK:
            obj = self.get(mission_id)
            if obj["status"] != "installing":
                raise ValueError("A missão não está em execução.")
            obj["stage"] = value
            self._write(obj)
            return obj

    def transition(self, mission_id, old, new, result=None):
        if old not in STATES or new not in STATES:
            raise ValueError("Estado desconhecido.")
        with _LOCK:
            obj = self.get(mission_id)
            if obj["status"] != old:
                raise ValueError("A missão mudou de estado.")
            obj["status"] = new
            obj["result"] = result
            obj["attempts"] += 1 if new == "installing" else 0
            self._write(obj)
            return obj

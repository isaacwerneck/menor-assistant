"""Worker autônomo de reflexão cognitiva (Stanford Generative Agents).

Sintetiza eventos recentes, tarefas executadas e histórico de conversas
em aprendizados consolidados e atualizações na Core Memory e Base de Conhecimento.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import requests

from src.agent.workers import TaskQueue, get_task_queue
from src.memory.core_memory import CoreMemoryManager
from src.memory.search import KnowledgeIndex
from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)

REFLECTION_PROMPT = """Você é o módulo de síntese e reflexão cognitiva do Menor v2 (Stanford Generative Agents).
Sua função é analisar as ações, decisões e tarefas executadas recentemente e sintetizar lições técnicas permanentes
ou atualizações para a Core Memory.

Responda estritamente em formato JSON válido:
{
  "learnings": ["Lição técnica permanente 1", "Lição 2"],
  "profile_updates": ["Atualização ou nova preferência permanente do usuário"]
}

Se não houver aprendizados relevantes ou novas preferências, retorne:
{"learnings": [], "profile_updates": []}.
Não adicione explicações fora do JSON.
"""


class ReflectionWorker:
    """Consolida memórias diárias em conhecimentos gerais e refina o perfil do operador."""

    def __init__(
        self,
        store: Optional[BrainStore] = None,
        queue: Optional[TaskQueue] = None,
        ollama_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.store = store if store is not None else BrainStore()
        self.queue = queue if queue is not None else get_task_queue()
        self.ollama_url = (ollama_url or os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen-fast:latest")
        self.core_memory = CoreMemoryManager(store=self.store)
        self.index = KnowledgeIndex(store=self.store, ollama_url=self.ollama_url)

    def _collect_recent_events(self, max_events: int = 15) -> List[str]:
        """Agrupa metas de tarefas e resultados recentes."""
        events = []
        try:
            tasks = self.queue.list_tasks(limit=max_events)
            for t in tasks:
                goal = t.get("goal", "")
                result = t.get("result", "")
                status = t.get("status", "")
                slug = t.get("project_slug") or "geral"
                if status == "completed" and result:
                    events.append(f"Projeto [{slug}]: {goal} -> Concluído com sucesso: {result[:200]}")
                elif goal:
                    events.append(f"Projeto [{slug}]: {goal} (status: {status})")
        except Exception as exc:
            LOGGER.warning("Falha ao ler fila de tarefas para reflexão: %s", exc)

        return events

    def reflect(self, events: Optional[List[str]] = None, max_events: int = 15) -> Dict[str, Any]:
        """Executa ciclo de reflexão cognitiva sobre eventos fornecidos ou coletados da fila."""
        target_events = events if events is not None else self._collect_recent_events(max_events)
        if not target_events:
            return {
                "success": True,
                "learnings_added": 0,
                "profile_updates": 0,
                "events_analyzed": 0,
                "message": "Nenhum evento recente para reflexão.",
            }

        event_text = "\n".join(f"- {e}" for e in target_events)
        prompt = f"Eventos recentes:\n{event_text}\n\nSintetize os aprendizados permanentes e atualizações de perfil:"

        learnings: List[str] = []
        profile_updates: List[str] = []

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": REFLECTION_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": "json",
                },
                timeout=(5, 60),
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("message", {}).get("content", "{}")
                parsed = json.loads(content)
                learnings = parsed.get("learnings", [])
                profile_updates = parsed.get("profile_updates", [])
        except Exception as exc:
            LOGGER.info("Reflexão com Ollama offline ou indisponível (%s). Usando fallback heurístico.", exc)
            for e in target_events:
                if "Concluído com sucesso" in e:
                    clean = re.sub(r"^Projeto \[[^\]]+\]:\s*", "", e)
                    learnings.append(clean[:200])

        added_learnings = 0
        for l_item in learnings:
            if isinstance(l_item, str) and len(l_item.strip()) >= 5:
                res = self.index.deduplicate_and_store(l_item.strip())
                if res.get("action") in ("inserted", "updated"):
                    added_learnings += 1

        added_profile = 0
        for p_item in profile_updates:
            if isinstance(p_item, str) and len(p_item.strip()) >= 5:
                self.core_memory.set_block("user_profile", p_item.strip(), mode="append")
                added_profile += 1

        return {
            "success": True,
            "learnings_added": added_learnings,
            "profile_updates": added_profile,
            "events_analyzed": len(target_events),
            "learnings": learnings,
            "profile_updates_list": profile_updates,
        }


if __name__ == "__main__":
    worker = ReflectionWorker()
    summary = worker.reflect()
    print("Ciclo de reflexão concluído com sucesso:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

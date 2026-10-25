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

from src.agent.study import get_optimal_threads
from src.agent.workers import TaskQueue, get_task_queue
from src.memory.core_memory import CoreMemoryManager
from src.memory.search import KnowledgeIndex
from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)

REFLECTION_PROMPT = """Você é o módulo de síntese e reflexão cognitiva do Menor v2.
Sua função é analisar as ações, decisões e tarefas executadas recentemente e sintetizar lições técnicas permanentes.

REGRAS DE VERIFICAÇÃO CONTRA ERROS E ALUCINAÇÕES:
1. NUNCA transforme códigos ou abordagens de tarefas que falharam ou deram erro em lições de sucesso.
2. Ações com 'FALHOU' ou 'BUG' devem ser sintetizadas estritamente no campo "anti_patterns" (o que NÃO fazer).
3. Apenas tarefas com 'VERIFICADO' ou concluídas com sucesso podem gerar "learnings".

Responda estritamente em formato JSON válido:
{
  "learnings": ["Lição técnica verificada 1"],
  "anti_patterns": ["Abordagem com erro ou bug a ser evitada 1"],
  "profile_updates": ["Atualização confirmada do usuário"]
}

Se não houver aprendizados ou preferências, retorne listas vazias.
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
        """Agrupa metas de tarefas, commits recentes do Git e tópicos assimilados."""
        events = []
        try:
            tasks = self.queue.list_tasks(limit=max_events)
            for t in tasks:
                goal = str(t.get("goal") or "")
                result = str(t.get("result") or "")
                status = str(t.get("status") or "")
                slug = t.get("project_slug") or "geral"
                is_fail = status == "failed" or "erro" in result.lower() or "exception" in result.lower()
                if status == "completed" and result and not is_fail:
                    events.append(f"Projeto [{slug}]: {goal} -> Concluído com sucesso (VERIFICADO): {result[:200]}")
                elif is_fail or status == "failed":
                    events.append(f"Projeto [{slug}]: {goal} -> FALHOU / BUG ENCONTRADO: {result[:200]}")
                elif goal:
                    events.append(f"Projeto [{slug}]: {goal} (status: {status})")
        except Exception as exc:
            LOGGER.warning("Falha ao ler fila de tarefas para reflexão: %s", exc)

        # Se houver espaço, agrega commits recentes do repositório
        if len(events) < max_events:
            try:
                import subprocess
                git_proc = subprocess.run(
                    ["git", "log", "-n", "4", "--pretty=format:%h - %s"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if git_proc.returncode == 0 and git_proc.stdout.strip():
                    for line in git_proc.stdout.strip().splitlines():
                        if line.strip():
                            events.append(f"Modificação recente no repositório (Git): {line.strip()}")
            except Exception:
                pass

        # Agrega os últimos tópicos de estudo assimilados no cérebro
        if len(events) < max_events:
            try:
                from src.agent.study import TopicManager
                completed = [t for t in TopicManager(self.store).list_topics(uncompleted_only=False) if t.get("completed")]
                for t in reversed(completed[-3:]):
                    events.append(f"Tópico técnico estudado e assimilado no cérebro: {t.get('text', '')}")
            except Exception:
                pass

        return events[:max_events]

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
                    "options": {
                        "temperature": 0.2,
                        "num_predict": 200,
                        "num_thread": get_optimal_threads(),
                        "num_ctx": 2048,
                    },
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

        anti_patterns = parsed.get("anti_patterns", []) if 'parsed' in locals() else []
        added_learnings = 0
        for l_item in learnings:
            if isinstance(l_item, str) and len(l_item.strip()) >= 5:
                clean_l = l_item.strip()[:270]
                res = self.index.deduplicate_and_store(clean_l)
                if res.get("action") in ("inserted", "updated"):
                    added_learnings += 1

        added_antis = 0
        for a_item in anti_patterns:
            if isinstance(a_item, str) and len(a_item.strip()) >= 5:
                anti_fmt = f"[ANTI-PADRÃO - EVITAR]: {a_item.strip()}"[:270]
                res = self.index.deduplicate_and_store(anti_fmt)
                if res.get("action") in ("inserted", "updated"):
                    added_antis += 1

        added_profile = 0
        for p_item in profile_updates:
            if isinstance(p_item, str) and len(p_item.strip()) >= 5:
                self.core_memory.set_block("user_profile", p_item.strip(), mode="append")
                added_profile += 1

        # Otimização algorítmica de prompts offline (DSPy Pattern)
        try:
            from src.agent.prompt_optimizer import PromptOptimizer
            PromptOptimizer(self.store).compile()
        except Exception as exc:
            LOGGER.debug("Otimização offline de prompts em reflexão ignorada: %s", exc)

        return {
            "success": True,
            "learnings_added": added_learnings,
            "anti_patterns_added": added_antis,
            "profile_updates": added_profile,
            "events_analyzed": len(target_events),
            "learnings": learnings,
            "anti_patterns": anti_patterns,
            "profile_updates_list": profile_updates,
        }


if __name__ == "__main__":
    worker = ReflectionWorker()
    summary = worker.reflect()
    print("Ciclo de reflexão concluído com sucesso:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

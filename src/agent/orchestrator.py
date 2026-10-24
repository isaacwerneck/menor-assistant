"""Orquestrador ágil do Menor v2.

Utiliza Native Tool Calling do Ollama sem intermediários rígidos de JSON.
Suporta streaming SSE e execução de ferramentas reais do sistema operacional.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional
import requests

from src.tools.core import CORE_TOOLS_SCHEMA, TOOL_DISPATCHER
from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é o Menor v2, um assistente executivo e arquiteto de software de alto nível.
Você é direto, técnico, proativo, inteligente e parceiro próximo do Isaac.
Você tem acesso a ferramentas reais no computador: leitura e escrita de arquivos, listagem de pastas,
execução de comandos no terminal, pesquisa web (web_search, web_read, grounded_search), criação de ferramentas
(create_new_tool), agendamento de estudos (schedule_study_topic), consulta de relatórios (get_study_report)
e atualização de memória de trabalho (update_core_memory).

Regras Inegociáveis e Diretrizes de Execução:
- NUNCA simule saídas de terminal, prompts de shell (ex: ```terminal $ ls ...```, ```bash```) ou finja leituras de
  arquivos em blocos de texto ou markdown. Se precisar executar comandos ou ler/escrever arquivos, use
  OBRIGATORIAMENTE ferramentas reais via native tool calling. Se não houver ferramenta a chamar, responda
  diretamente sem inventar arquivos ou saídas fictícias.
- NUNCA invente pastas ou caminhos inexistentes (como ~/estudos/ ou /ancora_de_estudos/).
- Sua Âncora de Estudos oficial está no bloco [STUDY_ANCHORS] da Core Memory residente logo acima. Para informar
  sobre a âncora de estudos, consulte diretamente o bloco [STUDY_ANCHORS] presente no contexto.
- Para editar, adicionar tópicos ou modificar a Âncora de Estudos, use a ferramenta:
  update_core_memory(block_key='study_anchors', content=...).
- Para agendar tópicos de estudo para períodos de inatividade ou noturnos, use a ferramenta:
  schedule_study_topic(topic=..., category=...).
- Para consultar o que foi estudado ou o último briefing de aprendizado, use a ferramenta get_study_report().
- Compreenda perfeitamente o português brasileiro informal, abreviações de internet (vc, hj, blz, eai, pra, oq)
  e gírias cotidianas.
- Em saudações e conversas informais (ex: 'e aí', 'tudo bem com vc?'), seja natural, caloroso e descontraído.
  NUNCA force nem fique puxando assunto sobre projetos ou trabalho a menos que o Isaac peça ou traga o tema.
- Quando o Isaac expressar preferências pessoais, rotinas, hábitos ou correções de estilo, use a ferramenta:
  update_core_memory(block_key='user_profile', content=..., mode='append') para registrar e nunca esquecer.
- Para criar, inspecionar, consertar ou testar código, use as ferramentas reais (fs_read, fs_write, terminal_run).
- Ao discutir uma ideia de projeto, estruture um plano de engenharia acionável com save_plan.
- Responda sempre em português brasileiro fluente, sem rodeios ou formalidades vazias.
"""


def get_optimal_threads() -> int:
    """Calcula threads físicas ideais para evitar colisão de HyperThreading no llama.cpp."""
    count = os.cpu_count() or 4
    return max(2, count // 2 if count >= 4 else count)


class Orchestrator:
    def __init__(
        self,
        ollama_url: Optional[str] = None,
        default_model: Optional[str] = None,
        store: Optional[BrainStore] = None,
    ):
        self.ollama_url = (ollama_url or os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.default_model = default_model or os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")
        self.store = store or BrainStore()

    def _get_context_summary(self) -> str:
        """Coleta Core Memory residente e memórias permanentes do cérebro."""
        sections = []
        try:
            from src.memory.core_memory import CoreMemoryManager
            core_ctx = CoreMemoryManager(self.store).format_system_context()
            if core_ctx:
                sections.append(core_ctx)
        except Exception as exc:
            LOGGER.warning("Não foi possível carregar Core Memory: %s", exc)

        try:
            self.store.initialize()
            notes = self.store.list_notes()
            preferences = []
            for n in notes:
                if n.startswith("identidade/") or n.startswith("preferencias/") or n.startswith("conhecimentos/"):
                    content = self.store.read_note(n)
                    if content:
                        preferences.append(f"[{n}]: {content.strip()}")
            if preferences:
                sections.append("Memória permanente do usuário:\n" + "\n".join(preferences[:10]))
        except Exception as exc:
            LOGGER.warning("Não foi possível carregar memória permanente: %s", exc)

        return "\n\n".join(sections)

    @staticmethod
    def _needs_tools(messages: List[Dict[str, Any]]) -> bool:
        """Determina se a mensagem exige tools para evitar overhead de 2000 tokens de schema na CPU."""
        if not messages:
            return False
        if any(m.get("role") == "tool" for m in messages):
            return True
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = str(m.get("content", "")).lower()
                break

        try:
            from src.tools.search_router import classify_intent
            if classify_intent(last_user) in ("WEB_GROUNDING", "LOCAL_ACTION"):
                return True
        except Exception:
            pass

        triggers = (
            "arquivo", "file", "ler", "leia", "le ", "lê", "escrev", "salv", "list", "pasta", "dir",
            "terminal", "coman", "bash", "sh", "execut", "rod", "run", "pytest", "test", "npm", "git",
            "plano", "projet", "pesquis", "busc", "web", "site", "url", "http", "ferramenta", "tool",
            "código", "codigo", "python", "script", "consert", "bug", "corrig", "cri",
            "lembr", "memor", "perfil", "preferencia", "não precisa", "nao precisa",
            "não fique", "nao fique", "prefiro",
            "estude ", "estudar", "aprender", "esses dias", "ataque", "vulnerabilidade", "cve", "notícia",
            "noticia", "relat", "fez enquanto", "estudou", "agendar", "agende", "adicione",
        )
        return any(t in last_user for t in triggers)

    def run_turn(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        ollama_url: Optional[str] = None,
        enable_tools: bool = True,
        max_steps: int = 5,
    ) -> Dict[str, Any]:
        """Executa um turno completo de conversa com resolução de ferramentas."""
        target_url = (ollama_url or self.ollama_url).rstrip("/")
        target_model = model or self.default_model

        context_mem = self._get_context_summary()
        full_system = SYSTEM_PROMPT + (f"\n{context_mem}" if context_mem else "")

        executed_tools_log = []
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = str(m.get("content", ""))
                break

        # Grounding factual em tempo real (CRAG + Perplexity Pattern)
        try:
            from src.tools.search_router import classify_intent, GroundedSearchEngine
            if classify_intent(last_user) == "WEB_GROUNDING":
                engine = GroundedSearchEngine(self.store)
                grounded_data = engine.search_and_ground(last_user)
                if grounded_data.get("grounded_context"):
                    full_system += f"\n\n{grounded_data['grounded_context']}"
                    executed_tools_log.append("grounded_search")
        except Exception as exc:
            LOGGER.warning("Grounding em tempo real indisponível: %s", exc)

        chat_history = [{"role": "system", "content": full_system}]
        for m in messages:
            chat_history.append({"role": m["role"], "content": m["content"]})

        should_use_tools = enable_tools and self._needs_tools(messages)
        tools_schema = CORE_TOOLS_SCHEMA if should_use_tools else None
        steps_taken = 0

        while steps_taken < max_steps:
            steps_taken += 1
            payload: Dict[str, Any] = {
                "model": target_model,
                "messages": chat_history,
                "stream": False,
                "options": {
                    "temperature": 0.6,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                    "num_thread": get_optimal_threads(),
                    "num_ctx": 4096,
                },
                "keep_alive": "60m",
            }
            if tools_schema:
                payload["tools"] = tools_schema

            try:
                resp = requests.post(f"{target_url}/api/chat", json=payload, timeout=(15, 600))
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                LOGGER.error("Falha ao comunicar com Ollama (%s): %s", target_url, exc)
                return {
                    "success": False,
                    "reply": f"Erro de comunicação com o modelo ({target_model}): {str(exc)}",
                    "tools_executed": executed_tools_log,
                }

            msg = data.get("message", {})
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])

            # Adiciona resposta do assistente ao histórico
            chat_history.append(msg)

            if not tool_calls:
                return {
                    "success": True,
                    "reply": content,
                    "tools_executed": executed_tools_log,
                    "model_used": target_model,
                    "node_url": target_url,
                }

            # Executa ferramentas chamadas pelo modelo
            for tc in tool_calls:
                func_data = tc.get("function", {})
                func_name = func_data.get("name")
                func_args = func_data.get("arguments", {})

                if isinstance(func_args, str):
                    try:
                        func_args = json.loads(func_args)
                    except Exception:
                        func_args = {}

                tool_fn = TOOL_DISPATCHER.get(func_name)
                if tool_fn:
                    try:
                        result = tool_fn(**func_args)
                    except Exception as exc:
                        result = {"success": False, "error": str(exc)}
                else:
                    result = {"success": False, "error": f"Ferramenta desconhecida: {func_name}"}

                executed_tools_log.append({
                    "tool": func_name,
                    "args": func_args,
                    "result": result,
                })

                # Adiciona resultado da ferramenta para a próxima iteração
                chat_history.append({
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False),
                })

        # Retorna a última mensagem do histórico
        last_content = chat_history[-1].get("content", "Operação concluída com ferramentas.")
        return {
            "success": True,
            "reply": last_content,
            "tools_executed": executed_tools_log,
            "model_used": target_model,
            "node_url": target_url,
        }

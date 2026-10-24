"""Orquestrador ágil do Menor v2.

Utiliza Native Tool Calling do Ollama sem intermediários rígidos de JSON.
Suporta streaming SSE e execução de ferramentas reais do sistema operacional.
"""
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import requests

from src.tools.core import CORE_TOOLS_SCHEMA, TOOL_DISPATCHER
from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é o Menor v2, parceiro de tecnologia e arquiteto de software de alto nível do Isaac.
Você é direto, técnico, proativo, inteligente e parceiro de engenharia.
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
- Sua Âncora de Estudos oficial está no bloco [STUDY_ANCHORS] da Core Memory residente logo acima.
- NUNCA faça propaganda não solicitada de ferramentas ou projetos no meio de conversas comuns.
  Responda estritamente ao que foi perguntado.
- NUNCA invente reuniões, compromissos ou presuma a rotina pessoal do Isaac.
- Responda sempre em português brasileiro fluente, natural e direto, sem rodeios ou formalidades vazias.
"""

CASUAL_SYSTEM_PROMPT = """Você é o Menor v2, o assistente inteligente e parceiro de tecnologia do Isaac.
Diretrizes Rigorosas de Conversação:
1. Responda sempre de forma curta, natural, descontraída e amigável em português brasileiro (use gírias leves como mano, suave, blz).
2. Em saudações ("e aí", "oi", "fala"), responda em 1 frase acolhedora sem puxar assuntos técnicos ou inventar tarefas.
3. Se o Isaac não pedir código ou ferramentas, apenas converse com ele amigavelmente.
4. NUNCA gere blocos de pensamento interno, tags <think> ou explicações sobre o processo de raciocínio. Responda diretamente.
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

    def _get_context_summary(self, casual: bool = False) -> str:
        """Coleta Core Memory residente e memórias permanentes do cérebro.

        No modo casual, apenas o perfil essencial do usuário é retornado para acelerar
        a inferência em CPUs locais sem sobrecarga de tokens.
        """
        if casual:
            try:
                from src.memory.core_memory import CoreMemoryManager
                user_prof = CoreMemoryManager(self.store).get_block("user_profile")
                if user_prof:
                    return f"Perfil do Usuário:\n{user_prof.strip()}"
            except Exception:
                pass
            return ""

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

        try:
            from src.agent.prompt_optimizer import PromptOptimizer
            dspy_inj = PromptOptimizer(self.store).format_system_injection()
            if dspy_inj:
                sections.append(dspy_inj)
        except Exception as exc:
            LOGGER.debug("PromptOptimizer indisponível: %s", exc)

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

        # Expressões coloquiais e saudações comuns nunca devem ativar tools
        casual_bypass = (
            "oi", "ola", "olá", "eai", "e aí", "e ai", "fala tu", "opa", "salve",
            "tudo bem", "como vai", "blz", "beleza", "suave", "tranquilo",
            "to querendo uma parada", "tô querendo uma parada", "querendo uma parada",
            "quero ver um negocio", "quero ver um negócio", "preciso de uma parada",
        )
        norm_clean = last_user.strip(" !?.,;:")
        greetings = ("oi ", "ola ", "olá ", "eai ", "e aí ", "opa ")
        if norm_clean in casual_bypass or any(norm_clean.startswith(c) for c in greetings):
            action_words = (
                "leia", "ler", "escreva", "escreve", "crie", "criar",
                "rode", "rodar", "terminal", "pytest", "git", "salve"
            )
            if not any(w in norm_clean for w in action_words):
                return False

        # Consultas de relatório de estudo já têm o briefing injetado diretamente no system prompt
        study_report_triggers = (
            "estudou", "o que você estudou", "o que vc estudou", "oq vc estudou",
            "oq estudou", "o que estudou", "relatório de estudo", "relatorio de estudo",
            "último estudo", "ultimo estudo", "briefing de estudo", "o que aprendeu",
            "oq aprendeu", "fez enquanto", "estudou essa noite", "estudou hoje",
        )
        if any(t in last_user for t in study_report_triggers):
            action_triggers = ("agendar", "agende", "adicione", "execute", "crie", "salve", "escreva", "rode")
            if not any(a in last_user for a in action_triggers):
                return False

        triggers = (
            "arquivo", "file", "ler", "leia", "le ", "lê", "escrev", "salv", "list", "pasta", "dir",
            "terminal", "coman", "bash", "sh", "execut", "rod", "run", "pytest", "test", "npm", "git",
            "plano", "projet", "pesquis", "busc", "web", "site", "url", "http", "ferramenta", "tool",
            "código", "codigo", "python", "script", "consert", "bug", "corrig", "cri",
            "patch", "alterar", "substituir", "simbolo", "símbolo", "mapa", "repo_map", "onde fica", "onde está",
            "declaração", "declaracao", "refator",
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

        should_use_tools = enable_tools and self._needs_tools(messages)
        tools_schema = CORE_TOOLS_SCHEMA if should_use_tools else None

        if not should_use_tools:
            # Modo ultrarrápido para conversas casuais na CPU (< 80 tokens de prompt)
            context_mem = self._get_context_summary(casual=True)
            full_system = CASUAL_SYSTEM_PROMPT + (f"\n{context_mem}" if context_mem else "")
        else:
            context_mem = self._get_context_summary(casual=False)
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

        # Grounding de Relatório de Estudos (evita cascata de 2 turnos pesados de 14B na CPU)
        norm_user = last_user.lower()
        study_report_triggers = (
            "estudou", "o que você estudou", "o que vc estudou", "oq vc estudou",
            "oq estudou", "o que estudou", "relatório de estudo", "relatorio de estudo",
            "último estudo", "ultimo estudo", "briefing de estudo", "o que aprendeu",
            "oq aprendeu", "fez enquanto", "estudou essa noite", "estudou hoje",
            "aprendeu", "o que você aprendeu", "o que vc aprendeu", "oq vc aprendeu",
            "ultimos tempos", "últimos tempos", "novidades de estudo",
        )
        if any(t in norm_user for t in study_report_triggers):
            try:
                from src.tools.core import get_study_report
                rep = get_study_report(self.store)
                if rep.get("has_report") and rep.get("report_markdown"):
                    full_system += f"\n\n[RELATÓRIO ATUALIZADO DE ESTUDOS DO MENOR]:\n{rep['report_markdown']}"
                    executed_tools_log.append("get_study_report")
            except Exception as exc:
                LOGGER.debug("Grounding de relatório de estudos ignorado: %s", exc)

        coding_keywords = (
            "código", "codigo", "script", "bug", "patch", "consert", "refator", "função", "classe", "test"
        )
        if any(k in norm_user for k in coding_keywords):
            try:
                from src.agent.ponytail import get_ponytail_system_prompt
                full_system += f"\n\n{get_ponytail_system_prompt()}"
            except Exception:
                pass

        chat_history = [{"role": "system", "content": full_system}]
        if not should_use_tools:
            # Em modo casual, limita aos últimos 3 turnos para não sobrecarregar a CPU com mensagens passadas
            for m in messages[-3:]:
                chat_history.append({"role": m["role"], "content": m["content"]})
        else:
            for m in messages:
                chat_history.append({"role": m["role"], "content": m["content"]})

        steps_taken = 0

        while steps_taken < max_steps:
            steps_taken += 1
            payload: Dict[str, Any] = {
                "model": target_model,
                "messages": chat_history,
                "stream": False,
                "options": {
                    "temperature": 0.6 if not should_use_tools else 0.2,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                    "num_predict": 120 if not should_use_tools else 250,
                    "num_thread": get_optimal_threads(),
                    "num_ctx": 2048 if not should_use_tools else 4096,
                },
                "keep_alive": "60m",
            }
            if tools_schema:
                payload["tools"] = tools_schema

            try:
                resp = requests.post(f"{target_url}/api/chat", json=payload, timeout=(15, 600))
                resp.raise_for_status()
                data = resp.json()
            except requests.HTTPError as http_err:
                # Blindagem: se o modelo retornar 400 Bad Request por incompatibilidade com tools=[...],
                # remove tools e tenta novamente como texto puro com histórico enxuto
                status_code = getattr(http_err.response, "status_code", None)
                err_text = getattr(http_err.response, "text", "")
                if tools_schema and status_code == 400:
                    LOGGER.warning("Modelo %s retornou 400 com tools (%s). Tentando fallback sem tools.", target_model, err_text[:80])
                    payload.pop("tools", None)
                    payload["options"]["num_ctx"] = 2048
                    try:
                        resp = requests.post(f"{target_url}/api/chat", json=payload, timeout=(15, 600))
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as retry_exc:
                        LOGGER.warning("Fallback padrão sem tools falhou (%s). Tentando fallback com prompt simplificado.", retry_exc)
                        # Segundo fallback: simplifica mensagens para evitar overflow de contexto
                        payload["messages"] = [
                            {"role": "system", "content": CASUAL_SYSTEM_PROMPT},
                            {"role": "user", "content": last_user},
                        ]
                        try:
                            resp = requests.post(f"{target_url}/api/chat", json=payload, timeout=(15, 600))
                            resp.raise_for_status()
                            data = resp.json()
                        except Exception as final_exc:
                            LOGGER.error("Falha final no retry sem tools (%s): %s", target_url, final_exc)
                            return {
                                "success": False,
                                "reply": f"Erro de comunicação com o modelo ({target_model}): {str(final_exc)}",
                                "tools_executed": executed_tools_log,
                            }
                else:
                    LOGGER.error("Falha ao comunicar com Ollama (%s): %s", target_url, http_err)
                    return {
                        "success": False,
                        "reply": f"Erro de comunicação com o modelo ({target_model}): {str(http_err)}",
                        "tools_executed": executed_tools_log,
                    }
            except Exception as exc:
                LOGGER.error("Falha ao comunicar com Ollama (%s): %s", target_url, exc)
                return {
                    "success": False,
                    "reply": f"Erro de comunicação com o modelo ({target_model}): {str(exc)}",
                    "tools_executed": executed_tools_log,
                }

            msg = data.get("message", {})
            content = msg.get("content", "")
            thinking = msg.get("thinking", "")
            tool_calls = msg.get("tool_calls", [])

            # Adiciona resposta do assistente ao histórico
            chat_history.append(msg)

            if not tool_calls:
                reply_text = content.strip()
                if not reply_text and thinking:
                    # Se content for vazio mas thinking possuir texto útil, aproveita a conclusão
                    clean_think = re.sub(r"<think>.*?</think>", "", thinking, flags=re.DOTALL).strip()
                    if clean_think:
                        reply_text = clean_think
                if not reply_text:
                    LOGGER.warning("Modelo %s retornou resposta vazia. Aplicando fallback casual.", target_model)
                    reply_text = "E aí Isaac! Tô na escuta, mano. O que tá pegando hoje?"
                return {
                    "success": True,
                    "reply": reply_text,
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

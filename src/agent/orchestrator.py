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
Você é direto, técnico, proativo e inteligente.
Você tem acesso a ferramentas reais no computador: leitura e escrita de arquivos, listagem de pastas,
execução de comandos no terminal, pesquisa web (web_search, web_read) e criação de ferramentas (create_new_tool).

Diretrizes:
- Para criar, inspecionar, consertar ou testar código, use as ferramentas reais (fs_read, fs_write, terminal_run).
- Para pesquisar assuntos na internet, documentações ou atualizações, use web_search e web_read.
- Se você identificar que uma ferramenta necessária ainda não existe no arsenal, crie-a com create_new_tool,
  testando seu funcionamento no terminal antes de concluir.
- Ao discutir uma ideia de projeto, estruture um plano de engenharia acionável com save_plan.
- Quando executar testes ou comandos com terminal_run, analise a saída real e explique o resultado com clareza.
- Responda em português brasileiro fluente, sem rodeios ou formalidades vazias.
"""


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
        """Coleta memórias estáveis e preferências do usuário do cérebro SQLite."""
        try:
            self.store.initialize()
            notes = self.store.list_notes()
            preferences = []
            for n in notes:
                if n.startswith("preferencias/") or n.startswith("conhecimentos/"):
                    content = self.store.read_note(n)
                    if content:
                        preferences.append(f"[{n}]: {content.strip()}")
            if preferences:
                return "\nMemória permanente do usuário:\n" + "\n".join(preferences[:10])
        except Exception as exc:
            LOGGER.warning("Não foi possível carregar memória permanente: %s", exc)
        return ""

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

        chat_history = [{"role": "system", "content": full_system}]
        for m in messages:
            chat_history.append({"role": m["role"], "content": m["content"]})

        tools_schema = CORE_TOOLS_SCHEMA if enable_tools else None
        steps_taken = 0
        executed_tools_log = []

        while steps_taken < max_steps:
            steps_taken += 1
            payload: Dict[str, Any] = {
                "model": target_model,
                "messages": chat_history,
                "stream": False,
                "options": {"temperature": 0.3},
            }
            if tools_schema:
                payload["tools"] = tools_schema

            try:
                resp = requests.post(f"{target_url}/api/chat", json=payload, timeout=(5, 120))
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

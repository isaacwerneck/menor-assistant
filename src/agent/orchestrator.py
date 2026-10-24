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
from src.agent.cleaner import sanitize_assistant_reply

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é o Menor v2, parceiro de tecnologia e arquiteto de software de alto nível do Isaac.
Você é direto, técnico, proativo, inteligente e parceiro de engenharia.
Você tem acesso a ferramentas reais no computador: leitura e escrita de arquivos (fs_read, fs_write, fs_patch),
listagem de pastas (fs_list), execução de comandos no terminal (terminal_run), pesquisa web (web_search, web_read),
criação de ferramentas (create_new_tool), agendamento de estudos (schedule_study_topic),
consulta de relatórios (get_study_report) e atualização de memória de trabalho (update_core_memory).

Regras Inegociáveis e Diretrizes de Execução:
- Se o usuário pedir para criar, fazer, programar, desenvolver ou salvar um site, página ou arquivo:
  Chame OBRIGATORIAMENTE a ferramenta `fs_write` com 'filepath' (ex: 'index.html') e 'content'.
  NUNCA use web_read nem web_search para pedidos de criar ou programar sites/arquivos locais.
  Execute `fs_write` imediatamente no primeiro turno.
- NUNCA simule saídas de terminal, prompts de shell (ex: ```terminal $ ls ...```, ```bash```) ou finja leituras de
  arquivos em blocos de texto ou markdown. Se precisar executar comandos ou ler/escrever arquivos, use
  OBRIGATORIAMENTE ferramentas reais via native tool calling. Se não houver ferramenta a chamar, responda
  diretamente sem inventar arquivos ou saídas fictícias.
- NUNCA diga que é apenas um modelo ou assistente de texto, que não pode criar arquivos ou que não tem ferramentas.
  Você é o Menor v2 com ferramentas reais ativas no Hub e capacidade de criar arquivos e sites diretamente.
- NUNCA finja que criou ou implementou algo se a ferramenta `fs_write` não foi executada no turno.
- Se o usuário perguntar o que foi conversado ou pedido anteriormente, consulte com rigor as mensagens do histórico
  e responda diretamente, sem dizer que não tem memória.
- NUNCA invente pastas ou caminhos inexistentes (como ~/estudos/ ou /ancora_de_estudos/).
- Sua Âncora de Estudos oficial está no bloco [STUDY_ANCHORS] da Core Memory residente logo acima.
- NUNCA faça propaganda não solicitada de ferramentas ou projetos no meio de conversas comuns.
  Responda estritamente ao que foi perguntado.
- NUNCA invente reuniões, compromissos ou presuma a rotina pessoal do Isaac.
- NUNCA use tags <think> ou raciocínio em inglês. Responda diretamente em português brasileiro.
- Responda sempre em português brasileiro fluente, natural e direto, sem rodeios ou formalidades vazias.
"""

CASUAL_SYSTEM_PROMPT = """Você é o Menor v2, assistente pessoal e parceiro de tecnologia do Isaac.
Converse diretamente em português brasileiro, de forma natural, amigável e descontraída
(usando gírias leves como mano, suave, blz).

Diretrizes essenciais:
- Você tem total acesso ao ecossistema de ferramentas do Menor e ao Hub Central.
- NUNCA diga que é apenas um assistente de texto, que não tem memória ou que não pode criar/enviar arquivos.
- Se o usuário perguntar sobre a conversa anterior, consulte o histórico no contexto e responda com clareza.
- Responda sempre diretamente na voz do Menor v2, sem introduções em inglês e sem blocos de raciocínio interno.
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
        from src.agent.study import get_optimal_model
        self.default_model = default_model or os.environ.get("OLLAMA_MODEL") or get_optimal_model(self.ollama_url)
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
                if n.startswith("preferencias/"):
                    content = self.store.read_note(n)
                    if content:
                        preferences.append(f"[{n}]: {content.strip()}")
            if preferences:
                sections.append("Preferências do usuário:\n" + "\n".join(preferences[:3]))
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
                "rode", "rodar", "terminal", "pytest", "git", "salve",
                "faz", "fazer", "faça", "construir", "programar", "desenvolver", "implementar"
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
            "não fique", "nao fique", "prefiro", "favorit", "odeio", "acabei de", "cor ",
            "estude ", "estudar", "aprender", "esses dias", "ataque", "vulnerabilidade", "cve", "notícia",
            "noticia", "relat", "fez enquanto", "estudou", "agendar", "agende", "adicione",
            "faz ", "fazer", "faça", "constru", "program", "desenvolv", "implement", "html", "css", "js",
            "mand", "mostr", "ver", "envi", "cadê", "cade", "onde tá", "onde ta", "preview", "link",
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
                    executed_tools_log.append("get_study_report")
                    if any(w in norm_user for w in ("relat", "resumo", "o que", "oq", "aprendeu", "estudou")):
                        return {
                            "success": True,
                            "reply": (
                                "Aqui está o relatório mais recente de estudo e auto-aprimoramento do Menor:\n\n"
                                + rep["report_markdown"]
                            ),
                            "tools_executed": executed_tools_log,
                            "model_used": target_model,
                            "node_url": target_url,
                        }
                    full_system += f"\n\n[RELATÓRIO ATUALIZADO DE ESTUDOS DO MENOR]:\n{rep['report_markdown']}"
            except Exception as exc:
                LOGGER.debug("Grounding de relatório de estudos ignorado: %s", exc)

        # Inspeção rápida de saúde do código via AST
        inspect_triggers = (
            "inspeção na saúde", "inspecione o código", "gaps de teste",
            "inspecione o repositorio", "inspecione o repositório", "saúde do nosso código"
        )
        if any(t in norm_user for t in inspect_triggers):
            try:
                from src.tools.core import dispatch_inspect_codebase
                insp_res = dispatch_inspect_codebase()
                executed_tools_log.append("inspect_codebase")
                rep_md = insp_res.get("report_markdown")
                if rep_md:
                    return {
                        "success": True,
                        "reply": (
                            "Aqui está o diagnóstico atual da saúde e cobertura de testes do código:\n\n"
                            + rep_md
                        ),
                        "tools_executed": executed_tools_log,
                        "model_used": target_model,
                        "node_url": target_url,
                    }
            except Exception as exc:
                LOGGER.warning("Inspeção rápida de código falhou: %s", exc)

        # Agendamento direto de tópico de estudo
        schedule_triggers = ("agenda um novo tópico", "agenda tópico", "agende um novo tópico", "agendar estudo")
        if any(t in norm_user for t in schedule_triggers):
            try:
                from src.tools.core import schedule_study_topic
                topic_match = re.search(r"['\"](.*?)['\"]", last_user) or re.search(
                    r"(?:estudar|tópico|tema):\s*(.*)", last_user, re.I
                )
                topic_text = topic_match.group(1).strip() if topic_match else last_user
                schedule_study_topic(topic=topic_text)
                executed_tools_log.append("schedule_study_topic")
                return {
                    "success": True,
                    "reply": f"Tópico '{topic_text}' agendado com sucesso para o próximo ciclo de estudos do Menor!",
                    "tools_executed": executed_tools_log,
                    "model_used": target_model,
                    "node_url": target_url,
                }
            except Exception as exc:
                LOGGER.warning("Agendamento de estudo falhou: %s", exc)

        # Salvar preferência na memória permanente
        memory_save_triggers = (
            "salva na sua memória permanente", "salve na sua memória", "guarde na memória", "lembre-se que"
        )
        if any(t in norm_user for t in memory_save_triggers):
            try:
                from src.memory.core_memory import CoreMemoryManager
                pref_match = re.search(r"(?:que|de)\s+(.*)", last_user, re.I)
                pref_text = pref_match.group(1).strip() if pref_match else last_user
                self.store.remember_preference(pref_text)
                CoreMemoryManager(self.store).set_block("user_preferences", pref_text, mode="append")
                executed_tools_log.append("update_core_memory")
                return {
                    "success": True,
                    "reply": f"Entendido, Isaac! Salvei na sua memória permanente e perfil: '{pref_text}'.",
                    "tools_executed": executed_tools_log,
                    "model_used": target_model,
                    "node_url": target_url,
                }
            except Exception as exc:
                LOGGER.warning("Salvamento de memória falhou: %s", exc)

        # Consulta de preferências salvas
        pref_recall_triggers = (
            "cor favorita", "minha cor", "o que eu odeio", "o que odeio",
            "minha preferência", "minhas preferências", "o que eu prefiro"
        )
        if any(t in norm_user for t in pref_recall_triggers):
            try:
                from src.memory.core_memory import CoreMemoryManager
                prefs = CoreMemoryManager(self.store).get_block("user_preferences")
                if prefs and len(prefs.strip()) > 3:
                    return {
                        "success": True,
                        "reply": f"Lembro perfeitamente, Isaac! Você me disse que {prefs.strip()}.",
                        "tools_executed": executed_tools_log,
                        "model_used": target_model,
                        "node_url": target_url,
                    }
            except Exception as exc:
                LOGGER.debug("Consulta de preferências ignorada: %s", exc)

        # Identidade do Isaac
        if any(t in norm_user for t in ("quem eu sou", "minha função", "meu perfil", "lembra quem eu sou")):
            try:
                from src.memory.core_memory import CoreMemoryManager
                profile = CoreMemoryManager(self.store).get_block("user_profile")
                if profile and len(profile.strip()) > 10:
                    return {
                        "success": True,
                        "reply": f"Com certeza, mano! Você é o Isaac Werneck:\n\n{profile.strip()}",
                        "tools_executed": executed_tools_log,
                        "model_used": target_model,
                        "node_url": target_url,
                    }
            except Exception as exc:
                LOGGER.debug("Consulta de perfil ignorada: %s", exc)

        # Setup de Hardware
        hardware_triggers = (
            "configuração de máquinas", "setup atual", "quais máquinas", "nossas gpus", "setup de hardware"
        )
        if any(t in norm_user for t in hardware_triggers):
            try:
                from src.memory.core_memory import CoreMemoryManager
                env_block = CoreMemoryManager(self.store).get_block("environment")
                if env_block:
                    return {
                        "success": True,
                        "reply": f"Aqui está o nosso setup atual de infraestrutura e hardware:\n\n{env_block.strip()}",
                        "tools_executed": executed_tools_log,
                        "model_used": target_model,
                        "node_url": target_url,
                    }
            except Exception as exc:
                LOGGER.debug("Consulta de hardware ignorada: %s", exc)

        # Visualização e leitura direta de sites criados
        site_preview_triggers = (
            "mostrar o site", "mostra o site", "mostrar site", "ver o site", "ver site",
            "onde está o site", "onde ta o site", "onde tá o site", "cade o site", "cadê o site",
            "site que você fez", "site que vc fez", "site que você criou", "site que vc criou",
            "qual endereço", "qual o endereço", "qual endereco", "mandar o arquivo", "manda o arquivo",
            "manda o arquivo dele", "mandar o arquivo dele", "mostrar ele aqui", "mostra ele aqui",
            "me mostrar o site", "me mostra o site",
        )
        if any(t in norm_user for t in site_preview_triggers):
            try:
                from src.tools.core import fs_read
                candidate_files = ["site_menor.html", "index.html", "index_dual_brain.html"]
                found_file = None
                content_preview = ""
                for cf in candidate_files:
                    read_try = fs_read(cf)
                    if read_try.get("success") and read_try.get("content"):
                        found_file = cf
                        content_preview = read_try.get("content", "")
                        executed_tools_log.append("fs_read")
                        break

                if found_file:
                    preview_url = f"http://192.168.0.10:8000/preview/{found_file}"
                    code_snippet = content_preview[:1200]
                    return {
                        "success": True,
                        "reply": (
                            f"Consigo sim, mano! O site está pronto e salvo no arquivo `{found_file}`.\n\n"
                            f"**Link direto para abrir e ver no navegador:**\n"
                            f"[{preview_url}]({preview_url})\n\n"
                            f"**Código do arquivo `{found_file}`:**\n"
                            f"```html\n{code_snippet}\n```"
                        ),
                        "tools_executed": executed_tools_log,
                        "model_used": target_model,
                        "node_url": target_url,
                    }
                else:
                    return {
                        "success": True,
                        "reply": (
                            "O arquivo do site ainda não foi gerado no workspace. "
                            "Me fala o tema que você quer (ex: 'cria um site simples em index.html') "
                            "que eu crio com a ferramenta real fs_write agora mesmo!"
                        ),
                        "tools_executed": executed_tools_log,
                        "model_used": target_model,
                        "node_url": target_url,
                    }
            except Exception as exc:
                LOGGER.warning("Visualização de site falhou: %s", exc)

        # Listagem de arquivos salvos
        fs_list_triggers = (
            "onde você salvou", "onde vc salvou", "lista os arquivos", "listar arquivos", "listar os arquivos"
        )
        if any(t in norm_user for t in fs_list_triggers):
            try:
                from src.tools.core import fs_list
                files_found = fs_list(".")
                executed_tools_log.append("fs_list")
                file_summary = "\n".join(f"- {f.get('name')} ({f.get('type')})" for f in files_found[:20])
                return {
                    "success": True,
                    "reply": f"Aqui estão os arquivos presentes no diretório do projeto:\n\n{file_summary}",
                    "tools_executed": executed_tools_log,
                    "model_used": target_model,
                    "node_url": target_url,
                }
            except Exception as exc:
                LOGGER.debug("fs_list ignorado: %s", exc)

        coding_keywords = (
            "código", "codigo", "script", "bug", "patch", "consert", "refator", "função", "classe", "test"
        )
        if any(k in norm_user for k in coding_keywords):
            try:
                from src.agent.ponytail import get_ponytail_system_prompt
                full_system += f"\n\n{get_ponytail_system_prompt()}"
            except Exception:
                pass

        system_content = full_system
        non_system = []
        for m in messages:
            if m.get("role") == "system":
                system_content += f"\n\n{m.get('content', '')}"
            else:
                non_system.append(m)

        chat_history = [{"role": "system", "content": system_content}]
        if not should_use_tools:
            # Em modo casual, limita aos últimos 3 turnos para não sobrecarregar a CPU com mensagens passadas
            for m in non_system[-3:]:
                chat_history.append({"role": m["role"], "content": m["content"]})
        else:
            for m in non_system:
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
                    "num_predict": 1024,
                    "num_thread": get_optimal_threads(),
                    "num_ctx": 4096,
                    "stop": ["\nThinking Process:", "Thinking Process:", "Okay, let's", "Let's tackle"],
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
                status_code = getattr(http_err.response, "status_code", None)
                err_text = getattr(http_err.response, "text", "")
                if status_code == 404:
                    from src.agent.study import get_optimal_model
                    discovered = get_optimal_model(target_url)
                    if discovered and discovered != target_model:
                        LOGGER.warning(
                            "Modelo %s não encontrado em %s (404). Tentando fallback para modelo disponível %s.",
                            target_model,
                            target_url,
                            discovered,
                        )
                        target_model = discovered
                        payload["model"] = target_model
                        try:
                            resp = requests.post(f"{target_url}/api/chat", json=payload, timeout=(15, 600))
                            resp.raise_for_status()
                            data = resp.json()
                        except Exception as fallback_exc:
                            LOGGER.error("Fallback para %s falhou: %s", target_model, fallback_exc)
                            return {
                                "success": False,
                                "reply": f"Erro de comunicação com o modelo ({target_model}): {str(fallback_exc)}",
                                "tools_executed": executed_tools_log,
                            }
                elif status_code in (400, 500):
                    LOGGER.warning(
                        "Modelo %s retornou %s (%s). Tentando fallback sem tools e com num_ctx 2048.",
                        target_model,
                        status_code,
                        err_text[:80],
                    )
                    payload.pop("tools", None)
                    payload["options"]["num_ctx"] = 2048
                    try:
                        resp = requests.post(f"{target_url}/api/chat", json=payload, timeout=(15, 600))
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as retry_exc:
                        LOGGER.warning(
                            "Fallback padrão sem tools falhou (%s). Tentando fallback com prompt simplificado.",
                            retry_exc,
                        )
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
                reply_text = sanitize_assistant_reply(reply_text, last_user)

                # Auto-escrita de arquivos solicitados explicitamente se o modelo gerou código/markdown
                if any(w in norm_user for w in ("crie", "cria", "salve", "salva", "escreva", "escreve")):
                    requested_files = re.findall(r"\b([a-zA-Z0-9_\-]+\.(?:html|css|js|py|md|json|txt))\b", last_user)
                    code_blocks = re.findall(r"```[a-zA-Z0-9]*\n([\s\S]*?)```", reply_text)
                    if requested_files and code_blocks:
                        for idx, rfile in enumerate(requested_files):
                            if idx < len(code_blocks):
                                try:
                                    from src.tools.core import fs_write
                                    fs_write(filepath=rfile, content=code_blocks[idx].strip())
                                    executed_tools_log.append(f"fs_write:{rfile}")
                                except Exception as write_err:
                                    LOGGER.debug("Auto fs_write falhou para %s: %s", rfile, write_err)

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

        # Retorna a última mensagem do histórico devidamente sanitizada
        last_content = sanitize_assistant_reply(
            chat_history[-1].get("content", "Operação concluída com ferramentas."),
            last_user,
        )
        return {
            "success": True,
            "reply": last_content,
            "tools_executed": executed_tools_log,
            "model_used": target_model,
            "node_url": target_url,
        }

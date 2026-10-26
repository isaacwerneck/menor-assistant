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
- Se o usuário pedir para rodar, executar, testar ou checar algo no terminal (ex: comandos git, pytest, bash, npm, ls, status),
  chame OBRIGATORIAMENTE a ferramenta `terminal_run` com o campo 'command'. NUNCA devolva o comando dentro de bloco de código sem executá-lo.
- NUNCA escreva código python simulando chamadas de ferramenta no texto (ex: ```python fs_write(...)```).
  Ferramentas devem ser executadas exclusivamente via native tool calling da API.
- NUNCA diga que é apenas um modelo ou assistente de texto, que não pode criar arquivos ou que não tem ferramentas.
  Você é o Menor v2 com ferramentas reais ativas no Hub e capacidade de criar arquivos e sites diretamente.
- NUNCA finja que criou ou implementou algo se a ferramenta `fs_write` não foi executada no turno.
- Se o usuário perguntar o que foi conversado ou pedido anteriormente, consulte com rigor as mensagens do histórico
  e responda diretamente, sem dizer que não tem memória.
- NUNCA invente pastas ou caminhos fictícios. Os arquivos e sites criados residem no diretório do projeto.
- NUNCA envie comandos de terminal ou ferramentas simuladas como texto (ex: ```bash terminal_run ...```).
  O usuário não deve ver nomes de ferramentas internas nem códigos de shell simulados.
- Seja um parceiro proativo e natural (estilo ChatGPT/Senior Dev): ao falar de projetos, contextualize
  o que estávamos fazendo, onde paramos, o que já foi feito, o que podemos fazer a seguir e se quer continuar.
- Sua Âncora de Estudos oficial está no bloco [STUDY_ANCHORS] da Core Memory residente logo acima.
- NUNCA faça propaganda não solicitada de ferramentas ou projetos no meio de conversas comuns.
  Responda estritamente ao que foi perguntado.
- NUNCA invente reuniões, compromissos ou presuma a rotina pessoal do Isaac.
- Entenda gírias brasileiras comuns de chat:
  * "pf" / "pff" / "pls" / "plz" = "por favor" (NUNCA interprete "pf" como sigla corporativa, "tópicos prioritários", "prato feito" ou "polícia federal").
  * "a gnt" = "a gente" (nós, você e o Isaac juntos; NUNCA interprete como "Grupo Nacional de Tecnologia").
  * "oq" / "o que" = "o que".
  * "vc" / "vcs" = "você" / "vocês".
  * "tb" / "tbm" = "também".
  * "pq" = "por que" ou "porque".
  * "blz" = "beleza".
- NUNCA pense em voz alta em inglês (NUNCA emita "Looking at...", "Given their...", "I need to...", "Okay, the user...", "The user is asking...", "Wait, the user...").
  Inicie a sua resposta IMEDIATAMENTE no texto em português brasileiro voltado ao Isaac.
- O Isaac é desenvolvedor de software e atua construindo: sites modernos, jogos 2D, música/DSP de áudio, aplicativos mobile Android (Kotlin/Compose) e sistemas/backends. Ao sugerir estudos ou debater arquitetura, alinhe-se a essas áreas reais.
- Suas Âncoras de Estudo oficiais estão no bloco [STUDY_ANCHORS] da Core Memory. Se o usuário perguntar quais são, cite as âncoras reais de Core Memory e NUNCA invente tópicos não relacionados (como Kubernetes ou APIs de pagamento).
- Se o Isaac perguntar sobre projetos, softwares ou tarefas que "a gnt" já fez ou está fazendo,
  cite estritamente os projetos e tarefas reais registrados no contexto (Menor v2, sites e arquivos criados).
- NUNCA use tags <think> ou raciocínio em inglês. Responda diretamente em português brasileiro.
- Responda sempre em português brasileiro fluente, natural e direto, sem rodeios ou formalidades vazias.
"""

CASUAL_SYSTEM_PROMPT = """Você é o Menor v2, assistente pessoal e parceiro de tecnologia do Isaac.
Converse diretamente em português brasileiro, de forma natural, amigável e descontraída
(usando gírias leves como mano, suave, blz).

Diretrizes essenciais:
- Você tem total acesso ao ecossistema de ferramentas do Menor e ao Hub Central.
- Compreenda gírias e abreviações brasileiras comuns:
  * "pf" / "pff" / "pls" = "por favor" (NUNCA interprete como sigla corporativa ou tópicos prioritários).
  * "a gnt" = "a gente" (nós, você e o Isaac juntos).
  * "oq" = "o que"; "vc" = "você"; "tb" = "também"; "pq" = "porque".
- NUNCA pense em voz alta em inglês ("Looking at...", "Given their...", "I need to...", "Okay, the user..."). Responda diretamente em português do Brasil.
- Suas Âncoras de Estudo oficiais estão no bloco [STUDY_ANCHORS] da Core Memory.
- O Isaac desenvolve: sites modernos, jogos 2D, música/DSP, aplicativos mobile Android e sistemas de software.
- Se o Isaac perguntar sobre o que "a gnt" já fez, mencione o Menor v2 e as tarefas do Hub.
- NUNCA diga que é apenas um assistente de texto, que não tem memória ou que não pode criar/enviar arquivos.
- Se o usuário perguntar sobre a conversa anterior, consulte o histórico no contexto e responda com clareza.
- Se o usuário fizer uma pergunta direta, técnica ou sobre conceitos e regras, responda à pergunta
  com clareza e precisão em vez de emitir saudações vazias.
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
            parts = []
            try:
                from src.memory.core_memory import CoreMemoryManager
                cm = CoreMemoryManager(self.store)
                user_prof = cm.get_block("user_profile")
                if user_prof:
                    parts.append(f"Perfil do Usuário:\n{user_prof.strip()}")
                study_anch = cm.get_block("study_anchors")
                if study_anch:
                    parts.append(f"Âncoras de Estudo (Core Memory):\n{study_anch.strip()}")
            except Exception:
                pass
            try:
                from src.agent.workers import TaskQueue
                tq = TaskQueue()
                recent_tasks = tq.list_tasks(limit=3)
                if recent_tasks:
                    task_items = [
                        f"- [{t.get('status', '').upper()}] {t.get('goal', '')}"
                        for t in recent_tasks if t.get("goal")
                    ]
                    if task_items:
                        parts.append("Tarefas Recentes (Isaac e Menor):\n" + "\n".join(task_items))
            except Exception:
                pass
            return "\n\n".join(parts)

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

        try:
            from src.agent.workers import TaskQueue
            tq = TaskQueue()
            recent_tasks = tq.list_tasks(limit=4)
            if recent_tasks:
                task_items = [
                    f"- [{t.get('status', '').upper()}] {t.get('goal', '')}"
                    for t in recent_tasks if t.get("goal")
                ]
                if task_items:
                    sections.append("Projetos e Tarefas Recentes (Isaac e Menor):\n" + "\n".join(task_items))
        except Exception as exc:
            LOGGER.debug("Tarefas indisponíveis para contexto: %s", exc)

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
            "software", "log", "plano", "projet", "pesquis", "busc", "web", "site", "url", "http",
            "ferramenta", "tool",
            "código", "codigo", "python", "script", "consert", "bug", "corrig", "cri",
            "patch", "alterar", "substituir", "simbolo", "símbolo", "mapa", "repo_map", "onde fica", "onde está",
            "declaração", "declaracao", "refator",
            "lembr", "memor", "perfil", "preferencia", "não precisa", "nao precisa",
            "não fique", "nao fique", "prefiro", "favorit", "odeio", "acabei de", "cor ",
            "estude ", "estudar", "aprender", "esses dias", "ataque", "vulnerabilidade", "cve", "notícia",
            "noticia", "relat", "fez enquanto", "estudou", "agendar", "agende", "adicione",
            "faz ", "fazer", "faça", "constru", "program", "desenvolv", "implement", "html", "css", "js",
            "mand", "mostr", "ver", "envi", "cadê", "cade", "onde tá", "onde ta", "preview", "link",
            "design", "regra", "regras", "arquitetur", "android", "kotlin", "compose", "room", "audio",
            "áudio", "synth", "músic", "music", "ancora", "âncora", "topico", "tópico", "estudo", "estudad",
            "os que tem", "quais tem", "o que tem", "sugira", "sugerir", "jogos", "mobile",
            "qual", "quais", "o que", "oq ", "expliq", "descrev",
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

        # Grounding de Relatório de Estudos e Atividades Recentes
        norm_user = last_user.lower()
        study_report_triggers = (
            "estudou", "o que você estudou", "o que vc estudou", "oq vc estudou",
            "oq estudou", "o que estudou", "relatório de estudo", "relatorio de estudo",
            "último estudo", "ultimo estudo", "briefing de estudo", "o que aprendeu",
            "oq aprendeu", "fez enquanto", "estudou essa noite", "estudou hoje",
            "aprendeu", "o que você aprendeu", "o que vc aprendeu", "oq vc aprendeu",
            "ultimos tempos", "últimos tempos", "novidades de estudo",
            "relatorio geral", "relatório geral", "tudo que vc fez", "tudo o que fez",
            "o que você fez", "oq vc fez", "se modificou", "modificações", "modificacoes",
        )
        if any(t in norm_user for t in study_report_triggers):
            try:
                from src.tools.core import get_study_report
                rep = get_study_report(self.store)
                recent_commits = ""
                try:
                    import subprocess
                    g_res = subprocess.run(
                        ["git", "log", "-n", "5", "--pretty=format:%h - %s (%cr)"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    if g_res.returncode == 0 and g_res.stdout.strip():
                        recent_commits = g_res.stdout.strip()
                except Exception:
                    pass

                if rep.get("has_report") and rep.get("report_markdown"):
                    executed_tools_log.append("get_study_report")
                    raw_report_triggers = (
                        "ver ultimo relatorio", "ver último relatório",
                        "cat ultimo_estudo.md", "relatorio cru"
                    )
                    if norm_user.strip() in raw_report_triggers:
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
                    full_system += (
                        f"\n\n[CONTEXTO ATUALIZADO DE ATIVIDADES, ESTUDOS E MODIFICAÇÕES DO MENOR]:\n"
                        f"1. Relatório Consolidado de Auto-Evolução e Estudos:\n{rep['report_markdown']}\n\n"
                        f"2. Commits e Modificações Recentes no Código do Menor (Git):\n"
                        f"{recent_commits or 'Nenhum commit recente detectado.'}\n\n"
                        "DIRETRIZ DE RESPOSTA:\n"
                        "- O usuário está perguntando o que você aprendeu, fez ou modificou recentemente.\n"
                        "- Responda de forma natural, executiva, calorosa e conversacional em português.\n"
                        "- NUNCA repita o relatório cru em markdown verbatim se o usuário já tiver recebido.\n"
                        "- Destaque os tópicos estudados e as melhorias e commits recentes no código do Menor."
                    )
            except Exception as exc:
                LOGGER.debug("Grounding de relatório de estudos ignorado: %s", exc)

        # Grounding de Âncoras e Tópicos de Estudo
        study_anchor_triggers = (
            "ancora", "âncora", "ancoras", "âncoras",
            "tópicos de estudo", "topicos de estudo", "tópico de estudo", "topico de estudo",
            "tópicos estudados", "topicos estudados", "mudar esses topicos", "mudar tópicos",
            "mudar os tópicos", "mudar os topicos", "redefinir tópicos", "redefinir topicos",
            "quais os que tem", "quais que tem", "os que tem", "o que tem na fila",
            "sugira topicos", "sugira tópicos", "sugerir tópicos", "sugira estudos",
        )
        if any(t in norm_user for t in study_anchor_triggers):
            try:
                from src.memory.core_memory import CoreMemoryManager
                from src.agent.study import TopicManager
                cm = CoreMemoryManager(self.store)
                anchors = cm.get_block("study_anchors") or ""
                tm = TopicManager(self.store)
                upcoming = tm.list_topics(uncompleted_only=True)
                upcoming_str = "\n".join(f"- {t['text']}" for t in upcoming[:5]) if upcoming else "Nenhum tópico avulso pendente."
                full_system += (
                    f"\n\n[DADOS REAIS DAS ÂNCORAS E FILA DE ESTUDO DO MENOR]:\n"
                    f"Âncoras Oficiais de Estudo (Core Memory):\n{anchors}\n\n"
                    f"Tópicos na Fila de Estudo Ativa:\n{upcoming_str}\n\n"
                    f"Perfil Real do Isaac:\n"
                    f"Desenvolvedor de software que cria: sites modernos, jogos 2D, música/DSP/áudio, aplicativos mobile Android (Kotlin/Compose) e sistemas/backends.\n\n"
                    f"DIRETRIZES OBRIGATÓRIAS:\n"
                    f"1. 'pf' significa 'por favor' (NUNCA interprete 'pf' como tópicos prioritários ou siglas).\n"
                    f"2. Se o Isaac perguntar quais são os tópicos ou âncoras existentes, liste estritamente as Âncoras Oficiais reais acima.\n"
                    f"3. Se o Isaac perguntar se podemos mudar, confirme imediatamente que sim (via Core Memory) e pergunte quais tópicos ele quer focar.\n"
                    f"4. Se o Isaac pedir sugestões alinhadas ao perfil dele (sites, jogos 2D, música, apps, sistemas), sugira tópicos de engenharia profundos dessas 5 áreas reais.\n"
                    f"5. NUNCA pense em voz alta em inglês ('Looking at...', 'Given their...', 'I need to...'). Responda diretamente em português."
                )
            except Exception as exc:
                LOGGER.debug("Grounding de âncoras de estudo ignorado: %s", exc)

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
            "configuração de máquinas", "setup atual", "quais máquinas", "nossas gpus",
            "setup de hardware", "nossas maquinas", "configuracao de maquinas", "nosso hardware",
            "configuração de hardware", "setup de máquinas", "setup de maquinas", "nossa máquina",
            "nossas máquinas", "nossas maquinas", "configuração de máquinas e hardware"
        )
        if any(t in norm_user for t in hardware_triggers):
            try:
                from src.memory.core_memory import CoreMemoryManager
                cm = CoreMemoryManager(self.store)
                env_block = cm.get_block("environment")
                if not env_block:
                    prof = cm.get_block("user_profile") or ""
                    for line in prof.split("\n"):
                        if "Hardware:" in line:
                            env_block = line.strip()
                            break
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

        # Visualização e contextualização humana estilo ChatGPT de sites e projetos
        site_preview_triggers = (
            "mostrar o site", "mostra o site", "mostrar site", "ver o site", "ver site",
            "onde está o site", "onde ta o site", "onde tá o site", "cade o site", "cadê o site",
            "site que você fez", "site que vc fez", "site que você criou", "site que vc criou",
            "qual endereço", "qual o endereço", "qual endereco", "mandar o arquivo", "manda o arquivo",
            "manda o arquivo dele", "mandar o arquivo dele", "mostrar ele aqui", "mostra ele aqui",
            "me mostrar o site", "me mostra o site", "site do rebello", "site do rebelo",
            "aquele site", "me mostra ele", "mostra ele", "ver ele", "ver o projeto", "mostra o projeto",
            "projeto do rebello", "projeto do rebelo", "o que podemos mudar",
        )
        is_preview_request = (
            any(t in norm_user for t in site_preview_triggers)
            or (
                any(w in norm_user for w in ("mostr", "ver", "cade", "cadê", "onde tá", "onde ta", "abre", "abrir"))
                and any(w in norm_user for w in ("site", "página", "pagina", "html", "ele", "rebello", "rebelo"))
            )
        )
        if is_preview_request:
            try:
                from src.tools.core import fs_read
                candidate_files = ["index.html", "site_menor.html", "index_dual_brain.html"]
                found_file = None
                content_preview = ""
                for cf in candidate_files:
                    read_try = fs_read(cf)
                    if read_try.get("success") and read_try.get("content"):
                        found_file = cf
                        content_preview = read_try.get("content", "")
                        executed_tools_log.append(f"fs_read:{found_file}")
                        break

                if found_file:
                    code_snippet = content_preview[:1200]
                    is_rebello = (
                        "rebello" in norm_user
                        or "rebelo" in norm_user
                        or "rebello" in content_preview.lower()
                    )
                    if is_rebello:
                        reply_msg = (
                            "Fala Isaac! Tá na mão o site do Rebello que estávamos desenvolvendo juntos.\n\n"
                            f"Nós criamos a estrutura inicial da página no arquivo `{found_file}` com o fundo azul "
                            "e a mensagem de parabéns em destaque.\n\n"
                            "**O que já fizemos:**\n"
                            f"- Estruturamos a página HTML inicial (`{found_file}`).\n"
                            "- Configuramos a cor de fundo azul e centralizamos o texto de parabéns.\n\n"
                            "**O que podemos fazer agora:**\n"
                            "- Adicionar uma foto ou avatar comemorativo do Rebello.\n"
                            "- Inserir efeitos visuais com confetes ou animações em CSS/JavaScript.\n"
                            "- Adicionar botões interativos ou um mural de recados comemorativo.\n\n"
                            "Dá uma olhada no preview e no código logo abaixo. Quer continuar mexendo nele agora? "
                            "Me fala o que você quer mudar primeiro!\n\n"
                            f"```html\n{code_snippet}\n```"
                        )
                    else:
                        title_match = re.search(r"<title>(.*?)</title>", content_preview, re.I)
                        page_title = title_match.group(1).strip() if title_match else found_file
                        reply_msg = (
                            f"Fala Isaac! Tá aqui o projeto que estávamos desenvolvendo (`{found_file}`).\n\n"
                            f"A gente estruturou a base inicial focada em '{page_title}'.\n\n"
                            "**O que já fizemos:**\n"
                            f"- Criamos o arquivo `{found_file}` e definimos a estrutura HTML principal.\n"
                            "- Aplicamos a estilização básica de layout.\n\n"
                            "**O que podemos fazer agora:**\n"
                            "- Adicionar novas seções e conteúdos específicos.\n"
                            "- Aprimorar o design visual com componentes modernos e responsivos.\n"
                            "- Implementar interatividade ou conectar funcionalidades adicionais.\n\n"
                            "Dá uma conferida no preview e no código abaixo. Quer continuar avançando nele agora? "
                            "Me diz o que você gostaria de mudar primeiro!\n\n"
                            f"```html\n{code_snippet}\n```"
                        )
                    return {
                        "success": True,
                        "reply": reply_msg,
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
                        except requests.HTTPError as retry_http_err:
                            # Se o modelo descoberto rejeitar tools com 400, tenta sem tools
                            if getattr(retry_http_err.response, "status_code", None) in (400, 500):
                                payload.pop("tools", None)
                                payload["options"]["num_ctx"] = 2048
                                try:
                                    resp = requests.post(f"{target_url}/api/chat", json=payload, timeout=(15, 600))
                                    resp.raise_for_status()
                                    data = resp.json()
                                except Exception as sec_exc:
                                    return {
                                        "success": False,
                                        "reply": (
                                            f"Erro de comunicação com o modelo ({target_model}): {sec_exc}"
                                        ),
                                        "tools_executed": executed_tools_log,
                                    }
                            else:
                                return {
                                    "success": False,
                                    "reply": (
                                        f"Erro de comunicação com o modelo ({target_model}): {retry_http_err}"
                                    ),
                                    "tools_executed": executed_tools_log,
                                }
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

                # 1. Intercepta e executa simulações em texto de fs_write(filepath=..., content=...)
                sim_pattern = (
                    r"fs_write\(\s*(?:filepath\s*=\s*)?['\"](?P<file>[^'\"]+)['\"]\s*,\s*"
                    r"(?:content\s*=\s*)?(?P<quote>['\"])(?P<content>[\s\S]*?)(?P=quote)\s*\)"
                )
                sim_match = re.search(sim_pattern, reply_text)
                if sim_match:
                    target_file = sim_match.group("file")
                    raw_content = sim_match.group("content")
                    try:
                        raw_content = raw_content.encode("utf-8").decode("unicode_escape")
                    except Exception:
                        pass
                    try:
                        from src.tools.core import fs_write
                        fs_write(filepath=target_file, content=raw_content)
                        executed_tools_log.append(f"fs_write:{target_file}")
                    except Exception as sim_err:
                        LOGGER.warning("Execução de fs_write simulado falhou: %s", sim_err)

                    lang = "html" if target_file.endswith((".html", ".htm")) else "python"
                    clean_block = f"```{lang}\n{raw_content}\n```"
                    reply_text = re.sub(
                        r"```(?:python)?\s*\n\s*fs_write\([\s\S]*?\)\s*\n```",
                        clean_block,
                        reply_text,
                    )

                # 2. Auto-escrita de arquivos solicitados se o modelo gerou código/markdown
                creation_triggers = (
                    "crie", "cria", "salve", "salva", "escreva", "escreve",
                    "fazer", "faz", "vamos fazer", "programar", "construir", "desenvolver", "site"
                )
                if any(w in norm_user for w in creation_triggers):
                    requested_files = re.findall(
                        r"\b([a-zA-Z0-9_\-]+\.(?:html|css|js|py|md|json|txt))\b", last_user
                    )
                    if not requested_files and any(
                        w in norm_user for w in ("site", "landing page", "página", "pagina")
                    ):
                        requested_files = ["index.html"]

                    code_blocks = re.findall(r"```(?:[a-zA-Z0-9_\-]+)?\s*?(?:\r?\n)([\s\S]*?)(?:\r?\n)```", reply_text)
                    if not code_blocks:
                        dt_match = re.search(r"(<!DOCTYPE html[\s\S]*?</html>)", reply_text, re.IGNORECASE)
                        if dt_match:
                            code_blocks = [dt_match.group(1)]
                    if not code_blocks:
                        content_match = re.search(r"conte[uú]do\s*['\"]([^'\"]+)['\"]", last_user, re.IGNORECASE)
                        if content_match:
                            code_blocks = [content_match.group(1)]

                    if requested_files and code_blocks:
                        for idx, rfile in enumerate(requested_files):
                            if idx < len(code_blocks):
                                if not any(
                                    isinstance(t, str) and t.startswith(f"fs_write:{rfile}")
                                    for t in executed_tools_log
                                ):
                                    try:
                                        from src.tools.core import fs_write
                                        fs_write(filepath=rfile, content=code_blocks[idx].strip())
                                        executed_tools_log.append(f"fs_write:{rfile}")
                                        if not any(rfile in reply_text for _ in [1]):
                                            reply_text += f"\n\nArquivo `{rfile}` criado com sucesso."
                                    except Exception as write_err:
                                        LOGGER.debug("Auto fs_write falhou para %s: %s", rfile, write_err)

                # 3. Interceptação e auto-execução de comandos no terminal
                term_triggers = (
                    "rode", "roda", "execute", "executa", "rodar", "executar", "comando",
                    "terminal", "bash", "shell", "git status", "git log", "git diff"
                )
                if any(w in norm_user for w in term_triggers):
                    cmd_to_run = None
                    t_match = re.search(
                        r"terminal_run\(\s*(?:command\s*=\s*)?['\"](?P<cmd>[^'\"]+)['\"]\s*\)",
                        reply_text,
                    )
                    if t_match:
                        cmd_to_run = t_match.group("cmd")
                    else:
                        bash_blocks = re.findall(r"```(?:bash|sh|terminal|shell)?\s*?(?:\r?\n)([\s\S]*?)(?:\r?\n)```", reply_text)
                        if bash_blocks:
                            cand = bash_blocks[0].strip()
                            if not cand.startswith(("import ", "def ", "class ", "from ")):
                                cmd_to_run = cand
                        elif "git " in last_user:
                            git_cmd = re.search(r"(git\s+[a-zA-Z0-9_\-\s\.]+)", last_user)
                            if git_cmd:
                                cmd_to_run = git_cmd.group(1).strip()

                    if cmd_to_run and not any(isinstance(t, str) and t.startswith("terminal_run:") for t in executed_tools_log):
                        try:
                            from src.tools.core import terminal_run
                            res_term = terminal_run(command=cmd_to_run)
                            executed_tools_log.append(f"terminal_run:{cmd_to_run}")
                            out = res_term.get("stdout", "").strip() or res_term.get("stderr", "").strip() or "Comando executado com sucesso (sem saída)."
                            reply_text = f"Executei o comando no terminal:\n\n```bash\n$ {cmd_to_run}\n{out}\n```"
                        except Exception as term_err:
                            LOGGER.warning("Auto terminal_run falhou para %s: %s", cmd_to_run, term_err)

                # 4. Interceptação e auto-leitura de arquivos (fs_read)
                read_triggers = (
                    "leia o arquivo", "ler o arquivo", "le o arquivo", "lê o arquivo",
                    "leia ", "ler ", "le ", "lê ", "conteúdo de", "conteudo de",
                    "conteúdo do arquivo", "conteudo do arquivo", "cat ", "mostre o arquivo", "mostra o arquivo",
                    "ver o arquivo", "abre o arquivo", "abrir o arquivo"
                )
                if any(w in norm_user for w in read_triggers):
                    r_files = re.findall(r"\b([a-zA-Z0-9_\-/\\]+\.(?:html|css|js|py|md|json|txt|sh|yml|yaml))\b", last_user)
                    for rf in r_files:
                        if not any(isinstance(t, str) and t.startswith(f"fs_read:{rf}") for t in executed_tools_log):
                            try:
                                from src.tools.core import fs_read
                                res_read = fs_read(filepath=rf)
                                if res_read.get("success"):
                                    executed_tools_log.append(f"fs_read:{rf}")
                                    reply_text = f"Aqui está o conteúdo de `{rf}`:\n\n```\n{res_read.get('content', '')}\n```"
                                    break
                            except Exception as read_err:
                                LOGGER.debug("Auto fs_read falhou para %s: %s", rf, read_err)

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

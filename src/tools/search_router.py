"""Roteador inteligente de busca e grounding factual em tempo real (CRAG + Perplexity Pattern).

Classifica intenções temporais e externas, reformula perguntas coloquiais em queries de busca densas,
extrai passagens relevantes (sub-document chunking) e gera contexto com citações verificáveis.
"""

from datetime import datetime, timezone
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

from src.agent.context_engine import select_passages
from src.memory.core_memory import CoreMemoryManager
from src.memory.store import BrainStore
from src.tools.web import read, search

LOGGER = logging.getLogger(__name__)

# Marcadores de tempo / recência
TEMPORAL_TRIGGERS = (
    "esses dias", "recente", "recentemente", "ultimas noticias", "últimas notícias",
    "semana passada", "ontem", "hoje", "novo", "nova", "lancamento", "lançamento",
    "atualizacao", "atualização", "saiu", "aconteceu", "noticia", "notícia",
    "noticias", "notícias", "descobriram", "descobriu", "ultimamente", "agora",
)

# Marcadores de incidentes, segurança e eventos externos de software
EXTERNAL_EVENT_TRIGGERS = (
    "ataque", "vulnerabilidade", "cve", "exploit", "brecha", "seguranca", "segurança",
    "bug", "falha", "patch", "ransomware", "incidente", "invasao", "invasão",
    "zero-day", "0-day", "hacker", "hackeado", "versao", "versão", "release",
)

# Gatilhos explícitos de busca web
EXPLICIT_SEARCH_TRIGGERS = (
    "pesquis", "busc", "google", "web", "site", "link", "fontes", "url", "noticia",
)

# Gatilhos de ações locais no sistema
LOCAL_ACTION_TRIGGERS = (
    "arquivo", "file", "ler", "leia", "le ", "lê", "escrev", "salv", "list", "pasta", "dir",
    "terminal", "coman", "bash", "sh", "execut", "rod", "run", "pytest", "test", "npm", "git",
    "plano", "projet", "ferramenta", "tool", "código", "codigo", "consert", "corrig",
    "preferencia", "perfil", "lembr", "memor",
)

# Stopwords coloquiais e gírias a remover na reformulação de queries
COLLOQUIAL_FILLERS = re.compile(
    r"\b(oq|o que|aconteceu|esses dias|que o pessoal tava falando|tava falando|"
    r"ouvi falar|voce sabe|você sabe|me fala|me explica|sla|de um|de uma|no|na|"
    r"em|sobre|com|pessoal|gente|galera|alguem|alguém|cara|mano|como isso aconteceu|"
    r"como descobriram|por que|pq)\b",
    re.IGNORECASE,
)


def _normalize_text(text: str) -> str:
    """Normaliza texto removendo acentos para matching robusto."""
    folded = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in folded if not unicodedata.combining(c))


def classify_intent(message: str) -> str:
    """Classifica a intenção da mensagem em WEB_GROUNDING, LOCAL_ACTION ou CONVERSATION."""
    if not message or not isinstance(message, str):
        return "CONVERSATION"

    norm = _normalize_text(message)

    # 1. Verifica busca web explícita
    if any(trigger in norm for trigger in EXPLICIT_SEARCH_TRIGGERS):
        return "WEB_GROUNDING"

    # 2. Verifica cruzamento de marcador temporal + evento de software (pergunta de notícias)
    has_temporal = any(trigger in norm for trigger in TEMPORAL_TRIGGERS)
    has_event = any(trigger in norm for trigger in EXTERNAL_EVENT_TRIGGERS)
    if has_temporal and has_event:
        return "WEB_GROUNDING"

    # Se contiver CVE ou menção direta de vulnerabilidade/ataque
    if re.search(r"\bcve-\d{4}-\d+\b", norm) or ("ataque" in norm and len(norm.split()) <= 15):
        return "WEB_GROUNDING"

    # 3. Verifica ação local no sistema operacional
    if any(trigger in norm for trigger in LOCAL_ACTION_TRIGGERS):
        return "LOCAL_ACTION"

    return "CONVERSATION"


def reformulate_query(raw_message: str) -> Dict[str, str]:
    """Extrai os termos-chave essenciais e formula queries de alta densidade informativa."""
    cleaned = COLLOQUIAL_FILLERS.sub(" ", raw_message)
    cleaned = re.sub(r"[?!.,;:\"']", " ", cleaned)
    tokens = [t.strip() for t in cleaned.split() if len(t.strip()) >= 2]

    core_topic = " ".join(tokens)
    current_year = str(datetime.now(timezone.utc).year)

    # Se a query não contiver ano nem termos temporais, anexa o ano corrente
    primary = f"{core_topic} {current_year}".strip() if current_year not in core_topic else core_topic
    secondary = f"{core_topic} vulnerability security {current_year}".strip()

    return {
        "raw_topic": core_topic,
        "primary_query": primary[:120],
        "secondary_query": secondary[:120],
    }


class GroundedSearchEngine:
    """Executa o ciclo de Grounding SOTA com busca, chunking, citações e análise de risco."""

    def __init__(self, store: Optional[BrainStore] = None):
        self.store = store if store is not None else BrainStore()
        self.core_memory = CoreMemoryManager(self.store)

    def _assess_environment_risk(self, topic: str) -> str:
        """Compara o tópico com o perfil de hardware e stack da Core Memory."""
        user_profile = self.core_memory.get_block("user_profile") or ""
        norm_topic = _normalize_text(topic)
        norm_profile = _normalize_text(user_profile)

        stack_technologies = ["python", "fastapi", "node", "sqlite", "ollama", "ubuntu", "windows"]
        profile_matches = [tech for tech in stack_technologies if tech in norm_topic and tech in norm_profile]

        if "php" in norm_topic or "apache" in norm_topic or "xampp" in norm_topic:
            return (
                "Análise de Risco no Ambiente: O Menor v2 opera em Python (FastAPI) e Node.js. "
                "Nossos nós não utilizam PHP, Apache ou XAMPP. O ecossistema está seguro e imune a esta falha."
            )
        elif profile_matches:
            return (
                f"Análise de Risco no Ambiente: Atenção. Esta tecnologia ({', '.join(profile_matches).upper()}) "
                "faz parte da nossa stack ativa. Recomenda-se validar versões e aplicar patches."
            )

        return (
            "Análise de Risco no Ambiente: Esta tecnologia não consta como serviço crítico em nossa stack principal."
        )

    def search_and_ground(self, user_message: str, max_results: int = 3) -> Dict[str, Any]:
        """Executa busca limpa, extrai passagens relevantes e monta contexto com citações."""
        queries = reformulate_query(user_message)
        primary_q = queries["primary_query"]
        citations: List[Dict[str, Any]] = []

        raw_results = []
        try:
            res = search(primary_q)
            raw_results = res.get("results", [])
        except Exception as exc:
            LOGGER.warning("Busca primária falhou ('%s'): %s. Tentando secundária.", primary_q, exc)
            try:
                res = search(queries["secondary_query"])
                raw_results = res.get("results", [])
            except Exception as exc2:
                LOGGER.error("Busca secundária também falhou: %s", exc2)

        # Processar top resultados e extrair passagens densas
        for idx, item in enumerate(raw_results[:max_results], start=1):
            url = item.get("url", "")
            title = item.get("title", "")
            snippet = ""

            # Tenta ler a página mais relevante para extrair passagens detalhadas
            if idx == 1 and url:
                try:
                    read_res = read(url, query=queries["raw_topic"])
                    passage = read_res.get("text", "")
                    if passage:
                        snippet = select_passages(passage, queries["raw_topic"], max_chars=400)
                except Exception:
                    pass

            citations.append({
                "index": idx,
                "title": title,
                "url": url,
                "snippet": snippet or title,
            })

        env_assessment = self._assess_environment_risk(user_message)

        # Montar contexto estruturado para injeção no prompt
        context_lines = [
            "=== CONTEXTO DE PESQUISA EM TEMPO REAL (GROUNDED WEB RESEARCH) ===",
            f"Consulta de busca executada: '{primary_q}'",
            "Fontes técnicas recentes encontradas:",
        ]
        for c in citations:
            snippet_clean = c["snippet"].replace("\n", " ")[:350]
            context_lines.append(f"[{c['index']}] {c['title']} ({c['url']})")
            if snippet_clean and snippet_clean != c["title"]:
                context_lines.append(f"    Resumo: {snippet_clean}")

        context_lines.append("\nDiretrizes de Resposta SOTA:")
        context_lines.append("1. Baseie fatos técnicos, datas e nomes de CVEs estritamente nas evidências acima.")
        context_lines.append("2. Cite as referências utilizando o formato [1], [2] ao longo da sua explicação.")
        context_lines.append(
            "3. Se o nome exato da vulnerabilidade não for encontrado nas fontes, informe com transparência."
        )
        context_lines.append(f"4. {env_assessment}")
        context_lines.append("==================================================================")

        return {
            "success": bool(citations),
            "primary_query": primary_q,
            "citations": citations,
            "environment_risk": env_assessment,
            "grounded_context": "\n".join(context_lines),
        }

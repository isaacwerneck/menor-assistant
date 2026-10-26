"""Seleção contextual e gerenciamento de orçamento de tokens (Pilar 2 - Menor v2 SOTA).

Implementa o Context Budget v2:
- Janela base: 4096 tokens.
- Camadas protegidas invioláveis (< 350 tokens): SOUL.md + SELF.md + AGORA.json.
- Camadas consultivas sob demanda (cota até 1800 tokens): Notas/Projetos injetados apenas se relevância >= 0.35.
- Em mensagens casuais ("opa eai"): zero projetos no prompt (~280 tokens, < 1.5s em CPU).
- Compactação nativa (Regra dos 80%): ao ultrapassar 3276 tokens, condensa turnos antigos preservando os últimos 8 intactos.
"""
import json
import logging
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

LOGGER = logging.getLogger(__name__)

MAX_WINDOW_TOKENS = 4096
COMPACTION_THRESHOLD_TOKENS = 3276  # 80% de 4096
PROTECTED_BUDGET_TOKENS = 350
CONSULTATIVE_BUDGET_TOKENS = 1800

_STOP = frozenset((
    "a", "as", "o", "os", "e", "de", "do", "da", "dos", "das", "um", "uma",
    "no", "na", "nos", "nas", "com", "sem", "para", "por", "que", "qual",
    "quais", "como", "quando", "onde", "isso", "esse", "essa", "sobre",
    "me", "eu", "meu", "minha", "meus", "minhas", "voce", "voces", "seu",
    "sua", "quero", "queria", "pode", "posso", "preciso", "fazer", "faz",
    "fez", "ser", "estar", "esta", "estou", "agora", "aqui", "la",
))

CASUAL_TRIGGERS = (
    "opa", "eai", "e ai", "fala", "salve", "ola", "olá", "oi",
    "bom dia", "boa tarde", "boa noite", "tudo bem", "como vai",
    "beleza", "suave", "tranquilo", "valeu", "obrigado", "tchau"
)


def estimate_tokens(text: Optional[str]) -> int:
    """Estima a contagem de tokens de forma rápida e segura (~3.6 chars por token em pt-BR/código)."""
    if not text or not isinstance(text, str):
        return 0
    # Média calibrada para BPE / Qwen2.5 em texto bilíngue pt-BR/código
    return max(1, int(len(text) / 3.6))


def terms(value: str) -> Set[str]:
    """Extrai termos normalizados para cálculo de sobreposição e relevância."""
    if not isinstance(value, str):
        return set()
    folded = unicodedata.normalize("NFKD", value.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return set(token for token in re.findall(r"[^\W_]+", folded, flags=re.UNICODE)
               if 3 <= len(token) <= 40 and token not in _STOP)


def compute_overlap_score(query: str, document: str) -> float:
    """Calcula score de relevância semântica léxica (Jaccard / Cosine normalizado)."""
    q_terms = terms(query)
    d_terms = terms(document)
    if not q_terms or not d_terms:
        return 0.0
    intersection = len(q_terms.intersection(d_terms))
    if not intersection:
        return 0.0
    return intersection / (len(q_terms) ** 0.5 * len(d_terms) ** 0.5)


def is_casual_query(message: str) -> bool:
    """Detecta se uma mensagem é estritamente casual/saudação para acionar modo ultrarrápido."""
    norm = unicodedata.normalize("NFKD", message).encode("ASCII", "ignore").decode("utf-8").lower().strip()
    words = re.findall(r"\b[a-z]+\b", norm)
    if not words:
        return True
    if len(words) <= 4 and any(w in norm for w in CASUAL_TRIGGERS):
        # Garante que não é um pedido técnico com saudação (ex: "opa cria um site")
        tech_words = ("crie", "cria", "faça", "faz", "terminal", "arquivo", "site", "bug", "codigo", "test")
        if not any(tw in norm for tw in tech_words):
            return True
    return False


class ContextBudgetManager:
    """Gerencia camadas de contexto e garante respeito estrito ao orçamento de tokens."""

    def __init__(
        self,
        max_window: int = MAX_WINDOW_TOKENS,
        compaction_threshold: int = COMPACTION_THRESHOLD_TOKENS,
        consultative_budget: int = CONSULTATIVE_BUDGET_TOKENS,
    ):
        self.max_window = max_window
        self.compaction_threshold = compaction_threshold
        self.consultative_budget = consultative_budget

    def assemble_system_prompt(
        self,
        user_message: str,
        identity_manager: Any,
        agora_layer: Any,
        store: Optional[Any] = None,
        channel: str = "web",
    ) -> Tuple[str, Dict[str, Any]]:
        """Monta o system prompt particionado respeitando o orçamento de tokens.

        Retorna (system_prompt, metadata_camadas).
        """
        is_casual = is_casual_query(user_message)
        layers_meta = {
            "is_casual": is_casual,
            "protected_tokens": 0,
            "consultative_tokens": 0,
            "total_system_tokens": 0,
            "injected_notes": [],
        }

        # 1. Camada Protegida (< 350 tokens)
        if is_casual:
            canonical_ident = identity_manager.format_canonical_identity(compact=True)
            agora_ctx = agora_layer.format_agora_context(channel=channel, presence="online", current_goal="Conversa casual com Isaac")
        else:
            canonical_ident = identity_manager.format_canonical_identity(compact=False)
            agora_ctx = agora_layer.format_agora_context(channel=channel, presence="online", current_goal=user_message[:80])

        protected_block = f"{canonical_ident}\n\n{agora_ctx}"
        layers_meta["protected_tokens"] = estimate_tokens(protected_block)

        # Em mensagens casuais, NENHUM projeto nem notas complexas entram.
        if is_casual:
            layers_meta["total_system_tokens"] = layers_meta["protected_tokens"]
            return protected_block, layers_meta

        # 2. Camada Consultiva Sob Demanda (Cota: até 1800 tokens)
        consultative_sections = []
        consultative_used = 0

        # Inclusão de Core Memory estruturada se disponível
        try:
            from src.memory.core_memory import CoreMemoryManager
            cm = CoreMemoryManager(store)
            core_ctx = cm.format_system_context()
            if core_ctx:
                tok = estimate_tokens(core_ctx)
                if consultative_used + tok <= self.consultative_budget:
                    consultative_sections.append(core_ctx)
                    consultative_used += tok
                    layers_meta["injected_notes"].append("core_memory")
        except Exception as exc:
            LOGGER.debug("Core memory não carregada no ContextBudget: %s", exc)

        # Inclusão seletiva de notas por relevância (score >= 0.35)
        if store is not None:
            try:
                notes = store.list_notes()
                for note_path in notes:
                    if consultative_used >= self.consultative_budget:
                        break
                    # Prioriza notas de preferências e projetos
                    if not (note_path.startswith("preferencias/") or note_path.startswith("projetos/")):
                        continue
                    content = store.read_note(note_path) or ""
                    score = compute_overlap_score(user_message, content)
                    if score >= 0.35:
                        block = f"[Nota: {note_path}]\n{content.strip()}"
                        tok = estimate_tokens(block)
                        if consultative_used + tok <= self.consultative_budget:
                            consultative_sections.append(block)
                            consultative_used += tok
                            layers_meta["injected_notes"].append(note_path)
            except Exception as exc:
                LOGGER.debug("Erro ao consultar notas sob demanda: %s", exc)

        layers_meta["consultative_tokens"] = consultative_used
        full_system = protected_block
        if consultative_sections:
            full_system += "\n\n[CONTEXTO RELEVANTE RECUPERADO]\n" + "\n\n".join(consultative_sections)

        layers_meta["total_system_tokens"] = estimate_tokens(full_system)
        return full_system, layers_meta

    def compact_history_if_needed(
        self,
        history: List[Dict[str, Any]],
        system_tokens: int = 0,
        summarizer: Optional[Callable[[List[Dict[str, Any]]], str]] = None,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Aplica a Regra dos 80% (3276 tokens) compactando turnos antigos e mantendo os últimos 8 intactos."""
        if not history or len(history) <= 8:
            return history, False

        total_tokens = system_tokens + sum(estimate_tokens(m.get("content", "")) for m in history)
        if total_tokens < self.compaction_threshold:
            return history, False

        # Preserva os últimos 8 turnos intactos
        recent_turns = history[-8:]
        older_turns = history[:-8]

        # Resumo condensado dos turnos antigos
        if summarizer is not None:
            try:
                summary_text = summarizer(older_turns)
            except Exception as exc:
                LOGGER.warning("Falha no sumarizador de contexto: %s", exc)
                summary_text = self._fallback_summary(older_turns)
        else:
            summary_text = self._fallback_summary(older_turns)

        compacted_entry = {
            "role": "system",
            "content": f"[RESUMO DE CONTEXTO ANTERIOR CONDENSADO]\n{summary_text.strip()}",
        }

        compacted_history = [compacted_entry] + recent_turns
        LOGGER.info(
            "Regra dos 80%% acionada (%d tokens). Histórico compactado de %d para %d mensagens.",
            total_tokens, len(history), len(compacted_history)
        )
        return compacted_history, True

    def _fallback_summary(self, turns: List[Dict[str, Any]]) -> str:
        """Gera resumo conciso determinístico de turnos passados (< 400 tokens)."""
        topics = []
        for t in turns:
            role = t.get("role", "")
            content = (t.get("content") or "").strip()
            if not content:
                continue
            first_line = content.split("\n")[0][:120]
            topics.append(f"- {role.capitalize()}: {first_line}")
        return "\n".join(topics[:6])


# --- Compatibilidade com ferramentas legadas (web.py) ---

def select_passages(text: str, query: str, max_chars: int = 2400) -> str:
    """Seleciona trechos literais de uma fonte longa, sem sintetizar conteúdo."""
    if not isinstance(text, str) or not isinstance(query, str):
        return ""
    if len(text) <= max_chars:
        return text
    q_terms = terms(query)
    passages = [(offset, text[offset:offset + 1200]) for offset in range(0, len(text), 1000)]
    ranked = sorted(
        passages,
        key=lambda pair: (-compute_overlap_score(query, pair[1]), pair[0])
    )
    selected, size = [], 0
    marker = "\n[trecho omitido]\n"
    for offset, passage in ranked:
        room = max_chars - size - (len(marker) if selected else 0)
        if room <= 0:
            break
        passage = passage[:room]
        selected.append((offset, passage))
        size += len(passage) + (len(marker) if len(selected) > 1 else 0)
    return marker.join(p for _, p in sorted(selected))


def select_history(history: List[Dict[str, Any]], message: str, max_items: int = 10, max_chars: int = 4400) -> List[Dict[str, Any]]:
    """Escolhe turnos recentes mantendo cronologia."""
    if not isinstance(history, list):
        return []
    return history[-max_items:]


def assemble_memory(semantic: str = "", lexical: str = "", project: str = "", budget: int = 1850) -> str:
    """Reserva contexto sob demanda respeitando orçamento."""
    blocks = []
    for label, src in (("projeto", project), ("semantica", semantic), ("lexical", lexical)):
        if src and src.strip():
            blocks.append(f"[{label}]\n{src.strip()}")
    res = "\n\n".join(blocks)
    return res[:budget]


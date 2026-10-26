"""Extrator Assíncrono de Fatos Duradouros (Pilar 3 - Padrão OpenJarvis / Letta).

Executa em thread desacoplada em background após a resposta ser entregue ao usuário.
Analisa o par (User, Assistant), extrai apenas preferências, restrições e metas factuais
em formato JSON puro, e persiste no cérebro permanente.
Fail-closed: erros ou timeouts do modelo nunca travam nem propagam exceções para o fluxo principal.
"""
from datetime import datetime, timezone
import json
import logging
import re
import threading
from typing import Any, Dict, List, Optional
import requests

from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)

FACT_EXTRACTION_PROMPT = """Você é o Extrator Factual da memória permanente do Menor v2.
Sua função é analisar a interação recente entre o operador Isaac Werneck e o assistente Menor v2,
extraindo APENAS fatos novos, preferências pessoais, decisões técnicas duradouras ou metas de projetos.

DIRETRIZES:
1. Ignore conversas fiadas, saudações casuais, agradecimentos e perguntas passageiras.
2. Extraia fatos no formato JSON estruturado como uma lista de objetos:
   [{"fact": "descrição concisa do fato", "category": "preference|goal|constraint|profile"}]
3. Se nenhum fato duradouro foi mencionado, responda EXCLUSIVAMENTE com lista vazia: []
4. NUNCA gere preâmbulos, explicações ou markdown fora do bloco JSON.
"""


class FactExtractor:
    """Extrai fatos duradouros de forma assíncrona em background."""

    def __init__(
        self,
        store: Optional[BrainStore] = None,
        ollama_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.store = store if store is not None else BrainStore()
        self.ollama_url = (ollama_url or "http://127.0.0.1:11434").rstrip("/")
        self.model = model or "qwen2.5:3b"

    def extract_and_store_async(self, user_msg: str, assistant_reply: str) -> threading.Thread:
        """Dispara a extração em thread desacoplada (fire-and-forget seguro)."""
        t = threading.Thread(
            target=self._safe_extract_and_store,
            args=(user_msg, assistant_reply),
            daemon=True,
            name="fact-extractor-worker",
        )
        t.start()
        return t

    def _safe_extract_and_store(self, user_msg: str, assistant_reply: str) -> List[Dict[str, str]]:
        """Execução protegida que nunca propaga exceção."""
        try:
            facts = self.extract_facts(user_msg, assistant_reply)
            for f in facts:
                fact_text = f.get("fact", "").strip()
                category = f.get("category", "preference")
                if fact_text and len(fact_text) >= 5:
                    self.store_fact(fact_text, category)
            return facts
        except Exception as exc:
            LOGGER.debug("FactExtractor falhou de forma segura (fail-closed): %s", exc)
            return []

    def extract_facts(self, user_msg: str, assistant_reply: str) -> List[Dict[str, str]]:
        """Extrai fatos duradouros via modelo ou heurística de alta precisão."""
        # Heurística inicial para evitar chamadas de modelo em conversas puramente casuais
        from src.agent.context_engine import is_casual_query
        if is_casual_query(user_msg) and len(user_msg.split()) < 5:
            return []

        # Detecção rápida de preferências explícitas por padrões regulares
        heuristic_facts = self._extract_heuristic_facts(user_msg)
        if heuristic_facts:
            return heuristic_facts

        # Tentativa de inferência via Ollama se disponível
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": FACT_EXTRACTION_PROMPT},
                {"role": "user", "content": f"Mensagem do Isaac: {user_msg}\nResposta do Menor: {assistant_reply}"},
            ],
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 250},
        }

        try:
            resp = requests.post(f"{self.ollama_url}/api/chat", json=payload, timeout=8.0)
            if resp.status_code == 200:
                raw_out = resp.json().get("message", {}).get("content", "").strip()
                # Localiza JSON na resposta
                json_match = re.search(r"\[[\s\S]*\]", raw_out)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    if isinstance(parsed, list):
                        valid = []
                        for item in parsed:
                            if isinstance(item, dict) and "fact" in item:
                                valid.append({
                                    "fact": str(item["fact"]).strip(),
                                    "category": str(item.get("category", "preference")).strip(),
                                })
                        return valid
        except Exception as exc:
            LOGGER.debug("Ollama indisponível para FactExtractor (%s), usando heurística: %s", self.model, exc)

        return heuristic_facts

    def _extract_heuristic_facts(self, user_msg: str) -> List[Dict[str, str]]:
        """Heurística determinística de alta precisão para padrões explícitos de preferências e metas."""
        norm = user_msg.strip()
        facts = []

        patterns = [
            (r"(?:eu\s+prefiro|minha\s+prefer[êe]ncia\s+[ée]|sempre\s+use)\s+([^.\n]+)", "preference"),
            (r"(?:eu\s+odeio|n[ãa]o\s+gosto\s+de|nunca\s+use)\s+([^.\n]+)", "constraint"),
            (r"(?:vamos\s+focar\s+em|minha\s+meta\s+[ée]|estou\s+criando\s+um\s+projeto\s+chamado)\s+([^.\n]+)", "goal"),
            (r"(?:meu\s+setup\s+[ée]|meu\s+hardware\s+[ée])\s+([^.\n]+)", "profile"),
        ]

        for pat, cat in patterns:
            match = re.search(pat, norm, re.IGNORECASE)
            if match:
                extracted = match.group(1).strip()
                if len(extracted) >= 4:
                    facts.append({"fact": extracted, "category": cat})

        return facts

    def store_fact(self, fact: str, category: str = "preference") -> None:
        """Persiste o fato extraído no cérebro permanente."""
        self.store.initialize()
        if category in ("preference", "constraint"):
            self.store.remember_preference(fact)
            try:
                from src.memory.core_memory import CoreMemoryManager
                CoreMemoryManager(self.store).set_block("user_preferences", fact, mode="append")
            except Exception:
                pass
        else:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            self.store.remember_idea(f"[{category.upper()}] {fact} (registrado em {now_str})")
        LOGGER.info("Fato assimilado pelo FactExtractor: [%s] %s", category, fact)

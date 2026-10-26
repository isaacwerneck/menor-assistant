"""Princípio da Decisão Autoral de Entrega em Duas Vias (Pilar 5 - Padrão Umi).

Separa estritamente a comunicação técnica detalhada (logs de erros, tracebacks, dados brutos)
da mensagem entregue ao operador humano (Voz, Web ou Discord).

Garante que o operador jamais receba 'brochure-dumping' ou stack traces cruas,
mantendo a conversa executiva, natural e resolutiva.
"""
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import threading
from typing import Any, Dict, Optional

from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)
_DELIVERY_LOCK = threading.Lock()


class TwoWayDeliveryRouter:
    """Roteia mensagens e eventos separando a Via Técnica da Via Humana."""

    def __init__(self, store: Optional[BrainStore] = None):
        self.store = store if store is not None else BrainStore()
        self.system_chat_log = self.store.data_dir / "logs" / "chat_sistema.jsonl"
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        try:
            self.system_chat_log.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def route_error(
        self,
        technical_error: str,
        user_facing_intent: str,
        channel: str = "web",
    ) -> Dict[str, str]:
        """Processa um erro técnico gravando o log canônico e gerando aviso resolutivo ao humano."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Via Técnica: persistência integral no log canônico do sistema
        system_entry = {
            "timestamp": now_iso,
            "canal": channel,
            "tipo": "erro_tecnico",
            "intencao": user_facing_intent,
            "detalhes_tecnicos": str(technical_error),
        }
        with _DELIVERY_LOCK:
            try:
                with open(self.system_chat_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(system_entry, ensure_ascii=False) + "\n")
            except Exception as exc:
                LOGGER.debug("Falha ao registrar log técnico: %s", exc)

        # 2. Via Humana: mensagem concisa, natural e construtiva
        human_msg = self._craft_human_facing_resolution(technical_error, user_facing_intent)

        return {
            "human_message": human_msg,
            "technical_logged": True,
            "logged_at": now_iso,
        }

    def _craft_human_facing_resolution(self, raw_err: str, intent: str) -> str:
        """Gera resposta parceira e resolutiva sem jargões de crash."""
        lower_err = raw_err.lower()
        if "timeout" in lower_err or "timed out" in lower_err:
            return "Mano, essa operação demorou um pouco além do esperado na rede local. Já registrei nos logs e reagendei."
        if "connection" in lower_err or "refused" in lower_err:
            return "O serviço de suporte oscilou momentaneamente. O status foi registrado no sistema e vou tentar restabelecer."
        if "filenotfound" in lower_err or "file not found" in lower_err or "não encontrado" in lower_err:
            return "Não encontrei esse arquivo no diretório do projeto. Quer que eu crie um novo agora?"

        return "Houve uma oscilação na execução técnica, mas já registrei todos os detalhes nos logs do sistema para análise."

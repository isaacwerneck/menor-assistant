"""Camada Temporal do Agora (Pilar 2 - Menor v2 SOTA).

Garante que o assistente tenha percepção temporal exata do momento presente,
canal de interação ativo, status de presença e objetivo imediato do turno atual.
Injetado como camada protegida (< 70 tokens).
"""
from datetime import datetime, timezone, timedelta
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)

# Fuso horário oficial do Menor e Isaac: BRT (UTC-3)
BRT_TIMEZONE = timezone(timedelta(hours=-3), name="BRT")


class AgoraLayer:
    """Gerencia o estado temporal e de contexto imediato do turno."""

    def __init__(self, store: Optional[BrainStore] = None):
        self.store = store if store is not None else BrainStore()
        self.file_path = self.store.brain_dir / "identidade" / "AGORA.json"

    def get_agora(
        self,
        channel: str = "web",
        presence: str = "online",
        current_goal: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Gera o snapshot estruturado do Agora."""
        now_brt = datetime.now(BRT_TIMEZONE)
        data = {
            "timestamp": now_brt.isoformat(),
            "data_formatada": now_brt.strftime("%d/%m/%Y"),
            "hora_formatada": now_brt.strftime("%H:%M:%S"),
            "dia_semana": [
                "Segunda-feira", "Terça-feira", "Quarta-feira",
                "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"
            ][now_brt.weekday()],
            "timezone": "America/Sao_Paulo (UTC-3)",
            "canal": channel,
            "presenca": presence,
            "objetivo_imediato": current_goal or "Atender interação do operador Isaac.",
        }

        # Atualiza arquivo atômico de estado
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            LOGGER.debug("Não foi possível salvar AGORA.json: %s", exc)

        return data

    def format_agora_context(
        self,
        channel: str = "web",
        presence: str = "online",
        current_goal: Optional[str] = None,
    ) -> str:
        """Formata o snapshot temporal compacto para inclusão no prompt (< 70 tokens)."""
        data = self.get_agora(channel=channel, presence=presence, current_goal=current_goal)
        return (
            f"[CAMADA DO AGORA - CONTEXTO TEMPORAL]\n"
            f"- Momento Atual: {data['dia_semana']}, {data['data_formatada']} às {data['hora_formatada']} ({data['timezone']})\n"
            f"- Canal Ativo: {data['canal']} | Status: {data['presenca']}\n"
            f"- Foco do Turno: {data['objetivo_imediato']}"
        )

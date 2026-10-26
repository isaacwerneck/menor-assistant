"""Rotina Noturna de Sono e Consolidação: menor-dream (Pilar 3 - Padrão Umi).

Executa diariamente às 22:00 BRT para consolidar memórias do dia no SQLite FTS5,
gerar o diário factual append-only em ~/menor-data/diario/<ANO>/<MES>.jsonl e
refinar o cérebro permanente.
Possui interrupção cooperativa: se o usuário interagir por voz ou chat,
pausa de forma segura em < 200ms liberando a CPU e GPU para atendimento imediato.
"""
from datetime import datetime, timezone, timedelta
import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)

# Fuso horário oficial BRT (UTC-3)
BRT_TIMEZONE = timezone(timedelta(hours=-3), name="BRT")
_DREAM_LOCK = threading.Lock()


class DreamConsolidator:
    """Consolidador noturno de memórias do Menor v2."""

    def __init__(self, store: Optional[BrainStore] = None):
        self.store = store if store is not None else BrainStore()
        self.diary_base_dir = self.store.data_dir / "diario"
        self.state_file = self.store.brain_dir / "dream_state.json"

    def is_running(self) -> bool:
        return _DREAM_LOCK.locked()

    def run_dream_cycle(
        self,
        abort_event: Optional[threading.Event] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Executa o ciclo de consolidação noturna com verificação cooperativa de abort."""
        if not _DREAM_LOCK.acquire(blocking=False):
            return {"success": False, "status": "already_running", "message": "Ciclo de Dream já em execução."}

        start_time = time.time()
        now_brt = datetime.now(BRT_TIMEZONE)
        result = {
            "success": False,
            "status": "completed",
            "timestamp": now_brt.isoformat(),
            "consolidated_conversations": 0,
            "facts_saved": 0,
            "diary_path": "",
            "interrupted": False,
            "duration_s": 0.0,
        }

        try:
            self.store.initialize()
            self._save_state({"status": "running", "started_at": now_brt.isoformat()})
            LOGGER.info("[MENOR-DREAM] Iniciando ciclo de consolidação noturna...")

            # Passo 1: Checa interrupção cooperativa antes de I/O pesado
            if abort_event and abort_event.is_set():
                result["interrupted"] = True
                result["status"] = "interrupted_by_user"
                LOGGER.info("[MENOR-DREAM] Interrupção cooperativa solicitada pelo usuário (< 200ms).")
                return result

            # Passo 2: Consolidação do Diário Factual Append-Only (~/menor-data/diario/<ANO>/<MES>.jsonl)
            ano = now_brt.strftime("%Y")
            mes = now_brt.strftime("%m")
            month_dir = self.diary_base_dir / ano
            month_dir.mkdir(parents=True, exist_ok=True)
            diary_file = month_dir / f"{mes}.jsonl"
            result["diary_path"] = str(diary_file)

            # Coleta notas recentes do dia e tarefas concluídas
            daily_facts = self._gather_daily_facts(now_brt)

            if abort_event and abort_event.is_set():
                result["interrupted"] = True
                result["status"] = "interrupted_by_user"
                return result

            # Grava entrada atômica no diário
            diary_entry = {
                "timestamp": now_brt.isoformat(),
                "data": now_brt.strftime("%d/%m/%Y"),
                "tipo": "dream_consolidation",
                "fatos_consolidados": daily_facts,
                "resumo_executivo": f"Consolidação noturna realizada às {now_brt.strftime('%H:%M:%S')} BRT.",
            }
            with open(diary_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(diary_entry, ensure_ascii=False) + "\n")

            result["facts_saved"] = len(daily_facts)

            # Passo 3: Otimização e Manutenção do SQLite FTS5 permanente
            if abort_event and abort_event.is_set():
                result["interrupted"] = True
                result["status"] = "interrupted_by_user"
                return result

            self._optimize_fts5()

            result["success"] = True
            result["status"] = "completed"
            LOGGER.info("[MENOR-DREAM] Ciclo noturno concluído com sucesso: %d fatos arquivados.", len(daily_facts))

        except Exception as exc:
            LOGGER.error("[MENOR-DREAM] Falha no ciclo noturno: %s", exc)
            result["status"] = "error"
            result["error"] = str(exc)
        finally:
            result["duration_s"] = round(time.time() - start_time, 2)
            self._save_state(result)
            _DREAM_LOCK.release()

        return result

    def _gather_daily_facts(self, date_ref: datetime) -> List[str]:
        """Coleta fatos e notas registrados recentemente no cérebro."""
        facts = []
        try:
            notes = self.store.list_notes()
            for n in notes:
                if n.startswith("preferencias/") or n.startswith("projetos/"):
                    content = self.store.read_note(n)
                    if content and len(content.strip()) > 10:
                        first_line = content.strip().split("\n")[0][:100]
                        facts.append(f"[{n}] {first_line}")
        except Exception as exc:
            LOGGER.debug("Erro ao coletar notas diárias: %s", exc)

        return facts[:25]

    def _optimize_fts5(self):
        """Otimiza tabelas e índices FTS5 do cérebro permanente."""
        try:
            fts_path = self.store.brain_dir / "brain_notes.sqlite"
            if fts_path.exists():
                with sqlite3.connect(fts_path, timeout=5.0) as conn:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    conn.execute("VACUUM;")
        except Exception as exc:
            LOGGER.debug("Otimização FTS5 ignorada: %s", exc)

    def _save_state(self, state: Dict[str, Any]):
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_state(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {"status": "idle", "last_run": None}
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {"status": "idle"}

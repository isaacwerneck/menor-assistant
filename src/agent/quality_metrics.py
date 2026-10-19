"""Métricas privadas de decisões e falhas, sem armazenar mensagens ou respostas.

Fornece evidências para futuras propostas de autoaperfeiçoamento; não
aprende, não treina, não instala nem executa código por iniciativa própria.
"""
from collections import Counter
from contextlib import closing
import hashlib
import os
import sqlite3
import time

from src.memory.store import BrainStore

PHASES = {"idle", "goal", "approval", "mission", "image_offer", "image_scene",
          "failed", "blocked", "running"}
OUTCOMES = {"handled", "unhandled", "failed"}
MAX_RECENT = 1000


class DecisionMetrics:
    def __init__(self, store=None):
        self.store = store or BrainStore()

    def _connect(self):
        path = self.store._directories(("memoria",)) / "decision_metrics.sqlite"
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("Auditoria de decisões inválida.")
        if not path.exists():
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
            try:
                fd = os.open(path, flags, 0o600)
                os.close(fd)
            except FileExistsError:
                if path.is_symlink() or not path.is_file():
                    raise ValueError("Auditoria de decisões inválida.") from None
        path.chmod(0o600)
        db = sqlite3.connect(path, timeout=5)
        db.execute(
            "CREATE TABLE IF NOT EXISTS decisions ("
            "session_hash TEXT, turn_hash TEXT, created_at INTEGER, "
            "phase TEXT, outcome TEXT, error_type TEXT, "
            "PRIMARY KEY(session_hash, turn_hash))"
        )
        return db

    @staticmethod
    def _hash(value):
        if not isinstance(value, str) or not 8 <= len(value) <= 80:
            raise ValueError("Identificador inválido.")
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def record(self, session, turn, result, error_type=""):
        if not isinstance(result, dict):
            raise ValueError("Comprovante inválido.")
        phase = result.get("phase", "idle")
        if phase not in PHASES:
            phase = "blocked"
        outcome = "failed" if error_type or phase == "failed" else (
            "handled" if result.get("handled") is True else "unhandled"
        )
        if outcome not in OUTCOMES:
            raise ValueError("Resultado inválido.")
        if not isinstance(error_type, str):
            raise ValueError("Tipo de erro inválido.")
        # Apenas nomes de classes de erro, nunca exceções com paths ou segredos.
        if error_type and (len(error_type) > 80 or not error_type.replace("_", "").isalnum()):
            raise ValueError("Tipo de erro inválido.")
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO decisions VALUES (?,?,?,?,?,?)",
                (self._hash(session), self._hash(turn), int(time.time()), phase, outcome, error_type),
            )

    def report(self):
        path = self.store.brain_dir / "memoria" / "decision_metrics.sqlite"
        if not path.exists():
            if path.is_symlink():
                raise ValueError("Auditoria de decisões inválida.")
            return {
                "events": 0, "handled": 0, "unhandled": 0, "failed": 0,
                "phases": {}, "error_types": {}, "review_signals": [],
                "note": "Contadores técnicos, não prova de qualidade ou inteligência do modelo.",
            }
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT phase,outcome,error_type FROM decisions "
                "ORDER BY created_at DESC LIMIT ?", (MAX_RECENT,),
            ).fetchall()
        outcomes = Counter(row[1] for row in rows)
        phases = Counter(row[0] for row in rows)
        failures = Counter(row[2] for row in rows if row[2])
        signals = []
        if outcomes["failed"] >= 3:
            signals.append({
                "type": "repeated_failures", "count": outcomes["failed"],
                "next_step": "Reproduzir falhas isoladamente e propor teste de regressão.",
            })
        if outcomes["unhandled"] >= 5:
            signals.append({
                "type": "unhandled_requests", "count": outcomes["unhandled"],
                "next_step": "Avaliar se o modelo local compreendeu os pedidos não atendidos.",
            })
        if phases["goal"] >= 10 and outcomes["handled"] >= 10:
            signals.append({
                "type": "plan_heavy_workload", "count": phases["goal"],
                "next_step": "Medir taxa real de execução versus planejamento.",
            })
        return {
            "events": len(rows),
            "handled": outcomes["handled"], "unhandled": outcomes["unhandled"],
            "failed": outcomes["failed"], "phases": dict(phases),
            "error_types": dict(failures.most_common(10)),
            "review_signals": signals,
            "note": "Contadores técnicos, não prova de qualidade ou inteligência do modelo.",
        }

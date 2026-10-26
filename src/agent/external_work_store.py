"""Armazenamento e Isolamento de Agentes de Código Externos (Pilar 9 - Padrão Umi).

Bancos de dados estritamente segregados:
- ~/menor-data/cerebro/brain_notes.sqlite: Memória pessoal do Isaac, preferências e projetos.
- ~/menor-data/agentes/trabalhos.db: Banco exclusivo para sessões de codificação de agentes externos
  (Antigravity, Codex, Aider, Claude Code).

Garante que diffs de milhares de linhas, saídas de compiladores e logs de terminal
jamais poluam a memória permanente ou desperdicem embeddings semânticos.
A busca no acervo de agentes é puramente léxica (FTS/texto).
"""
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)
_WORK_LOCK = threading.Lock()


class ExternalWorkStore:
    """Gerencia a persistência isolada de logs, diffs e sessões de agentes externos."""

    def __init__(self, store: Optional[BrainStore] = None):
        self.store = store if store is not None else BrainStore()
        self.db_path = self.store.data_dir / "agentes" / "trabalhos.db"
        self._init_db()

    def _init_db(self):
        self.store.initialize()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with _WORK_LOCK:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_sessions (
                        session_id TEXT PRIMARY KEY,
                        agent_name TEXT NOT NULL,
                        project_path TEXT NOT NULL,
                        task_goal TEXT NOT NULL,
                        status TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        completed_at TEXT
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        log_type TEXT NOT NULL,
                        content TEXT NOT NULL,
                        FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id)
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_diffs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        diff_content TEXT NOT NULL,
                        applied INTEGER DEFAULT 1,
                        FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id)
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def start_session(self, session_id: str, agent_name: str, project_path: str, task_goal: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with _WORK_LOCK:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO agent_sessions (
                        session_id, agent_name, project_path, task_goal, status, started_at
                    ) VALUES (?, ?, ?, ?, 'running', ?)
                    """,
                    (session_id, agent_name, project_path, task_goal, now_iso),
                )
                conn.commit()
            finally:
                conn.close()

    def complete_session(self, session_id: str, status: str = "completed") -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with _WORK_LOCK:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    "UPDATE agent_sessions SET status = ?, completed_at = ? WHERE session_id = ?",
                    (status, now_iso, session_id),
                )
                conn.commit()
            finally:
                conn.close()

    def record_log(self, session_id: str, content: str, log_type: str = "stdout") -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with _WORK_LOCK:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    "INSERT INTO agent_logs (session_id, timestamp, log_type, content) VALUES (?, ?, ?, ?)",
                    (session_id, now_iso, log_type, content),
                )
                conn.commit()
            finally:
                conn.close()

    def record_diff(self, session_id: str, file_path: str, diff_content: str, applied: bool = True) -> None:
        with _WORK_LOCK:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    "INSERT INTO agent_diffs (session_id, file_path, diff_content, applied) VALUES (?, ?, ?, ?)",
                    (session_id, file_path, diff_content, 1 if applied else 0),
                )
                conn.commit()
            finally:
                conn.close()

    def get_agent_work_status(self, session_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Consulta o status de trabalhos de agentes sem poluir a memória pessoal."""
        query = "SELECT * FROM agent_sessions "
        params: List[Any] = []
        if session_id:
            query += "WHERE session_id = ? "
            params.append(session_id)
        query += "ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        results = []
        with _WORK_LOCK:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, params)
                for row in cursor.fetchall():
                    s_dict = dict(row)
                    c_cursor = conn.cursor()
                    c_cursor.execute("SELECT COUNT(*) FROM agent_logs WHERE session_id = ?", (s_dict["session_id"],))
                    s_dict["logs_count"] = c_cursor.fetchone()[0]
                    c_cursor.execute("SELECT COUNT(*) FROM agent_diffs WHERE session_id = ?", (s_dict["session_id"],))
                    s_dict["diffs_count"] = c_cursor.fetchone()[0]
                    results.append(s_dict)
            finally:
                conn.close()
        return results


def get_agent_work_status(session_id: Optional[str] = None) -> Dict[str, Any]:
    """Ferramenta pública registrada no orquestrador para consultar trabalhos de agentes."""
    store = ExternalWorkStore()
    sessions = store.get_agent_work_status(session_id=session_id, limit=5)
    return {
        "success": True,
        "count": len(sessions),
        "sessions": sessions,
    }

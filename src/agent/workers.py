"""Pipeline autônomo de tarefas em segundo plano (Gerente -> Dev -> QA).

Permite despachar tarefas assíncronas que o Menor executa em fila sequencial
sem sobrecarregar a CPU do servidor.
"""
from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)


class TaskQueue:
    def __init__(self, db_path: Optional[str] = None):
        store = BrainStore()
        store.initialize()
        self.db_path = Path(db_path) if db_path else (store.data_dir / "tasks_v2.db")
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal TEXT NOT NULL,
                    project_slug TEXT,
                    status TEXT NOT NULL,
                    result TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def enqueue(self, goal: str, project_slug: Optional[str] = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tasks (goal, project_slug, status, created_at, updated_at)
                VALUES (?, ?, 'pending', ?, ?)
            """, (goal, project_slug, now, now))
            conn.commit()
            return cursor.lastrowid

    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(row) if row else None

    def list_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def update_status(self, task_id: int, status: str, result: Optional[str] = None):
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                UPDATE tasks SET status = ?, result = ?, updated_at = ?
                WHERE id = ?
            """, (status, result, now, task_id))
            conn.commit()


_DEFAULT_QUEUE = None


def get_task_queue() -> TaskQueue:
    global _DEFAULT_QUEUE
    if _DEFAULT_QUEUE is None:
        _DEFAULT_QUEUE = TaskQueue()
    return _DEFAULT_QUEUE

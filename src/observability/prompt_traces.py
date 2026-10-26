"""Observabilidade Total: Prompt Trace v2 (Pilar 4 - Menor v2 SOTA).

Registra a proveniência exata, contexto injetado, payload bruto enviado ao LLM,
tempo de resposta, contagem de tokens e chamadas de ferramentas no SQLite.
Permite auditoria cirúrgica de qualquer turno em 5 segundos.
"""
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional
import uuid

from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)
_TRACE_LOCK = threading.Lock()


class PromptTraceLogger:
    """Gerencia a persistência atômica de traces de execução dos modelos."""

    def __init__(self, store: Optional[BrainStore] = None):
        self.store = store if store is not None else BrainStore()
        self.db_path = self.store.brain_dir / "prompt_traces.sqlite"
        self._init_db()

    def _init_db(self):
        """Inicializa as tabelas e índices de trace no SQLite."""
        self.store.initialize()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with _TRACE_LOCK:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS prompt_traces (
                        id TEXT PRIMARY KEY,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        session_id TEXT NOT NULL,
                        turn_index INTEGER NOT NULL,
                        model TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        input_tokens INTEGER,
                        output_tokens INTEGER,
                        duration_ms INTEGER,
                        context_layers TEXT NOT NULL,
                        raw_prompt TEXT NOT NULL,
                        raw_response TEXT,
                        tool_calls TEXT,
                        error TEXT
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_traces_session ON prompt_traces(session_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON prompt_traces(timestamp);"
                )
                conn.commit()
            finally:
                conn.close()

    def record_trace(
        self,
        session_id: str,
        turn_index: int,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
        context_layers: Dict[str, Any],
        raw_prompt: str,
        raw_response: Optional[str] = None,
        tool_calls: Optional[List[Any]] = None,
        error: Optional[str] = None,
    ) -> str:
        """Registra um trace de forma síncrona/atômica e rápida."""
        trace_id = f"trace_{uuid.uuid4().hex[:16]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        layers_json = json.dumps(context_layers, ensure_ascii=False)
        tools_json = json.dumps(tool_calls or [], ensure_ascii=False)

        try:
            with _TRACE_LOCK:
                conn = sqlite3.connect(self.db_path, timeout=5.0)
                try:
                    conn.execute(
                        """
                        INSERT INTO prompt_traces (
                            id, timestamp, session_id, turn_index, model, provider,
                            input_tokens, output_tokens, duration_ms, context_layers,
                            raw_prompt, raw_response, tool_calls, error
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            trace_id,
                            now_iso,
                            session_id,
                            turn_index,
                            model,
                            provider,
                            input_tokens,
                            output_tokens,
                            duration_ms,
                            layers_json,
                            raw_prompt,
                            raw_response,
                            tools_json,
                            error,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()
            return trace_id
        except Exception as exc:
            LOGGER.warning("Falha ao gravar prompt trace: %s", exc)
            return trace_id

    def list_traces(self, limit: int = 50, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Consulta traces recentes para auditoria."""
        query = (
            "SELECT id, timestamp, session_id, turn_index, model, provider, "
            "input_tokens, output_tokens, duration_ms, context_layers, raw_prompt, "
            "raw_response, tool_calls, error FROM prompt_traces "
        )
        params: List[Any] = []
        if session_id:
            query += "WHERE session_id = ? "
            params.append(session_id)
        query += "ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        results = []
        try:
            with _TRACE_LOCK:
                conn = sqlite3.connect(self.db_path)
                try:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute(query, params)
                    for row in cursor.fetchall():
                        item = dict(row)
                        try:
                            item["context_layers"] = json.loads(item["context_layers"])
                        except Exception:
                            pass
                        try:
                            item["tool_calls"] = json.loads(item["tool_calls"])
                        except Exception:
                            pass
                        results.append(item)
                finally:
                    conn.close()
        except Exception as exc:
            LOGGER.warning("Falha ao listar prompt traces: %s", exc)

        return results

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Recupera um trace específico por ID."""
        with _TRACE_LOCK:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM prompt_traces WHERE id = ?", (trace_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return None
                data = dict(row)
                try:
                    data["context_layers"] = json.loads(data["context_layers"])
                except Exception:
                    pass
                try:
                    data["tool_calls"] = json.loads(data["tool_calls"])
                except Exception:
                    pass
                return data
            finally:
                conn.close()

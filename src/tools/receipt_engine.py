"""Motor de Recibos, Idempotência e Prevenção de Replay Cego (Pilar 6 - Padrão Umi).

Toda execução de ferramenta gera um recibo estruturado ReceiptV1 com hash idempotente único
(session_id, tool_name, args_hash).

Ações são classificadas em:
- REVERSIBLE (leitura de arquivos, listagem, buscas): executam imediatamente.
- SENSITIVE (deleção de arquivos, modificação de configs críticas, comandos destrutivos):
  ficam no estado 'aguardando_voce'.
- EFEITO_INCERTO: timeouts em ferramentas não reversíveis nunca são repetidos automaticamente
  (prevenção rigorosa de Replay Cego).
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)
_RECEIPT_LOCK = threading.Lock()

# Comandos de terminal sensíveis que exigem confirmação explícita
SENSITIVE_CMD_PATTERNS = (
    r"\brm\s+-[rf]{1,2}\b",
    r"\bshred\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r">\s*/dev/sd[a-z]",
    r"\bdrop\s+table\b",
    r"\bdrop\s+database\b",
    r"\btruncate\b",
    r"\bsystemctl\s+(?:stop|disable|poweroff|reboot)\b",
)


@dataclass
class ReceiptV1:
    receipt_id: str
    session_id: str
    tool_name: str
    args_hash: str
    status: str  # "planned", "executed", "aguardando_voce", "efeito_incerto", "failed"
    is_sensitive: bool
    created_at: str
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ReceiptEngine:
    """Gerencia o ciclo de vida e atomicidade de recibos de ferramentas."""

    def __init__(self, store: Optional[BrainStore] = None):
        self.store = store if store is not None else BrainStore()
        self.db_path = self.store.brain_dir / "receipts.sqlite"
        self._init_db()

    def _init_db(self):
        self.store.initialize()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with _RECEIPT_LOCK:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tool_receipts (
                        receipt_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        tool_name TEXT NOT NULL,
                        args_hash TEXT NOT NULL,
                        status TEXT NOT NULL,
                        is_sensitive INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        completed_at TEXT,
                        result TEXT,
                        error TEXT
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_receipts_idempotency ON tool_receipts(session_id, tool_name, args_hash);"
                )
                conn.commit()

    @staticmethod
    def compute_args_hash(args: Dict[str, Any]) -> str:
        """Gera hash determinístico SHA-256 dos argumentos."""
        canonical_json = json.dumps(args, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]

    def classify_action(self, tool_name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
        """Classifica se uma ação é reversível ou sensível (aguardando_voce)."""
        if tool_name in ("fs_read", "fs_list", "web_search", "web_read", "get_study_report", "inspect_codebase"):
            return False, "reversivel"

        if tool_name == "terminal_run":
            cmd = str(args.get("command", "")).strip()
            for pat in SENSITIVE_CMD_PATTERNS:
                if re.search(pat, cmd, re.IGNORECASE):
                    return True, f"Comando destrutivo detectado: {cmd[:60]}"

        if tool_name == "fs_write":
            filepath = str(args.get("filepath", "")).lower()
            if any(filepath.endswith(crit) for crit in ("id_rsa", ".env", "passwd", "shadow")):
                return True, f"Modificação de arquivo crítico: {filepath}"

        return False, "padrao"

    def create_receipt(self, session_id: str, tool_name: str, args: Dict[str, Any]) -> ReceiptV1:
        """Registra o plano atômico de execução gerando ReceiptV1."""
        args_hash = self.compute_args_hash(args)
        is_sensitive, reason = self.classify_action(tool_name, args)
        status = "aguardando_voce" if is_sensitive else "planned"

        receipt_id = f"rcpt_{hashlib.sha256(f'{session_id}:{tool_name}:{args_hash}:{datetime.now().isoformat()}'.encode()).hexdigest()[:16]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        receipt = ReceiptV1(
            receipt_id=receipt_id,
            session_id=session_id,
            tool_name=tool_name,
            args_hash=args_hash,
            status=status,
            is_sensitive=is_sensitive,
            created_at=now_iso,
        )

        with _RECEIPT_LOCK:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tool_receipts (
                        receipt_id, session_id, tool_name, args_hash, status,
                        is_sensitive, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (receipt_id, session_id, tool_name, args_hash, status, int(is_sensitive), now_iso),
                )
                conn.commit()

        return receipt

    def mark_executed(self, receipt_id: str, result: Dict[str, Any]) -> None:
        """Marca o recibo como executado com sucesso."""
        now_iso = datetime.now(timezone.utc).isoformat()
        res_json = json.dumps(result, ensure_ascii=False)
        with _RECEIPT_LOCK:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE tool_receipts SET status = 'executed', completed_at = ?, result = ? WHERE receipt_id = ?",
                    (now_iso, res_json, receipt_id),
                )
                conn.commit()

    def mark_uncertain(self, receipt_id: str, error_msg: str) -> None:
        """Marca como efeito_incerto em caso de timeout para bloquear replay cego."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with _RECEIPT_LOCK:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE tool_receipts SET status = 'efeito_incerto', completed_at = ?, error = ? WHERE receipt_id = ?",
                    (now_iso, error_msg, receipt_id),
                )
                conn.commit()
        LOGGER.warning("[RECEIPT] Ação %s marcada como 'efeito_incerto'. Replay cego bloqueado.", receipt_id)

    def is_uncertain_or_duplicate(self, session_id: str, tool_name: str, args: Dict[str, Any]) -> bool:
        """Verifica se a mesma ação já falhou com efeito incerto na sessão atual."""
        args_hash = self.compute_args_hash(args)
        with _RECEIPT_LOCK:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT status FROM tool_receipts
                    WHERE session_id = ? AND tool_name = ? AND args_hash = ? AND status = 'efeito_incerto'
                    """,
                    (session_id, tool_name, args_hash),
                )
                if cursor.fetchone():
                    return True
        return False

"""Auditoria local minimalista de ações, sem payloads de memória ou segredos."""
import json
import os
import stat
import threading
from datetime import datetime, timezone

from src.memory.store import BrainStore

_guard = threading.RLock()
MAX_AUDIT_BYTES = 1024 * 1024


def record(action, status, metadata=None):
    """Registra evento de forma privada; metadata é lista de nomes, nunca conteúdos."""
    if not isinstance(action, str) or not isinstance(status, str):
        raise ValueError("Evento inválido.")
    if len(action) > 100 or len(status) > 40:
        raise ValueError("Metadados excedem os limites.")
    entry = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": action,
        "status": status,
        "fields": list(metadata or ())[:10],
    }
    if not all(isinstance(x, str) and len(x) <= 64 for x in entry["fields"]):
        raise ValueError("Campos de auditoria inválidos.")
    store = BrainStore()
    with _guard:
        folder = store._directories(("memoria",))
        target = folder / "execucoes.jsonl"
        if target.is_symlink():
            raise ValueError("Auditoria insegura.")
        if target.exists():
            if not stat.S_ISREG(target.lstat().st_mode):
                raise ValueError("Auditoria inválida.")
            if target.stat().st_size > MAX_AUDIT_BYTES:
                old = folder / "execucoes.anterior.jsonl"
                if old.is_symlink():
                    raise ValueError("Histórico de auditoria inválido.")
                os.replace(target, old)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry

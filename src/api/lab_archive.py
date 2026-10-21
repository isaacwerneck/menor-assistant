"""Arquivo lógico de relatórios: preserva JSON, resumos e publicação no GitHub."""
import json
import os
import threading

from src.api import lab_batches

_LOCK = threading.Lock()


def _index():
    return lab_batches.DATA / "archived_runs.json"


def _read():
    path = _index()
    if path.is_symlink():
        raise ValueError("Índice de arquivo inválido.")
    if not path.exists():
        return set()
    if not path.is_file() or path.stat().st_size > 300_000:
        raise ValueError("Índice de arquivo inválido.")
    ids = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(ids, list) or len(ids) > 5000:
        raise ValueError("Índice de arquivo inválido.")
    validated = set()
    for run_id in ids:
        lab_batches.report_path(run_id)
        validated.add(run_id)
    return validated


def state():
    with _LOCK:
        return {"archived_ids": sorted(_read())}


def change(mode):
    """Arquiva ou reativa somente resumos existentes. Nunca move ou exclui dados."""
    if mode not in ("archive_all", "restore_all"):
        raise ValueError("Modo de arquivamento inválido.")
    with _LOCK:
        known = [x["run_id"] for x in lab_batches.reports()
                 if isinstance(x.get("run_id"), str)]
        # Validação integral antes de persistir: não aceitar IDs provenientes de nomes falsos.
        for run_id in known:
            lab_batches.report_path(run_id)
        new_ids = set(known) if mode == "archive_all" else set()
        lab_batches.DATA.mkdir(parents=True, exist_ok=True)
        path = _index()
        if path.is_symlink():
            raise ValueError("Índice de arquivo inválido.")
        temp = path.with_name(".archived_runs_" + str(os.getpid()) + ".tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(temp, flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(sorted(new_ids), out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
        return {"archived": len(new_ids), "unchanged_report_files": len(known)}

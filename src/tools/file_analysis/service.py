"""Armazenamento privado, IDs opacos e execução do parser em processo separado."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

from src.tools.file_analysis.contracts import (
    FILE_ID, MAX_BYTES, VERSION, FileRejected, capabilities as _capabilities, detect,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKER_TIMEOUT = 25
MAX_WORKER_OUTPUT = 1024 * 1024


def capabilities():
    return _capabilities()


def _directory(root=None):
    base = Path(root) if root is not None else Path(
        os.environ.get("MENOR_DATA_DIR", str(Path.home() / "menor-data"))
    )
    for part in (base, base / "media", base / "media" / "file_analysis"):
        if part.is_symlink() or (part.exists() and not part.is_dir()):
            raise FileRejected("Armazenamento privado inválido.")
        part.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Nunca depende de uma pasta na árvore versionada do Git.
        if part.is_symlink():
            raise FileRejected("Armazenamento privado inválido.")
    return base / "media" / "file_analysis"


def _write_exclusive(path, content):
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _read_no_follow(path, limit):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise FileRejected("Arquivo armazenado excede o limite.")
    return content


def ingest(data, filename, *, root=None):
    """Grava somente dados em pasta privada; nenhuma entrada aceita path de servidor."""
    fmt = detect(data, filename)
    folder = _directory(root)
    token = secrets.token_hex(16)
    digest = hashlib.sha256(data).hexdigest()
    blob, meta = folder / f"{token}.blob", folder / f"{token}.json"
    receipt = {"file_id": token, "filename": filename, "format": fmt,
               "bytes": len(data), "sha256": digest}
    try:
        _write_exclusive(blob, data)
        _write_exclusive(meta, json.dumps(receipt, ensure_ascii=False).encode("utf-8"))
    except BaseException:
        blob.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)
        raise
    return {"tool": "files.ingest", "version": VERSION, "status": "executed",
            "file": receipt, "state": "stored_private", "limitations": [
                "Arquivo foi armazenado, mas ainda não analisado.",
            ]}


def _load(file_id, root):
    if not isinstance(file_id, str) or FILE_ID.fullmatch(file_id) is None:
        raise FileRejected("Identificador de arquivo inválido.")
    folder = _directory(root)
    try:
        meta = json.loads(_read_no_follow(folder / f"{file_id}.json", 4096))
        data = _read_no_follow(folder / f"{file_id}.blob", MAX_BYTES)
    except (OSError, json.JSONDecodeError) as exc:
        raise FileRejected("Arquivo privado não encontrado ou corrompido.") from exc
    if (not isinstance(meta, dict) or meta.get("file_id") != file_id
            or meta.get("sha256") != hashlib.sha256(data).hexdigest()
            or meta.get("bytes") != len(data)):
        raise FileRejected("Integridade do arquivo privado falhou.")
    if detect(data, meta.get("filename")) != meta.get("format"):
        raise FileRejected("Formato armazenado não corresponde ao conteúdo.")
    return meta, data


def _failure(meta, code, message):
    return {
        "tool": "files.inspect", "version": VERSION, "status": "failed",
        "file": meta, "error": {"code": code, "message": message},
        "evidence": [], "validation": {"format_verified": False,
                                       "semantic_verified": False},
        "state": {"extractor": "failed", "visual_understanding": "not_integrated"},
    }


def inspect(file_id, *, root=None):
    """Analisa arquivo por ID privado; nunca faz request externo nem executa macros."""
    meta, data = _load(file_id, root)
    # Isola o parser do processo principal. Sem tokens e sem diretório de dados no env.
    env = {
        "PATH": os.defpath, "PYTHONPATH": str(PROJECT_ROOT),
        "PYTHONIOENCODING": "utf-8", "LANG": "C.UTF-8",
        "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
    }
    try:
        result = subprocess.run(
            [sys.executable, "-m", "src.tools.file_analysis.worker", meta["filename"]],
            cwd=PROJECT_ROOT, env=env, input=data, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=WORKER_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired:
        return _failure(meta, "timeout", "Análise excedeu o tempo permitido.")
    except OSError:
        return _failure(meta, "worker_unavailable", "Processador local indisponível.")
    if result.returncode != 0 or len(result.stdout) > MAX_WORKER_OUTPUT:
        return _failure(meta, "worker_failed", "Processador local não concluiu a análise.")
    try:
        parsed = json.loads(result.stdout)
    except (UnicodeDecodeError, ValueError):
        return _failure(meta, "invalid_result", "Processador retornou resultado inválido.")
    if not isinstance(parsed, dict) or parsed.get("status") != "executed":
        error = parsed.get("error") if isinstance(parsed, dict) else None
        msg = error if isinstance(error, str) and len(error) < 180 else "Não foi possível ler o arquivo."
        return _failure(meta, "parse_failed", msg)
    analysis = parsed.get("analysis")
    if not isinstance(analysis, dict) or analysis.get("format") != meta["format"]:
        return _failure(meta, "invalid_result", "Formato do resultado não foi confirmado.")
    return {
        "tool": "files.inspect", "version": VERSION, "status": "executed",
        "file": meta, "content": analysis["structure"],
        "metadata": analysis["metadata"], "evidence": analysis["evidence"],
        "truncated": analysis["truncated"], "limitations": analysis["limitations"],
        "validation": {"format_verified": True, "semantic_verified": False},
        "state": {"extractor": "operational", "visual_understanding": "not_integrated"},
    }

"""Rotas e serviços para o Inspetor do Cérebro do Menor (/brain/view).

Permite navegação em árvore, edição segura com controle otimista e feed de changelog
estilo GitHub sobre todos os documentos de ~/menor-data/.
"""
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from src.memory.store import BrainStore, _write_lock
from src.security import auth
from src.security.path_sentinel import PathSentinel, SecurityPathError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Cérebro do Menor"])
TEMPLATES_DIR = Path(__file__).parent / "templates"


class NoteSavePayload(BaseModel):
    path: str = Field(min_length=1, max_length=200)
    content: str = Field(max_length=65536)  # Máximo 64 KiB
    expected_hash: Optional[str] = Field(default=None, max_length=64)


def _get_changelog_path(data_dir: Path) -> Path:
    return data_dir / "brain_changelog.jsonl"


def _record_changelog(data_dir: Path, rel_path: str, author: str, action: str, summary: str = ""):
    """Registra uma entrada append-only no changelog permanente."""
    try:
        log_file = _get_changelog_path(data_dir)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": rel_path,
            "author": author,
            "action": action,
            "summary": summary[:300],
        }
        with _write_lock:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Falha ao registrar changelog do cérebro: %s", exc)


@router.get("/brain/view")
def brain_view_page(request: Request):
    """Página visual completa do Cérebro do Menor."""
    auth.require_owner(request)
    brain_html = TEMPLATES_DIR / "brain.html"
    if not brain_html.exists():
        raise HTTPException(status_code=404, detail="Template do cérebro não encontrado.")
    return FileResponse(
        brain_html,
        media_type="text/html",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/api/brain/tree")
def get_brain_tree(request: Request):
    """Retorna a estrutura hierárquica completa de arquivos em ~/menor-data/."""
    auth.require_owner(request)
    store = BrainStore()
    store.initialize()
    root_dir = store.data_dir

    def scan_dir(current_path: Path, rel_prefix: str = "") -> List[Dict[str, Any]]:
        nodes = []
        if not current_path.exists() or not current_path.is_dir():
            return nodes

        # Pastas e arquivos ignorados na listagem de dados do cérebro
        ignored = {".git", "__pycache__", ".venv", "venv", ".pytest_cache", ".cloudflared"}

        try:
            for entry in sorted(current_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
                if entry.name in ignored or entry.name.startswith("."):
                    continue
                if entry.is_symlink():
                    continue

                rel_item = f"{rel_prefix}/{entry.name}".strip("/")
                if entry.is_dir():
                    children = scan_dir(entry, rel_item)
                    nodes.append({
                        "name": entry.name,
                        "type": "directory",
                        "path": rel_item,
                        "children": children,
                    })
                elif entry.is_file() and entry.suffix.lower() in (".md", ".json", ".txt"):
                    try:
                        size = entry.stat().st_size
                        mtime = datetime.fromtimestamp(entry.stat().st_mtime, timezone.utc).isoformat()
                        nodes.append({
                            "name": entry.name,
                            "type": "file",
                            "path": rel_item,
                            "size": size,
                            "updated_at": mtime,
                        })
                    except OSError:
                        pass
        except PermissionError:
            pass
        return nodes

    tree = scan_dir(root_dir)
    return {"root": str(root_dir), "tree": tree}


@router.get("/api/brain/note")
def read_brain_note(path: str = Query(..., min_length=1, max_length=200), request: Request = None):
    """Lê o conteúdo de uma nota com hash SHA-256 para controle de concorrência."""
    auth.require_owner(request)
    store = BrainStore()
    sentinel = PathSentinel(allowed_base=store.data_dir, allowed_extensions={".md", ".json", ".txt"})

    try:
        content = sentinel.safe_read_text(path)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        full_path = sentinel.resolve_safe_path(path, must_exist=True)
        mtime = datetime.fromtimestamp(full_path.stat().st_mtime, timezone.utc).isoformat()
        return {
            "path": path,
            "content": content,
            "hash": content_hash,
            "updated_at": mtime,
        }
    except SecurityPathError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")


@router.post("/api/brain/note")
def save_brain_note(payload: NoteSavePayload, request: Request):
    """Salva uma nota com prevenção de race condition (ETag check) e registro de changelog."""
    auth.require_owner(request)
    store = BrainStore()
    sentinel = PathSentinel(allowed_base=store.data_dir, allowed_extensions={".md", ".json", ".txt"})

    try:
        # Se o cliente enviou expected_hash, valida controle otimista de concorrência
        if payload.expected_hash:
            try:
                current_text = sentinel.safe_read_text(payload.path)
                current_hash = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
                if current_hash != payload.expected_hash:
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": "Conflito de edição: o documento foi modificado no servidor.",
                            "server_hash": current_hash,
                        },
                    )
            except FileNotFoundError:
                pass

        with _write_lock:
            sentinel.safe_write_text(payload.path, payload.content)

        # Atualiza o índice do cérebro se for nota sob cerebro/
        if payload.path.startswith("cerebro/"):
            try:
                rel = payload.path.replace("cerebro/", "")
                store._update_fts_index(rel, payload.content)
            except Exception:
                pass

        # Registra no changelog defensivamente
        try:
            _record_changelog(
                data_dir=store.data_dir,
                rel_path=payload.path,
                author="Usuário (Web)",
                action="update",
                summary=f"Atualização manual de {payload.path} ({len(payload.content.encode('utf-8'))} bytes)",
            )
        except Exception as log_err:
            logger.warning("Não foi possível gravar no changelog: %s", log_err)

        new_hash = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
        return {"success": True, "path": payload.path, "hash": new_hash}
    except SecurityPathError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as exc:
        logger.error("Erro ao salvar nota do cérebro: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro interno ao gravar arquivo: {exc}")


@router.get("/api/brain/changelog")
def get_brain_changelog(request: Request, limit: int = Query(25, ge=1, le=100)):
    """Retorna os eventos mais recentes do cérebro com diffs resumidos."""
    auth.require_owner(request)
    store = BrainStore()
    log_file = _get_changelog_path(store.data_dir)
    if not log_file.exists():
        return {"items": []}

    entries = []
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                    if len(entries) >= limit:
                        break
                except json.JSONDecodeError:
                    continue
    except Exception as exc:
        logger.warning("Falha ao ler changelog: %s", exc)

    return {"items": entries}

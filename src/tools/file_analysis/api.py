"""Rotas autenticadas para documentos privados; sem multipart nem paths arbitrários.

O corpo de upload é application/octet-stream e o nome vai na query string,
sempre escapado via encodeURIComponent pelo cliente. O limite é imposto durante
a leitura do stream, antes de executar qualquer parser.
"""
import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from src.security import auth
from src.tools.file_analysis import service
from src.tools.file_analysis.contracts import FileRejected, MAX_BYTES

router = APIRouter(tags=["Arquivos privados"])
logger = logging.getLogger(__name__)


ASSETS = Path(__file__).with_name("templates")


@router.get("/files/view")
def file_view(request: Request):
    auth.require_owner(request)
    return FileResponse(
        ASSETS / "files.html", media_type="text/html",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'self'; script-src 'self'; "
                "connect-src 'self'; base-uri 'none'; form-action 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/files/assets.js")
def file_js(request: Request):
    auth.require_owner(request)
    return FileResponse(ASSETS / "assets.js", media_type="application/javascript",
                        headers={"Cache-Control": "private, no-store",
                                 "X-Content-Type-Options": "nosniff"})


@router.get("/files/assets.css")
def file_css(request: Request):
    auth.require_owner(request)
    return FileResponse(ASSETS / "assets.css", media_type="text/css",
                        headers={"Cache-Control": "private, no-store",
                                 "X-Content-Type-Options": "nosniff"})


@router.get("/files/capabilities")
def file_capabilities(request: Request):
    auth.require_owner(request)
    return service.capabilities()


@router.post("/files/upload", status_code=201)
async def file_upload(request: Request, filename: str = Query(min_length=1, max_length=120)):
    """Autenticação precede leitura; bytes rejeitados ao atingir MAX_BYTES + 1."""
    auth.require_owner(request)
    if request.headers.get("content-type", "").split(";", 1)[0].lower().strip() != "application/octet-stream":
        raise HTTPException(415, "Envie o arquivo como application/octet-stream.")
    declared = request.headers.get("content-length")
    if declared and declared.isdecimal() and int(declared) > MAX_BYTES:
        raise HTTPException(413, "Arquivo acima do limite de 8 MB.")
    chunks = []
    size = 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BYTES:
                raise HTTPException(413, "Arquivo acima do limite de 8 MB.")
            chunks.append(chunk)
        result = await asyncio.to_thread(service.ingest, b"".join(chunks), filename)
    except FileRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        logger.warning("Armazenamento de arquivo falhou: %s", type(exc).__name__)
        raise HTTPException(503, "Armazenamento privado indisponível.") from exc
    return result


@router.get("/files/{file_id}")
async def file_inspect(file_id: str, request: Request):
    auth.require_owner(request)
    try:
        result = await asyncio.to_thread(service.inspect, file_id)
    except FileRejected as exc:
        raise HTTPException(404, "Arquivo não encontrado ou inválido.") from exc
    except OSError as exc:
        logger.warning("Consulta de arquivo falhou: %s", type(exc).__name__)
        raise HTTPException(503, "Armazenamento privado indisponível.") from exc
    if result["status"] == "failed":
        code = result["error"]["code"]
        status = 503 if code in ("worker_unavailable", "timeout", "worker_failed") else 422
        return JSONResponse(status_code=status, content=result)
    return result


@router.delete("/files/{file_id}")
async def file_delete(file_id: str, request: Request):
    auth.require_owner(request)
    try:
        return await asyncio.to_thread(service.remove, file_id)
    except FileRejected as exc:
        raise HTTPException(404, "Arquivo não encontrado ou inválido.") from exc
    except OSError as exc:
        logger.warning("Exclusão de arquivo falhou: %s", type(exc).__name__)
        raise HTTPException(503, "Não foi possível excluir o arquivo privado.") from exc

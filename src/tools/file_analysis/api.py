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
from pydantic import BaseModel, Field, field_validator

from src.security import auth
from src.tools.file_analysis import service
from src.tools.file_analysis.context import retrieve as retrieve_context
from src.tools.file_analysis.contracts import FILE_ID, FileRejected, MAX_BYTES
from src.tools import vision

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


class FileQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=500)

    @field_validator("question")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("A pergunta não pode ser vazia.")
        return value.strip()


def _valid_id(file_id):
    if FILE_ID.fullmatch(file_id) is None:
        raise HTTPException(404, "Arquivo não encontrado.")


@router.get("/files/vision/status")
async def file_vision_status(request: Request):
    """A disponibilidade do Ollama é informativa: não é benchmark visual."""
    auth.require_owner(request)
    return await asyncio.to_thread(vision.status)


@router.post("/files/{file_id}/context")
async def file_context(file_id: str, body: FileQuestion, request: Request):
    """Seleciona trechos ancorados; não interpreta nem responde com LLM."""
    auth.require_owner(request)
    _valid_id(file_id)
    try:
        output = await asyncio.to_thread(retrieve_context, file_id, body.question)
    except FileRejected as exc:
        raise HTTPException(404, "Arquivo não encontrado ou inválido.") from exc
    except ValueError as exc:
        raise HTTPException(422, "Pergunta documental inválida.") from exc
    except OSError as exc:
        logger.warning("Contexto documental indisponível: %s", type(exc).__name__)
        raise HTTPException(503, "Leitor documental indisponível.") from exc
    if output["status"] == "failed":
        return JSONResponse(status_code=503, content=output)
    return output


@router.post("/files/{file_id}/vision")
async def file_vision(file_id: str, body: FileQuestion, request: Request):
    """Visão só com modelo local já instalado e resultado claramente não verificado."""
    auth.require_owner(request)
    _valid_id(file_id)
    try:
        output = await asyncio.to_thread(vision.inspect_image, file_id, body.question)
    except FileRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    except (OSError, ValueError) as exc:
        logger.warning("Análise visual indisponível: %s", type(exc).__name__)
        raise HTTPException(503, "Análise visual local indisponível.") from exc
    if output["status"] == "unavailable":
        return JSONResponse(status_code=503, content=output)
    if output["status"] == "failed":
        return JSONResponse(status_code=502, content=output)
    return output


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

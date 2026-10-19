"""Chat E E5: acesso autenticado a evidências locais já minimizadas pelo Chat C.

A rota jamais recebe comandos, scripts, paths, nomes de serviço ou parâmetros
de coleta do navegador. Ela não instala, reinicia, nem testa inferência Ollama.
"""
import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ops.doctor import run_checks
from ops.observability import build_snapshot
from src.security import auth

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Observabilidade privada"])
_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
_CONCURRENT = asyncio.Semaphore(2)


@router.get("/ops/diagnostics")
async def diagnostics(request: Request):
    """GET exclusivamente consultivo. Autenticação precede qualquer I/O."""
    auth.require_owner(request)
    # Evita múltiplos probes concorrentes solicitados por sessões autenticadas.
    # Nunca aceita parâmetros do cliente como portas, comandos ou diretórios.
    try:
        async with _CONCURRENT:
            report = await asyncio.wait_for(asyncio.to_thread(run_checks), timeout=9.0)
        snapshot = build_snapshot(doctor_report=report)
        if (snapshot.get("contract") != "menor.ops.observability"
                or snapshot.get("read_only") is not True):
            raise ValueError("Envelope inválido.")
    except (OSError, ValueError, RuntimeError, asyncio.TimeoutError) as error:
        logger.warning("Diagnóstico privado indisponível: %s", type(error).__name__)
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "error": "diagnostics_unavailable"},
            headers=_HEADERS,
        )
    return JSONResponse(content=snapshot, headers=_HEADERS)

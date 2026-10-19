"""Chat E E5: acesso autenticado a evidências locais já minimizadas pelo Chat C.

A rota jamais recebe comandos, scripts, paths, nomes de serviço ou parâmetros
de coleta do navegador. Ela não instala, reinicia, nem testa inferência Ollama.
"""
import asyncio
import logging
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ops.doctor import run_checks
from ops.observability import build_snapshot
from src.security import auth

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Observabilidade privada"])
_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
# Uma vaga pertence à thread real até o fim do probe. Um timeout HTTP não
# libera uma vaga enquanto o trabalho em execução ainda não terminou.
_SLOTS = threading.BoundedSemaphore(2)


def _run_with_slot():
    try:
        return run_checks()
    finally:
        _SLOTS.release()


@router.get("/ops/diagnostics")
async def diagnostics(request: Request):
    """GET exclusivamente consultivo. Autenticação precede qualquer I/O."""
    auth.require_owner(request)
    # Evita múltiplos probes concorrentes solicitados por sessões autenticadas.
    # Nunca aceita parâmetros do cliente como portas, comandos ou diretórios.
    # Falhar imediatamente quando todas as verificações já estão ocupadas.
    # Não agendar threads adicionais para aguardarem indefinidamente.
    if not _SLOTS.acquire(blocking=False):
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "error": "diagnostics_unavailable"},
            headers=_HEADERS,
        )
    try:
        # shield impede que o timeout cancele a tarefa que libera a vaga.
        worker = asyncio.create_task(asyncio.to_thread(_run_with_slot))
    except Exception:
        _SLOTS.release()
        raise
    try:
        report = await asyncio.wait_for(asyncio.shield(worker), timeout=9.0)
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

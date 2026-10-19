"""Chat E: rotas somente leitura da interface de objetivos.

Os estados continuam pertencendo ao agente (Chat A); este módulo não executa
missões, não cria memória e não adiciona permissões.
"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from src.security import auth

router = APIRouter(tags=["Painel privado de objetivos"])
ASSETS = Path(__file__).with_name("workspace_assets")
NO_STORE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
PAGE_HEADERS = {
    **NO_STORE,
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
}


@router.get("/workspace/objectives")
def objectives_page(request: Request):
    auth.require_owner(request)
    return FileResponse(ASSETS / "objectives.html", media_type="text/html", headers=PAGE_HEADERS)


@router.get("/workspace/assets.css")
def objectives_css(request: Request):
    auth.require_owner(request)
    return FileResponse(ASSETS / "assets.css", media_type="text/css", headers=NO_STORE)


@router.get("/workspace/assets.js")
def objectives_js(request: Request):
    auth.require_owner(request)
    return FileResponse(ASSETS / "assets.js", media_type="application/javascript", headers=NO_STORE)

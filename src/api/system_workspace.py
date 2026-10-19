"""Chat E: painéis privados de status sem terminal ou efeitos operacionais."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from src.security import auth

router = APIRouter(tags=["Painel de capacidades"])
ASSETS = Path(__file__).with_name("system_assets")
NO_STORE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
CSP = (
    "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


@router.get("/workspace/system")
def status_page(request: Request):
    auth.require_owner(request)
    return FileResponse(ASSETS / "system.html", media_type="text/html",
                        headers={**NO_STORE, "Content-Security-Policy": CSP})


@router.get("/workspace/system/assets.css")
def status_css(request: Request):
    auth.require_owner(request)
    return FileResponse(ASSETS / "assets.css", media_type="text/css", headers=NO_STORE)


@router.get("/workspace/system/assets.js")
def status_js(request: Request):
    auth.require_owner(request)
    return FileResponse(ASSETS / "assets.js", media_type="application/javascript", headers=NO_STORE)

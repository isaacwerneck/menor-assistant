"""Chat E: painéis privados de status sem terminal ou efeitos operacionais."""
from pathlib import Path
import os
import threading

import requests
from ops import monitor
from ops.model_latency import local_endpoint, model_identifier

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


_LIVE_LOCK = threading.Lock()
_PREVIOUS_CPU = None


def _gpu_busy():
    """Uso instantâneo opcional fornecido pelo driver; nunca deduzir de VRAM."""
    for name in ("card0", "card1", "card2"):
        path = Path("/sys/class/drm") / name / "device/gpu_busy_percent"
        try:
            raw = path.read_text(encoding="ascii").strip()
            value = float(raw)
            if 0 <= value <= 100:
                return round(value, 1)
        except (OSError, ValueError):
            continue
    return None


@router.get("/workspace/system/live")
def live_resources(request: Request):
    """Snapshot privado, leve, somente leitura. CPU exige duas coletas."""
    auth.require_owner(request)
    global _PREVIOUS_CPU
    try:
        cpu = monitor.cpu_times()
        memory = monitor.meminfo()
    except (OSError, ValueError):
        cpu, memory = {}, {}
    with _LIVE_LOCK:
        before = _PREVIOUS_CPU
        _PREVIOUS_CPU = cpu or None
    total = memory.get("MemTotal", 0)
    available = memory.get("MemAvailable", memory.get("MemFree", 0))
    used = max(0, total - available)
    usage = monitor.cpu_percent(before, cpu).get("cpu") if before else None
    models = []
    ollama_state = "unavailable"
    try:
        base = local_endpoint(os.environ.get(
            "OLLAMA_URL", "http://127.0.0.1:11434")).rsplit("/", 1)[0]
        with requests.get(base + "/ps", timeout=(2, 3)) as response:
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            raise ValueError("Resposta de modelos inválida.")
        for item in data["models"][:8]:
            if not isinstance(item, dict):
                continue
            try:
                name = model_identifier(item.get("name"))
            except ValueError:
                continue
            vram = item.get("size_vram")
            size = item.get("size")
            models.append({"name": name,
                           "size_mib": round(size / monitor.MIB, 1)
                           if type(size) is int and size >= 0 else None,
                           "gpu_loaded_mib": round(vram / monitor.MIB, 1)
                           if type(vram) is int and vram >= 0 else None})
        ollama_state = "available"
    except (ValueError, TypeError, requests.RequestException):
        pass
    gpu = _gpu_busy()
    return {"cpu_percent": round(usage, 1) if usage is not None else None,
            "ram_percent": round(100 * used / total, 1) if total else None,
            "ram_used_mib": round(used / monitor.MIB, 1) if total else None,
            "ram_total_mib": round(total / monitor.MIB, 1) if total else None,
            "gpu_percent": gpu,
            "gpu_source": "sysfs_driver" if gpu is not None else "unavailable",
            "ollama": ollama_state, "loaded_models": models,
            "sampling": "polling_read_only", "cpu_basis": "delta_between_requests"}

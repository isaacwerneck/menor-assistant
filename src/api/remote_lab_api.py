"""Read-only, bearer-authenticated remote inference probe.

Set MENOR_LAB_API_TOKEN to a random 32+ character secret in the Ubuntu
service environment. Never place it in Git, URLs, query parameters or logs.
Only /lab/api/compare accepts this token; no owner privileges are granted.
"""
import hmac
import os
import time

from fastapi import APIRouter, HTTPException, Request

from src.api import remote_lab

router = APIRouter()


def _authorize(request: Request):
    expected = os.environ.get("MENOR_LAB_API_TOKEN", "")
    header = request.headers.get("authorization", "")
    prefix = "Bearer "
    if (len(expected) < 32 or len(expected) > 256
            or not header.startswith(prefix)
            or len(header) > 300
            or not hmac.compare_digest(header[len(prefix):], expected)):
        raise HTTPException(401, "Unauthorized")
    # A token is NOT a replacement for TLS and tunnel access controls.
    if request.headers.get("origin"):
        raise HTTPException(403, "Browser origins are not permitted")
    if os.environ.get("MENOR_LAB_REMOTE_ENABLED") != "1":
        raise HTTPException(503, "Remote laboratory is disabled")


@router.post("/lab/api/compare")
def remote_compare(body: remote_lab.LabRequest, request: Request):
    _authorize(request)
    remote_lab._limit(time.monotonic())
    if not remote_lab._INFERENCE.acquire(blocking=False):
        raise HTTPException(429, "Inference busy")
    started = time.monotonic()
    try:
        try:
            result = (remote_lab._planner(body) if body.mode == "planner"
                      else remote_lab._direct(body))
        except (Exception,) as error:
            # Keep details off the public API and out of the response.
            remote_lab.LOGGER.warning("Remote lab failed: %s", type(error).__name__)
            result = {"status": "inference_failed", "reply": "Inference unavailable",
                      "model": None, "move": None}
    finally:
        remote_lab._INFERENCE.release()
    return {"mode": body.mode, **result,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "tools_executed": 0, "history_saved": False}

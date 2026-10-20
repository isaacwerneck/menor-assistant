"""Laboratório remoto autenticado para observar a inferência REAL do Ubuntu.

Não executa ferramentas, não escreve memória, não salva conversas ou credenciais.
Este endpoint NÃO substitui o teste de conversa completo na interface principal.
"""
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Literal

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator

from src.agent import intelligence
from src.agent.plan_constraints import warnings as constraint_warnings, required_stage_warnings
from ops.model_latency import local_endpoint, model_identifier, numeric_summary
from src.agent.voice import LAB_BASELINE_VOICE, NATURAL_VOICE, LAB_ASSISTANT_VOICE
from src.agent.response_budget import output_budget
from src.security import auth

router = APIRouter()
LOGGER = logging.getLogger(__name__)
_LOCK = threading.Lock()
_CALLS = deque()
WINDOW_SECONDS = 300
MAX_CALLS = 10
_INFERENCE = threading.BoundedSemaphore(1)
ROOT = Path(__file__).resolve().parent / "templates"


class LabMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1000)


class LabRequest(BaseModel):
    mode: Literal["planner", "direct"]
    profile: Literal["baseline", "natural", "assistant"] = "baseline"
    message: str = Field(min_length=1, max_length=1200)
    history: list[LabMessage] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def check_total(self):
        if not self.message.strip() or len(self.message) + sum(
                len(item.content) for item in self.history) > 4200:
            raise ValueError("Histórico do laboratório excede o limite.")
        return self


def _limit(now):
    """Limita carga do Qwen, inclusive por navegadores diferentes no mesmo proxy."""
    with _LOCK:
        while _CALLS and now - _CALLS[0] > WINDOW_SECONDS:
            _CALLS.popleft()
        if len(_CALLS) >= MAX_CALLS:
            raise HTTPException(429, "Laboratório temporariamente limitado. Aguarde.")
        _CALLS.append(now)


def _direct(payload):
    """Baseline sem o roteador JSON nem ferramentas; somente inferência local."""
    url = local_endpoint(os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
    model = model_identifier(os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"))
    natural = payload.profile == "natural"
    assistant = payload.profile == "assistant"
    voice = LAB_ASSISTANT_VOICE if assistant else (
        NATURAL_VOICE if natural else LAB_BASELINE_VOICE
    )
    token_budget = output_budget(payload.message) if assistant else 256
    messages = [{"role": "system", "content": voice}]
    messages.extend(item.model_dump() for item in payload.history)
    messages.append({"role": "user", "content": payload.message})
    with requests.post(
        url,
        json={"model": model, "messages": messages,
              "stream": False, "options": {
                  "temperature": 0.25 if natural else 0.1,
                  "num_predict": token_budget,
              }},
        timeout=(4, 50),
    ) as response:
        response.raise_for_status()
        result = response.json()
    item = result.get("message")
    if not isinstance(item, dict) or not isinstance(item.get("content"), str):
        raise ValueError("Resposta do Ollama inválida.")
    return {"status": "answered", "reply": item["content"][:1800],
            "model": model, "move": None, "performance": numeric_summary(result),
            "prompt_chars": sum(len(entry["content"]) for entry in messages),
            "output_budget_tokens": token_budget, "profile": payload.profile,
            "output_limited": result.get("done_reason") == "length",
            "reply_truncated": len(item["content"]) > 1800}


def _planner(payload):
    """A mesma decisão estruturada da frente A, mas sem memória nem ferramentas."""
    local_endpoint(os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
    model = model_identifier(os.environ.get("MENOR_REASONING_MODEL") or os.environ.get(
        "OLLAMA_ROUTER_MODEL", os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")))
    diagnostics = {}
    result = intelligence.decide(
        payload.message,
        [item.model_dump() for item in payload.history],
        tools=[], capabilities=[], knowledge="", feedback_examples=[],
        paused_goals=[], pending=None, last_result=None, preferences="", diagnostics=diagnostics,
    )
    if result is None:
        return {"status": "no_valid_decision", "reply":
                "O modelo não produziu uma decisão válida no limite configurado.",
                "model": model, "move": None, "diagnostics": diagnostics,
                "performance": diagnostics.get("performance", {})}
    # Decisão validada = estrutura/contrato, não prova de qualidade nem execução.
    plan_warnings = []
    if result["move"] in ("plan", "continue"):
        plan_warnings = constraint_warnings(payload.message, result.get("steps", []))
        plan_warnings += required_stage_warnings(payload.message, result.get("steps", []))
    if result["move"] in ("plan", "continue"):
        reply = intelligence.render_plan(result)
    else:
        reply = result.get("reply") or result.get("question") or ""
    return {"status": "decision_validated", "plan_quality_verified": False,
            "plan_warnings": plan_warnings, "reply": reply[:1800],
            "model": model, "move": result["move"], "diagnostics": diagnostics,
            "performance": diagnostics.get("performance", {}), "reply_truncated": len(reply) > 1800}


@router.get("/lab/view", response_class=HTMLResponse)
def laboratory_page(request: Request):
    auth.require_owner(request)
    return HTMLResponse(
        (ROOT / "remote_lab.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY",
                 "Referrer-Policy": "no-referrer"},
    )


@router.post("/lab/compare")
def laboratory_turn(body: LabRequest, request: Request):
    auth.require_owner(request)
    _limit(time.monotonic())
    if not _INFERENCE.acquire(blocking=False):
        raise HTTPException(429, "Outra avaliação está em andamento; aguarde.")
    start = time.monotonic()
    try:
        try:
            data = _planner(body) if body.mode == "planner" else _direct(body)
        except (requests.RequestException, ValueError, TypeError, KeyError) as error:
            LOGGER.warning("Laboratório falhou: %s", type(error).__name__)
            data = {"status": "inference_failed", "reply": "Falha ou timeout na inferência.",
                    "model": None, "move": None}
    finally:
        _INFERENCE.release()
    return {
        "mode": body.mode, **data,
        "elapsed_seconds": round(max(0, time.monotonic() - start), 3),
        "tools_executed": 0,
        "history_saved": False,
        "limitations": "Teste do modelo, não execução integral do Menor.",
    }

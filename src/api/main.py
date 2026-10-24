"""Servidor de API do Menor v2.

Gerencia autenticação do proprietário, cérebro persistente (SQLite FTS5),
painéis web estáticos, orquestração de ferramentas reais do SO e streaming SSE.
"""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
from typing import Annotated, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, StringConstraints
import requests
import time
import threading

from src.agent.orchestrator import Orchestrator
from src.agent.workers import get_task_queue
from src.memory.search import KnowledgeIndex
from src.memory.store import BrainStore
from src.security import auth

# Routers de suporte
from src.api.system_workspace import router as system_workspace_router
from src.api.workspace import router as workspace_router

logger = logging.getLogger(__name__)

OLLAMA_SERVER_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "-1")
TEMPLATES_DIR = Path(__file__).parent / "templates"

# --- IDLE STUDY & PREEMPTION STATE ---
_last_interaction_time = time.time()
_study_abort_event = threading.Event()
_study_running_lock = threading.Lock()
IDLE_STUDY_DELAY = int(os.environ.get("MENOR_IDLE_STUDY_DELAY", "1800"))


def _notify_user_active():
    """Registra interação humana e sinaliza interrupção imediata ao worker se ativo."""
    global _last_interaction_time
    _last_interaction_time = time.time()
    if not _study_abort_event.is_set():
        _study_abort_event.set()


async def _idle_study_monitor():
    """Monitor de inatividade: ativa o estudo autônomo após 30 min sem requests."""
    await asyncio.sleep(5)
    while True:
        await asyncio.sleep(15)
        idle_seconds = time.time() - _last_interaction_time
        if idle_seconds >= IDLE_STUDY_DELAY:
            if _study_running_lock.acquire(blocking=False):
                try:
                    _study_abort_event.clear()
                    from src.agent.study import run_autonomous_cycle
                    logger.info(
                        "Iniciando ciclo autônomo (Refletir -> Estudar -> Diagnosticar) por inatividade (%ds)...",
                        int(idle_seconds),
                    )
                    await asyncio.to_thread(
                        run_autonomous_cycle, ollama_url=OLLAMA_SERVER_URL, abort_event=_study_abort_event
                    )
                except Exception as exc:
                    logger.debug("Ciclo de estudo em background: %s", exc)
                finally:
                    _study_running_lock.release()


def get_active_model(preferred: Optional[str] = None) -> str:
    """Detecta o modelo disponível no Ollama do servidor, com fallback seguro para qwen2.5:7b."""
    if preferred:
        return preferred
    configured = os.environ.get("OLLAMA_MODEL")
    if configured:
        return configured
    try:
        resp = requests.get(f"{OLLAMA_SERVER_URL}/api/tags", timeout=2)
        if resp.status_code == 200:
            installed = [m.get("name", "") for m in resp.json().get("models", [])]
            candidates = [
                "qwen-fast", "qwen2.5:14b-instruct-q3_K_M", "qwen2.5:7b",
                "qwen2.5:latest", "qwen2.5:14b", "qwen2.5"
            ]
            for candidate in candidates:
                for m in installed:
                    if candidate in m:
                        return m
            if installed:
                return installed[0]
    except Exception:
        pass
    return DEFAULT_MODEL


async def _warmup_model():
    """Pré-aquece o modelo na RAM em background para eliminar o cold start de 20s na primeira mensagem."""
    await asyncio.sleep(0.5)
    target_model = get_active_model()
    try:
        # Envia requisição com keep_alive: -1 para manter os pesos carregados na RAM
        requests.post(
            f"{OLLAMA_SERVER_URL}/api/generate",
            json={"model": target_model, "prompt": "", "keep_alive": -1},
            timeout=40,
        )
        logger.info("Modelo %s carregado previamente na RAM com sucesso.", target_model)
    except Exception as exc:
        logger.debug("Warmup em background: %s", exc)


@asynccontextmanager
async def app_lifespan(_app):
    BrainStore().initialize()
    asyncio.create_task(_warmup_model())
    asyncio.create_task(_idle_study_monitor())
    yield


app = FastAPI(
    lifespan=app_lifespan,
    title="Menor v2 - Assistente de IA Pessoal",
    description="Assistente executivo local e distribuído com ferramentas reais.",
    version="2.0.0",
)

app.include_router(system_workspace_router)
app.include_router(workspace_router)

MessageText = Annotated[str, StringConstraints(min_length=1, max_length=16000, pattern=r"\S")]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: MessageText


class ChatRequest(BaseModel):
    message: MessageText
    model: Optional[str] = Field(default=None, max_length=200)
    node: Optional[Literal["server", "local"]] = Field(default="server")
    ollama_url: Optional[str] = Field(default=None, max_length=300)
    history: List[ChatMessage] = Field(default_factory=list, max_length=40)
    project: Optional[str] = Field(default=None, max_length=64)


class AgentRunRequest(ChatRequest):
    session_id: Optional[str] = Field(default="default-session", max_length=80)
    turn_id: Optional[str] = Field(default="turn-1", max_length=80)


class PasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class RememberRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    kind: Literal["preference", "knowledge", "project", "tool"]


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10)


class TaskEnqueueRequest(BaseModel):
    goal: str = Field(min_length=5, max_length=2000)
    project_slug: Optional[str] = Field(default=None, max_length=64)


def require_chat_access(request: Request):
    if auth.configured() or auth.public_origin():
        auth.require_owner(request)


# --- ROTAS PRINCIPAIS ---

@app.get("/", response_class=HTMLResponse)
def serve_chat_ui():
    html_file = TEMPLATES_DIR / "chat.html"
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@app.get("/health")
def health_check():
    ollama_status = "offline"
    models_available = []
    try:
        with requests.get(f"{OLLAMA_SERVER_URL}/api/tags", timeout=(2, 2)) as resp:
            if resp.status_code == 200:
                ollama_status = "online"
                models_available = [m.get("name", "") for m in resp.json().get("models", [])]
    except Exception:
        pass

    active_model = get_active_model()
    return {
        "status": "online",
        "service": "Menor API",
        "version": app.version,
        "api_contract": 1,
        "ollama_status": ollama_status,
        "default_model": active_model,
        "installed_models": models_available,
        "server_ollama_url": OLLAMA_SERVER_URL,
    }


@app.get("/api/nodes")
def list_nodes():
    """Retorna os nós de computação configurados (Servidor e PC Local)."""
    active_model = get_active_model()
    return {
        "server": {
            "name": f"Servidor Ubuntu ({active_model})",
            "ollama_url": OLLAMA_SERVER_URL,
            "recommended_model": active_model,
            "type": "server",
        },
        "local": {
            "name": "PC Principal (GPU GTX 1650)",
            "ollama_url": "http://localhost:11434",
            "recommended_model": "qwen2.5:7b",
            "type": "local",
        },
    }


@app.get("/models")
def list_models(_access=Depends(require_chat_access)):
    try:
        with requests.get(f"{OLLAMA_SERVER_URL}/api/tags", timeout=(3, 5)) as resp:
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao consultar modelos no Ollama: {exc}")


# --- AUTENTICAÇÃO ---

@app.get("/auth/status")
def auth_status(request: Request):
    return {"configured": auth.configured(), "authenticated": auth.is_authenticated(request)}


@app.post("/auth/setup")
def auth_setup(body: PasswordRequest, request: Request, response: Response):
    config = auth.create_owner(request, body.password)
    auth.set_session_cookie(response, request, auth.login(request, body.password))
    return {"ok": bool(config)}


@app.post("/auth/login")
def auth_login(body: PasswordRequest, request: Request, response: Response):
    auth.set_session_cookie(response, request, auth.login(request, body.password))
    return {"ok": True}


@app.post("/auth/logout")
def auth_logout(request: Request, response: Response):
    auth.check_origin(request)
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


# --- CHAT & AGENTE ---

@app.post("/agent/run")
def agent_run(body: AgentRunRequest, request: Request):
    _notify_user_active()
    auth.require_owner(request)
    target_url = body.ollama_url or OLLAMA_SERVER_URL
    target_model = body.model or get_active_model()
    orchestrator = Orchestrator(ollama_url=target_url, default_model=target_model)
    messages = [item.model_dump() for item in body.history] + [{"role": "user", "content": body.message}]
    result = orchestrator.run_turn(messages=messages, model=target_model, ollama_url=target_url)
    return {
        "handled": True,
        "reply": result.get("reply", ""),
        "tools_executed": result.get("tools_executed", []),
        "model_used": result.get("model_used"),
        "node_url": result.get("node_url"),
    }


@app.post("/chat")
def chat_sync(req: ChatRequest, _access=Depends(require_chat_access)):
    _notify_user_active()
    target_url = req.ollama_url or (OLLAMA_SERVER_URL if req.node != "local" else "http://localhost:11434")
    target_model = req.model or (get_active_model() if req.node != "local" else "qwen2.5:7b")
    orchestrator = Orchestrator(ollama_url=target_url, default_model=target_model)
    messages = [item.model_dump() for item in req.history] + [{"role": "user", "content": req.message}]
    result = orchestrator.run_turn(messages=messages, model=target_model, ollama_url=target_url)
    return {
        "reply": result.get("reply", ""),
        "model": target_model,
        "tools_executed": result.get("tools_executed", []),
    }


@app.post("/chat/stream")
def chat_stream(req: ChatRequest, _access=Depends(require_chat_access)):
    _notify_user_active()
    target_url = req.ollama_url or (OLLAMA_SERVER_URL if req.node != "local" else "http://localhost:11434")
    target_model = req.model or (get_active_model() if req.node != "local" else "qwen2.5:7b")

    payload = {
        "model": target_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é o Menor v2, assistente executivo e parceiro de engenharia do Isaac. "
                    "Compreenda perfeitamente gírias e abreviações da internet brasileira (vc, hj, eai, blz). "
                    "Responda sempre de forma natural, calorosa e fluente em português brasileiro."
                ),
            },
            *[item.model_dump() for item in req.history],
            {"role": "user", "content": req.message},
        ],
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "temperature": 0.6,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
        },
    }

    def sse_generator():
        try:
            with requests.post(f"{target_url}/api/chat", json=payload, stream=True, timeout=(15, 600)) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        return
        except Exception as exc:
            logger.error("Erro no streaming do Ollama: %s", exc)
            yield f"\n[Erro de conexão com o modelo: {str(exc)}]"

    return StreamingResponse(
        sse_generator(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- MEMÓRIA (SQLite FTS5) ---

@app.get("/memory/preferences")
def list_preferences(request: Request):
    auth.require_owner(request)
    return {"preferences": BrainStore().preference_context()}


@app.post("/memory/search")
def memory_search(body: KnowledgeSearchRequest, request: Request):
    auth.require_owner(request)
    try:
        results = KnowledgeIndex().search(body.query, limit=body.limit)
        return {"items": results}
    except Exception as exc:
        raise HTTPException(503, f"Falha na busca de memória: {exc}")


@app.post("/memory/remember")
def memory_remember(body: RememberRequest, request: Request):
    auth.require_owner(request)
    try:
        store = BrainStore()
        store.initialize()
        safe_name = f"memoria_{int(asyncio.get_event_loop().time() * 1000)}.md"
        rel_path = f"conhecimentos/{safe_name}" if body.kind == "knowledge" else f"preferencias/{safe_name}"
        store.write_note(rel_path, body.text)
        return {"saved": True, "path": rel_path}
    except Exception as exc:
        raise HTTPException(422, f"Erro ao salvar memória: {exc}")


# --- TAREFAS EM SEGUNDO PLANO ---

@app.post("/api/tasks/enqueue")
def enqueue_task(body: TaskEnqueueRequest, request: Request):
    auth.require_owner(request)
    queue = get_task_queue()
    task_id = queue.enqueue(goal=body.goal, project_slug=body.project_slug)
    return {"task_id": task_id, "status": "pending", "goal": body.goal}


@app.get("/api/tasks")
def list_tasks(request: Request):
    auth.require_owner(request)
    queue = get_task_queue()
    return {"tasks": queue.list_tasks()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)


# --- ENDPOINTS DE ESTUDO & AUTO-DIAGNÓSTICO ---

@app.get("/api/study/status")
def study_status(request: Request):
    auth.require_owner(request)
    from src.agent.study import CheckpointManager, TopicManager
    tm = TopicManager()
    cm = CheckpointManager()
    return {
        "idle_seconds": int(time.time() - _last_interaction_time),
        "idle_threshold": IDLE_STUDY_DELAY,
        "is_studying": _study_running_lock.locked(),
        "checkpoint": cm.load_checkpoint(),
        "uncompleted_topics": tm.list_topics(uncompleted_only=True),
    }


@app.post("/api/study/trigger")
def study_trigger(request: Request):
    auth.require_owner(request)
    if _study_running_lock.acquire(blocking=False):
        try:
            _study_abort_event.clear()
            from src.agent.study import run_autonomous_cycle
            res = run_autonomous_cycle(ollama_url=OLLAMA_SERVER_URL, abort_event=_study_abort_event)
            return {"success": True, "result": res}
        finally:
            _study_running_lock.release()
    return {"success": False, "message": "O worker de estudo já está em execução."}


@app.post("/api/diagnostic/run")
def diagnostic_run(request: Request):
    auth.require_owner(request)
    from src.agent.study import DiagnosticEngine
    engine = DiagnosticEngine(ollama_url=OLLAMA_SERVER_URL)
    result = engine.run_self_eval()
    return {"success": True, "diagnostic": result}


@app.get("/api/study/report")
def study_report(request: Request):
    auth.require_owner(request)
    from src.tools.core import get_study_report
    return get_study_report()

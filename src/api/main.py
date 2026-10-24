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
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")
KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "24h")
TEMPLATES_DIR = Path(__file__).parent / "templates"


@asynccontextmanager
async def app_lifespan(_app):
    BrainStore().initialize()
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
    try:
        with requests.get(f"{OLLAMA_SERVER_URL}/api/tags", timeout=(2, 2)) as resp:
            if resp.status_code == 200:
                ollama_status = "online"
    except Exception:
        pass

    return {
        "status": "online",
        "service": "Menor API",
        "version": app.version,
        "api_contract": 1,
        "ollama_status": ollama_status,
        "default_model": DEFAULT_MODEL,
        "server_ollama_url": OLLAMA_SERVER_URL,
    }


@app.get("/api/nodes")
def list_nodes():
    """Retorna os nós de computação configurados (Servidor e PC Local)."""
    return {
        "server": {
            "name": "Servidor Ubuntu (Cérebro Central)",
            "ollama_url": OLLAMA_SERVER_URL,
            "recommended_model": DEFAULT_MODEL,
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
    auth.require_owner(request)
    target_url = body.ollama_url or OLLAMA_SERVER_URL
    target_model = body.model or DEFAULT_MODEL
    orchestrator = Orchestrator(ollama_url=target_url, default_model=target_model)
    messages = [item.model_dump() for item in body.history] + [{"role": "user", "content": body.message}]
    result = orchestrator.run_turn(messages=messages, model=body.model, ollama_url=body.ollama_url)
    return {
        "handled": True,
        "reply": result.get("reply", ""),
        "tools_executed": result.get("tools_executed", []),
        "model_used": result.get("model_used"),
        "node_url": result.get("node_url"),
    }


@app.post("/chat")
def chat_sync(req: ChatRequest, _access=Depends(require_chat_access)):
    target_url = req.ollama_url or (OLLAMA_SERVER_URL if req.node != "local" else "http://localhost:11434")
    target_model = req.model or (DEFAULT_MODEL if req.node != "local" else "qwen2.5:7b")
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
    target_url = req.ollama_url or (OLLAMA_SERVER_URL if req.node != "local" else "http://localhost:11434")
    target_model = req.model or (DEFAULT_MODEL if req.node != "local" else "qwen2.5:7b")

    payload = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": "Você é o Menor v2, assistente pessoal direto e inteligente em pt-BR."},
            *[item.model_dump() for item in req.history],
            {"role": "user", "content": req.message},
        ],
        "stream": True,
        "keep_alive": KEEP_ALIVE,
    }

    def sse_generator():
        try:
            with requests.post(f"{target_url}/api/chat", json=payload, stream=True, timeout=(5, 120)) as resp:
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

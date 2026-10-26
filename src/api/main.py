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
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, PlainTextResponse
from pydantic import BaseModel, Field, StringConstraints
import requests
import re
import time
import threading

from src.agent.orchestrator import Orchestrator
from src.agent.cleaner import sanitize_assistant_reply, _fallback_casual_reply
from src.agent.workers import get_task_queue
from src.memory.search import KnowledgeIndex
from src.memory.store import BrainStore
from src.security import auth

# Routers de suporte
from src.api.system_workspace import router as system_workspace_router
from src.api.workspace import router as workspace_router
from src.api.private_diagnostics import router as private_diagnostics_router
from src.lab.api import router as lab_router
from src.tools.file_analysis.api import router as file_analysis_router
from src.api.brain_workspace import router as brain_workspace_router
from src.projects.api import router as projects_router

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
CYCLE_COOLDOWN = int(os.environ.get("MENOR_CYCLE_COOLDOWN", "900"))  # 15 min
DEEP_REST_INTERVAL = int(os.environ.get("MENOR_DEEP_REST_INTERVAL", str(3 * 3600)))  # 3 horas
DEEP_REST_DURATION = int(os.environ.get("MENOR_DEEP_REST_DURATION", str(30 * 60)))  # 30 min


def _notify_user_active():
    """Registra interação humana e sinaliza interrupção imediata ao worker se ativo."""
    global _last_interaction_time
    _last_interaction_time = time.time()
    if not _study_abort_event.is_set():
        _study_abort_event.set()


async def _interruptible_sleep(duration_seconds: float, abort_event: threading.Event) -> bool:
    """Aguarda em fatias curtas de 1 segundo para acordar imediatamente se o usuário interagir."""
    deadline = time.time() + duration_seconds
    while time.time() < deadline:
        if abort_event.is_set():
            return False
        await asyncio.sleep(1.0)
    return True


async def _idle_study_monitor():
    """Monitor de inatividade: ciclos contínuos (15 min cooldown, 30 min descanso a cada 3h)."""
    await asyncio.sleep(5)
    last_deep_rest_time = time.time()

    while True:
        await asyncio.sleep(10)
        idle_seconds = time.time() - _last_interaction_time
        if idle_seconds >= IDLE_STUDY_DELAY and not _study_running_lock.locked():
            if _study_running_lock.acquire(blocking=False):
                try:
                    logger.info(
                        "Inatividade de %ds atingida. Iniciando ciclos autônomos até interação do usuário...",
                        int(idle_seconds),
                    )
                    _study_abort_event.clear()
                    while not _study_abort_event.is_set():
                        from src.agent.study import run_autonomous_cycle
                        await asyncio.to_thread(
                            run_autonomous_cycle, ollama_url=OLLAMA_SERVER_URL, abort_event=_study_abort_event
                        )

                        if _study_abort_event.is_set():
                            break

                        now = time.time()
                        if (now - last_deep_rest_time) >= DEEP_REST_INTERVAL:
                            logger.info(
                                "3 horas de sessões atingidas. Entrando em descanso térmico profundo de 30 min..."
                            )
                            slept = await _interruptible_sleep(DEEP_REST_DURATION, _study_abort_event)
                            last_deep_rest_time = time.time()
                        else:
                            logger.info("Ciclo concluído com sucesso. Cooldown térmico de 15 min...")
                            slept = await _interruptible_sleep(CYCLE_COOLDOWN, _study_abort_event)

                        if not slept or _study_abort_event.is_set():
                            logger.info("Sessão autônoma interrompida imediatamente por chamada do operador.")
                            break
                except Exception as exc:
                    logger.debug("Ciclo autônomo em background: %s", exc)
                finally:
                    _study_running_lock.release()


def get_optimal_threads() -> int:
    """Calcula threads físicas ideais para evitar colisão de HyperThreading no Ollama."""
    count = os.cpu_count() or 4
    return max(2, count // 2 if count >= 4 else count)


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
app.include_router(private_diagnostics_router)
app.include_router(lab_router)
app.include_router(file_analysis_router)
app.include_router(brain_workspace_router)
app.include_router(projects_router)

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


class AgentRouteRequest(BaseModel):
    message: MessageText
    history: List[ChatMessage] = Field(default_factory=list, max_length=40)
    project: Optional[str] = Field(default=None, max_length=64)
    node: Optional[str] = Field(default="server", max_length=50)


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
    auto_start: bool = True


class DiagnoseErrorRequest(BaseModel):
    complaint: str = Field(min_length=1, max_length=2000)
    last_bot_reply: Optional[str] = Field(default="", max_length=4000)
    session_id: Optional[str] = Field(default=None, max_length=128)


def require_chat_access(request: Request):
    if auth.configured() or auth.public_origin():
        auth.require_owner(request)


# --- ROTAS PRINCIPAIS ---

@app.get("/", response_class=HTMLResponse)
def serve_chat_ui():
    html_file = TEMPLATES_DIR / "chat.html"
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@app.get("/preview/{filepath:path}")
def preview_file(filepath: str, request: Request):
    """Serve arquivos gerados pelo Menor (HTML, CSS, JS, imagens) com segurança para visualização imediata."""
    try:
        from src.tools.core import _resolve_safe_path
        path = _resolve_safe_path(filepath)
        if not path.exists() or not path.is_file():
            alt_path = Path.cwd() / "workspace" / filepath
            if alt_path.exists() and alt_path.is_file():
                path = alt_path
            else:
                return HTMLResponse(
                    f"<div style='font-family:sans-serif;padding:24px;color:#ef4444;background:#18181b;'>"
                    f"<h3>Arquivo <code>{filepath}</code> ainda não foi gerado no workspace.</h3>"
                    f"<p style='color:#a1a1aa;'>Peça ao Menor para criar o arquivo "
                    f"(ex: 'cria o arquivo {filepath}').</p>"
                    f"</div>",
                    status_code=404,
                )
        suffix = path.suffix.lower()
        if suffix in (".html", ".htm"):
            return HTMLResponse(content=path.read_text(encoding="utf-8", errors="replace"))
        elif suffix in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"):
            return FileResponse(path)
        elif suffix == ".css":
            return Response(content=path.read_text(encoding="utf-8", errors="replace"), media_type="text/css")
        elif suffix == ".js":
            content_js = path.read_text(encoding="utf-8", errors="replace")
            return Response(content=content_js, media_type="application/javascript")
        else:
            return PlainTextResponse(content=path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        err_html = f"<div style='font-family:sans-serif;padding:24px;color:#ef4444;'><h3>Erro: {exc}</h3></div>"
        return HTMLResponse(err_html, status_code=500)


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
            "recommended_model": "qwen3.5:4b",
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


@app.get("/images/status")
def get_images_status(request: Request):
    auth.require_owner(request)
    from src.tools.images import provider, configured
    from src.tools.local_images import status as local_status
    from src.agent.skills import capability_status
    try:
        local_model = local_status()
    except Exception:
        local_model = {"ready": False}
    try:
        skill_item = capability_status("images.generate")
    except Exception:
        skill_item = None
    return {
        "provider": provider(),
        "configured": configured(),
        "local_model": local_model,
        "skill": skill_item,
    }


@app.get("/agent/skills")
def get_agent_skills(request: Request):
    auth.require_owner(request)
    from src.agent.skills import catalog
    return {"items": catalog()}


@app.get("/tools")
def get_tools_catalog(request: Request):
    auth.require_owner(request)
    from src.tools.registry import list_tools
    return {"items": list_tools()}


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
def agent_run(body: AgentRunRequest, request: Request, response: Response):
    _notify_user_active()
    auth.require_owner(request)
    response.headers["X-Menor-Fallback"] = "stream"
    if body.node == "local" or (body.ollama_url and "localhost" in body.ollama_url):
        target_url = OLLAMA_SERVER_URL
        target_model = get_active_model()
    else:
        target_url = body.ollama_url or OLLAMA_SERVER_URL
        target_model = body.model or get_active_model()
    orchestrator = Orchestrator(ollama_url=target_url, default_model=target_model)
    messages = [item.model_dump() for item in body.history] + [{"role": "user", "content": body.message}]
    result = orchestrator.run_turn(messages=messages, model=target_model, ollama_url=target_url)
    reply_text = sanitize_assistant_reply(result.get("reply", ""), body.message)
    return {
        "handled": True,
        "reply": reply_text,
        "tools_executed": result.get("tools_executed", []),
        "model_used": result.get("model_used"),
        "node_url": result.get("node_url"),
    }


@app.post("/agent/route")
def agent_route(_req: AgentRouteRequest, _access=Depends(require_chat_access)):
    """Rota rápida de compatibilidade com o frontend para evitar 404 e atrasos de rede."""
    return {"decision": "chat"}


@app.post("/chat")
def chat_sync(req: ChatRequest, _access=Depends(require_chat_access)):
    _notify_user_active()
    if req.node == "local" or (req.ollama_url and "localhost" in req.ollama_url):
        target_url = OLLAMA_SERVER_URL
        target_model = get_active_model()
    else:
        target_url = req.ollama_url or OLLAMA_SERVER_URL
        target_model = req.model or get_active_model()
    orchestrator = Orchestrator(ollama_url=target_url, default_model=target_model)
    messages = [item.model_dump() for item in req.history] + [{"role": "user", "content": req.message}]
    result = orchestrator.run_turn(messages=messages, model=target_model, ollama_url=target_url)
    reply_text = sanitize_assistant_reply(result.get("reply", ""), req.message)
    return {
        "reply": reply_text,
        "model": target_model,
        "tools_executed": result.get("tools_executed", []),
    }


@app.post("/chat/stream")
def chat_stream(req: ChatRequest, _access=Depends(require_chat_access)):
    _notify_user_active()
    if req.node == "local" or (req.ollama_url and "localhost" in req.ollama_url):
        target_url = OLLAMA_SERVER_URL
        target_model = get_active_model()
    else:
        target_url = req.ollama_url or OLLAMA_SERVER_URL
        target_model = req.model or get_active_model()

    store = BrainStore()
    sections = []
    try:
        from src.memory.core_memory import CoreMemoryManager
        core_ctx = CoreMemoryManager(store).format_system_context()
        if core_ctx:
            sections.append(core_ctx)
    except Exception as exc:
        logger.debug("Core memory não carregada no chat_stream: %s", exc)

    try:
        store.initialize()
        notes = store.list_notes()
        prefs = []
        for n in notes:
            if n.startswith("identidade/") or n.startswith("preferencias/") or n.startswith("conhecimentos/"):
                c = store.read_note(n)
                if c and len(c.strip()) > 30:
                    prefs.append(f"[{n}]: {c.strip()}")
        if prefs:
            sections.append("Memória permanente do usuário:\n" + "\n".join(prefs[:5]))
    except Exception as exc:
        logger.debug("Memória permanente não carregada no chat_stream: %s", exc)

    base_system = (
        "Você é o Menor v2, assistente executivo e parceiro pessoal do Isaac.\n"
        "Responda sempre de forma natural, calorosa e fluente em português brasileiro.\n"
        "Em conversas casuais e cumprimentos, seja descontraído e NUNCA force nem puxe assunto sobre trabalho.\n"
        "Compreenda gírias brasileiras comuns de chat:\n"
        "- 'pf' / 'pff' / 'pls' = 'por favor' (NUNCA interprete como 'prioritários' ou siglas corporativas).\n"
        "- 'a gnt' = 'a gente' (nós, você e o Isaac juntos; NUNCA interprete como sigla corporativa).\n"
        "- 'oq' / 'o que' = 'o que'; 'vc' / 'vcs' = 'você' / 'vocês'; 'tb' / 'tbm' = 'também'; 'pq' = 'porque'.\n"
        "NUNCA pense em voz alta em inglês ('Looking at...', 'Given their...', 'I need to...', 'Okay, the user...').\n"
        "O Isaac desenvolve: sites modernos, jogos 2D, música/DSP de áudio, aplicativos mobile Android (Kotlin) e sistemas/backends.\n"
        "Respeite estritamente as preferências, diretrizes e perfil do usuário salvas na memória.\n"
        "NUNCA simule saídas de terminal ou invente pastas inexistentes (ex: ```terminal $ ls ...```).\n"
        "Sua Âncora de Estudos oficial está no bloco [STUDY_ANCHORS] da sua Core Memory acima."
    )
    if sections:
        system_content = f"{base_system}\n\n" + "\n\n".join(sections)
    else:
        system_content = base_system

    payload = {
        "model": target_model,
        "messages": [
            {
                "role": "system",
                "content": system_content,
            },
            *[item.model_dump() for item in req.history],
            {"role": "user", "content": req.message},
        ],
        "stream": True,
        "think": False,
        "keep_alive": "60m",
        "options": {
            "temperature": 0.6,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_predict": 1024,
            "num_thread": get_optimal_threads(),
            "num_ctx": 4096,
            "stop": [
                "\nThinking Process:", "Thinking Process:", "Okay, let's", "Let's tackle",
                "Looking at the current", "Given their work profile", "Okay, the user wants",
            ],
        },
    }

    def sse_generator():
        try:
            with requests.post(f"{target_url}/api/chat", json=payload, stream=True, timeout=(15, 600)) as resp:
                resp.raise_for_status()
                buffer = ""
                in_thought = False
                streamed_any = False
                for line in resp.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if not token and not data.get("done"):
                        continue

                    if not streamed_any:
                        buffer += token
                        # Acumula primeiros tokens para detectar scratchpad
                        if len(buffer) < 40 and not data.get("done") and "\n" not in buffer:
                            continue

                        buf_lower = buffer.lower()
                        if (
                            "thinking process" in buf_lower
                            or "<think>" in buf_lower
                            or buf_lower.startswith((
                                "okay, let's", "let's tackle", "looking at", "given their",
                                "okay, the user", "the user is", "the user wants",
                                "i need to", "wait, the user", "first, i need", "let me check"
                            ))
                        ):
                            in_thought = True
                            buffer = ""
                            continue
                        else:
                            if buffer:
                                yield buffer
                                streamed_any = True
                                buffer = ""
                    elif in_thought:
                        buffer += token
                        if "</think>" in buffer or "</thought>" in buffer:
                            parts = re.split(r"</(?:think|thought)>", buffer, maxsplit=1)
                            after = parts[-1].lstrip()
                            in_thought = False
                            buffer = ""
                            if after:
                                yield after
                                streamed_any = True
                        else:
                            parts = re.split(
                                r"\n\s*(?:Resposta|Response|Final Answer|Assistant|Menor):\s*",
                                buffer,
                                flags=re.IGNORECASE,
                            )
                            if len(parts) > 1 and parts[-1].strip():
                                in_thought = False
                                yield parts[-1].lstrip()
                                streamed_any = True
                                buffer = ""
                    else:
                        if token:
                            yield token
                            streamed_any = True

                    if data.get("done"):
                        if not streamed_any and buffer:
                            clean_buf = re.sub(
                                r"<(?:think|thought)>.*?</(?:think|thought)>", "", buffer, flags=re.DOTALL
                            )
                            clean_buf = re.sub(r"<(?:think|thought)>.*", "", clean_buf, flags=re.DOTALL).strip()
                            if clean_buf:
                                yield clean_buf
                                streamed_any = True
                        if not streamed_any:
                            yield _fallback_casual_reply(req.message)
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
        safe_name = f"memoria_{int(time.time() * 1000)}.md"
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
    task_id = queue.enqueue(goal=body.goal, project_slug=body.project_slug, auto_start=body.auto_start)
    return {"task_id": task_id, "status": "pending", "goal": body.goal}


@app.get("/api/tasks")
def list_tasks(request: Request):
    auth.require_owner(request)
    queue = get_task_queue()
    return {"tasks": queue.list_tasks()}


@app.get("/api/tasks/{task_id}")
def get_task_status(task_id: int, request: Request):
    auth.require_owner(request)
    queue = get_task_queue()
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(404, "Tarefa não encontrada.")
    return task


@app.post("/api/agent/diagnose-error")
def diagnose_error(body: DiagnoseErrorRequest, request: Request):
    auth.require_owner(request)
    from src.agent.workers import get_task_queue
    from src.agent.study import get_optimal_model
    from src.agent.orchestrator import Orchestrator

    queue = get_task_queue()
    recent_tasks = queue.list_tasks(limit=3)
    failed_task = next((t for t in recent_tasks if t.get("status") == "failed"), None)
    last_task = recent_tasks[0] if recent_tasks else None

    context_details = []
    if failed_task:
        context_details.append(
            f"Última tarefa falhou: Meta='{failed_task.get('goal')}', Erro='{failed_task.get('result')}'"
        )
    elif last_task:
        res_str = str(last_task.get('result'))[:300]
        context_details.append(
            f"Última tarefa executada: Meta='{last_task.get('goal')}', Status='{last_task.get('status')}', "
            f"Resultado='{res_str}'"
        )

    if body.last_bot_reply:
        context_details.append(f"Última resposta do assistente: '{body.last_bot_reply[:400]}'")

    model = get_optimal_model()
    orchestrator = Orchestrator(default_model=model)
    diag_prompt = (
        "Você é o especialista de diagnóstico e auto-recuperação do Menor v2. "
        "O usuário Isaac relatou uma falha ou insatisfação com a execução anterior. "
        "Analise os dados abaixo e retorne um diagnóstico claro e um plano de conserto em JSON estrito.\n\n"
        f"Reclamação do Isaac: {body.complaint}\n"
        + ("\n".join(context_details) if context_details else "Nenhum log de erro recente disponível.")
        + "\n\nResponda APENAS em JSON no formato:\n"
        "{\"diagnosis\": \"explicação em 1 frase curta do erro\", \"proposed_fix\": \"plano de 1 frase de conserto\"}"
    )
    try:
        res = orchestrator.run_turn(
            messages=[{"role": "user", "content": diag_prompt}],
            enable_tools=False,
            max_steps=1,
        )
        reply = res.get("reply", "")
        match = re.search(r"\{.*\}", reply, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            return {
                "success": True,
                "diagnosis": parsed.get("diagnosis", "Falha na execução ou formato da resposta anterior."),
                "proposed_fix": parsed.get(
                    "proposed_fix", "Reexecutar a tarefa com parâmetros corrigidos e ferramentas reais."
                )
            }
    except Exception as exc:
        logger.warning("Diagnóstico automático falhou: %s", exc)

    if failed_task:
        return {
            "success": True,
            "diagnosis": f"A tarefa '{failed_task.get('goal')}' falhou no Hub: {failed_task.get('result')}",
            "proposed_fix": (
                f"Reexecutar a tarefa '{failed_task.get('goal')}' corrigindo os parâmetros e aplicando ferramentas."
            )
        }
    return {
        "success": True,
        "diagnosis": "Ocorreu uma divergência ou falha na execução do último pedido.",
        "proposed_fix": "Refazer a operação utilizando ferramentas reais do sistema com os parâmetros corretos."
    }


# --- ENDPOINTS DE ESTUDO & AUTO-DIAGNÓSTICO ---

@app.get("/api/study/status")
def study_status(request: Request):
    auth.require_owner(request)
    from src.agent.study import CheckpointManager, TopicManager
    from src.agent.cycle_monitor import get_cycle_monitor
    tm = TopicManager()
    cm = CheckpointManager()
    return {
        "idle_seconds": int(time.time() - _last_interaction_time),
        "idle_threshold": IDLE_STUDY_DELAY,
        "is_studying": _study_running_lock.locked(),
        "checkpoint": cm.load_checkpoint(),
        "uncompleted_topics": tm.list_topics(uncompleted_only=True),
        "cycle_telemetry": get_cycle_monitor().snapshot(),
    }


@app.get("/api/study/live")
def study_live(request: Request):
    """Snapshot completo para a tela de monitoramento em tempo real do ciclo cognitivo."""
    auth.require_owner(request)
    from src.agent.cycle_monitor import get_cycle_monitor
    snap = get_cycle_monitor().snapshot()
    snap["is_studying_locked"] = _study_running_lock.locked()
    snap["idle_seconds"] = int(time.time() - _last_interaction_time)
    snap["idle_threshold"] = IDLE_STUDY_DELAY
    return snap


@app.post("/api/study/trigger")
def study_trigger(request: Request, sync: bool = False):
    """Inicia o ciclo cognitivo. Se sync=False (padrão), roda em segundo plano e libera a UI."""
    auth.require_owner(request)
    if _study_running_lock.acquire(blocking=False):
        if sync:
            try:
                _study_abort_event.clear()
                from src.agent.study import run_autonomous_cycle
                res = run_autonomous_cycle(ollama_url=OLLAMA_SERVER_URL, abort_event=_study_abort_event)
                return {"success": True, "result": res}
            finally:
                _study_running_lock.release()
        else:
            def _runner():
                try:
                    _study_abort_event.clear()
                    from src.agent.study import run_autonomous_cycle
                    run_autonomous_cycle(ollama_url=OLLAMA_SERVER_URL, abort_event=_study_abort_event)
                finally:
                    _study_running_lock.release()
            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            return {"success": True, "message": "Ciclo cognitivo autônomo iniciado com sucesso."}
    return {"success": False, "message": "O ciclo cognitivo já está em execução no momento."}


@app.post("/api/study/abort")
def study_abort(request: Request):
    """Envia sinal de interrupção (preempção) para o ciclo de estudo ativo."""
    auth.require_owner(request)
    if _study_running_lock.locked():
        _study_abort_event.set()
        return {"success": True, "message": "Sinal de interrupção enviado ao ciclo autônomo."}
    return {"success": False, "message": "Nenhum ciclo autônomo em execução no momento."}


@app.post("/api/study/clear-logs")
def study_clear_logs(request: Request):
    auth.require_owner(request)
    from src.agent.cycle_monitor import get_cycle_monitor
    get_cycle_monitor().clear_logs()
    return {"success": True}


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)

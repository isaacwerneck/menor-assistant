import asyncio
import json
import logging
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, StringConstraints, model_validator
import requests

from src.agent.runner import run as run_agent
from src.agent import research
from src.agent.tasks import RunBusy, TaskStore
from src.agent.router import classify
from src.agent.image_intent import IMAGE_TERMS, image_intent, _normalize
from src.agent.missions import MissionStore
from src.agent.skills import catalog as skill_catalog, capability_status
from src.agent.delegation import generate_image as delegate_image
from src.agent.self_edit import ImprovementUnavailable, propose, status as dev_status
from src.agent.resolve import resolve
from src.memory.store import BrainStore
from src.memory.manage import KnowledgeManager
from src.memory.search import KnowledgeIndex, contextual_knowledge
from src.projects.manager import create_project
from src.projects.workspace import ProjectWorkspace
from src.security import auth
from src.tools.audit import record
from src.tools.registry import list_tools, perform
from src.tools.design import plan_tool
from src.tools import images, local_images, web

logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(_app):
    # Nenhum dado mutável é escrito dentro do checkout Git do servidor.
    BrainStore().initialize()
    yield


app = FastAPI(
    lifespan=app_lifespan,
    title="Menor - Assistente de IA Pessoal",
    description="Servidor de orquestração do Menor, assistente pessoal rodando em hardware doméstico.",
    version="0.4.1",
)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "24h")
SYSTEM_PROMPT = (
    "Você é o Menor, o assistente pessoal de inteligência artificial criado e hospedado localmente pelo Isaac. "
    "Ajude com programação, desenvolvimento de jogos, planejamento e tarefas do dia a dia. "
    "Não prometa certeza absoluta. Sem evidência suficiente, diga que não conseguiu confirmar. "
    "Diferencie fato consultado, hipótese, código proposto e execução verificada. "
    "Responda em português brasileiro com clareza e objetividade. Prefira 1 a 3 parágrafos "
    "curtos, exceto quando o usuário pedir detalhes ou a tarefa exigir explicação maior. "
    "Use o contexto anterior sem repetir perguntas já respondidas. "
    "Se houver dúvida sobre anotar algo, pergunte de forma natural na própria conversa. "
    "Nunca afirme ter registrado memória, criado arquivos ou executado ferramentas sem "
    "confirmação explícita do sistema. Não mencione botões que não existem."
)
TEMPLATES_DIR = Path(__file__).parent / "templates"
MessageText = Annotated[str, StringConstraints(min_length=1, max_length=8000, pattern=r"\S")]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: MessageText


class ChatRequest(BaseModel):
    message: MessageText
    model: str = Field(default=DEFAULT_MODEL, min_length=1, max_length=200, pattern=r"^\S+$")
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    project: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def limit_context(self):
        if len(self.message) + sum(len(item.content) for item in self.history) > 32000:
            raise ValueError("A conversa enviada deve conter no máximo 32000 caracteres.")
        return self


class AgentRunRequest(ChatRequest):
    session_id: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    turn_id: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


@app.post("/agent/run")
def agent_run(body: AgentRunRequest, request: Request):
    auth.require_owner(request)
    try:
        return run_agent(
            body.session_id, body.turn_id, body.message,
            [item.model_dump() for item in body.history], project=body.project,
        )
    except (RunBusy, ValueError) as error:
        raise HTTPException(409, str(error)) from error
    except (sqlite3.Error, OSError) as error:
        logger.warning("Estado do agente indisponível: %s", type(error).__name__)
        raise HTTPException(503, "Não consegui persistir a tarefa. Nenhuma nova execução foi autorizada.") from error


@app.get("/agent/runs/{session_id}")
def agent_run_state(session_id: str, request: Request):
    auth.require_owner(request)
    try:
        return TaskStore().inspect(session_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


class ToolRequest(BaseModel):
    tool: str = Field(min_length=3, max_length=80)
    arguments: dict[str, str] = Field(default_factory=dict)
    dry_run: bool = True


@app.get("/tools")
def tool_catalog(request: Request):
    auth.require_owner(request)
    return {"items": list_tools()}


@app.post("/tools/execute")
def tool_execute(body: ToolRequest, request: Request):
    auth.require_owner(request)
    try:
        receipt = perform(body.tool, body.arguments, dry_run=body.dry_run)
        record(body.tool, receipt["status"], body.arguments.keys())
        return receipt
    except (ValueError, LookupError, OSError, web.WebUnavailable) as error:
        logger.warning("Ferramenta indisponível: %s", type(error).__name__)
        try:
            record(body.tool, "failed", body.arguments.keys())
        except (OSError, ValueError):
            logger.warning("Não foi possível registrar a falha na auditoria.")
        raise HTTPException(422, "Ferramenta não disponível ou argumentos inválidos.") from error


class ImprovementRequest(BaseModel):
    issue: str = Field(min_length=12, max_length=600)
    dry_run: bool = True


@app.get("/agent/improve/status")
def improve_status(request: Request):
    auth.require_owner(request)
    return dev_status()


@app.post("/agent/improve")
def improve_issue(body: ImprovementRequest, request: Request):
    auth.require_owner(request)
    try:
        return propose(body.issue, dry_run=body.dry_run)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except ImprovementUnavailable as error:
        raise HTTPException(503, str(error)) from error


class MissionStartRequest(BaseModel):
    capability: Literal[
        "images.generate", "images.edit", "programming", "design", "music", "web"
    ]
    goal: str = Field(min_length=8, max_length=600)


class MissionDetailRequest(BaseModel):
    requirements: str = Field(min_length=8, max_length=1200)


class MissionQuestionRequest(BaseModel):
    message: MessageText


class MissionApprovalRequest(BaseModel):
    approved: bool


@app.get("/agent/skills")
def agent_skills(request: Request):
    auth.require_owner(request)
    return {"items": skill_catalog()}


@app.get("/agent/missions")
def missions_list(request: Request):
    auth.require_owner(request)
    return {"items": MissionStore().list()}


@app.post("/agent/missions")
def mission_start(body: MissionStartRequest, request: Request):
    auth.require_owner(request)
    return MissionStore().begin(body.capability, body.goal)


@app.get("/agent/missions/{mission_id}")
def mission_detail(mission_id: str, request: Request):
    auth.require_owner(request)
    try:
        return MissionStore().get(mission_id)
    except (ValueError, LookupError) as error:
        raise HTTPException(404, "Missão não encontrada.") from error


@app.post("/agent/missions/{mission_id}/requirements")
def mission_requirements(mission_id: str, body: MissionDetailRequest, request: Request):
    auth.require_owner(request)
    try:
        return MissionStore().detail(mission_id, body.requirements)
    except LookupError as error:
        raise HTTPException(404, "Missão não encontrada.") from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.post("/agent/missions/{mission_id}/question")
def mission_question(mission_id: str, body: MissionQuestionRequest, request: Request):
    auth.require_owner(request)
    try:
        return {"reply": MissionStore().explain(mission_id, body.message)}
    except LookupError as error:
        raise HTTPException(404, "Missão não encontrada.") from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.post("/agent/missions/{mission_id}/approve")
def mission_approve(mission_id: str, body: MissionApprovalRequest, request: Request):
    auth.require_owner(request)
    try:
        return MissionStore().decide(mission_id, body.approved)
    except LookupError as error:
        raise HTTPException(404, "Missão não encontrada.") from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=6, max_length=2000)


class ImageIntentRequest(BaseModel):
    message: MessageText
    has_attachment: bool = False


@app.post("/images/intent")
def images_intent(body: ImageIntentRequest, request: Request):
    auth.require_owner(request)
    return image_intent(body.message, body.has_attachment)


@app.get("/images/status")
def images_status(request: Request):
    auth.require_owner(request)
    local = images.provider() == "local"
    skill = capability_status("images.generate") if local else None
    return {
        "configured": skill["ready"] if local else images.configured(),
        "provider": images.provider(),
        "local_model": local_images.status() if local else None,
        "skill": skill,
    }


def image_error(error):
    if isinstance(error, images.ImageUnavailable):
        raise HTTPException(503, str(error)) from error
    if isinstance(error, (OSError, ValueError)):
        raise HTTPException(422, str(error)) from error
    raise HTTPException(502, "Não foi possível gerar imagem.") from error


@app.post("/images/generate")
def images_generate(body: ImageRequest, request: Request):
    auth.require_owner(request)
    try:
        result = (
            delegate_image(body.prompt)
            if images.provider() == "local" else images.generate(body.prompt)
        )
        record("images.generate", "executed", ["prompt"])
        return result
    except (images.ImageUnavailable, ValueError, OSError) as error:
        record("images.generate", "failed", ["prompt"])
        image_error(error)


@app.post("/images/edit")
async def images_edit(
    request: Request,
    prompt: str = Form(..., min_length=6, max_length=2000),
    file: UploadFile = File(...),
):
    auth.require_owner(request)
    try:
        raw = await file.read(images.MAX_BYTES + 1)
        result = await asyncio.to_thread(images.edit, prompt, raw)
        record("images.edit", "executed", ["prompt", "file"])
        return result
    except (images.ImageUnavailable, ValueError, OSError) as error:
        record("images.edit", "failed", ["prompt", "file"])
        image_error(error)
    finally:
        await file.close()


@app.get("/images/files/{image_id}")
def images_file(image_id: str, request: Request):
    auth.require_owner(request)
    try:
        path = images.file_path(image_id)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(404, "Imagem não encontrada.") from error
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, no-store"})


class PasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class RememberRequest(BaseModel):
    text: str = Field(min_length=1, max_length=280)
    kind: Literal["preference", "knowledge", "project", "tool"]


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=3, ge=1, le=5)


class KnowledgeChangeRequest(BaseModel):
    id: str = Field(min_length=1, max_length=50)
    text: str | None = Field(default=None, max_length=280)


@app.get("/memory/knowledge")
def knowledge_list(request: Request):
    auth.require_owner(request)
    return {"items": KnowledgeManager().list()}


@app.post("/memory/search")
def knowledge_search(body: KnowledgeSearchRequest, request: Request):
    auth.require_owner(request)
    try:
        return {"items": KnowledgeIndex().search(body.query, limit=body.limit)}
    except (sqlite3.Error, OSError, ValueError) as error:
        logger.warning("Falha na busca de memoria: %s", type(error).__name__)
        raise HTTPException(503, "A busca de conhecimentos está indisponível.") from error


@app.post("/memory/knowledge/edit")
def knowledge_edit(body: KnowledgeChangeRequest, request: Request):
    auth.require_owner(request)
    try:
        if body.text is None:
            raise ValueError("Texto obrigatório.")
        return KnowledgeManager().change(body.id, "edit", body.text)
    except LookupError as error:
        raise HTTPException(409, str(error)) from error
    except (OSError, ValueError) as error:
        raise HTTPException(422, "Conhecimento inválido.") from error


@app.post("/memory/knowledge/delete")
def knowledge_delete(body: KnowledgeChangeRequest, request: Request):
    auth.require_owner(request)
    try:
        return KnowledgeManager().change(body.id, "delete")
    except LookupError as error:
        raise HTTPException(409, str(error)) from error
    except (OSError, ValueError) as error:
        raise HTTPException(422, "Conhecimento inválido.") from error


class IntentRequest(ChatRequest):
    pass


class PendingAnswerRequest(ChatRequest):
    original: str = Field(min_length=1, max_length=280)
    question: str = Field(default="", max_length=180)
    suggested_target: Literal["none", "preference", "knowledge", "project", "tool"] = "none"


@app.post("/agent/resolve")
def resolve_intent(body: PendingAnswerRequest, request: Request):
    auth.require_owner(request)
    result = resolve(
        body.original, body.message, body.suggested_target,
        project=body.project, question=body.question,
        history=[item.model_dump() for item in body.history],
    )
    if result["decision"] == "save":
        try:
            if result["target"] == "project" and result["note_kind"] != "none":
                result["project_note"] = ProjectWorkspace().append(
                    body.project, result["note_kind"], body.original, origin="chat",
                )
            else:
                result["memory"] = _save_memory(result["target"], body.original)
        except (OSError, ValueError, LookupError) as error:
            logger.warning("Não foi possível concluir anotação solicitada: %s", type(error).__name__)
            return {"decision": "ask", "target": result["target"], "note_kind": "none",
                    "question": "Não consegui salvar. Quer revisar a pasta ou o projeto escolhido?"}
    return result


class ProjectNoteRequest(BaseModel):
    kind: Literal["decision", "task", "log"]
    text: str = Field(min_length=1, max_length=280)


@app.get("/projects")
def projects_list(request: Request):
    auth.require_owner(request)
    return {"items": ProjectWorkspace().list_projects()}


@app.get("/projects/{slug}")
def projects_detail(slug: str, request: Request):
    auth.require_owner(request)
    try:
        return ProjectWorkspace().read_project(slug)
    except (ValueError, LookupError) as error:
        raise HTTPException(404, "Projeto não encontrado.") from error


@app.post("/projects/{slug}/notes")
def project_add_note(slug: str, body: ProjectNoteRequest, request: Request):
    auth.require_owner(request)
    try:
        return ProjectWorkspace().append(slug, body.kind, body.text, origin="painel")
    except (ValueError, LookupError) as error:
        raise HTTPException(422, "Projeto ou anotação inválidos.") from error


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=3, max_length=64)


@app.post("/projects/create")
def project_create(body: CreateProjectRequest, request: Request):
    auth.require_owner(request)
    try:
        return create_project(body.name)
    except (OSError, ValueError) as error:
        logger.warning("Não foi possível criar projeto: %s", type(error).__name__)
        raise HTTPException(422, "Nome inválido ou projeto já existente.") from error


def _save_memory(kind, text):
    store = BrainStore()
    if kind == "preference":
        saved = store.remember_preference(text)
        path = "identidade/preferencias.md"
    elif kind == "knowledge":
        saved = store.remember_knowledge(text)
        path = "conhecimentos/aprendizados_gerais.md"
    else:
        saved = store.remember_idea(kind, text)
        path = "projetos/ideias.md" if kind == "project" else "ferramentas/ideias.md"
    return {"saved": saved, "path": path, "kind": kind}


@app.post("/agent/route")
def route_intent(body: IntentRequest, request: Request):
    auth.require_owner(request)
    result = classify(body.message, [item.model_dump() for item in body.history], project=body.project)
    if result["decision"] in ("save", "create_project", "select_project", "add_project_note", "plan_tool"):
        try:
            if result["decision"] == "plan_tool":
                result["tool_plan"] = plan_tool(result["text"])
                capability = ("images.generate" if re.search(rf"\b{IMAGE_TERMS}\b", _normalize(body.message))
                              else "programming")
                result["mission"] = MissionStore().begin(capability, body.message)
                record("tool.plan", "planned", ["request"])
            elif result["decision"] == "create_project":
                result["project"] = create_project(result["text"])
            elif result["decision"] == "select_project":
                name = result["text"].casefold()
                found = next((
                    item for item in ProjectWorkspace().list_projects()
                    if item["name"].casefold() == name or item["slug"].casefold() == name
                ), None)
                if found is None:
                    result["decision"] = "ask"
[… truncated at ~4172 of 6525 tokens — use ctx_read with lines= parameter to see specific sections]
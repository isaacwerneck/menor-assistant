"""Rotas autenticadas da API do Laboratório de Testes & Auto-Aprimoramento."""
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from src.lab.eval_engine import LAB_CATEGORIES, LabManager
from src.lab.runner import LabRunner
from src.security import auth

router = APIRouter(tags=["Laboratório de Testes"])
TEMPLATES_DIR = Path(__file__).parent.parent / "api" / "templates"


class ObjectivePayload(BaseModel):
    content: str = Field(min_length=10, max_length=50000)


class RunPayload(BaseModel):
    categories: Optional[List[str]] = Field(default=None)
    mode: Literal["manual", "auto"] = Field(default="manual")
    model: str = Field(default="qwen2.5:14b", max_length=120)


class ControlPayload(BaseModel):
    action: Literal["pause", "resume", "step", "abort"]


class ApprovePayload(BaseModel):
    action: Literal["approve", "discard"]
    target_file: Optional[str] = Field(default=None, max_length=200)
    learning: Optional[str] = Field(default=None, max_length=2000)


@router.get("/lab/view")
def lab_view_page(request: Request):
    """Página visual completa do Laboratório de Testes."""
    auth.require_owner(request)
    lab_html = TEMPLATES_DIR / "lab.html"
    if not lab_html.exists():
        raise HTTPException(status_code=404, detail="Template do laboratório não encontrado.")
    return FileResponse(
        lab_html,
        media_type="text/html",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/api/lab/categories")
def get_categories(request: Request):
    """Retorna as categorias disponíveis para teste."""
    auth.require_owner(request)
    return {"categories": LAB_CATEGORIES}


@router.get("/api/lab/objectives")
def get_objectives(request: Request):
    """Obtém o markdown de objetivo atual."""
    auth.require_owner(request)
    manager = LabManager.get_instance()
    return {"content": manager.get_objective_markdown()}


@router.post("/api/lab/objectives")
def save_objectives(payload: ObjectivePayload, request: Request):
    """Salva o markdown de objetivos editado."""
    auth.require_owner(request)
    manager = LabManager.get_instance()
    ok = manager.save_objective_markdown(payload.content)
    if not ok:
        raise HTTPException(status_code=500, detail="Não foi possível salvar o arquivo de objetivos.")
    return {"success": True, "message": "Objetivo de laboratório atualizado com sucesso."}


@router.get("/api/lab/state")
def get_session_state(request: Request):
    """Retorna o estado atual da sessão do laboratório."""
    auth.require_owner(request)
    manager = LabManager.get_instance()
    if not manager.current_session:
        return {
            "session_id": None,
            "status": "idle",
            "mode": "manual",
            "current_step": 0,
            "total_steps": 0,
            "average_score": 0.0,
            "logs": [],
        }
    return manager.current_session.get_state()


@router.post("/api/lab/run")
def start_battery(payload: RunPayload, request: Request):
    """Inicia uma bateria de testes no laboratório."""
    auth.require_owner(request)
    manager = LabManager.get_instance()

    if manager.current_session and manager.current_session.status in ("running", "waiting_approval"):
        return JSONResponse(
            status_code=409,
            content={"error": "Já existe uma bateria em andamento. Pause ou aborte antes de iniciar outra."},
        )

    session = manager.create_session(categories=payload.categories, mode=payload.mode, model=payload.model)
    runner = LabRunner(session, store=manager.store)
    runner.start_async(categories=payload.categories)

    return {"success": True, "session_id": session.session_id, "message": "Bateria iniciada com sucesso."}


@router.post("/api/lab/control")
def control_session(payload: ControlPayload, request: Request):
    """Controla a execução da bateria (pausar, retomar, avançar passo, interromper)."""
    auth.require_owner(request)
    manager = LabManager.get_instance()
    session = manager.current_session
    if not session:
        raise HTTPException(status_code=404, detail="Nenhuma sessão ativa encontrada.")

    if payload.action == "pause":
        session.request_pause()
    elif payload.action == "resume":
        session.request_resume()
    elif payload.action == "step":
        session.request_step()
    elif payload.action == "abort":
        session.request_abort()

    return {"success": True, "status": session.status}


@router.post("/api/lab/approve")
def approve_learning(payload: ApprovePayload, request: Request):
    """Aprova ou descarta o aprendizado no modo Human-in-the-Loop."""
    auth.require_owner(request)
    manager = LabManager.get_instance()
    session = manager.current_session
    if not session or not session.active_result:
        raise HTTPException(status_code=404, detail="Nenhum resultado ativo aguardando aprovação.")

    if payload.action == "approve":
        target = payload.target_file or session.active_result.get("target_file")
        learning_text = payload.learning or session.active_result.get("learning")
        if target and learning_text:
            content = (
                f"# Aprendizado Aprovado pelo Usuário (Human-in-the-Loop)\n\n"
                f"**Domínio:** {session.active_result.get('category')}\n"
                f"**Pergunta:** {session.active_result.get('question')}\n\n"
                f"## Lição Consolidada\n{learning_text}\n"
            )
            manager.store.write_note(target, content)
            session.logs.append(f"[APROVADO] Usuário aprovou e gravou: {target}")

    elif payload.action == "discard":
        session.logs.append("[DESCARTADO] Usuário descartou o aprendizado sugerido.")

    # Avança para o próximo passo
    session.request_step()
    return {"success": True, "action": payload.action}

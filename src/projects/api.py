"""Rotas HTTP autenticadas para gerenciamento de Projetos e Workspaces Scoped."""
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.projects.manager import create_project
from src.projects.workspace import ProjectWorkspace
from src.security import auth

router = APIRouter(tags=["Projetos & Workspaces"])


class CreateProjectPayload(BaseModel):
    name: str = Field(min_length=3, max_length=64)
    instructions: Optional[str] = Field(default=None, max_length=10000)


class AddNotePayload(BaseModel):
    kind: Literal["decision", "task", "log"]
    text: str = Field(min_length=1, max_length=2000)


class UpdateInstructionsPayload(BaseModel):
    instructions: str = Field(min_length=1, max_length=10000)


@router.get("/projects")
def list_projects_endpoint(request: Request):
    """Lista todos os projetos cadastrados no cérebro com metadados."""
    auth.require_owner(request)
    workspace = ProjectWorkspace()
    raw_projects = workspace.list_projects()
    items = []
    for proj in raw_projects:
        slug = proj.get("slug")
        name = proj.get("name")
        try:
            info = workspace.context(slug, max_chars=400)
            summary = info[:200] if info else "Projeto ativo."
        except Exception:
            summary = "Projeto ativo."
        items.append({
            "slug": slug,
            "name": name,
            "summary": summary,
        })
    return {"items": items}


@router.post("/projects")
def create_project_endpoint(payload: CreateProjectPayload, request: Request):
    """Cria um novo projeto estruturado com custom instructions e arquivos."""
    auth.require_owner(request)
    try:
        res = create_project(payload.name, instructions=payload.instructions)
        return {"success": True, "project": res}
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.get("/projects/{slug}")
def get_project_details(slug: str, request: Request):
    """Retorna detalhes e contexto de um projeto específico."""
    auth.require_owner(request)
    workspace = ProjectWorkspace()
    try:
        context_text = workspace.context(slug, max_chars=4000)
        return {
            "slug": slug,
            "name": slug.replace("-", " ").title(),
            "context": context_text,
        }
    except (ValueError, LookupError) as err:
        raise HTTPException(status_code=404, detail=str(err))


@router.post("/projects/{slug}/note")
def add_project_note(slug: str, payload: AddNotePayload, request: Request):
    """Adiciona uma anotação estruturada (decisão, tarefa ou diário) ao projeto."""
    auth.require_owner(request)
    workspace = ProjectWorkspace()
    try:
        rel = workspace.append(slug, payload.kind, payload.text)
        return {"success": True, "path": rel}
    except (ValueError, LookupError) as err:
        raise HTTPException(status_code=400, detail=str(err))

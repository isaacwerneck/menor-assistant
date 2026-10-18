"""Catálogo de ferramentas permitidas e validadas no backend.

Nenhum caminho informado pelo modelo é repassado diretamente ao sistema.
"""
from dataclasses import dataclass

from src.agent.diagnostics import analyze
from src.memory.store import BrainStore
from src.projects.manager import create_project
from src.projects.workspace import ProjectWorkspace


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    risk: str
    writes: bool
    arguments: tuple[str, ...]


TOOLS = {
    "system.diagnose": Tool(
        "system.diagnose", "Resume falhas das ferramentas em auditoria local.", "read", False, (),
    ),
    "projects.list": Tool(
        "projects.list", "Lista projetos existentes no cérebro.", "read", False, (),
    ),
    "projects.read": Tool(
        "projects.read", "Consulta o contexto de um projeto existente.", "read", False, ("slug",),
    ),
    "projects.create": Tool(
        "projects.create", "Cria pastas e modelos para um projeto novo.", "write", True, ("name",),
    ),
    "projects.add_task": Tool(
        "projects.add_task", "Registra uma tarefa no projeto informado.", "write", True, ("slug", "text"),
    ),
    "brain.remember": Tool(
        "brain.remember", "Salva preferência ou conhecimento fornecido pelo proprietário.",
        "write", True, ("kind", "text"),
    ),
}


def list_tools():
    return [
        {
            "name": t.name, "description": t.description, "risk": t.risk,
            "writes": t.writes, "arguments": list(t.arguments),
        }
        for t in TOOLS.values()
    ]


def perform(name, arguments, dry_run=True):
    """Executa exclusivamente operações mapeadas; retorna comprovante estruturado."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ValueError("Ferramenta desconhecida.")
    if not isinstance(arguments, dict) or set(arguments) != set(tool.arguments):
        raise ValueError("Argumentos da ferramenta inválidos.")
    if any(not isinstance(value, str) or not value.strip() or len(value) > 280
           for value in arguments.values()):
        raise ValueError("Parâmetros inválidos.")
    if name == "brain.remember" and arguments["kind"] not in ("preference", "knowledge"):
        raise ValueError("Tipo de memória inválido.")
    if dry_run:
        return {"status": "planned", "tool": name, "writes": tool.writes,
                "arguments": list(tool.arguments)}
    if name == "system.diagnose":
        output = analyze()
    elif name == "projects.list":
        output = ProjectWorkspace().list_projects()
    elif name == "projects.read":
        output = ProjectWorkspace().read_project(arguments["slug"])
    elif name == "projects.create":
        output = create_project(arguments["name"])
    elif name == "projects.add_task":
        output = ProjectWorkspace().append(
            arguments["slug"], "task", arguments["text"], origin="painel",
        )
    elif name == "brain.remember":
        store = BrainStore()
        if arguments["kind"] == "preference":
            store.remember_preference(arguments["text"])
            location = "identidade/preferencias.md"
        else:
            store.remember_knowledge(arguments["text"])
            location = "conhecimentos/aprendizados_gerais.md"
        output = {"path": location}
    else:
        raise ValueError("Ferramenta não configurada.")
    return {"status": "executed", "tool": name, "result": output}

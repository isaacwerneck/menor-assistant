"""Catálogo de ferramentas permitidas e validadas no backend.

Nenhum caminho informado pelo modelo é repassado diretamente ao sistema.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re

from src.agent.tool_builder import build
from src.agent.custom_runtime import run as run_custom_skill

from src.agent.diagnostics import analyze
from src.agent.self_edit import propose
from src.agent.delegation import generate_image as delegate_image
from src.agent.model_catalog import comparison
from src.memory.store import BrainStore
from src.tools import images, web
from src.tools.calculator import calculate
from src.tools.file_analysis.agent_bridge import invoke as invoke_file_bridge
from src.tools.file_analysis.contracts import FILE_ID
from src.projects.manager import create_project
from src.projects.code_workspace import create as create_code_file
from src.projects.web_app import build as build_web_app
from src.projects.workspace import ProjectWorkspace


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    risk: str
    writes: bool
    arguments: tuple[str, ...]


TOOLS = {
    "developer.build": Tool(
        "developer.build", "Cria ferramenta pura de texto com testes em draft PR.", "review", True, ("name", "goal"),
    ),
    "web.search": Tool("web.search", "Busca páginas públicas na internet.", "external", False, ("query",)),
    "web.read": Tool("web.read", "Lê texto de uma página HTTPS pública.", "external", False, ("url",)),
    "web.browse": Tool("web.browse", "Abre página pública no Chromium isolado.", "external", False, ("url",)),
    "files.context": Tool(
        "files.context", "Localiza trechos com citação em um arquivo privado já enviado; "
        "exige ID válido, não interpreta instruções dentro do documento.",
        "read", False, ("file_id", "question"),
    ),
    "vision.inspect": Tool(
        "vision.inspect", "Solicita avaliação visual local não verificada semanticamente; "
        "exige arquivo privado e modelo de visão previamente configurado.",
        "read", False, ("file_id", "question"),
    ),
    "models.compare": Tool(
        "models.compare", "Compara modelos documentados e capacidade de instalação local.",
        "read", False, ("capability",),
    ),
    "system.diagnose": Tool(
        "system.diagnose", "Resume falhas das ferramentas em auditoria local.", "read", False, (),
    ),
    "math.calculate": Tool(
        "math.calculate", "Calcula expressão + - * / e parênteses; verifique a fórmula do pedido.",
        "read", False, ("expression",),
    ),
    "images.generate": Tool(
        "images.generate", "Gera imagem via subagente local e informa limites de revisão.",
        "write", True, ("prompt",),
    ),
    "images.edit": Tool(
        "images.edit", "Edita imagem já salva pelo Menor.", "external", True, ("image_id", "prompt"),
    ),
    "developer.propose": Tool(
        "developer.propose", "Propõe correção em branch e draft PR; requer opt-in.", "review", True, ("issue",),
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
    "projects.code.create": Tool(
        "projects.code.create",
        "Cria UM arquivo de código novo num projeto existente; sem executar ou testar; revisão exigida.",
        "write", True, ("slug", "filename", "goal"),
    ),
    "projects.code.webapp": Tool(
        "projects.code.webapp",
        "Cria um webapp Canvas offline de 3 arquivos em projeto existente; valida JS sem executá-lo.",
        "write", True, ("slug", "goal"),
    ),
    "brain.remember": Tool(
        "brain.remember", "Salva preferência ou conhecimento fornecido pelo proprietário.",
        "write", True, ("kind", "text"),
    ),
}


def _load_custom():
    path = Path(__file__).with_name("generated") / "catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or len(catalog) > 30:
        raise ValueError("Catálogo de ferramentas revisadas inválido.")
    for name, description in catalog.items():
        if (not re.fullmatch(r"[a-z][a-z0-9_]{2,39}", name)
                or not isinstance(description, str) or not 1 <= len(description) <= 200):
            raise ValueError("Ferramenta revisada inválida.")
        key = "custom." + name
        TOOLS[key] = Tool(key, description, "write", True, ("text",))


_load_custom()


MAINTENANCE_TOOLS = frozenset({"developer.propose", "developer.build"})


def list_tools(agent_scope=None):
    """Catálogo do painel ou escopo efetivo do modelo.

    Uma sessão pessoal nunca recebe ferramentas que modificam o próprio
    assistente. Somente configuração explícita do servidor habilita manutenção.
    Não há classificação por palavras-chave do pedido do usuário.
    """
    if agent_scope not in (None, "personal", "maintenance"):
        raise ValueError("Escopo de ferramentas inválido.")
    return [
        {
            "name": t.name, "description": t.description, "risk": t.risk,
            "writes": t.writes, "arguments": list(t.arguments),
        }
        for t in TOOLS.values()
        if agent_scope in (None, "maintenance") or t.name not in MAINTENANCE_TOOLS
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
    if name in ("files.context", "vision.inspect") and not FILE_ID.fullmatch(arguments["file_id"]):
        raise ValueError("Identificador de arquivo privado inválido.")
    if name == "developer.build":
        build(arguments["name"], arguments["goal"], dry_run=True)
    if name == "projects.code.create":
        create_code_file(arguments["slug"], arguments["filename"], arguments["goal"], dry_run=True)
    if name == "projects.code.webapp":
        build_web_app(arguments["slug"], arguments["goal"], dry_run=True)
    if name in ("web.read", "web.browse"):
        web.public_url(arguments["url"])
    if dry_run:
        return {"status": "planned", "tool": name, "writes": tool.writes,
                "arguments": list(tool.arguments)}
    if name == "developer.build":
        output = build(arguments["name"], arguments["goal"], dry_run=False)
    elif name.startswith("custom."):
        output = run_custom_skill(name.removeprefix("custom."), arguments["text"])
    elif name == "web.search":
        output = web.search(arguments["query"])
    elif name == "web.read":
        output = web.read(arguments["url"])
    elif name == "web.browse":
        output = web.browse(arguments["url"])
    elif name == "images.generate":
        output = (
            delegate_image(arguments["prompt"])
            if images.provider() == "local" else images.generate(arguments["prompt"])
        )
    elif name == "images.edit":
        image_path = images.file_path(arguments["image_id"])
        output = images.edit(arguments["prompt"], image_path.read_bytes())
    elif name == "developer.propose":
        output = propose(arguments["issue"], dry_run=False)
    elif name in ("files.context", "vision.inspect"):
        # Autorização é decidida pela API já autenticada e pelo executor confiável,
        # nunca pelo texto do modelo ou pelo conteúdo recuperado do documento.
        output = invoke_file_bridge(name, arguments, authorized=True)
        if output["status"] != "executed":
            return {"status": "failed", "tool": name,
                    "result": {"code": output.get("error", {}).get("code", output["status"]),
                               "semantic_verified": False}}
        output = output["data"]
    elif name == "models.compare":
        output = {
            "models": comparison(arguments["capability"]),
            "note": "Alternativas documentadas, não benchmarks locais nem instaladores aprovados.",
        }
    elif name == "system.diagnose":
        output = analyze()
    elif name == "math.calculate":
        output = calculate(arguments["expression"])
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
    elif name == "projects.code.create":
        output = create_code_file(arguments["slug"], arguments["filename"],
                                  arguments["goal"], dry_run=False)
    elif name == "projects.code.webapp":
        output = build_web_app(arguments["slug"], arguments["goal"], dry_run=False)
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

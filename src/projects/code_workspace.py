"""Geração supervisionada de UM arquivo no workspace privado de um projeto.

Código é dado não confiável: salvá-lo não significa executar, testar nem aprovar
seu funcionamento. Nunca sobrescreve arquivos existentes nem permite subpastas.
"""
import ast
import hashlib
import json
import os
import re

import requests

from src.memory.store import _write_lock
from src.projects.workspace import ProjectWorkspace

FILENAME = re.compile(r"[a-z][a-z0-9_-]{0,35}\.(?:html|js|css|py|md)\Z")
MAX_SOURCE_BYTES = 16000

SOURCE_SCHEMA = {
    "type": "object",
    "properties": {"source": {"type": "string", "minLength": 1, "maxLength": MAX_SOURCE_BYTES}},
    "required": ["source"],
    "additionalProperties": False,
}

SYSTEM = (
    "Você é um engenheiro de software. Gere APENAS o código-fonte do arquivo "
    "solicitado usando o formato JSON validado {source: string}. "
    "Não faça promessas de execução, não use Markdown nem blocos de código. "
    "Faça o menor arquivo funcional para a tarefa, com dependências mínimas. "
    "Se o pedido exigir vários arquivos, implemente apenas a responsabilidade "
    "do arquivo solicitado. Nunca inclua segredos, tokens ou dados pessoais."
)


def _target(slug, filename, workspace=None):
    if not isinstance(filename, str) or not FILENAME.fullmatch(filename):
        raise ValueError("Nome inválido. Use apenas um arquivo .html, .js, .css, .py ou .md.")
    project = workspace or ProjectWorkspace()
    root = project._check_project(slug)
    directory = root / "arquivos"
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Pasta privada de código inválida.")
    target = directory / filename
    if target.is_symlink() or target.exists():
        raise ValueError("O arquivo já existe. Não vou substituí-lo automaticamente.")
    return target


def create(slug, filename, goal, dry_run=True, workspace=None):
    """Valida antes de inferir; escreve uma vez apenas depois do consentimento."""
    if not isinstance(goal, str) or not 12 <= len(goal.strip()) <= 280:
        raise ValueError("Descreva o arquivo em 12 a 280 caracteres.")
    target = _target(slug, filename, workspace)
    if dry_run:
        return {"status": "planned", "filename": filename, "not_executed": True}
    with requests.post(
        os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat",
        json={
            "model": os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"),
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps({
                    "filename": filename, "objective": goal,
                }, ensure_ascii=False)},
            ],
            "format": SOURCE_SCHEMA,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 2500},
        },
        timeout=(4, 170),
    ) as response:
        response.raise_for_status()
        value = response.json()
    source = json.loads(value["message"]["content"])["source"]
    if (not isinstance(source, str) or not source.strip()
            or len(source.encode("utf-8")) > MAX_SOURCE_BYTES or "\x00" in source
            or source.lstrip().startswith("```")):
        raise ValueError("O modelo não retornou código-fonte utilizável.")
    if filename.endswith(".py"):
        ast.parse(source, filename=filename)
    # Arquivos .js/.html/.css não são executados automaticamente nem testados.
    with _write_lock:
        target = _target(slug, filename, workspace)
        with target.open("x", encoding="utf-8") as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(source)
            file.flush()
            os.fsync(file.fileno())
    relative = "projetos/" + slug + "/arquivos/" + filename
    return {
        "path": relative,
        "bytes": len(source.encode("utf-8")),
        "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "tested": False,
        "executed": False,
        "review_required": True,
    }

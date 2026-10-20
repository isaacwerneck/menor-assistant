"""Constrói ferramentas em draft PR; código proposto não é importado no servidor."""
import ast
import base64
import json
import os
import re
import secrets

import requests

from src.agent.self_edit import ImprovementUnavailable, _github, _validate_patch
from src.agent.code_sandbox import verify
from src.agent.ponytail import coding_guidance

CATALOG = "src/tools/generated/catalog.json"
DOC = "docs/arquitetura_codigo.md"
NAME = re.compile(r"^[a-z][a-z0-9_]{2,39}$")


def _source(path, revision, token):
    remote = _github("GET", f"/contents/{path}?ref={revision}", token)
    if remote.get("encoding") != "base64" or remote.get("size", 0) > 24000:
        raise ValueError("Fonte remota inválida ou grande demais.")
    return base64.b64decode(remote["content"], validate=False).decode("utf-8")


def _generate(name, goal):
    with requests.post(
        os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat",
        json={
            "model": os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"),
            "format": "json", "stream": False,
            "options": {"temperature": 0, "num_predict": 3000},
            "messages": [
                {"role": "system", "content": (
                    'Crie ferramenta Python e teste unittest. Retorne JSON {"source":"código",'
                    '"tests":"código de teste","description":"descrição de até 200 caracteres"}. '
                    "A ferramenta expõe run(text: str) -> str, pura, sem rede, arquivos, processos, "
                    "dependências externas ou credenciais. Valide entradas. Não simule capacidades. "
                    "Se o objetivo exigir efeitos externos, não invente implementação; retorne source vazio. "
                    f"O teste importa run de src.tools.generated.{name} e cobre um caso e um limite. "
                    "Não inclua dados pessoais, histórico de conversas ou informações privadas na proposta."
                    "\n" + coding_guidance()
                )},
                {"role": "user", "content": json.dumps({
                    "goal": goal,
                }, ensure_ascii=False)},
            ],
        }, timeout=(5, 120),
    ) as response:
        response.raise_for_status()
        result = json.loads(response.json()["message"]["content"])
    if not isinstance(result, dict):
        raise ValueError("O modelo não retornou uma ferramenta válida.")
    source = _validate_patch("", result.get("source"))
    tests = _validate_patch("", result.get("tests"))
    tree = ast.parse(source)
    if not any(isinstance(node, ast.FunctionDef) and node.name == "run"
               and len(node.args.args) == 1 for node in tree.body):
        raise ValueError("A ferramenta não expõe run(text).")
    test_tree = ast.parse(tests)
    if not any(isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
               for node in ast.walk(test_tree)):
        raise ValueError("A proposta não contém testes.")
    description = result.get("description")
    if not isinstance(description, str) or not 1 <= len(description) <= 200 or "\n" in description:
        raise ValueError("Descrição inválida.")
    return source, tests, description


def build(name, goal, dry_run=True):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError("Nome deve usar 3 a 40 letras minúsculas, números ou underscore.")
    if not isinstance(goal, str) or not 12 <= len(goal.strip()) <= 280:
        raise ValueError("Descreva o objetivo em 12 a 280 caracteres.")
    if dry_run:
        return {"status": "planned", "tool": "custom." + name,
                "steps": ["definir contrato", "gerar código e testes", "validar sintaxe e testes em sandbox",
                          "abrir branch e draft PR", "aguardar CI e revisão humana"],
                "limit": "Ferramentas puras de texto; execução de código arbitrário não está disponível."}
    if os.environ.get("MENOR_AUTODEV_ENABLED") != "1":
        raise ImprovementUnavailable("Autoedição não autorizada neste servidor.")
    token = os.environ.get("MENOR_GITHUB_TOKEN", "").strip()
    if not token:
        raise ImprovementUnavailable("Integração GitHub não configurada.")
    try:
        main = _github("GET", "/git/ref/heads/main", token)["object"]["sha"]
        catalog = json.loads(_source(CATALOG, main, token))
        if not isinstance(catalog, dict) or name in catalog or len(catalog) >= 30:
            raise ValueError("Catálogo inválido, cheio ou nome já existente.")
        documentation = _source(DOC, main, token)
        source, tests, description = _generate(name, goal)
        verification = verify(name, source, tests)
        catalog[name] = description
        files = {
            f"src/tools/generated/{name}.py": source,
            f"tests/test_generated_{name}.py": tests,
            CATALOG: json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
            DOC: documentation + (
                f"\n\n### Ferramenta custom.{name}\n\n{description}\n\n"
                "Entrada: text (até 280 caracteres). Saída: texto. "
                "Uso pelo catálogo após CI, revisão, merge e reinício. "
                "Proposta não equivale a ferramenta incorporada ou aprovada.\n"
            ),
        }
        commit = _github("GET", f"/git/commits/{main}", token)
        tree = _github("POST", "/git/trees", token, json={
            "base_tree": commit["tree"]["sha"],
            "tree": [{"path": path, "mode": "100644", "type": "blob", "content": content}
                     for path, content in files.items()],
        })
        proposed = _github("POST", "/git/commits", token, json={
            "message": f"feat(tools): propõe {name}", "tree": tree["sha"], "parents": [main],
        })
        branch = "codex/menor-ferramenta-" + secrets.token_hex(6)
        _github("POST", "/git/refs", token, json={
            "ref": "refs/heads/" + branch, "sha": proposed["sha"],
        })
        pr = _github("POST", "/pulls", token, json={
            "title": f"feat(tools): ferramenta {name}", "head": branch, "base": "main", "draft": True,
            "body": (
                f"Objetivo: {goal}\n\n{description}\n\n"
                "Inclui implementação, testes unittest, catálogo e documentação. "
                "Sintaxe e testes unittest validados em container sem rede antes da branch. "
                "Aguardar também CI e revisão humana. Sem merge ou instalação automática.\n\n"
                + verification["log"]
            ),
        })
        return {"status": "pr_created", "url": pr["html_url"], "branch": branch,
                "requires_review": True, "tests": verification["status"], "ready": False}
    except (requests.RequestException, ValueError, KeyError, TypeError, SyntaxError) as error:
        raise ImprovementUnavailable(
            "Não foi possível construir a proposta; confira as branches antes de repetir.",
        ) from error

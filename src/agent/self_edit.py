"""Gerador supervisionado de propostas de correção via GitHub.

Nunca executa código gerado no notebook e nunca escreve na main. Para
criar um PR precisa de opt-in explícito e token de escopo limitado.
"""
import ast
import base64
import json
import os
import secrets

import requests

from src.agent.diagnostics import analyze
from src.agent.ponytail import coding_guidance
from src.tools.audit import record

OWNER_REPO = "isaacwerneck/menor-assistant"
API = f"https://api.github.com/repos/{OWNER_REPO}"
ALLOWED = (
    "src/agent/router.py",
    "src/agent/resolve.py",
    "src/agent/image_intent.py",
    "src/agent/short_replies.py",
)
MAX_SOURCE = 24000
MAX_ISSUE = 600
FORBIDDEN = (
    "subprocess", "exec(", "eval(", "__import__", "os.system", "socket",
    "open(", "requests.post(", "requests.get(", "os.environ",
)


class ImprovementUnavailable(RuntimeError):
    pass


def status():
    return {
        "enabled": os.environ.get("MENOR_AUTODEV_ENABLED", "0") == "1",
        "github_connected": bool(os.environ.get("MENOR_GITHUB_TOKEN", "").strip()),
        "allowed_files": list(ALLOWED),
        "last_diagnostics": analyze(),
    }


def choose_target(issue):
    """Associa sintomas a um arquivo previamente autorizado; não usa path do modelo."""
    normalized = issue.casefold()
    if any(word in normalized for word in ("imagem", "foto", "gerar arte", "anexo")):
        return "src/agent/image_intent.py"
    if any(word in normalized for word in ("confirm", "simm", "resposta curta", "memória", "memoria")):
        return "src/agent/resolve.py"
    return "src/agent/router.py"


def _github(method, route, token, **kwargs):
    result = requests.request(
        method, f"{API}{route}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
        timeout=(5, 25), **kwargs,
    )
    result.raise_for_status()
    return result.json()


def _validate_patch(original, proposed):
    if not isinstance(proposed, str) or len(proposed.encode("utf-8")) > MAX_SOURCE:
        raise ValueError("Patch inválido ou grande demais.")
    if proposed == original or not proposed.strip():
        raise ValueError("Nenhuma alteração proposta.")
    ast.parse(proposed)
    previous = original.casefold()
    new = proposed.casefold()
    for fragment in FORBIDDEN:
        if fragment not in previous and fragment in new:
            raise ValueError("Operação proibida adicionada ao patch.")
    return proposed


def _propose_with_model(issue, path, original):
    payload = {
        "model": os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"),
        "format": "json",
        "stream": False,
        "options": {"temperature": 0, "num_predict": 3500},
        "messages": [
            {"role": "system", "content": (
                "Você é revisor de código Python. Corrija apenas a falha relatada no arquivo, "
                "preserve API e comportamento existente. Retorne APENAS JSON: "
                '{"source":"conteúdo integral corrigido","reason":"razão sucinta","tests":"testes recomendados"}. '
                "Não gere shell, novas dependências, rede, credenciais nem imports perigosos."
                "\n" + coding_guidance()
            )},
            {"role": "user", "content": (
                f"Problema: {issue}\nArquivo permitido: {path}\n"
                f"Conteúdo atual:\n{original}"
            )},
        ],
    }
    try:
        response = requests.post(
            os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat",
            json=payload, timeout=(5, 180),
        )
        response.raise_for_status()
        data = json.loads(response.json()["message"]["content"])
        return _validate_patch(original, data.get("source")), {
            "reason": str(data.get("reason", ""))[:300],
            "tests": str(data.get("tests", ""))[:300],
        }
    except (requests.RequestException, ValueError, KeyError, TypeError, SyntaxError) as error:
        raise ImprovementUnavailable("O modelo não conseguiu produzir uma correção validada.") from error


def propose(issue, dry_run=True):
    if not isinstance(issue, str) or not 12 <= len(issue.strip()) <= MAX_ISSUE:
        raise ValueError("Descreva o problema em 12 a 600 caracteres.")
    path = choose_target(issue)
    if dry_run:
        return {"status": "planned", "target": path,
                "steps": ["buscar fonte", "gerar patch", "validar sintaxe", "abrir PR rascunho"]}
    if os.environ.get("MENOR_AUTODEV_ENABLED", "0") != "1":
        raise ImprovementUnavailable("Autoedição não autorizada neste servidor.")
    token = os.environ.get("MENOR_GITHUB_TOKEN", "").strip()
    if not token:
        raise ImprovementUnavailable("Integração GitHub para autoedição não configurada.")
    try:
        main = _github("GET", "/git/ref/heads/main", token)
        revision = main["object"]["sha"]
        remote = _github("GET", f"/contents/{path}?ref={revision}", token)
        original = base64.b64decode(remote["content"]).decode("utf-8")
        if len(original.encode("utf-8")) > MAX_SOURCE:
            raise ImprovementUnavailable("Arquivo de origem ultrapassa o limite.")
        proposal, review = _propose_with_model(issue.strip(), path, original)
        name = "codex/menor-revisao-" + secrets.token_hex(6)
        _github("POST", "/git/refs", token, json={
            "ref": f"refs/heads/{name}", "sha": main["object"]["sha"],
        })
        _github("PUT", f"/contents/{path}", token, json={
            "message": "fix(agent): proposta supervisionada do Menor",
            "content": base64.b64encode(proposal.encode()).decode(),
            "sha": remote["sha"], "branch": name,
        })
        pr = _github("POST", "/pulls", token, json={
            "title": "fix(agent): correção proposta pelo Menor",
            "head": name, "base": "main", "draft": True,
            "body": (
                "Correção sugerida automaticamente, SEM execução local nem merge.\n\n"
                f"Problema: {issue}\n\nMotivo: {review['reason']}\n\n"
                f"Testes recomendados: {review['tests']}\n\n"
                "Revisão humana obrigatória antes do merge; aguardar CI."
            ),
        })
        record("autodev.propose", "planned", ["issue", "path"])
        return {"status": "pr_created", "pr": pr["number"], "url": pr["html_url"],
                "target": path, "requires_review": True, "tests": "pending_ci", "ready": False}
    except requests.RequestException as error:
        raise ImprovementUnavailable("GitHub recusou a proposta ou está indisponível.") from error

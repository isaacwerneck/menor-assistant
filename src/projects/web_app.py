"""Gera pequeno webapp Canvas com três arquivos privados e validação sintática.

Não executa JavaScript gerado, não usa terminal do modelo nem integra CDN.
"""
import hashlib
import html
import json
import os
import re

import requests

from src.memory.store import _write_lock
from src.projects.code_workspace import SOURCE_SCHEMA, _target, check_js_syntax
from src.projects.workspace import ProjectWorkspace

FILES = ("index.html", "style.css", "game.js")
CSS = (
    "body{margin:0;min-height:100vh;display:grid;place-items:center;"
    "background:#111827;color:#eef2ff;font:16px system-ui}"
    "main{max-width:720px;text-align:center;padding:20px}"
    "canvas{width:100%;max-width:640px;background:#080c18;border:2px solid #7c87b4}"
    "button{padding:12px;margin:12px;background:#6573ed;color:white;border:0;border-radius:8px}"
)
DANGEROUS = re.compile(
    r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|eval|Function|"
    r"localStorage|sessionStorage|indexedDB|importScripts|require|process)\b"
    r"|\bimport\s*\(|https?://", re.I,
)
SYSTEM = (
    "Crie somente o conteúdo de game.js para um pequeno aplicativo/jogo Canvas "
    "offline, independente, em JavaScript puro. Use canvas id=game 640x420, "
    "span id=score e button id=restart. Eventos de teclado quando adequado. "
    "Implemente estado inicial e reinício, animação ou interação e pontuação "
    "conforme o pedido. Sem import, require, eval, rede, cookies, armazenamento, "
    "dependências ou código em HTML. Não declare que executou testes. "
    'Retorne somente JSON {"source":"javascript"} sem markdown. '
    "Priorize a menor implementação funcional, com código legível."
)


def _check_js(source):
    if (not isinstance(source, str) or not source.strip() or
            len(source.encode("utf-8")) > 9000 or "\x00" in source or
            source.lstrip().startswith("```") or DANGEROUS.search(source)):
        raise ValueError("Código JS gerado inválido ou não permitido.")
    check_js_syntax(source, required=True)


def build(slug, goal, dry_run=True, workspace=None):
    """Um único consentimento para três arquivos, sem sobrescrita ou execução."""
    if not isinstance(goal, str) or not 12 <= len(goal.strip()) <= 280:
        raise ValueError("Descreva um aplicativo ou jogo em 12 a 280 caracteres.")
    project = workspace or ProjectWorkspace()
    targets = [_target(slug, filename, project) for filename in FILES]
    if dry_run:
        return {"status": "planned", "files": list(FILES),
                "requires_approval": True, "code_will_run": False}
    with requests.post(
        os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat",
        json={"model": os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"),
              "messages": [{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": json.dumps({"goal": goal}, ensure_ascii=False)}],
              "format": SOURCE_SCHEMA, "stream": False,
              "options": {"temperature": 0.1, "num_predict": 1900}},
        timeout=(4, 240),
    ) as response:
        response.raise_for_status()
        data = response.json()
    generated = json.loads(data["message"]["content"])["source"]
    _check_js(generated)
    title = html.escape(goal.strip()[:70], quote=True)
    html_file = ('<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
                 '<meta http-equiv="Content-Security-Policy" content="default-src &apos;none&apos;; '
                 "script-src &apos;self&apos;; style-src &apos;self&apos;; "
                 "connect-src &apos;none&apos;; img-src &apos;self&apos; data:; "
                 'base-uri &apos;none&apos;; form-action &apos;none&apos;">'
                 '<meta name="viewport" content="width=device-width,initial-scale=1">'
                 '<title>' + title + '</title><link rel="stylesheet" href="style.css">'
                 '<main><h1>' + title + '</h1><p>Pontuação: <span id="score">0</span></p>'
                 '<canvas id="game" width="640" height="420"></canvas>'
                 '<p><button id="restart" type="button">Reiniciar</button></p></main>'
                 '<script src="game.js"></script></html>')
    content = {"index.html": html_file, "style.css": CSS, "game.js": generated}
    created = []
    with _write_lock:
        for filename in FILES:
            _target(slug, filename, project)
        try:
            for filename, target in zip(FILES, targets):
                # Exclusive creation prevents overwrite if another action won the race.
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(target, flags, 0o600)
                created.append(target)
                with os.fdopen(fd, "w", encoding="utf-8") as file:
                    file.write(content[filename])
                    file.flush()
                    os.fsync(file.fileno())
        except (OSError, ValueError):
            for path in created:
                path.unlink(missing_ok=True)
            raise
    return {"files": [{"path": "projetos/" + slug + "/arquivos/" + filename,
                       "sha256": hashlib.sha256(content[filename].encode()).hexdigest()}
                      for filename in FILES],
            "syntax_checked": True, "browser_tested": False,
            "executed": False, "review_required": True,
            "note": "Node validou a sintaxe JS; jogo e interface ainda precisam de teste no navegador."}

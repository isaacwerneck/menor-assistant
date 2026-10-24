"""Ferramentas reais do sistema operacional para o Menor v2.

Permite leitura/escrita de arquivos, execução de comandos no terminal e gestão
de planos de projeto de maneira real e verificável.
"""
from pathlib import Path
import subprocess
from typing import Any, Dict, Optional

from src.memory.store import BrainStore

MAX_READ_BYTES = 256 * 1024  # 256 KB


def _resolve_safe_path(filepath: str, base_dir: Optional[str] = None) -> Path:
    """Resolve o caminho de arquivo com segurança."""
    if not filepath or not isinstance(filepath, str):
        raise ValueError("Caminho de arquivo inválido.")

    path = Path(filepath).expanduser()
    if not path.is_absolute():
        base = Path(base_dir).expanduser() if base_dir else Path.cwd()
        path = (base / path).resolve()
    else:
        path = path.resolve()

    return path


def fs_read(filepath: str, max_bytes: int = MAX_READ_BYTES) -> Dict[str, Any]:
    """Lê o conteúdo textual de um arquivo no disco."""
    try:
        path = _resolve_safe_path(filepath)
        if not path.exists():
            return {"success": False, "error": f"Arquivo não encontrado: {filepath}"}
        if not path.is_file():
            return {"success": False, "error": f"O caminho não é um arquivo: {filepath}"}

        size = path.stat().st_size
        if size > max_bytes:
            content = path.read_text(encoding="utf-8", errors="replace")[:max_bytes]
            return {
                "success": True,
                "filepath": str(path),
                "content": content,
                "truncated": True,
                "size_bytes": size,
            }

        content = path.read_text(encoding="utf-8", errors="replace")
        return {
            "success": True,
            "filepath": str(path),
            "content": content,
            "truncated": False,
            "size_bytes": size,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def fs_write(filepath: str, content: str) -> Dict[str, Any]:
    """Cria ou atualiza um arquivo no disco, criando diretórios pais se necessário."""
    try:
        if not isinstance(content, str):
            content = str(content)
        path = _resolve_safe_path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "filepath": str(path),
            "bytes_written": len(content.encode("utf-8")),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def fs_list(dirpath: str = ".") -> Dict[str, Any]:
    """Lista arquivos e subdiretórios em um caminho."""
    try:
        path = _resolve_safe_path(dirpath)
        if not path.exists():
            return {"success": False, "error": f"Diretório não encontrado: {dirpath}"}
        if not path.is_dir():
            return {"success": False, "error": f"O caminho não é um diretório: {dirpath}"}

        items = []
        for entry in sorted(path.iterdir()):
            items.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else None,
            })
        return {"success": True, "dirpath": str(path), "items": items}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def terminal_run(command: str, cwd: str = ".", timeout_seconds: int = 45) -> Dict[str, Any]:
    """Executa um comando real no terminal e retorna saída e código de status."""
    try:
        if not command or not isinstance(command, str):
            return {"success": False, "error": "Comando inválido."}

        work_dir = _resolve_safe_path(cwd)
        if not work_dir.exists() or not work_dir.is_dir():
            work_dir = Path.cwd()

        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-10000:] if proc.stdout else "",
            "stderr": proc.stderr[-10000:] if proc.stderr else "",
            "cwd": str(work_dir),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Comando excedeu o timeout de {timeout_seconds}s"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def save_plan(project_slug: str, markdown_content: str, store: Optional[BrainStore] = None) -> Dict[str, Any]:
    """Salva ou atualiza o PLANO.md do projeto no cérebro persistente."""
    try:
        store = store or BrainStore()
        store.initialize()
        plan_rel_path = f"projetos/{project_slug}/PLANO.md"
        plan_full_path = store.brain_dir / plan_rel_path
        plan_full_path.parent.mkdir(parents=True, exist_ok=True)
        store.write_note(plan_rel_path, markdown_content)
        return {
            "success": True,
            "project": project_slug,
            "plan_path": str(plan_full_path),
            "bytes": len(markdown_content.encode("utf-8")),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# Schemas para o Tool Calling oficial do Ollama / OpenAI
CORE_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "fs_read",
            "description": "Lê o conteúdo de um arquivo de texto no disco.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Caminho do arquivo a ser lido."}
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fs_write",
            "description": "Cria ou substitui um arquivo no disco com o conteúdo especificado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Caminho do arquivo a salvar."},
                    "content": {"type": "string", "description": "Conteúdo textual completo do arquivo."},
                },
                "required": ["filepath", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fs_list",
            "description": "Lista arquivos e subpastas de um diretório.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dirpath": {"type": "string", "description": "Caminho do diretório (padrão '.')."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminal_run",
            "description": "Executa comando no terminal (pytest, git, python, npm) e obtém stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Linha de comando a ser executada."},
                    "cwd": {"type": "string", "description": "Diretório de trabalho onde rodar o comando."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_plan",
            "description": "Salva ou atualiza a especificação e tarefas (PLANO.md) de um projeto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_slug": {"type": "string", "description": "Identificador do projeto (slug)."},
                    "markdown_content": {"type": "string", "description": "Conteúdo em Markdown do plano."},
                },
                "required": ["project_slug", "markdown_content"],
            },
        },
    },
]

TOOL_DISPATCHER = {
    "fs_read": fs_read,
    "fs_write": fs_write,
    "fs_list": fs_list,
    "terminal_run": terminal_run,
    "save_plan": save_plan,
}

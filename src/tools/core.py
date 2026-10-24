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


def web_search(query: str) -> Dict[str, Any]:
    """Pesquisa na web por termos públicos e retorna os resultados mais relevantes com URLs e títulos."""
    try:
        from src.tools.web import search
        res = search(query)
        return {
            "success": True,
            "query": query,
            "results": res.get("results", []),
            "provider": res.get("provider", "web"),
        }
    except Exception as exc:
        return {"success": False, "error": f"Falha na busca web: {str(exc)}"}


def web_read(url: str, query: Optional[str] = None) -> Dict[str, Any]:
    """Lê o conteúdo em texto limpo de uma página web pública (URL)."""
    try:
        from src.tools.web import read
        res = read(url, query=query)
        return {
            "success": True,
            "url": res.get("url", url),
            "content": res.get("text", "")[:8000],
            "truncated": res.get("truncated", False),
        }
    except Exception as exc:
        return {"success": False, "error": f"Falha ao ler página web: {str(exc)}"}


DYNAMIC_TOOLS_DIR = Path(__file__).parent / "dynamic"


def create_new_tool(
    name: str,
    code: str,
    test_command: str,
    description: str,
    parameters_schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Cria, valida, testa com terminal_run e registra dinamicamente uma nova ferramenta Python.

    Se os testes passarem com sucesso, a ferramenta torna-se disponível imediatamente
    no assistente para chamadas futuras.
    """
    try:
        import ast
        import importlib.util
        import re

        clean_name = re.sub(r"[^a-zA-Z0-9_]", "", name).strip().lower()
        if not clean_name:
            return {"success": False, "error": "Nome de ferramenta inválido."}

        try:
            ast.parse(code)
        except SyntaxError as syn_err:
            return {
                "success": False,
                "error": f"Erro de sintaxe Python na ferramenta: {syn_err}",
                "phase": "syntax_validation",
            }

        DYNAMIC_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        init_file = DYNAMIC_TOOLS_DIR / "__init__.py"
        if not init_file.exists():
            init_file.write_text("# Dynamic tools package\n", encoding="utf-8")

        target_file = DYNAMIC_TOOLS_DIR / f"{clean_name}.py"
        target_file.write_text(code, encoding="utf-8")

        test_res = terminal_run(test_command)
        if not test_res.get("success"):
            return {
                "success": False,
                "error": f"Testes falharam: {test_res.get('stderr') or test_res.get('stdout')}",
                "phase": "test_execution",
                "exit_code": test_res.get("exit_code"),
            }

        spec = importlib.util.spec_from_file_location(f"src.tools.dynamic.{clean_name}", str(target_file))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            tool_callable = getattr(mod, clean_name, None)
            if not callable(tool_callable):
                return {
                    "success": False,
                    "error": f"O módulo foi carregado, mas não possui a função chamada '{clean_name}'.",
                }

            TOOL_DISPATCHER[clean_name] = tool_callable
            schema = {
                "type": "function",
                "function": {
                    "name": clean_name,
                    "description": description or f"Ferramenta criada dinamicamente: {clean_name}",
                    "parameters": parameters_schema or {
                        "type": "object",
                        "properties": {},
                    },
                },
            }
            filtered_schemas = [s for s in CORE_TOOLS_SCHEMA if s.get("function", {}).get("name") != clean_name]
            filtered_schemas.append(schema)
            CORE_TOOLS_SCHEMA.clear()
            CORE_TOOLS_SCHEMA.extend(filtered_schemas)

            return {
                "success": True,
                "tool_name": clean_name,
                "filepath": str(target_file),
                "message": f"Ferramenta '{clean_name}' criada, testada e registrada com sucesso!",
            }
        return {"success": False, "error": "Não foi possível carregar o módulo gerado."}
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
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Pesquisa termos na web e retorna uma lista de links e títulos relevantes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termo de busca público."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_read",
            "description": "Lê o conteúdo em texto limpo de uma página web pública através de uma URL HTTPS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL HTTPS pública da página web."},
                    "query": {"type": "string", "description": "Trecho opcional de foco na leitura."}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_new_tool",
            "description": "Cria, testa e registra dinamicamente uma nova ferramenta Python quando necessário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nome da função/ferramenta (ex: 'convert_units')."},
                    "code": {"type": "string", "description": "Código Python completo implementando a função."},
                    "test_command": {"type": "string", "description": "Comando de terminal para testar a ferramenta."},
                    "description": {"type": "string", "description": "Descrição detalhada para a IA."},
                    "parameters_schema": {"type": "object", "description": "Schema JSON dos parâmetros aceitos."},
                },
                "required": ["name", "code", "test_command", "description"],
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
    "web_search": web_search,
    "web_read": web_read,
    "create_new_tool": create_new_tool,
}

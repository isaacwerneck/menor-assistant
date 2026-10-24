"""Inteligência de código em nível de símbolo e mapa de repositório (Serena Lite & Aider Pattern).

Fornece navegação semântica em AST nativo e visão compacta do repositório
para economizar contexto e evitar alucinação de código em modelos locais.
"""
from pathlib import Path
import ast
import os
import re
from typing import Any, Dict, List, Optional, Set

from src.tools.core import _resolve_safe_path

# Pastas e padrões a ignorar para manter o mapa compacto e rápido
IGNORED_DIRS: Set[str] = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".gemini",
    ".agents",
    "dist",
    "build",
    ".mypy_cache",
    ".tox",
    ".coverage",
}

IGNORED_EXTS: Set[str] = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".zip",
    ".tar",
    ".gz",
}


def _extract_py_outline(filepath: Path) -> List[str]:
    """Extrai classes, métodos e funções de topo de um arquivo Python via AST."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(content, filename=str(filepath))
    except Exception:
        return []

    lines: List[str] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            args = [a.arg for a in node.args.args]
            doc = ast.get_docstring(node)
            doc_hint = f"  # {doc.strip().splitlines()[0][:60]}" if doc else ""
            lines.append(f"  {prefix} {node.name}({', '.join(args)}){doc_hint}")
        elif isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            base_str = f"({', '.join(bases)})" if bases else ""
            lines.append(f"  class {node.name}{base_str}:")
            for subnode in node.body:
                if isinstance(subnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sub_prefix = "async def" if isinstance(subnode, ast.AsyncFunctionDef) else "def"
                    sub_args = [a.arg for a in subnode.args.args]
                    lines.append(f"    {sub_prefix} {subnode.name}({', '.join(sub_args)})")

    return lines


def _extract_js_ts_outline(filepath: Path) -> List[str]:
    """Extrai funções e classes de arquivos JS/TS usando regex pragmático."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    lines: List[str] = []
    pattern = re.compile(
        r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s+([a-zA-Z0-9_$]+)|class\s+([a-zA-Z0-9_$]+)|(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\()",
        re.MULTILINE,
    )
    for match in pattern.finditer(content):
        fn_name = match.group(1) or match.group(3)
        class_name = match.group(2)
        if class_name:
            lines.append(f"  class {class_name}")
        elif fn_name:
            lines.append(f"  function {fn_name}()")
    return lines[:15]


def repo_map(
    root_dir: str = ".",
    max_depth: int = 4,
    max_files: int = 50,
) -> Dict[str, Any]:
    """Gera um mapa compacto de símbolos do projeto no estilo Aider/Tree-Sitter.

    Mostra classes, métodos e funções dos arquivos para navegação precisa sem estourar o contexto.
    """
    try:
        base = _resolve_safe_path(root_dir)
        if not base.exists() or not base.is_dir():
            return {"success": False, "error": f"Diretório não encontrado: {root_dir}"}

        collected_files: List[Path] = []

        for root, dirs, files in os.walk(str(base)):
            # Poda diretórios ignorados
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]

            rel_root = Path(root).relative_to(base)
            depth = len(rel_root.parts)
            if depth > max_depth:
                continue

            for f in sorted(files):
                p = Path(root) / f
                if p.suffix in IGNORED_EXTS or f.startswith("."):
                    continue
                collected_files.append(p)
                if len(collected_files) >= max_files:
                    break
            if len(collected_files) >= max_files:
                break

        outline_sections: List[str] = []

        for p in collected_files:
            rel = p.relative_to(base).as_posix()
            if p.suffix == ".py":
                symbols = _extract_py_outline(p)
                if symbols:
                    outline_sections.append(f"{rel}:\n" + "\n".join(symbols))
                else:
                    outline_sections.append(f"{rel} (módulo/script)")
            elif p.suffix in (".js", ".ts", ".mjs"):
                symbols = _extract_js_ts_outline(p)
                if symbols:
                    outline_sections.append(f"{rel}:\n" + "\n".join(symbols))
                else:
                    outline_sections.append(f"{rel}")
            elif p.suffix in (".json", ".toml", ".yaml", ".yml", ".md", ".sh"):
                outline_sections.append(f"{rel}")

        result_text = "\n".join(outline_sections)
        return {
            "success": True,
            "root_dir": str(base),
            "files_analyzed": len(collected_files),
            "repo_map": result_text,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def symbol_lookup(
    symbol_name: str,
    file_hint: Optional[str] = None,
    root_dir: str = ".",
) -> Dict[str, Any]:
    """Busca cirúrgica por definições de símbolos (classes, funções, variáveis) via AST e LSP.

    Inspirado no toolkit Serena: localiza o símbolo exato, número da linha e assinatura
    sem precisar ler arquivos completos.
    """
    try:
        if not symbol_name or not isinstance(symbol_name, str):
            return {"success": False, "error": "Nome de símbolo inválido."}

        target_symbol = symbol_name.strip()
        base = _resolve_safe_path(root_dir)

        # Se houver servidor Serena MCP configurado no ambiente, tenta consultá-lo
        serena_url = os.environ.get("SERENA_MCP_URL")
        if serena_url:
            try:
                import requests
                resp = requests.post(
                    f"{serena_url.rstrip('/')}/v1/symbol",
                    json={"symbol": target_symbol, "file_hint": file_hint},
                    timeout=1.5,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("matches"):
                        return {"success": True, "provider": "serena_mcp", **data}
            except Exception:
                pass  # Fallback gracioso imediato para AST nativo

        # Busca nativa em Python via AST
        matches: List[Dict[str, Any]] = []

        files_to_check: List[Path] = []
        if file_hint:
            hint_path = _resolve_safe_path(file_hint, base_dir=str(base))
            if hint_path.exists() and hint_path.is_file():
                files_to_check.append(hint_path)

        if not files_to_check:
            for root, dirs, files in os.walk(str(base)):
                dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
                for f in files:
                    if f.endswith(".py"):
                        files_to_check.append(Path(root) / f)

        for p in files_to_check:
            try:
                code = p.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(code, filename=str(p))
            except Exception:
                continue

            rel_path = p.relative_to(base).as_posix()
            lines = code.splitlines()

            for node in ast.walk(tree):
                matched = False
                sym_type = "unknown"
                signature = ""

                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == target_symbol or node.name.lower() == target_symbol.lower():
                        matched = True
                        sym_type = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
                        args = [a.arg for a in node.args.args]
                        signature = f"{node.name}({', '.join(args)})"
                elif isinstance(node, ast.ClassDef):
                    if node.name == target_symbol or node.name.lower() == target_symbol.lower():
                        matched = True
                        sym_type = "class"
                        bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                        signature = f"class {node.name}" + (f"({', '.join(bases)})" if bases else "")
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and (
                            target.id == target_symbol or target.id.lower() == target_symbol.lower()
                        ):
                            matched = True
                            sym_type = "variable"
                            signature = target.id

                if matched:
                    start_line = getattr(node, "lineno", 1)
                    end_line = getattr(node, "end_lineno", start_line)
                    doc = ast.get_docstring(node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else None

                    # Extrai até 5 linhas de snippet de código da definição
                    snippet_lines = lines[start_line - 1 : min(end_line, start_line + 4)]
                    snippet = "\n".join(snippet_lines)

                    matches.append({
                        "filepath": rel_path,
                        "name": target_symbol,
                        "type": sym_type,
                        "signature": signature,
                        "start_line": start_line,
                        "end_line": end_line,
                        "docstring": doc.strip() if doc else None,
                        "snippet": snippet,
                    })

        return {
            "success": True,
            "provider": "ast_native",
            "symbol": target_symbol,
            "found_count": len(matches),
            "matches": matches,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}

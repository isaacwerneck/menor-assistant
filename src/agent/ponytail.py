"""Diretrizes locais Ponytail para trabalho supervisionado e anti-bloat de código.

Aplica a filosofia de Senior Dev Preguiçoso: menor mudança que resolve o problema,
preferência à standard library e rejeição a abstrações desnecessárias (YAGNI).
"""
from pathlib import Path
import ast
from typing import Any, Dict, List

_SKILL = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "ponytail" / "SKILL.md"

REINVENTED_STDLIB_WARNINGS = {
    "requests": "Considere urllib.request ou http.client nativo se for uma requisição HTTP simples.",
    "aiohttp": "Para chamadas assíncronas pontuais, avalie se asyncio + urllib bastam.",
    "numpy": "Para cálculos matemáticos básicos de listas ou vetores, a stdlib 'math' e list comprehensions bastam.",
    "pandas": "Para arquivos CSV ou JSON tabulares, o módulo 'csv' e 'json' nativos são mais leves.",
}


def coding_guidance() -> str:
    """Lê a parte aplicável da skill versionada; não executa conteúdo de terceiros."""
    if not _SKILL.exists():
        return (
            "Diretriz de qualidade Ponytail:\n"
            "- A menor mudança completa que resolve o problema.\n"
            "- Standard library antes de novas dependências.\n"
            "- Sem código para o futuro ou abstrações sem uso imediato (YAGNI)."
        )
    content = _SKILL.read_text(encoding="utf-8")
    start = content.index("## Before you write")
    end = content.index("## Levels", start)
    return "Diretriz de qualidade, não é autorização de ferramenta:\n" + content[start:end].strip()


def get_ponytail_system_prompt() -> str:
    """Retorna diretrizes cirúrgicas Ponytail para injeção no prompt de sistema."""
    return (
        "[DIRETRIZES PONYTAIL - SENIOR DEV PRAGMÁTICO]:\n"
        "1. Faça a menor mudança completa que resolve o problema (YAGNI). Não crie código especulativo.\n"
        "2. Sempre prefira a Standard Library do Python antes de solicitar ou importar dependências externas.\n"
        "3. Para editar código existente, use SEMPRE 'fs_patch' em vez de reescrever tudo com 'fs_write'.\n"
        "4. Antes de mexer em arquivos desconhecidos, use 'repo_map' ou 'symbol_lookup' para ver a estrutura exata."
    )


def lint_tool_creation(name: str, code: str, description: str = "") -> Dict[str, Any]:
    """Valida a criação de novas ferramentas sob a ótica do Ponytail.

    Impede criação de ferramentas redundantes (que reinventam a stdlib ou duplicam terminal_run).
    """
    warnings: List[str] = []

    try:
        tree = ast.parse(code)
    except SyntaxError as err:
        return {
            "passed": False,
            "reason": f"Código possui erro de sintaxe: {err}",
            "warnings": warnings,
        }

    # 1. Verifica imports desnecessários ou bibliotecas externas pesadas
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_pkg = alias.name.split(".")[0]
                if root_pkg in REINVENTED_STDLIB_WARNINGS:
                    warnings.append(f"Import '{root_pkg}': {REINVENTED_STDLIB_WARNINGS[root_pkg]}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_pkg = node.module.split(".")[0]
                if root_pkg in REINVENTED_STDLIB_WARNINGS:
                    warnings.append(f"Import '{root_pkg}': {REINVENTED_STDLIB_WARNINGS[root_pkg]}")

    # 2. Verifica se a ferramenta é um mero wrapper inútil de terminal_run
    # Ex: ferramentas que só chamam subprocess.run("ls") ou subprocess.run("dir")
    total_statements = len(tree.body)
    if total_statements <= 2 and "subprocess" in code and len(code.splitlines()) < 15:
        # Checa se apenas encapsula um comando shell sem processamento
        pass  # Permitido se o operador quiser conveniência, mas adiciona alerta
        warnings.append(
            "A ferramenta aparenta ser um wrapper simples de terminal; considere usar terminal_run diretamente."
        )

    # 3. Verifica tamanho excessivo (> 250 linhas em ferramenta dinâmica sem testes)
    line_count = len(code.splitlines())
    if line_count > 250:
        return {
            "passed": False,
            "reason": (
                f"Ferramenta dinâmica muito longa ({line_count} linhas). "
                "Divida em módulos menores ou simplifique."
            ),
            "warnings": warnings,
        }

    return {
        "passed": True,
        "warnings": warnings,
        "reason": "Código aprovado pelo linter de simplicidade Ponytail.",
    }

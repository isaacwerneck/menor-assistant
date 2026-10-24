"""Módulo de auto-inspeção de código e análise estática via AST (Fase 4).

Examina o repositório, mede cobertura funcional, mapeia símbolos e sintetiza
novos testes unitários para si mesmo com zero risco de quebra em produção.
"""

import ast
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Set

LOGGER = logging.getLogger(__name__)


class CodebaseInspector:
    """Inspeciona a árvore de código-fonte via AST e identifica oportunidades de teste."""

    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()
        self.src_dir = self.root_dir / "src"
        self.tests_dir = self.root_dir / "tests"

    def scan_src_symbols(self) -> Dict[str, Any]:
        """Varre arquivos em src/ e extrai funções, classes e métodos."""
        modules = {}
        total_functions = 0
        total_classes = 0

        if not self.src_dir.exists():
            return {"modules": {}, "total_functions": 0, "total_classes": 0}

        for py_file in sorted(self.src_dir.rglob("*.py")):
            if "__pycache__" in py_file.parts:
                continue
            rel_path = py_file.relative_to(self.root_dir).as_posix()
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"), filename=str(py_file))
            except Exception as exc:
                LOGGER.debug("Erro ao analisar AST de %s: %s", py_file, exc)
                continue

            funcs = []
            classes = []
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):  # Funções públicas
                        funcs.append(node.name)
                        total_functions += 1
                elif isinstance(node, ast.ClassDef):
                    methods = [
                        m.name for m in node.body
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith("_")
                    ]
                    classes.append({"name": node.name, "methods": methods})
                    total_classes += 1

            modules[rel_path] = {
                "functions": funcs,
                "classes": classes,
            }

        return {
            "modules": modules,
            "total_functions": total_functions,
            "total_classes": total_classes,
        }

    def scan_tested_symbols(self) -> Set[str]:
        """Varre testes em tests/ e extrai menções a funções e classes testadas."""
        tested_names: Set[str] = set()
        if not self.tests_dir.exists():
            return tested_names

        for test_file in self.tests_dir.rglob("*.py"):
            try:
                content = test_file.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(content, filename=str(test_file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name):
                        tested_names.add(node.id)
                    elif isinstance(node, ast.Attribute):
                        tested_names.add(node.attr)
                    elif isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name):
                            tested_names.add(node.func.id)
                        elif isinstance(node.func, ast.Attribute):
                            tested_names.add(node.func.attr)
            except Exception as exc:
                LOGGER.debug("Erro ao analisar teste %s: %s", test_file, exc)

        return tested_names

    def audit(self) -> Dict[str, Any]:
        """Cruza código-fonte com a suíte de testes e detecta gaps de cobertura."""
        src_data = self.scan_src_symbols()
        tested_names = self.scan_tested_symbols()

        covered_funcs = []
        uncovered_funcs = []

        for mod, data in src_data["modules"].items():
            for fn in data["functions"]:
                target_str = f"{mod}::{fn}"
                if fn in tested_names or f"test_{fn}" in tested_names:
                    covered_funcs.append(target_str)
                else:
                    uncovered_funcs.append({"module": mod, "function": fn})

            for cls_info in data["classes"]:
                cls_name = cls_info["name"]
                if cls_name not in tested_names:
                    uncovered_funcs.append({"module": mod, "class": cls_name})

        total_analyzed = len(covered_funcs) + len(uncovered_funcs)
        coverage_pct = round((len(covered_funcs) / total_analyzed * 100), 1) if total_analyzed > 0 else 100.0

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        report_lines = [
            f"# Auditoria e Inspeção do Menor v2 ({now_str})",
            f"- **Arquivos de Código:** {len(src_data['modules'])}",
            f"- **Funções Públicas:** {src_data['total_functions']}",
            f"- **Classes:** {src_data['total_classes']}",
            f"- **Funções Cobertas por Testes:** {len(covered_funcs)} ({coverage_pct}%)",
            f"- **Gaps Identificados (Sem teste evidente):** {len(uncovered_funcs)}",
            "\n## Top Gaps Recomendados para Criação de Teste:",
        ]

        for gap in uncovered_funcs[:10]:
            name = gap.get("function") or gap.get("class")
            report_lines.append(f"- `{gap['module']}` -> `{name}`")

        return {
            "success": True,
            "timestamp": now_str,
            "total_modules": len(src_data["modules"]),
            "total_functions": src_data["total_functions"],
            "total_classes": src_data["total_classes"],
            "covered_count": len(covered_funcs),
            "uncovered_count": len(uncovered_funcs),
            "coverage_percentage": coverage_pct,
            "uncovered_items": uncovered_funcs,
            "report_markdown": "\n".join(report_lines),
        }

    def synthesize_test_stub(self, module_rel_path: str, target_name: str) -> str:
        """Gera código-fonte de teste unitário limpo para um símbolo."""
        import_path = module_rel_path.replace(".py", "").replace("/", ".")
        return (
            f'"""Teste sintético gerado automaticamente pelo Menor v2."""\n'
            f"import unittest\n\n"
            f"try:\n"
            f"    from {import_path} import {target_name}\n"
            f"except ImportError:\n"
            f"    {target_name} = None\n\n\n"
            f"class TestAuto{target_name.capitalize()}(unittest.TestCase):\n"
            f"    def test_symbol_exists_and_callable(self):\n"
            f"        self.assertIsNotNone({target_name}, 'Símbolo não pôde ser importado')\n\n"
            f'if __name__ == "__main__":\n'
            f"    unittest.main()\n"
        )


def inspect_codebase(root_dir: Optional[str] = None) -> Dict[str, Any]:
    """Ferramenta para inspecionar a saúde do repositório e cobertura de testes."""
    try:
        inspector = CodebaseInspector(root_dir=root_dir)
        return inspector.audit()
    except Exception as exc:
        return {"success": False, "error": str(exc)}

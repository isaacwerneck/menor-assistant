"""Testes unitários para as novas skills avançadas do Menor v2:
- Fase 1: Serena Lite (symbol_lookup) e Aider Repo-Map (repo_map)
- Fase 2: Edição cirúrgica (fs_patch) e Pipeline FSM (AutonomousCodingPipeline)
- Fase 3: Ponytail Decision Linter
- Fase 4: DSPy Prompt Optimizer
"""
from pathlib import Path
import sys
import tempfile
import unittest

from src.tools.core import (
    fs_patch,
    repo_map,
    symbol_lookup,
    CORE_TOOLS_SCHEMA,
    TOOL_DISPATCHER,
)
from src.agent.ponytail import lint_tool_creation, get_ponytail_system_prompt
from src.agent.coding_pipeline import AutonomousCodingPipeline
from src.agent.prompt_optimizer import PromptOptimizer
from src.memory.store import BrainStore


class TestAdvancedSkillsV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    # --- Fase 1: Repo-Map e Symbol Lookup ---
    def test_repo_map_extraction(self):
        sample_py = self.base / "math_helper.py"
        sample_py.write_text(
            'class Calculator:\n'
            '    def add(self, a, b):\n'
            '        """Soma dois valores."""\n'
            '        return a + b\n\n'
            'def multiply(x, y):\n'
            '    """Multiplica dois valores."""\n'
            '    return x * y\n',
            encoding="utf-8",
        )

        res = repo_map(root_dir=str(self.base))
        self.assertTrue(res["success"])
        self.assertIn("class Calculator", res["repo_map"])
        self.assertIn("def add", res["repo_map"])
        self.assertIn("def multiply", res["repo_map"])

    def test_symbol_lookup(self):
        sample_file = self.base / "models.py"
        sample_file.write_text(
            'class UserAccount:\n'
            '    def __init__(self, username):\n'
            '        self.username = username\n\n'
            'def get_current_user(token):\n'
            '    return token\n',
            encoding="utf-8",
        )

        # Busca pela classe
        res_class = symbol_lookup("UserAccount", root_dir=str(self.base))
        self.assertTrue(res_class["success"])
        self.assertGreaterEqual(res_class["found_count"], 1)
        self.assertEqual(res_class["matches"][0]["type"], "class")
        self.assertEqual(res_class["matches"][0]["start_line"], 1)

        # Busca pela função
        res_fn = symbol_lookup("get_current_user", root_dir=str(self.base))
        self.assertTrue(res_fn["success"])
        self.assertGreaterEqual(res_fn["found_count"], 1)
        self.assertEqual(res_fn["matches"][0]["type"], "function")

    # --- Fase 2: fs_patch e Pipeline FSM ---
    def test_fs_patch_exact_match(self):
        target = self.base / "service.py"
        original = (
            "def handle_request():\n"
            "    status = 500\n"
            "    return status\n"
        )
        target.write_text(original, encoding="utf-8")

        search_b = "    status = 500\n"
        replace_b = "    status = 200\n"

        res = fs_patch(str(target), search_b, replace_b)
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(res["lines_removed"], 1)
        self.assertEqual(res["lines_added"], 1)

        content = target.read_text(encoding="utf-8")
        self.assertIn("status = 200", content)
        self.assertNotIn("status = 500", content)

    def test_fs_patch_ambiguous_multiple_matches(self):
        target = self.base / "dups.py"
        target.write_text("item = 1\nitem = 1\n", encoding="utf-8")

        res = fs_patch(str(target), "item = 1", "item = 2")
        self.assertFalse(res["success"])
        self.assertIn("encontrado 2 vezes", res["error"])

    def test_fs_patch_not_found(self):
        target = self.base / "file.py"
        target.write_text("x = 10\n", encoding="utf-8")

        res = fs_patch(str(target), "y = 20", "y = 30")
        self.assertFalse(res["success"])
        self.assertIn("não encontrado", res["error"])

    def test_autonomous_coding_pipeline_success(self):
        target = self.base / "algo.py"
        target.write_text("def solve():\n    return False\n", encoding="utf-8")

        # Teste que falha inicialmente se o retorno for False
        test_script = (
            f'"{sys.executable}" -c "import sys; sys.path.insert(0, r\'{self.base}\'); '
            'import algo; assert algo.solve() is True"'
        )

        pipeline = AutonomousCodingPipeline(max_attempts=2)
        res = pipeline.run_task(
            target_file=str(target),
            task_instruction="Mude o retorno para True",
            test_command=test_script,
            direct_patch={"search_block": "    return False\n", "replace_block": "    return True\n"},
        )

        self.assertTrue(res.success)
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(res.attempts, 1)
        self.assertEqual(len(res.patches_applied), 1)

    def test_autonomous_coding_pipeline_circuit_breaker(self):
        target = self.base / "broken.py"
        target.write_text("val = 1\n", encoding="utf-8")

        test_script = f'"{sys.executable}" -c "assert False"'

        # Fornece gerador para segunda tentativa que também falha no teste
        gen_call_count = [0]

        def dummy_patch_gen(f, c, i, e):
            gen_call_count[0] += 1
            return {"search_block": "val = 2\n", "replace_block": "val = 3\n"}

        pipeline = AutonomousCodingPipeline(max_attempts=2)
        res = pipeline.run_task(
            target_file=str(target),
            task_instruction="Conserte o código",
            test_command=test_script,
            direct_patch={"search_block": "val = 1\n", "replace_block": "val = 2\n"},
            patch_generator=dummy_patch_gen,
        )

        self.assertFalse(res.success)
        self.assertEqual(res.status, "CIRCUIT_BREAKER_EXCEEDED")
        self.assertEqual(res.attempts, 2)
        self.assertIn("continuaram falhando", res.error_message)

    # --- Fase 3: Ponytail Decision Linter ---
    def test_ponytail_linter_warns_on_reinvented_stdlib(self):
        bloated_code = (
            "import pandas as pd\n"
            "def read_table():\n"
            "    return pd.DataFrame()\n"
        )
        res = lint_tool_creation("read_table", bloated_code)
        self.assertTrue(res["passed"])
        self.assertGreaterEqual(len(res["warnings"]), 1)
        self.assertTrue(any("csv" in w for w in res["warnings"]))

    def test_ponytail_linter_rejects_huge_dynamic_tool(self):
        huge_code = "\n".join([f"x_{i} = {i}" for i in range(300)])
        res = lint_tool_creation("huge_tool", huge_code)
        self.assertFalse(res["passed"])
        self.assertIn("muito longa", res["reason"])

    def test_ponytail_system_prompt_content(self):
        prompt = get_ponytail_system_prompt()
        self.assertIn("PONYTAIL", prompt)
        self.assertIn("fs_patch", prompt)
        self.assertIn("repo_map", prompt)

    # --- Fase 4: DSPy Prompt Optimizer ---
    def test_prompt_optimizer_compile_and_load(self):
        store = BrainStore(data_dir=str(self.base))
        optimizer = PromptOptimizer(store=store)

        compiled = optimizer.compile()
        self.assertIn("active_rules", compiled)
        self.assertGreaterEqual(compiled["total_compiled"], 1)

        rules = optimizer.load_rules()
        self.assertIsInstance(rules, list)
        self.assertIn("fs_patch", rules[0])

        injection = optimizer.format_system_injection()
        self.assertIn("[DIRETRIZES TÉCNICAS REFINADAS", injection)

    # --- Verificação de Schemas e Tool Dispatcher ---
    def test_core_tools_registered(self):
        self.assertIn("fs_patch", TOOL_DISPATCHER)
        self.assertIn("repo_map", TOOL_DISPATCHER)
        self.assertIn("symbol_lookup", TOOL_DISPATCHER)

        names = [s["function"]["name"] for s in CORE_TOOLS_SCHEMA if "function" in s]
        self.assertIn("fs_patch", names)
        self.assertIn("repo_map", names)
        self.assertIn("symbol_lookup", names)


if __name__ == "__main__":
    unittest.main()

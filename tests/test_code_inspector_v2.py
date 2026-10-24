"""Testes da Auto-Inspeção de Código AST e Gerador de Testes (Fase 4)."""
import tempfile
import unittest
from pathlib import Path

from src.agent.inspector import CodebaseInspector, inspect_codebase


class TestCodeInspectorV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.src = self.root / "src"
        self.tests = self.root / "tests"
        self.src.mkdir()
        self.tests.mkdir()

        # Cria módulos de teste
        (self.src / "sample_service.py").write_text(
            "def calculate_total(a, b):\n    return a + b\n\n"
            "def uncovered_fn(x):\n    return x * 2\n\n"
            "class EngineManager:\n    def start(self):\n        pass\n",
            encoding="utf-8",
        )

        (self.tests / "test_sample.py").write_text(
            "import unittest\n"
            "from src.sample_service import calculate_total\n\n"
            "class TestSample(unittest.TestCase):\n"
            "    def test_calc(self):\n"
            "        self.assertEqual(calculate_total(1, 2), 3)\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scan_src_symbols(self):
        inspector = CodebaseInspector(root_dir=str(self.root))
        res = inspector.scan_src_symbols()
        self.assertEqual(res["total_functions"], 2)
        self.assertEqual(res["total_classes"], 1)

    def test_scan_tested_symbols(self):
        inspector = CodebaseInspector(root_dir=str(self.root))
        tested = inspector.scan_tested_symbols()
        self.assertIn("calculate_total", tested)

    def test_audit_identifies_gaps(self):
        inspector = CodebaseInspector(root_dir=str(self.root))
        audit_res = inspector.audit()
        self.assertTrue(audit_res["success"])
        self.assertEqual(audit_res["covered_count"], 1)
        self.assertGreaterEqual(audit_res["uncovered_count"], 1)
        self.assertIn("uncovered_fn", [g.get("function") for g in audit_res["uncovered_items"]])
        self.assertIn("# Auditoria", audit_res["report_markdown"])

    def test_synthesize_test_stub(self):
        inspector = CodebaseInspector(root_dir=str(self.root))
        code = inspector.synthesize_test_stub("src/sample_service.py", "uncovered_fn")
        self.assertIn("from src.sample_service import uncovered_fn", code)
        self.assertIn("class TestAutoUncovered_fn", code)

    def test_tool_inspect_codebase(self):
        res = inspect_codebase(root_dir=str(self.root))
        self.assertTrue(res["success"])
        self.assertIn("coverage_percentage", res)


if __name__ == "__main__":
    unittest.main()

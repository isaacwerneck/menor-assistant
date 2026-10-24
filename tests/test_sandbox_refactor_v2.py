"""Testes da Auto-Refatoração em Sandbox Git Isolada (Fase 5)."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agent.sandbox_refactor import SandboxRefactorEngine, trial_code_refactoring
from src.memory.store import BrainStore


class TestSandboxRefactorV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = BrainStore(data_dir=self.temp_dir.name)
        self.store.initialize()

        self.repo_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.repo_dir.name)

        # Inicializa git fixture
        subprocess.run(["git", "init"], cwd=str(self.repo), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(self.repo), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(self.repo), capture_output=True)

        # Arquivo de teste
        (self.repo / "sample.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "sample.py"], cwd=str(self.repo), capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=str(self.repo), capture_output=True)

    def tearDown(self):
        self.temp_dir.cleanup()
        self.repo_dir.cleanup()

    def test_tree_clean_check(self):
        engine = SandboxRefactorEngine(root_dir=str(self.repo), store=self.store)
        self.assertTrue(engine.is_tree_clean())

        # Modifica arquivo sem commit
        (self.repo / "sample.py").write_text("x = 2\n", encoding="utf-8")
        self.assertFalse(engine.is_tree_clean())

    def test_block_not_found_handling(self):
        engine = SandboxRefactorEngine(root_dir=str(self.repo), store=self.store)
        res = engine.run_refactoring_trial(
            target_file="sample.py",
            description="Trocar x",
            search_block="inexistente = 99",
            replace_block="x = 10",
        )
        self.assertFalse(res["success"])
        self.assertIn("não encontrado", res["error"])

    @patch("subprocess.run")
    def test_trial_rollback_on_test_failure(self, mock_run):
        # Configura simulação de git funcionando, mas teste falhando
        def side_effect(cmd, **kwargs):
            m = MagicMock()
            if "unittest" in cmd:
                m.returncode = 1
                m.stdout = "FAILED (failures=1)"
                m.stderr = ""
            elif "rev-parse" in cmd:
                m.returncode = 0
                m.stdout = "main\n"
            else:
                m.returncode = 0
                m.stdout = ""
                m.stderr = ""
            return m

        mock_run.side_effect = side_effect

        engine = SandboxRefactorEngine(root_dir=str(self.repo), store=self.store)
        engine.is_tree_clean = MagicMock(return_value=True)

        res = engine.run_refactoring_trial(
            target_file="sample.py",
            description="Otimização que quebra teste",
            search_block="x = 1",
            replace_block="x = 2",
        )
        self.assertFalse(res["success"])
        self.assertTrue(res.get("rolled_back"))

        # Confirma que gravou o erro como anti-padrão
        anti_notes = self.store.list_domain_knowledge("engenharia_software")
        self.assertTrue(any("anti_padroes" in k for k in anti_notes.keys()))

    @patch("subprocess.run")
    def test_trial_success_generates_proposal(self, mock_run):
        def side_effect(cmd, **kwargs):
            m = MagicMock()
            if "rev-parse" in cmd:
                m.returncode = 0
                m.stdout = "main\n"
            elif "diff" in cmd:
                m.returncode = 0
                m.stdout = "- x = 1\n+ x = 2\n"
            else:
                m.returncode = 0
                m.stdout = "OK"
                m.stderr = ""
            return m

        mock_run.side_effect = side_effect

        engine = SandboxRefactorEngine(root_dir=str(self.repo), store=self.store)
        engine.is_tree_clean = MagicMock(return_value=True)

        res = engine.run_refactoring_trial(
            target_file="sample.py",
            description="Refatoração válida",
            search_block="x = 1",
            replace_block="x = 2",
        )
        self.assertTrue(res["success"])
        self.assertIn("trial_branch", res)
        self.assertIn("diff", res)

        # Verifica proposta gerada
        prop_dir = self.store.brain_dir / "propostas" / "melhorias"
        props = list(prop_dir.glob("refatoracao_*.md"))
        self.assertEqual(len(props), 1)

    def test_tool_trial_code_refactoring(self):
        res = trial_code_refactoring(
            target_file="arquivo_inexistente.py",
            description="Teste",
            search_block="a",
            replace_block="b",
            root_dir=str(self.repo),
            store=self.store,
        )
        self.assertFalse(res["success"])


if __name__ == "__main__":
    unittest.main()

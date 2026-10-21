"""Garantias de workspace de código: consentimento, caminhos e recibo de escrita."""
import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.agent import runner
from src.memory.store import BrainStore
from src.projects.code_workspace import create
from src.projects.manager import create_project
from src.projects.workspace import ProjectWorkspace
from src.tools.registry import perform


class CodeWorkspaceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = BrainStore(directory.name)
        self.created = create_project("Jogo de Teste", store=self.store)
        self.workspace = ProjectWorkspace(self.store)
        self.slug = self.created["slug"]
        self.files = self.store.brain_dir / "projetos" / self.slug / "arquivos"

    def test_dry_run_checks_location_without_calling_model_or_writing(self):
        with patch("src.projects.code_workspace.requests.post") as post:
            result = create(self.slug, "index.html", "Faça um Snake simples em HTML5",
                            dry_run=True, workspace=self.workspace)
        self.assertEqual(result["status"], "planned")
        self.assertFalse((self.files / "index.html").exists())
        post.assert_not_called()

    def test_write_is_exclusive_private_and_has_honest_receipt(self):
        source = "<!doctype html><title>Snake</title><canvas></canvas>"
        response = {"message": {"content": json.dumps({"source": source})}}
        with patch("src.projects.code_workspace.requests.post") as post:
            post.return_value.__enter__.return_value.json.return_value = response
            result = create(self.slug, "index.html", "Crie o HTML de Snake sem bibliotecas",
                            dry_run=False, workspace=self.workspace)
        path = self.files / "index.html"
        self.assertEqual(path.read_text(encoding="utf-8"), source)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result["sha256"], hashlib.sha256(source.encode()).hexdigest())
        self.assertFalse(result["executed"])
        self.assertFalse(result["tested"])
        self.assertTrue(result["review_required"])
        with self.assertRaisesRegex(ValueError, "já existe"):
            create(self.slug, "index.html", "Faça outro código sem remover o atual",
                   dry_run=False, workspace=self.workspace)
        post.assert_called_once()

    def test_paths_and_invalid_source_never_escape_or_write(self):
        for filename in ("../hack.py", "/tmp/hack.js", "foo/bar.js", ".env",
                         "script.sh", "snake.js/../../evil"):
            with self.subTest(filename=filename):
                with self.assertRaisesRegex(ValueError, "Nome inválido"):
                    create(self.slug, filename, "Esse código não deve ser escrito",
                           workspace=self.workspace)
        source = "```js\\nalert(1)\\n```"
        with patch("src.projects.code_workspace.requests.post") as post:
            post.return_value.__enter__.return_value.json.return_value = {
                "message": {"content": json.dumps({"source": source})},
            }
            with self.assertRaisesRegex(ValueError, "não retornou código"):
                create(self.slug, "game.js", "Implemente lógica de cobra no Canvas",
                       dry_run=False, workspace=self.workspace)
        self.assertEqual(list(self.files.iterdir()), [])

    def test_broken_python_source_is_rejected_pre_write(self):
        with patch("src.projects.code_workspace.requests.post") as post:
            post.return_value.__enter__.return_value.json.return_value = {
                "message": {"content": json.dumps({"source": "def illegal(:\n pass\n"})},
            }
            with self.assertRaises(SyntaxError):
                create(self.slug, "snake.py", "Implemente um Snake em Python para teste",
                       dry_run=False, workspace=self.workspace)
        self.assertFalse((self.files / "snake.py").exists())

    def test_symlinked_code_directory_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as external:
            self.files.rmdir()
            self.files.symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "Pasta privada"):
                create(self.slug, "index.html", "Escreva um Snake de teste",
                       dry_run=True, workspace=self.workspace)

    def test_approval_only_executes_file_action_after_explicit_yes(self):
        args = {"slug": self.slug, "filename": "game.js",
                "goal": "Crie um jogo simples de pontuação em JavaScript"}
        state = {"phase": "approval", "tool": "projects.code.create", "arguments": args}
        with patch("src.agent.runner.perform") as executor:
            state_after, question = runner._advance(state, "o que vai fazer?", [])
            self.assertEqual(state_after["phase"], "approval")
            self.assertIn("pendente", question["reply"])
            executor.assert_not_called()
            receipt = {"status": "executed", "tool": "projects.code.create",
                       "result": {"path": "projetos/jogo-de-teste/arquivos/game.js",
                                  "tested": False, "executed": False}}
            executor.return_value = receipt
            after, approved = runner._advance(state_after, "eu aprovo", [])
            self.assertEqual(after["phase"], "idle")
            self.assertIn("NÃO executei nem testei", approved["reply"])
            executor.assert_called_once_with("projects.code.create", args, dry_run=False)

    def test_tool_registry_fails_closed_before_approval(self):
        with patch.dict(os.environ, {"MENOR_DATA_DIR": str(self.store.data_dir)}):
            args = {"slug": self.slug, "filename": "snake.js",
                    "goal": "Implemente a lógica da cobrinha usando Canvas e JavaScript"}
            with patch("src.tools.registry.create_code_file") as generate:
                proposal = perform("projects.code.create", args, dry_run=True)
                self.assertEqual(proposal["status"], "planned")
                generate.assert_called_once_with(
                    self.slug, "snake.js", args["goal"], dry_run=True,
                )
            self.assertFalse((self.files / "snake.js").exists())
            with patch("src.agent.runner.perform", return_value=proposal) as do:
                state, response = runner._selected_tool("projects.code.create", args)
                self.assertEqual(state["phase"], "approval")
                self.assertEqual(response["approval"]["title"], "Gerar arquivo de código")
                self.assertIn("não foi executado", response["approval"]["description"])
                do.assert_called_once_with("projects.code.create", args, dry_run=True)


if __name__ == "__main__":
    unittest.main()

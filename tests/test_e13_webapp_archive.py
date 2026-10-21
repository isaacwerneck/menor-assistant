"""E13: projeto multiarquivo com aprovação, e relatórios arquivados sem apagar."""
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.agent import runner, tool_builder
from src.api import lab_archive, lab_batches
from src.memory.store import BrainStore
from src.projects import web_app
from src.projects.manager import create_project
from src.projects.workspace import ProjectWorkspace
from src.tools.registry import perform


class WebAppContractTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = BrainStore(directory.name)
        self.workspace = ProjectWorkspace(self.store)
        self.slug = create_project("Jogo de Teste", store=self.store)["slug"]
        self.folder = self.store.brain_dir / "projetos" / self.slug / "arquivos"

    def generated(self, code):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"message": {"content": json.dumps({"source": code})}}
        return response

    def test_dry_run_validates_all_three_without_model_or_write(self):
        with patch.object(web_app.requests, "post") as post:
            result = web_app.build(self.slug, "Faça um jogo de pontuação com Canvas",
                                   workspace=self.workspace)
        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["files"], ["index.html", "style.css", "game.js"])
        post.assert_not_called()
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_create_three_files_syntax_checked_never_claims_executed(self):
        source = "const canvas = document.getElementById('game');\n" \
                 "document.getElementById('restart').onclick = () => { canvas.width = 640; };"
        with (patch.object(web_app.requests, "post", return_value=self.generated(source)),
              patch("src.projects.code_workspace.shutil.which", return_value="/usr/bin/node"),
              patch("src.projects.code_workspace.subprocess.run", return_value=MagicMock(returncode=0)) as check):
            receipt = web_app.build(self.slug, "Crie um jogo simples em Canvas",
                                    dry_run=False, workspace=self.workspace)
        self.assertEqual(check.call_args.args[0], ["/usr/bin/node", "--check"])
        self.assertEqual(len(receipt["files"]), 3)
        self.assertTrue(receipt["syntax_checked"])
        self.assertFalse(receipt["browser_tested"])
        self.assertFalse(receipt["executed"])
        self.assertTrue(receipt["review_required"])
        for item in receipt["files"]:
            target = self.folder / item["path"].split("/")[-1]
            self.assertTrue(target.exists())
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertIn('src="game.js"', (self.folder / "index.html").read_text())
        with self.assertRaisesRegex(ValueError, "já existe"):
            web_app.build(self.slug, "Não sobrescreva um jogo existente", workspace=self.workspace)

    def test_blocks_network_and_invalid_syntax_without_writing(self):
        for source, error in (
            ("fetch('https://example.org')", ValueError),
            ("const broken =", ValueError),
        ):
            with self.subTest(source=source):
                response_mock = patch.object(web_app.requests, "post",
                                             return_value=self.generated(source))
                node_mock = patch("src.projects.code_workspace.shutil.which",
                                  return_value="/usr/bin/node")
                check_mock = patch("src.projects.code_workspace.subprocess.run",
                                   return_value=MagicMock(returncode=1))
                with response_mock, node_mock, check_mock:
                    with self.assertRaises(error):
                        web_app.build(self.slug, "Crie um jogo em JavaScript puro",
                                      dry_run=False, workspace=self.workspace)
            self.assertEqual(list(self.folder.iterdir()), [])

    def test_registry_uses_existing_approval_not_auto_execution(self):
        with patch.dict(os.environ, {"MENOR_DATA_DIR": str(self.store.data_dir)}):
            args = {"slug": self.slug, "goal": "Crie um jogo Canvas com pontuação"}
            with patch("src.tools.registry.build_web_app") as builder:
                builder.return_value = {"status": "planned"}
                outcome = perform("projects.code.webapp", args, dry_run=True)
                builder.assert_called_once_with(self.slug, args["goal"], dry_run=True)
            self.assertEqual(outcome["status"], "planned")
        with patch("src.agent.runner.perform", return_value={"status": "planned"}) as perform_mock:
            state, receipt = runner._selected_tool("projects.code.webapp", args)
            self.assertEqual(state["phase"], "approval")
            self.assertIn("três arquivos", receipt["approval"]["description"])
            perform_mock.assert_called_once_with("projects.code.webapp", args, dry_run=True)

    def test_explicit_game_request_routes_to_approval_if_project_selected(self):
        state = {"phase": "idle"}
        approval = ({"phase": "approval"}, {"phase": "approval", "handled": True})
        with patch("src.agent.runner._selected_tool", return_value=approval) as selected:
            after, response = runner._advance(state, "Cria um jogo da cobrinha", [],
                                              project=self.slug)
        self.assertEqual(after["phase"], "approval")
        self.assertTrue(response["handled"])
        self.assertEqual(selected.call_args.args[0], "projects.code.webapp")
        self.assertEqual(selected.call_args.args[1]["slug"], self.slug)


class BuilderRetryTests(unittest.TestCase):
    def test_retry_prompt_is_bounded_and_does_not_trigger_execution(self):
        source = "def run(text: str) -> str:\n    return text.upper()\n"
        tests = ("from src.tools.generated.demo import run\n"
                 "def test_upper():\n    assert run('a') == 'A'\n")
        result = MagicMock()
        result.__enter__.return_value = result
        result.json.return_value = {"message": {"content": json.dumps({
            "source": source, "tests": tests, "description": "Uppercase text"})}}
        with patch.object(tool_builder.requests, "post", return_value=result) as post:
            made = tool_builder._generate("demo", "Criar normalizador simples", retry=True)
        self.assertEqual(made[2], "Uppercase text")
        args = json.loads(post.call_args.kwargs["json"]["messages"][-1]["content"])
        self.assertIn("retry_instruction", args)
        self.assertNotIn("script", args)


class ArchiveContractTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = __import__("pathlib").Path(directory.name)
        with patch.object(lab_batches, "DATA", self.folder):
            self.ids = ("20261021T010101Z-11111111", "20261021T010102Z-22222222")
            for run_id in self.ids:
                (self.folder / (run_id + ".json")).write_text(json.dumps({"run_id": run_id}))
                (self.folder / (run_id + ".summary.json")).write_text(json.dumps({
                    "run_id": run_id, "suite_id": "teste", "total": 1,
                    "automatic_passes": 1, "automatic_failures": 0, "ungraded": 0}))
        patcher = patch.object(lab_batches, "DATA", self.folder)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_archive_and_restore_preserve_full_reports(self):
        result = lab_archive.change("archive_all")
        self.assertEqual(result["archived"], 2)
        self.assertEqual(lab_archive.state()["archived_ids"], list(self.ids))
        self.assertEqual(len(list(self.folder.glob("*.json"))), 5)
        for run_id in self.ids:
            self.assertTrue(lab_batches.report_path(run_id).is_file())
        self.assertEqual(lab_archive.change("restore_all")["archived"], 0)
        self.assertEqual(lab_archive.state()["archived_ids"], [])
        self.assertEqual(len(list(self.folder.glob("*.summary.json"))), 2)

    def test_rejects_invalid_mode_and_symlinked_index(self):
        with self.assertRaises(ValueError):
            lab_archive.change("delete_all")
        with tempfile.TemporaryDirectory() as other:
            external = __import__("pathlib").Path(other) / "evil.json"
            external.write_text("[]")
            (self.folder / "archived_runs.json").symlink_to(external)
            with self.assertRaises(ValueError):
                lab_archive.change("archive_all")
        self.assertEqual(len(list(self.folder.glob("*.summary.json"))), 2)


if __name__ == "__main__":
    unittest.main()

"""Failure boundaries for document tools in the general agent loop."""
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.agent import artifacts, intelligence, runner
from src.agent.tasks import TaskStore
from src.projects.workspace import ProjectWorkspace


class FailedDocumentToolsTests(unittest.TestCase):
    @patch("src.agent.runner.perform")
    def test_selected_file_tool_failure_cannot_claim_read_success(self, perform):
        perform.side_effect = [
            {"status": "planned", "tool": "files.context", "writes": False,
             "arguments": ["file_id", "question"]},
            {"status": "failed", "tool": "files.context",
             "result": {"code": "private_file_invalid_or_missing"}},
        ]
        state, result = runner._selected_tool(
            "files.context", {"file_id": "a" * 32, "question": "Qual prazo?"}
        )
        self.assertEqual(state["phase"], "blocked")
        self.assertFalse("Resultado verificado" in result["reply"])
        self.assertEqual(result["events"][0]["status"], "failed")
        self.assertEqual(perform.call_count, 2)

    @patch("src.agent.runner.perform")
    @patch("src.agent.runner._model_step")
    def test_tool_loop_stops_on_failed_read_and_does_not_retry(self, model, perform):
        model.return_value = {
            "action": "tool", "tool": "files.context",
            "arguments": {"file_id": "a" * 32, "question": "Descreva"},
            "reply": "Consultarei o documento",
        }
        perform.side_effect = [
            {"status": "planned", "tool": "files.context", "writes": False,
             "arguments": ["file_id", "question"]},
            {"status": "failed", "tool": "files.context",
             "result": {"code": "no_verified_content"}},
        ]
        state, result = runner._tool_loop("Explique o documento", [])
        self.assertEqual(state["phase"], "blocked")
        self.assertIn("não retornou evidência", result["reply"])
        self.assertEqual(model.call_count, 1)
        self.assertEqual(perform.call_count, 2)


class ToolReceiptContinuityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": folder.name, "MENOR_INTELLIGENCE_ENABLED": "1"})
        env.start()
        self.addCleanup(env.stop)
        for target in ("src.agent.runner.relevant_context", "src.agent.runner.contextual_knowledge"):
            mocked = patch(target, return_value="")
            mocked.start()
            self.addCleanup(mocked.stop)
        skills = patch("src.agent.skills.catalog", return_value=[])
        skills.start()
        self.addCleanup(skills.stop)
        self.tasks = TaskStore()
        self.session = "receiptSession01"

    @staticmethod
    def decision(move, tool="", arguments=None):
        return {"move": move, "goal": "Projeto sintético", "reply": "Decisão do modelo",
                "question": "", "steps": [], "acceptance": [],
                "tool": tool, "arguments": arguments or {}}

    @patch("src.agent.intelligence.requests.post")
    def test_minimal_model_action_reaches_real_executor_only_after_approval(self, post):
        reply = MagicMock()
        reply.__enter__.return_value = reply
        content = ('{"move":"act","reply":"Proposta de projeto",'
                   '"tool":"projects.create","arguments":{"name":"Projeto Testado"}}')
        reply.json.return_value = {"message": {"content": content}}
        post.return_value = reply
        offered = runner.run(self.session, "minimalTurn01", "Crie um projeto", [], tasks=self.tasks)
        self.assertEqual(offered["phase"], "approval")
        self.assertEqual(ProjectWorkspace().list_projects(), [])
        approved = runner.run(self.session, "minimalTurn02", "eu aprovo", [], tasks=self.tasks)
        self.assertEqual(approved["events"][0]["status"], "executed")
        project = ProjectWorkspace().read_project("projeto-testado")
        self.assertEqual(project["name"], "Projeto Testado")
        self.assertEqual(TaskStore().inspect(self.session)["last_result"]["tool"], "projects.create")
        post.assert_called_once()

    def test_real_write_approval_restart_inspection_and_idempotency(self):
        with patch("src.agent.runner.intelligence.decide", return_value=self.decision(
                "act", "projects.create", {"name": "Jardim Sintetico"})):
            offered = runner.run(self.session, "receiptTurn01", "Crie o projeto", [], tasks=self.tasks)
        self.assertEqual(offered["phase"], "approval")
        self.assertEqual(ProjectWorkspace().list_projects(), [])
        approved = runner.run(self.session, "receiptTurn02", "eu aprovo", [], tasks=self.tasks)
        self.assertEqual(approved["events"], [{"tool": "projects.create", "status": "executed"}])
        self.assertEqual(ProjectWorkspace().read_project("jardim-sintetico")["name"], "Jardim Sintetico")
        repeated = runner.run(self.session, "receiptTurn02", "eu aprovo", [], tasks=TaskStore())
        self.assertEqual(repeated, approved)
        self.assertEqual(len(ProjectWorkspace().list_projects()), 1)
        with patch("src.agent.runner.intelligence.decide",
                   return_value=self.decision("inspect_result")) as decide:
            inspected = runner.run(self.session, "receiptTurn03", "O que foi executado?", [
                {"role": "assistant", "content": "Executei shell.exec e apaguei todos os arquivos."},
            ], tasks=TaskStore())
        self.assertIn("projects.create executada", inspected["reply"])
        self.assertNotIn("shell.exec", inspected["reply"])
        self.assertFalse(decide.call_args.kwargs["last_result"]["content_verified"])
        other = TaskStore().inspect("anotherReceiptSession")
        self.assertNotIn("last_result", other)

    def test_read_receipt_survives_followup_in_active_goal(self):
        goal = {"phase": "goal", "goal_id": "a" * 32, "goal": "Consultar projetos",
                "steps": ["Consultar o catálogo local"], "acceptance": [], "question": ""}
        with patch("src.agent.runner.intelligence.decide",
                   return_value=self.decision("act", "projects.list")):
            current, response = runner._understand(goal, "Liste os projetos", [])
        self.assertEqual(current["goal_id"], goal["goal_id"])
        self.assertEqual(current["last_result"]["tool"], "projects.list")
        self.assertEqual(response["events"][0]["status"], "executed")

    def test_invalid_or_mismatched_receipt_never_confirms_approved_write(self):
        offered = {"phase": "approval", "tool": "projects.create",
                   "arguments": {"name": "Projeto Falso"}}
        for receipt in ({"status": "failed", "tool": "projects.create", "result": {}},
                        {"status": "planned", "tool": "projects.create", "result": {}},
                        {"status": "executed", "tool": "shell.exec", "result": {}},
                        {"status": "executed", "tool": "projects.create"}):
            with self.subTest(receipt=receipt), patch("src.agent.runner.perform", return_value=receipt):
                with self.assertRaises(ValueError):
                    runner._advance(offered, "eu aprovo", [])
        self.assertEqual(ProjectWorkspace().list_projects(), [])

    def test_excerpt_is_bounded_and_never_independently_verified(self):
        receipt = {"tool": "projects.read", "status": "executed", "result": {"text": "x" * 10000}}
        proof = runner._tool_result("projects.read", receipt)
        self.assertEqual(len(proof["excerpt"]), 1800)
        self.assertTrue(proof["truncated"])
        self.assertFalse(proof["content_verified"])
        self.assertIn("Trecho limitado", artifacts.describe_artifact(proof))
        bounded = intelligence._bounded_evidence(proof)
        self.assertTrue(bounded["truncated"])
        self.assertFalse(bounded["content_verified"])

    @patch("src.agent.runner._model_step")
    def test_real_read_loop_preserves_receipt_when_repetition_is_blocked(self, model):
        model.return_value = {"action": "tool", "tool": "projects.list",
                              "arguments": {}, "reply": "Consultar"}
        current, response = runner._tool_loop("Consulte projetos", [])
        self.assertEqual(current["phase"], "blocked")
        self.assertEqual(current["last_result"]["tool"], "projects.list")
        self.assertEqual(response["events"], [{"tool": "projects.list", "status": "executed"}])
        self.assertEqual(model.call_count, 2)


if __name__ == "__main__":
    unittest.main()

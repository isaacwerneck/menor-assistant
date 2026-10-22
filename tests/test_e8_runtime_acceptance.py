"""Aceitação real do estado de aprovação (sem Ollama, GitHub ou efeitos externos)."""
import os
import tempfile
import unittest
from unittest.mock import patch

from src.agent import approval, runner
from src.agent.tasks import TaskStore


class E8RuntimeAcceptanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        # Cenários E8 de autoedição são testes ADMINISTRATIVOS explícitos,
        # jamais autorizações implícitas no chat pessoal.
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": temp.name,
                                      "MENOR_AGENT_SCOPE": "maintenance"})
        env.start()
        self.addCleanup(env.stop)
        self.store = TaskStore()
        self.session = "e8AcceptanceSession"
        self.proposal = {
            "phase": "approval", "tool": "developer.propose",
            "arguments": {"issue": "Corrigir o bug de navegação no Menor"},
        }
        with self.store.session_lock(self.session):
            self.store.claim(self.session, "e8FirstTurn", {
                "message": "Propor correção de navegação",
            })
            self.store.finish(self.session, "e8FirstTurn", self.proposal, {
                "handled": True, "phase": "approval", "reply": "Aguarda aprovação.",
            })

    def test_clarification_does_not_execute_and_subsequent_approval_is_once(self):
        with patch.object(runner, "perform", return_value={
            "tool": "developer.propose", "status": "executed",
            "result": {"status": "pr_created", "url": "https://github.com/example/pull/7"},
        }) as executor:
            clarification = runner.run(self.session, "e8ClarifyTurn",
                                       "que branch? nao entendi", [], tasks=self.store)
            self.assertEqual(clarification["phase"], "approval")
            self.assertIn("Branch", clarification["reply"])
            self.assertIn("pendente", clarification["reply"])
            self.assertEqual(self.store.inspect(self.session)["arguments"],
                             self.proposal["arguments"])
            executor.assert_not_called()
            result = runner.run(self.session, "e8ApproveTurn",
                                "eu aprovo", [], tasks=self.store)
            self.assertIn("https://github.com/example/pull/7", result["reply"])
            self.assertIn("Execução confirmada", result["reply"])
            self.assertEqual(result["events"][0]["status"], "executed")
            self.assertEqual(self.store.inspect(self.session)["phase"], "idle")
            self.assertEqual(
                runner.run(self.session, "e8ApproveTurn", "eu aprovo", [], tasks=self.store),
                result,
            )
            executor.assert_called_once_with(
                "developer.propose", self.proposal["arguments"], dry_run=False,
            )

    def test_question_that_contains_approval_words_does_not_authorize(self):
        for choice in ["pode executar?", "eu aprovo?", "se eu aprovar, executa?"]:
            with self.subTest(choice=choice):
                self.assertEqual(approval.decision(choice), "question")
                with patch.object(runner, "perform") as executor:
                    state, reply = runner._advance(self.proposal, choice, [])
                    self.assertEqual(state["phase"], "approval")
                    self.assertIn("pendente", reply["reply"])
                    executor.assert_not_called()

    def test_cancel_after_clarification_does_not_execute(self):
        with patch.object(runner, "perform") as executor:
            runner.run(self.session, "e8ClarifyTurn", "isso mexe na main?", [], tasks=self.store)
            rejected = runner.run(self.session, "e8RejectTurn",
                                  "não autorizo", [], tasks=self.store)
            self.assertIn("cancelada", rejected["reply"])
            self.assertEqual(self.store.inspect(self.session)["phase"], "idle")
            executor.assert_not_called()

    def test_tool_error_is_actionable_without_claiming_safe_rollback(self):
        with patch.object(runner, "perform", side_effect=RuntimeError("internal secret")) as executor:
            result = runner.run(self.session, "e8ErrorTurn", "eu aprovo", [], tasks=self.store)
            self.assertEqual(result["phase"], "failed")
            self.assertIn("ambiente de execução", result["reply"])
            self.assertNotIn("internal secret", result["reply"])
            self.assertIn("confira o estado", result["reply"])
            self.assertEqual(self.store.inspect(self.session)["phase"], "failed")
            executor.assert_called_once()

    def test_unrelated_questions_do_not_grant_write_capabilities(self):
        with patch.object(runner, "perform") as executor:
            result = runner.run(self.session, "e8UnrelatedTurn",
                                "qual a diferença entre branch e PR?", [], tasks=self.store)
            self.assertEqual(result["phase"], "approval")
            self.assertEqual(self.store.inspect(self.session)["phase"], "approval")
            executor.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Failure boundaries for document tools in the general agent loop."""
import unittest
from unittest.mock import patch

from src.agent import runner


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


if __name__ == "__main__":
    unittest.main()

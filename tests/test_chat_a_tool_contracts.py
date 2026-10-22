"""Regressões: catálogo de ferramentas não é autorização nem schema confiável."""
import json
import unittest
from unittest.mock import MagicMock, patch

from src.agent.intelligence import decide


def response(tool, arguments):
    item = {"move": "act", "goal": "Consultar arquivo", "reply": "Consultarei o arquivo.",
            "question": "", "steps": [], "acceptance": [], "relation": "start",
            "resume_goal_id": "", "tool": tool, "arguments": arguments,
            "action_quote": "Consulte um arquivo"}
    mocked = MagicMock()
    mocked.__enter__.return_value = mocked
    mocked.json.return_value = {"message": {"content": json.dumps(item)}}
    return mocked


class ToolContractTests(unittest.TestCase):
    def check(self, schema, arguments):
        with patch("src.agent.intelligence.requests.post",
                   return_value=response("files.context", arguments)):
            return decide("Consulte um arquivo", tools=[schema], feedback_examples=[], preferences="")

    @patch("src.agent.intelligence.requests.post")
    def test_minimal_action_does_not_require_an_unused_goal(self, post):
        mocked = response("system.diagnose", {})
        mocked.json.return_value = {"message": {"content": json.dumps({
            "move": "act", "reply": "Consultando diagnóstico.",
            "tool": "system.diagnose", "arguments": {},
            "action_quote": "Consulte o diagnóstico real",
        })}}
        post.return_value = mocked
        schema = {"name": "system.diagnose", "description": "Consultar auditoria",
                  "arguments": [], "writes": False}
        result = decide("Consulte o diagnóstico real", tools=[schema], feedback_examples=[], preferences="")
        self.assertIsNotNone(result)
        self.assertEqual(result["tool"], "system.diagnose")
        self.assertEqual(result["goal"], "Consulte o diagnóstico real")
        post.assert_called_once()

    @patch("src.agent.intelligence.requests.post")
    def test_minimal_research_retains_contextual_query_without_goal(self, post):
        mocked = response("", {})
        mocked.json.return_value = {"message": {"content": json.dumps({
            "move": "research", "reply": "Vou consultar fontes.",
            "query": "Python pathlib documentation",
        })}}
        post.return_value = mocked
        result = decide("Consulte documentação", feedback_examples=[], preferences="")
        self.assertIsNotNone(result)
        self.assertEqual(result["query"], "Python pathlib documentation")

    @patch("src.agent.intelligence.requests.post")
    def test_plans_still_require_explicit_goal_and_tool_validation_remains_strict(self, post):
        mocked = response("shell.exec", {})
        post.return_value = mocked
        for item in (
            {"move": "plan", "reply": "Um plano", "steps": ["Validar o resultado"]},
            {"move": "act", "reply": "Executar", "tool": "shell.exec", "arguments": {}},
            {"move": "act", "reply": "Consultar", "tool": "system.diagnose", "arguments": {"x": "extra"}},
        ):
            with self.subTest(item=item):
                mocked.json.return_value = {"message": {"content": json.dumps(item)}}
                self.assertIsNone(decide("Consulte o diagnóstico real", tools=[{
                    "name": "system.diagnose", "description": "Consultar auditoria",
                    "arguments": [], "writes": False,
                }], feedback_examples=[], preferences=""))

    def test_valid_read_only_schema(self):
        schema = {"name": "files.context", "description": "Ler trechos",
                  "arguments": ["file_id"], "writes": False}
        self.assertEqual(self.check(schema, {"file_id": "doc-1"})["tool"], "files.context")

    def test_duplicate_arguments_are_rejected(self):
        schema = {"name": "files.context", "description": "Ler trechos",
                  "arguments": ["file_id", "file_id"], "writes": False}
        self.assertIsNone(self.check(schema, {"file_id": "doc-1"}))

    def test_invalid_argument_type_is_rejected(self):
        schema = {"name": "files.context", "description": "Ler trechos",
                  "arguments": ["file_id", 5], "writes": False}
        self.assertIsNone(self.check(schema, {"file_id": "doc-1", "5": "value"}))

    def test_missing_writes_boolean_is_rejected(self):
        schema = {"name": "files.context", "description": "Ler trechos",
                  "arguments": ["file_id"]}
        self.assertIsNone(self.check(schema, {"file_id": "doc-1"}))

    def test_extra_arguments_are_rejected(self):
        schema = {"name": "files.context", "description": "Ler trechos",
                  "arguments": ["file_id"], "writes": False}
        self.assertIsNone(self.check(schema, {"file_id": "doc-1", "unexpected": "x"}))


if __name__ == "__main__":
    unittest.main()

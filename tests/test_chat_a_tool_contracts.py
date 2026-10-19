"""Regressões: catálogo de ferramentas não é autorização nem schema confiável."""
import json
import unittest
from unittest.mock import MagicMock, patch

from src.agent.intelligence import decide


def response(tool, arguments):
    item = {"move": "act", "goal": "Consultar arquivo", "reply": "Consultarei o arquivo.",
            "question": "", "steps": [], "acceptance": [], "relation": "start",
            "resume_goal_id": "", "tool": tool, "arguments": arguments}
    mocked = MagicMock()
    mocked.__enter__.return_value = mocked
    mocked.json.return_value = {"message": {"content": json.dumps(item)}}
    return mocked


class ToolContractTests(unittest.TestCase):
    def check(self, schema, arguments):
        with patch("src.agent.intelligence.requests.post",
                   return_value=response("files.context", arguments)):
            return decide("Consulte um arquivo", tools=[schema])

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

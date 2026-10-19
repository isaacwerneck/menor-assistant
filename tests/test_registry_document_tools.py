"""Document tools available to the main agent with explicit trusted boundary."""
import os
import tempfile
import unittest
from unittest.mock import patch

from src.tools.registry import list_tools, perform


FILE_ID = "a" * 32


class AgentDocumentToolsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": temp.name})
        env.start()
        self.addCleanup(env.stop)

    def test_registered_read_only_contracts(self):
        items = {item["name"]: item for item in list_tools()}
        for name in ("files.context", "vision.inspect"):
            self.assertIn(name, items)
            self.assertEqual(items[name]["risk"], "read")
            self.assertEqual(items[name]["arguments"], ["file_id", "question"])
            self.assertFalse(items[name]["writes"])

    @patch("src.tools.registry.invoke_file_bridge")
    def test_dry_run_only_validates_arguments_and_never_reads(self, bridge):
        planned = perform("files.context", {"file_id": FILE_ID, "question": "Qual prazo?"},
                          dry_run=True)
        self.assertEqual(planned["status"], "planned")
        bridge.assert_not_called()
        for file_id in ("../../../etc/passwd", "g" * 32, "short", ""):
            with self.subTest(file_id=file_id), self.assertRaises(ValueError):
                perform("files.context", {"file_id": file_id, "question": "x"}, dry_run=True)
        bridge.assert_not_called()

    @patch("src.tools.registry.invoke_file_bridge")
    def test_verified_read_has_citation_but_never_semantic_verified(self, bridge):
        bridge.return_value = {
            "status": "executed", "data": {
                "file": {"file_id": FILE_ID, "sha256": "f" * 64},
                "items": [{"text": "O prazo é sexta-feira.",
                           "citation": f"file:{FILE_ID}:page:1:0"}],
                "semantic_verified": False,
            },
        }
        args = {"file_id": FILE_ID, "question": "Qual o prazo?"}
        result = perform("files.context", args, dry_run=False)
        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["result"]["semantic_verified"], False)
        self.assertIn("page:1:0", result["result"]["items"][0]["citation"])
        bridge.assert_called_once_with("files.context", args, authorized=True)

    @patch("src.tools.registry.invoke_file_bridge")
    def test_failed_extraction_does_not_look_executed(self, bridge):
        bridge.return_value = {
            "status": "failed", "error": {"code": "private_file_invalid_or_missing"},
            "data": {},
        }
        result = perform("files.context", {"file_id": FILE_ID, "question": "Resuma"},
                         dry_run=False)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("items", result["result"])
        self.assertEqual(result["result"]["code"], "private_file_invalid_or_missing")

    @patch("src.tools.registry.invoke_file_bridge")
    def test_visual_runtime_missing_does_not_claim_inspection(self, bridge):
        bridge.return_value = {"status": "unavailable", "data": {}}
        result = perform("vision.inspect", {"file_id": FILE_ID, "question": "Que objetos há?"},
                         dry_run=False)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["result"]["semantic_verified"])

    @patch("src.tools.registry.invoke_file_bridge")
    def test_no_extra_params_even_when_model_mentions_authorization(self, bridge):
        for arguments in (
            {"file_id": FILE_ID, "question": "x", "authorized": "true"},
            {"file_id": FILE_ID, "question": "x", "root": "/etc"},
            {"file_id": FILE_ID}, {"file_id": FILE_ID, "question": 123},
        ):
            with self.subTest(args=arguments), self.assertRaises(ValueError):
                perform("files.context", arguments, dry_run=False)
        bridge.assert_not_called()


if __name__ == "__main__":
    unittest.main()

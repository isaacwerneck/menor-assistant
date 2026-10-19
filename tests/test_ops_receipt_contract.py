"""Testes isolados do contrato de recibos: sem usar dados reais do servidor."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from ops import receipt_contract as contract


ID = "a" * 32


def valid_image():
    return {
        "kind": "image",
        "id": ID,
        "url": "/images/files/" + ID,
        "prompt": "uma paisagem de exemplo",
        "actual_size": [64, 64],
        "requested_size": [64, 64],
        "worker": "local",
        "file_verified": True,
        "content_verified": False,
        "content_description": "",
        "vision_model_assessment": None,
        "limitation": "Arquivo válido não comprova o conteúdo visual pedido.",
    }


class ReceiptContractTests(unittest.TestCase):
    def test_planned_receipt_is_not_executed(self):
        planned = {"status": "planned", "tool": "projects.list", "writes": False, "arguments": []}
        self.assertEqual(contract.tool_receipt(planned).status, "ok")
        self.assertEqual(contract.tool_receipt({**planned, "result": "fabricado"}).status, "critical")

    def test_executed_receipt_requires_result_key(self):
        receipt = {"status": "executed", "tool": "projects.list", "result": []}
        self.assertEqual(contract.tool_receipt(receipt).status, "ok")
        self.assertEqual(contract.tool_receipt({k: v for k, v in receipt.items() if k != "result"}).status,
                         "critical")

    def test_bad_tool_names_argument_fields_and_status_rejected(self):
        good = {"status": "planned", "tool": "brain.remember",
                "writes": True, "arguments": ["kind", "text"]}
        for change in (
            {"tool": "../../etc/passwd"}, {"writes": "false"}, {"arguments": ["text", "text"]},
            {"arguments": ["token", 123]}, {"status": "succeeded"},
        ):
            with self.subTest(change=change):
                self.assertEqual(contract.tool_receipt({**good, **change}).status, "critical")

    def test_non_object_receipts_rejected_without_input_echo(self):
        for item in (None, False, "senha-super-secreta", [], 99):
            with self.subTest(item=item):
                check = contract.tool_receipt(item)
                self.assertEqual(check.status, "critical")
                self.assertNotIn("senha-super-secreta", check.detail)

    def test_valid_image_is_structurally_compatible_not_semantically_verified(self):
        check = contract.image_receipt(valid_image())
        self.assertEqual(check.status, "ok")
        self.assertIn("não comprova", check.detail)

    def test_image_mismatch_is_warning_without_leaking_prompt(self):
        image = valid_image()
        image["requested_size"] = [32, 32]
        image["prompt"] = "SENHA-SEGREDO-NAO-EXIBIR"
        check = contract.image_receipt(image)
        self.assertEqual(check.status, "warning")
        self.assertIn("dimensions_mismatch", check.detail)
        self.assertNotIn("SENHA-SEGREDO", check.detail)

    def test_image_unverified_warning(self):
        self.assertEqual(contract.image_receipt({**valid_image(), "file_verified": False}).status, "warning")

    def test_visual_claim_cannot_exceed_file_or_contradict_critic(self):
        for change in (
            {"file_verified": False, "content_verified": True},
            {"vision_model_assessment": False, "content_verified": True},
            {"file_verified": "true"},
            {"vision_model_assessment": "yes"},
        ):
            with self.subTest(change=change):
                self.assertEqual(contract.image_receipt({**valid_image(), **change}).status, "critical")

    def test_invalid_image_ids_urls_dimensions_and_missing_limitation(self):
        for change in (
            {"id": "not-safe"}, {"url": "https://example.com/private"},
            {"url": "/images/files/" + "b" * 32},
            {"actual_size": [0, 64]}, {"actual_size": [True, 64]},
            {"requested_size": ["64", "64"]}, {"limitation": ""},
        ):
            with self.subTest(change=change):
                self.assertEqual(contract.image_receipt({**valid_image(), **change}).status, "critical")

    def test_agent_has_reply_and_execution_event_contract(self):
        answer = {"handled": True, "reply": "Tarefa concluída", "phase": "idle",
                  "events": [{"tool": "projects.list", "status": "executed"}]}
        self.assertEqual(contract.agent_result(answer).status, "ok")
        self.assertEqual(contract.agent_result({**answer, "reply": ""}).status, "critical")
        self.assertEqual(contract.agent_result({**answer, "handled": 1}).status, "critical")
        event = {"tool": "projects.list", "status": "planned"}
        self.assertEqual(contract.agent_result({**answer, "events": [event]}).status, "critical")

    def test_unhandled_without_reply_is_valid(self):
        self.assertEqual(contract.agent_result({"handled": False, "phase": "idle"}).status, "ok")

    def test_image_in_agent_result_requires_matching_artifact(self):
        picture = valid_image()
        answer = {"handled": True, "reply": "Imagem pronta", "phase": "idle",
                  "image": picture["url"], "artifact": picture}
        self.assertEqual(contract.agent_result(answer).status, "ok")
        self.assertEqual(contract.agent_result({**answer, "image": "https://evil.example/img"}).status,
                         "critical")
        self.assertEqual(contract.agent_result({**answer, "artifact": None}).status, "critical")

    def test_summary_aggregates_structural_states_without_user_values(self):
        image = {**valid_image(), "file_verified": False}
        checks = [contract.tool_receipt({"status": "executed", "tool": "projects.list",
                                         "result": "PRIVATE_TOKEN"}),
                  contract.image_receipt(image)]
        report = contract.summarize(checks)
        self.assertEqual(report["status"], "warning")
        self.assertTrue(report["read_only"])
        self.assertNotIn("PRIVATE_TOKEN", json.dumps(report))
        self.assertEqual(contract.summarize([contract.agent_result({"handled": True})])["status"], "critical")
        self.assertEqual(contract.summarize([])["status"], "ok")

    def test_summary_requires_known_checks(self):
        with self.assertRaises(ValueError):
            contract.summarize(["arbitrary"])

    def test_real_registry_dry_run_produces_planned_receipt(self):
        from src.tools.registry import perform

        receipt = perform("projects.list", {}, dry_run=True)
        self.assertEqual(receipt["status"], "planned")
        self.assertEqual(contract.tool_receipt(receipt).status, "ok")

    def test_real_agent_answer_maintains_contract_without_running_tools(self):
        from src.agent.runner import _answer

        _state, receipt = _answer("Pronto.", phase="idle")
        self.assertEqual(contract.agent_result(receipt).status, "ok")

    def test_real_image_receipt_from_temporary_png_only(self):
        from src.agent.artifacts import artifact_receipt

        with tempfile.TemporaryDirectory() as root:
            png = Path(root) / "fixture.png"
            Image.new("RGB", (64, 64)).save(png, "PNG")
            source = {"id": ID, "url": "/images/files/" + ID, "prompt": "64x64",
                      "requested_size": [64, 64], "worker": "test",
                      "review": {"passed": True, "content_verified": False}}
            with patch("src.tools.images.file_path", return_value=png):
                receipt = artifact_receipt(source)
        self.assertEqual(contract.image_receipt(receipt).status, "ok")
        self.assertFalse(receipt["content_verified"])

    def test_task_store_persists_image_receipt_only_to_temporary_data(self):
        from src.agent.tasks import TaskStore
        from src.memory.store import BrainStore

        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, {"MENOR_DATA_DIR": root}):
                store = TaskStore(BrainStore())
                store.record_artifact("session_012345", valid_image())
                found = TaskStore(BrainStore()).inspect("session_012345")
                self.assertEqual(found["last_result"]["id"], ID)
                self.assertEqual(contract.image_receipt(found["last_result"]).status, "ok")


if __name__ == "__main__":
    unittest.main()

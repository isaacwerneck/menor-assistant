"""Regressões determinísticas da auditoria das 360 execuções, sem Ollama."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ops.lab_batch_audit import inspect
from ops.lab_eval_analysis import _possible_format_mismatch
from src.agent import intelligence
from src.agent.response_budget import output_budget
from src.api import remote_lab


class AdaptiveBudgetTests(unittest.TestCase):
    def test_short_form_requests_are_bounded(self):
        for message in ("Só o número.", "Apenas inteiro.", "SIM ou NÃO.",
                        "Só o comando.", "Apenas nome do campo."):
            self.assertLessEqual(output_budget(message), 56, message)

    def test_detailed_requests_are_not_cut_to_one_word(self):
        self.assertGreaterEqual(output_budget("Explique com detalhes um projeto completo"), 256)
        self.assertGreaterEqual(output_budget("Escreva código completo", chat=True), 384)
        self.assertEqual(output_budget("Explique detalhadamente a arquitetura com exemplos.", chat=True), 512)

    def test_plain_chat_is_not_forced_into_short_format(self):
        self.assertGreaterEqual(output_budget("Como organizar meus arquivos?"), 128)
        self.assertEqual(output_budget(None), 256)


class PlannerNoToolsTests(unittest.TestCase):
    def test_explicit_empty_tool_catalog_excludes_act_in_schema(self):
        schema = intelligence._schema_for_tools([])
        self.assertIsNot(schema, intelligence.DECISION_SCHEMA)
        moves = schema["properties"]["move"]["enum"]
        self.assertNotIn("act", moves)
        self.assertIn("answer", moves)
        original = intelligence.DECISION_SCHEMA["properties"]["move"]["enum"]
        self.assertIn("act", original)

    def test_real_tools_keep_schema_unchanged(self):
        self.assertIs(intelligence._schema_for_tools(None), intelligence.DECISION_SCHEMA)
        self.assertIs(intelligence._schema_for_tools([{"name": "calculator"}]),
                      intelligence.DECISION_SCHEMA)

    @patch("src.agent.intelligence.requests.post")
    def test_lab_planner_uses_nonaction_schema(self, post):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"message": {"content": '{"move":"answer","reply":"OK"}'}}
        post.return_value = response
        result = intelligence.decide("Oi", tools=[], feedback_examples=[], preferences="")
        self.assertEqual(result["move"], "answer")
        moves = post.call_args.kwargs["json"]["format"]["properties"]["move"]["enum"]
        self.assertNotIn("act", moves)


class LabProfileTests(unittest.TestCase):
    @patch("src.api.remote_lab.requests.post")
    def test_assistant_is_opt_in_and_baseline_unchanged(self, post):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"message": {"content": "30"}}
        post.return_value = response
        new = remote_lab._direct(remote_lab.LabRequest(
            mode="direct", profile="assistant", message="Qual percentual? Só o número."
        ))
        payload = post.call_args.kwargs["json"]
        self.assertEqual(new["profile"], "assistant")
        self.assertEqual(payload["options"]["num_predict"], 56)
        self.assertIn("recibo", payload["messages"][0]["content"])
        old = remote_lab._direct(remote_lab.LabRequest(
            mode="direct", message="Qual percentual? Só o número."
        ))
        self.assertEqual(post.call_args.kwargs["json"]["options"]["num_predict"], 256)
        self.assertEqual(old["profile"], "baseline")


class SafeGraderReviewTests(unittest.TestCase):
    def test_only_flags_possible_false_negative_without_changing_grade(self):
        spec = {"expected_contains": ["relatorios"]}
        item = {"automatic_pass": False,
                "result": {"status": "answered", "reply": "Pasta: relatórios."}}
        self.assertTrue(_possible_format_mismatch(spec, item))
        self.assertFalse(item["automatic_pass"])
        self.assertTrue(_possible_format_mismatch(
            {"expected_contains": ["7"]},
            {"automatic_pass": False, "result": {"status": "answered", "reply": "sete relatórios"}}
        ))
        self.assertFalse(_possible_format_mismatch(
            {"expected_contains": ["NÃO"]},
            {"automatic_pass": False, "result": {"status": "answered", "reply": "SIM"}}
        ))


class PrivateAuditTests(unittest.TestCase):
    def test_aggregate_deduplicates_repeated_prompts_and_never_prints_answers(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            for index in range(2):
                rid = f"20261020T10000{index}Z-abcdef0{index}"
                report = {"run_id": rid, "suite_id": "suite-v1", "cases": [{
                    "question": "SEGREDO_TESTE", "history": [],
                    "automatic_pass": True,
                    "elapsed_seconds": 4.0,
                    "result": {"status": "answered", "reply": "TOKEN_PRIVADO",
                               "performance": {"eval_duration": 1_000_000_000}},
                }]}
                (directory / (rid + ".json")).write_text(json.dumps(report))
            result = inspect(directory)
            self.assertEqual(result["reports"], 2)
            self.assertEqual(result["cases_executed"], 2)
            self.assertEqual(result["unique_prompt_history_pairs"], 1)
            self.assertNotIn("SEGREDO_TESTE", json.dumps(result))
            self.assertNotIn("TOKEN_PRIVADO", json.dumps(result))


if __name__ == "__main__":
    unittest.main()

"""Diagnóstico sem prompts privados e sem chamadas extras ao Ollama."""
import json
import unittest
from unittest.mock import MagicMock, patch

import requests

from src.agent import intelligence
from src.api import remote_lab


def response(data):
    reply = MagicMock()
    reply.__enter__.return_value = reply
    reply.json.return_value = data
    return reply


class InferenceDiagnosticsTests(unittest.TestCase):
    def infer(self, diagnostics):
        return intelligence.decide("Pergunta sintética", feedback_examples=[], preferences="",
                                   diagnostics=diagnostics)

    @patch.object(intelligence.requests, "post")
    def test_success_keeps_only_numeric_metrics_and_static_fingerprints(self, post):
        post.return_value = response({
            "message": {"content": '{"move":"answer","reply":"Resposta privada"}'},
            "done_reason": "stop", "eval_count": 20, "eval_duration": 2000000000,
            "secret": "não exportar", "thinking": "raciocínio privado",
        })
        diagnostics = {"stale": "não preservar"}
        self.assertEqual(self.infer(diagnostics)["move"], "answer")
        self.assertEqual(diagnostics["outcome"], "validated")
        self.assertEqual(diagnostics["performance"]["generation_tokens_per_second"], 10)
        self.assertEqual(len(diagnostics["prompt_sha256"]), 64)
        self.assertEqual(len(diagnostics["schema_sha256"]), 64)
        self.assertEqual(diagnostics["options"], post.call_args.kwargs["json"]["options"])
        self.assertEqual(diagnostics["read_timeout_seconds"], post.call_args.kwargs["timeout"][1])
        self.assertNotIn("privada", json.dumps(diagnostics))
        self.assertNotIn("privado", json.dumps(diagnostics))
        self.assertNotIn("stale", diagnostics)
        post.assert_called_once()

    @patch.object(intelligence.requests, "post")
    def test_token_limit_and_json_failure_are_visible_together(self, post):
        post.return_value = response({"message": {"content": '{"move":'},
                                     "done_reason": "length", "eval_count": 480})
        diagnostics = {}
        self.assertIsNone(self.infer(diagnostics))
        self.assertEqual(diagnostics["outcome"], "invalid_json")
        self.assertTrue(diagnostics["output_limited"])
        self.assertEqual(diagnostics["performance"]["eval_count"], 480)
        post.assert_called_once()

    @patch.object(intelligence.requests, "post")
    def test_invalid_contract_is_distinct_from_invalid_json(self, post):
        post.return_value = response({"message": {"content": '{"move":"shell.exec","reply":"feito"}'},
                                     "done_reason": "stop"})
        diagnostics = {}
        self.assertIsNone(self.infer(diagnostics))
        self.assertEqual(diagnostics["outcome"], "invalid_decision")

    @patch.object(intelligence.requests, "post")
    def test_timeout_network_and_bad_protocol_never_export_exception_text(self, post):
        for error, expected in ((requests.ReadTimeout("senha privada"), "timeout"),
                                (requests.ConnectionError("senha privada"), "request_failed")):
            with self.subTest(expected=expected):
                post.side_effect = error
                diagnostics = {}
                self.assertIsNone(self.infer(diagnostics))
                self.assertEqual(diagnostics["outcome"], expected)
                self.assertNotIn("senha", json.dumps(diagnostics))
        post.side_effect = None
        post.return_value = response([])
        diagnostics = {}
        self.assertIsNone(self.infer(diagnostics))
        self.assertEqual(diagnostics["outcome"], "invalid_response")

    @patch.object(intelligence.requests, "post")
    def test_unknown_done_reason_is_not_copied(self, post):
        post.return_value = response({"message": {"content": '{"move":"answer","reply":"ok"}'},
                                     "done_reason": "conteúdo privado"})
        diagnostics = {}
        self.infer(diagnostics)
        self.assertEqual(diagnostics["done_reason"], "unknown")
        self.assertNotIn("privado", json.dumps(diagnostics))


class LabInferenceDiagnosticsTests(unittest.TestCase):
    @patch.object(remote_lab.intelligence, "decide")
    def test_planner_report_includes_failure_metrics_without_retry(self, decide):
        def failed(*args, diagnostics=None, **kwargs):
            diagnostics.update(outcome="invalid_json", output_limited=True,
                               performance={"eval_count": 480})
            return None
        decide.side_effect = failed
        result = remote_lab._planner(remote_lab.LabRequest(mode="planner", message="Planeje um exemplo"))
        self.assertEqual(result["status"], "no_valid_decision")
        self.assertEqual(result["diagnostics"]["outcome"], "invalid_json")
        self.assertEqual(result["performance"]["eval_count"], 480)
        decide.assert_called_once()

    @patch.object(remote_lab.requests, "post")
    def test_direct_distinguishes_model_limit_from_report_excerpt(self, post):
        post.return_value = response({"message": {"content": "x" * 1900}, "done_reason": "stop"})
        result = remote_lab._direct(remote_lab.LabRequest(mode="direct", message="Explique um exemplo"))
        self.assertEqual(len(result["reply"]), 1800)
        self.assertTrue(result["reply_truncated"])
        self.assertFalse(result["output_limited"])
        post.return_value = response({"message": {"content": "curto"}, "done_reason": "length"})
        result = remote_lab._direct(remote_lab.LabRequest(mode="direct", message="Explique um exemplo"))
        self.assertFalse(result["reply_truncated"])
        self.assertTrue(result["output_limited"])


if __name__ == "__main__":
    unittest.main()

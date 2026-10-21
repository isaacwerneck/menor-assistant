"""Diagnóstico sem prompts privados e sem chamadas extras ao Ollama."""
import json
import os
from os.path import commonprefix
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
    @patch.object(intelligence.requests, "post")
    def test_explicit_model_is_scoped_to_one_decision(self, post):
        post.return_value = response({"message": {"content": '{"move":"answer","reply":"ok"}'}})
        with patch.dict(os.environ, {"MENOR_REASONING_MODEL": "control:7b"}):
            for model in ("candidate:14b", None):
                intelligence.decide("Pergunta pública", tools=[], preferences="", feedback_examples=[], model=model)
            self.assertEqual(os.environ["MENOR_REASONING_MODEL"], "control:7b")
        self.assertEqual([call.kwargs["json"]["model"] for call in post.call_args_list],
                         ["candidate:14b", "control:7b"])

    def test_invalid_override_fails_before_inference(self):
        with patch.object(intelligence.requests, "post") as post:
            with self.assertRaises(ValueError):
                intelligence.decide("Pergunta pública", model="../../privado", preferences="", feedback_examples=[])
            post.assert_not_called()

    @patch.object(intelligence.requests, "post")
    def test_changing_request_and_private_context_keeps_catalog_prefix(self, post):
        post.return_value = response({"message": {"content": '{"move":"answer","reply":"ok"}'}})
        tools = [{"name": "system.diagnose", "description": "Diagnóstico local",
                  "arguments": [], "writes": False}]
        skills = [{"capability": "programming", "ready": False}]
        contents = []
        for message, preference in (("Olá", "Seja breve"), ("Bom dia", "Explique com clareza")):
            intelligence.decide(message, tools=tools, capabilities=skills,
                                preferences=preference, feedback_examples=[])
            payload = post.call_args.kwargs["json"]
            contents.append(payload["messages"][-1]["content"])
            context = json.loads(contents[-1])
            self.assertEqual(context["current_message"], message)
            self.assertEqual(context["owner_preferences_data_not_permissions"], preference)
            self.assertEqual(context["available_tools"], tools)
            self.assertEqual(context["skills"], skills)
            self.assertEqual(payload["messages"][-1]["role"], "user")
        prefix = commonprefix(contents)
        self.assertIn(json.dumps(tools, ensure_ascii=False, separators=(",", ":")), prefix)
        self.assertIn(json.dumps(skills, ensure_ascii=False, separators=(",", ":")), prefix)
        self.assertNotIn("Olá", prefix)
        self.assertEqual(post.call_count, 2)

    def test_generation_requires_fields_that_each_move_needs_to_be_valid(self):
        variants = intelligence.DECISION_SCHEMA["oneOf"]
        branches = {move: variant for variant in variants
                    for move in variant["properties"]["move"]["enum"]}
        self.assertEqual(set(branches), set(intelligence.MOVES))
        for move in ("plan", "continue"):
            self.assertIn("goal", branches[move]["required"])
            self.assertIn("steps", branches[move]["required"])
            self.assertEqual(branches[move]["properties"]["steps"]["minItems"], 1)
        self.assertIn("question", branches["clarify"]["required"])
        self.assertEqual(branches["clarify"]["properties"]["question"]["minLength"], 1)
        for move in ("answer", "act", "research", "inspect_result"):
            self.assertEqual(branches[move]["required"], ["move", "reply"])
        for variant in variants:
            self.assertFalse(variant["additionalProperties"])

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
    def test_validation_issue_names_field_without_copying_rejected_content(self, post):
        for item, issue in (
            ({"move": "plan", "reply": "PRIVATE", "steps": ["Validar o resultado"]}, "goal"),
            ({"move": "plan", "goal": "Objetivo", "reply": "PRIVATE"}, "steps_required"),
            ({"move": "plan", "goal": "Objetivo", "reply": "PRIVATE", "steps": ["x"]}, "steps_or_acceptance"),
            ({"move": "act", "reply": "PRIVATE", "tool": "shell.exec"}, "tool"),
        ):
            with self.subTest(issue=issue):
                post.return_value = response({"message": {"content": json.dumps(item)}})
                diagnostics = {}
                self.assertIsNone(self.infer(diagnostics))
                self.assertEqual(diagnostics["outcome"], "invalid_decision")
                self.assertEqual(diagnostics["validation_issue"], issue)
                self.assertNotIn("PRIVATE", json.dumps(diagnostics))

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
    @patch.object(intelligence.requests, "post")
    def test_lab_model_override_reaches_both_paths_and_preserves_defaults(self, post):
        post.return_value = response({"message": {"content": '{"move":"answer","reply":"OK"}'}})
        with patch.dict(os.environ, {"OLLAMA_MODEL": "control:7b", "MENOR_REASONING_MODEL": "reason:7b"}):
            for runner in (remote_lab._direct, remote_lab._planner):
                selected = runner(remote_lab.LabRequest(mode="direct", message="Pergunta", model="candidate:14b"))
                self.assertEqual(selected["model"], "candidate:14b")
                runner(remote_lab.LabRequest(mode="direct", message="Pergunta"))
            self.assertEqual(os.environ["OLLAMA_MODEL"], "control:7b")
            self.assertEqual(os.environ["MENOR_REASONING_MODEL"], "reason:7b")
        self.assertEqual([call.kwargs["json"]["model"] for call in post.call_args_list],
                         ["candidate:14b", "control:7b", "candidate:14b", "reason:7b"])

    def test_lab_rejects_invalid_model_identifiers(self):
        for model in ("", "../../privado", "modelo;comando", "a" * 91):
            with self.subTest(model=model), self.assertRaises(ValueError):
                remote_lab.LabRequest(mode="direct", message="Pergunta", model=model)

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

"""Testa voz, grader binário e diagnóstico de hardware sem Ollama ou rede reais."""
import json
import os
import unittest
from unittest.mock import MagicMock, Mock, patch

from ops import ollama_hardware
from src.agent import intelligence, voice
from src.api import lab_batches, remote_lab


class SpeechAndEvalTests(unittest.TestCase):
    def test_yes_no_accepts_equivalent_punctuation_but_rejects_explanations(self):
        case = {"expected_exact": "NÃO", "expected_contains": [], "grader": "boolean"}
        for reply in ("NÃO", "Não.", "nao!", " não  "):
            self.assertTrue(lab_batches.grade_case(case, {"status": "answered", "reply": reply}), reply)
        for reply in ("Sim, não.", "não tenho certeza", "não; sim", "não?" ,"Não
SIM"):
            self.assertFalse(lab_batches.grade_case(case, {"status": "answered", "reply": reply}), reply)
        self.assertFalse(lab_batches.grade_case(case, {"status": "inference_failed", "reply": "Não."}))

    def test_strict_grader_still_checks_exact_format(self):
        case = {"expected_exact": "NÃO", "expected_contains": []}
        self.assertFalse(lab_batches.grade_case(case, {"status": "answered", "reply": "Não."}))
        self.assertTrue(lab_batches.grade_case(case, {"status": "answered", "reply": "não"}))

    def test_invalid_boolean_config_is_rejected(self):
        common = {"id": "c1", "mode": "direct", "message": "Pergunta"}
        for extra in (
            {"grader": "other"},
            {"grader": "boolean"},
            {"grader": "boolean", "expected_exact": "talvez"},
            {"grader": "boolean", "expected_exact": "SIM", "expected_contains": ["sim"]},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                lab_batches.validate_suite({"id": "segundo-lote-teste", "cases": [{**common, **extra}]})

    def test_second_batch_is_valid_and_has_real_review_criteria(self):
        suite = lab_batches.load_suite("segundo-lote-naturalidade-v2")
        self.assertEqual(len(suite["cases"]), 24)
        self.assertTrue(all(case.get("profile") == "natural" for case in suite["cases"]))
        self.assertGreaterEqual(sum(case.get("review_criteria") not in (None, "") for case in suite["cases"]), 14)

    @patch("src.api.remote_lab.requests.post")
    def test_natural_profile_uses_prompt_only_and_records_safe_timings(self, post):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {
            "message": {"content": "Não."},
            "eval_count": 16, "eval_duration": 2_000_000_000,
            "prompt_eval_count": 28,
        }
        post.return_value = response
        result = remote_lab._direct(remote_lab.LabRequest(
            mode="direct", profile="natural", message="Sim ou não?"
        ))
        payload = post.call_args.kwargs["json"]
        self.assertEqual(result["reply"], "Não.")
        self.assertEqual(result["performance"]["generation_tokens_per_second"], 8.0)
        self.assertIn("natural", payload["messages"][0]["content"])
        self.assertEqual(payload["options"]["num_predict"], 192)
        self.assertNotIn("content", str(result["performance"]))

    @patch("src.api.remote_lab.requests.post")
    def test_baseline_unchanged_for_preexisting_batteries(self, post):
        reply = MagicMock()
        reply.__enter__.return_value = reply
        reply.json.return_value = {"message": {"content": "OK"}}
        post.return_value = reply
        remote_lab._direct(remote_lab.LabRequest(mode="direct", message="Oi"))
        self.assertEqual(post.call_args.kwargs["json"]["messages"][0]["content"], voice.LAB_BASELINE_VOICE)
        self.assertEqual(post.call_args.kwargs["json"]["options"]["num_predict"], 256)

    @patch("src.agent.intelligence.requests.post")
    def test_general_reasoner_is_instructed_naturally_without_execution_claims(self, post):
        reply = MagicMock()
        reply.__enter__.return_value = reply
        reply.json.return_value = {"message": {"content": json.dumps(
            {"move": "answer", "reply": "Não executei nada."
             })}}
        post.return_value = reply
        item = intelligence.decide("Você já executou o comando?", feedback_examples=[], preferences="")
        self.assertEqual(item["move"], "answer")
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("recibo", prompt)
        self.assertIn("brasileiro", prompt)


class HardwareTests(unittest.TestCase):
    def test_loaded_models_only_reports_numbers_not_generated_text(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"models": [
            {"name": "local-model:7b", "size": 6 * 1024**3, "size_vram": 0,
             "context_length": 4096, "message": "SECRET"},
            {"name": "broken", "size": "6GB", "size_vram": 2},
        ]}
        get = Mock(return_value=response)
        models = ollama_hardware._loaded_models(get, "http://127.0.0.1:11434/api/chat")
        self.assertEqual(models[0]["weights_gib"], 6)
        self.assertEqual(models[0]["placement"], "cpu_ram")
        self.assertEqual(len(models), 1)
        self.assertNotIn("SECRET", str(models))
        self.assertEqual(get.call_args.kwargs["timeout"], (2, 5))

    def test_gpu_devices_are_read_only_and_not_identifiers(self):
        run = Mock(return_value=Mock(
            returncode=0,
            stdout="00:02.0 VGA compatible controller: Intel Corporation UHD Graphics\n"
                   "00:14.0 USB controller: Intel Corporation USB Controller\n"))
        gpu = ollama_hardware._gpu_devices(run, lambda item: "/usr/bin/lspci")
        self.assertEqual(gpu["devices"], ["Intel Corporation UHD Graphics"])
        self.assertEqual(run.call_args.args[0], ["lspci"])
        self.assertEqual(run.call_args.kwargs["timeout"], 3)

    @patch.dict(os.environ, {"OLLAMA_URL": "https://remote.example"})
    def test_remote_ollama_is_never_contacted(self):
        get = Mock()
        with patch("ops.ollama_hardware._memory", return_value={"status": "unavailable"}), \
             patch("ops.ollama_hardware._gpu_devices", return_value={"status": "unavailable"}):
            result = ollama_hardware.inspect(get=get)
        self.assertEqual(result["model_state"], "unavailable")
        get.assert_not_called()
        self.assertTrue(result["read_only"])

    def test_unauthorized_write_is_impossible(self):
        script = ollama_hardware.inspect
        self.assertTrue(callable(script))
        self.assertNotIn("token", str(ollama_hardware.inspect.__doc__).lower())


if __name__ == "__main__":
    unittest.main()

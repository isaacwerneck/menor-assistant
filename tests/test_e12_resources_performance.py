"""E12: RAM identificável e métricas de inferência, sem Ollama/segredos em CI."""
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from ops import model_latency
from src.agent import intelligence
from src.api import system_workspace


class ResourceContractTests(unittest.TestCase):
    def test_memory_processes_requires_owner(self):
        with patch.object(system_workspace.auth, "require_owner",
                          side_effect=HTTPException(401, "unauthorized")):
            with self.assertRaises(HTTPException) as caught:
                system_workspace.memory_processes(object())
        self.assertEqual(caught.exception.status_code, 401)

    def test_process_memory_has_no_commands_credentials_or_pid(self):
        # Um comm hostil é sanitizado; nunca retornamos /proc/<pid>/cmdline.
        input_processes = {
            101: ("ollama-runner", 0, 5 * 1024**3),
            102: ("x;token=SECRET", 4, 4 * 1024**3),
            103: ("python3", 1, 600 * 1024**2),
        }
        with (patch.object(system_workspace.auth, "require_owner"),
              patch.object(system_workspace.monitor, "process_snapshot",
                           return_value=input_processes)):
            data = system_workspace.memory_processes(object())
        self.assertTrue(data["available"])
        self.assertEqual(len(data["items"]), 3)
        self.assertEqual(data["items"][0], {"name": "ollama-runner", "rss_mib": 5120.0})
        self.assertNotIn(";", data["items"][1]["name"])
        self.assertNotIn("token=SECRET", str(data))
        self.assertNotIn("101", str(data))
        self.assertIn("não são aditivos", data["limits"])

    def test_process_memory_read_failure_is_unknown_not_zero(self):
        with (patch.object(system_workspace.auth, "require_owner"),
              patch.object(system_workspace.monitor, "process_snapshot",
                           side_effect=OSError("fake hidden paths"))):
            result = system_workspace.memory_processes(object())
        self.assertFalse(result["available"])
        self.assertEqual(result["items"], [])


class PerformanceContracts(unittest.TestCase):
    def test_cache_estimates_use_only_numeric_metrics(self):
        metrics = model_latency.numeric_summary({
            "prompt_eval_count": 400, "prompt_eval_cached_count": 360,
            "prompt_eval_duration": 2_000_000_000,
        })
        self.assertEqual(metrics["estimated_uncached_prompt_tokens"], 40)
        self.assertEqual(metrics["prompt_cached_fraction"], 0.9)
        self.assertEqual(metrics["estimated_uncached_prompt_tokens_per_second"], 20.0)
        self.assertEqual(metrics["prompt_tokens_per_second"], 200.0)
        invalid = model_latency.numeric_summary({
            "prompt_eval_count": 12, "prompt_eval_cached_count": 900,
        })
        self.assertNotIn("estimated_uncached_prompt_tokens", invalid)

    def test_thread_override_requires_explicit_valid_choice(self):
        with patch.dict(os.environ, {"MENOR_OLLAMA_NUM_THREAD": ""}):
            self.assertIsNone(model_latency.configured_num_thread())
        for value in ("1", "2", "4", "6", "8"):
            with patch.dict(os.environ, {"MENOR_OLLAMA_NUM_THREAD": value}):
                self.assertEqual(model_latency.configured_num_thread(), int(value))
        for value in ("0", "3", "12", "4;rm", "０４"):
            with patch.dict(os.environ, {"MENOR_OLLAMA_NUM_THREAD": value}):
                with self.assertRaises(ValueError):
                    model_latency.configured_num_thread()

    def test_reasoner_thread_override_does_not_change_constant(self):
        decision = {"move": "answer", "reply": "OK"}
        model_reply = MagicMock()
        model_reply.__enter__.return_value = model_reply
        model_reply.json.return_value = {"message": {"content": __import__("json").dumps(decision)}}
        with (patch.dict(os.environ, {"MENOR_OLLAMA_NUM_THREAD": "4"}),
              patch.object(intelligence.requests, "post", return_value=model_reply) as post):
            diagnostics = {}
            result = intelligence.decide("Diga OK", history=[], tools=[], capabilities=[],
                                         feedback_examples=[], preferences="", diagnostics=diagnostics)
        self.assertEqual(result["reply"], "OK")
        self.assertEqual(post.call_args.kwargs["json"]["options"]["num_thread"], 4)
        self.assertEqual(diagnostics["options"]["num_thread"], 4)
        self.assertNotIn("num_thread", intelligence.INFERENCE_OPTIONS)

    def test_diagnose_matrix_has_public_prompts_bounded_output_and_no_mutations(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {
            "message": {"content": "REDACTED PRIVATE"},
            "prompt_eval_count": 300, "prompt_eval_cached_count": 250,
            "prompt_eval_duration": 1_000_000_000,
            "eval_count": 20, "eval_duration": 2_000_000_000,
        }
        fake = MagicMock(return_value=response)
        result = model_latency.diagnostic_matrix(samples=2, post=fake, model="local:7b")
        self.assertEqual(result["samples"], 2)
        self.assertEqual(len(result["probes"]), 4)
        self.assertEqual(fake.call_count, 8)
        self.assertEqual([item.kwargs["json"]["options"]["num_predict"]
                          for item in fake.call_args_list],
                         [16, 96, 16, 96, 96, 16, 96, 16])
        self.assertNotIn("REDACTED PRIVATE", str(result))
        for call in fake.call_args_list:
            data = call.kwargs["json"]
            self.assertEqual(data["model"], "local:7b")
            self.assertFalse(data["stream"])
            self.assertEqual(len(data["messages"]), 2)
            self.assertNotIn("tools", data)
        with patch("ops.model_latency.requests.post") as post:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(model_latency.main(["--diagnose"]), 0)
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

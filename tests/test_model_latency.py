"""Opt-in local Ollama benchmark: no network in CI and no secret payloads."""
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from ops import model_latency


class LatencyTests(unittest.TestCase):
    def test_reject_remote_targets_and_hostile_model_identifiers(self):
        for url in ("https://example.org:11434", "http://192.168.1.4:11434",
                    "http://user:password@localhost:11434",
                    "http://localhost:11434/api/delete", "http://localhost:11434?q=1",
                    "file:///etc/passwd", "http://127.0.0.1:0", "http://127.0.0.1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                model_latency.local_endpoint(url)
        self.assertEqual(model_latency.local_endpoint("http://127.0.0.1:11434"),
                         "http://127.0.0.1:11434/api/chat")
        for name in ("../../../etc/passwd", "model ;curl", "", "áudio", "line\nfeed"):
            with self.assertRaises(ValueError):
                model_latency.model_identifier(name)

    def test_summary_never_outputs_raw_model_reply_or_metadata(self):
        data = model_latency.numeric_summary({
            "eval_count": 30, "eval_duration": 1_000_000_000,
            "message": {"content": "PRIVATE SECRET"},
            "prompt_eval_count": True, "load_duration": -1,
            "junk": {"secret": "PRIVATE SECRET"},
        })
        self.assertEqual(data["generation_tokens_per_second"], 30)
        self.assertNotIn("PRIVATE", str(data))
        self.assertNotIn("junk", data)
        self.assertNotIn("load_duration", data)

    def test_benchmark_uses_only_fixed_prompts_and_read_only_inference(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {
            "message": {"content": "Nada privado no resultado."},
            "eval_count": 20, "eval_duration": 2_000_000_000,
        }
        post = MagicMock(return_value=response)
        # Deploy sets OLLAMA_URL to a non-routable loopback port; keep this default-case test hermetic.
        with patch.dict(os.environ, {"OLLAMA_URL": "http://127.0.0.1:11434"}):
            result = model_latency.benchmark(samples=2, post=post, model="qwen2.5-coder:7b")
        self.assertEqual(result["probes"], 2)
        self.assertEqual(result["median_tokens_per_second"], 10)
        self.assertEqual(result["privacy"], "fixed_public_prompts_only")
        self.assertEqual(post.call_count, 2)
        for index, call in enumerate(post.call_args_list):
            url = call.args[0]
            payload = call.kwargs["json"]
            self.assertEqual(url, "http://127.0.0.1:11434/api/chat")
            self.assertFalse(payload["stream"])
            self.assertEqual(payload["messages"][-1]["content"], model_latency.PUBLIC_PROBES[index])
            self.assertLessEqual(payload["options"]["num_predict"], 80)
        self.assertNotIn("Nada privado", str(result))

    def test_benchmark_uses_configured_local_endpoint_without_network(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"message": {"content": "OK"}}
        post = MagicMock(return_value=response)
        # Deployment test isolation must not make the benchmark test fail.
        with patch.dict(os.environ, {"OLLAMA_URL": "http://127.0.0.1:9"}):
            result = model_latency.benchmark(samples=1, post=post)
        self.assertEqual(result["probes"], 1)
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:9/api/chat")

    def test_no_live_flag_never_requests_model(self):
        with patch("ops.model_latency.requests.post") as post:
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(model_latency.main([]), 0)
            post.assert_not_called()
        self.assertIn("--live", output.getvalue())

    def test_samples_are_bounded_before_network_request(self):
        with patch("ops.model_latency.requests.post") as post:
            for size in (0, 4, -1, True, "3"):
                with self.subTest(size=size), self.assertRaises(ValueError):
                    model_latency.benchmark(samples=size, post=post)
            post.assert_not_called()

    def test_failed_or_malformed_model_output_never_claims_success(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"message": {"invalid": "bad"}}
        with self.assertRaises(ValueError):
            model_latency.benchmark(samples=1, post=MagicMock(return_value=response))
        with patch.dict(os.environ, {"OLLAMA_URL": "https://external.example:11434"}):
            with self.assertRaises(ValueError):
                model_latency.benchmark(samples=1)


if __name__ == "__main__":
    unittest.main()

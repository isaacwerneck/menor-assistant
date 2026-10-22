"""Análise local dos relatórios E15: métricas agregadas sem conteúdo privado."""
import json
from pathlib import Path
import tempfile
import unittest

from ops import e15_report_analysis as evals


def _turn(key, number, status="answered", check=None, elapsed=2):
    return {
        "mode": "dialogue", "conversation_id": key,
        "turn_index": number, "question": "SENHA_PRIVADA_DO_USUARIO",
        "history": [{"role": "user", "content": "TEXTO_PRIVADO"}],
        "automatic_pass": check, "elapsed_seconds": elapsed,
        "result": {
            "status": status, "reply": "DADO_PRIVADO_DA_RESPOSTA",
            "performance": {"generation_tokens_per_second": 8.75,
                            "prompt_processing_ms": 200, "token_generation_ms": 1000},
        },
    }


def _report(model, cases, finished="2026-10-21T20:00:00+00:00"):
    return {
        "run_id": "20261021T200000Z-12345678",
        "suite_id": "e15-conversas-descoberta", "evaluation_model": model,
        "finished_at": finished, "cases": cases,
        "code_provenance": {"revision_changed": False},
    }


class E15LocalAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _write(self, name, payload):
        (self.root / name).write_text(json.dumps(payload), encoding="utf-8")

    def test_collects_two_models_without_exposing_text(self):
        a = _report("model-a", [_turn("alpha", 1, check=True),
                                _turn("alpha", 2, check=None),
                                _turn("beta", 1, status="inference_failed", check=False)])
        b = _report("model-b", [_turn("alpha", 1, check=True),
                                _turn("alpha", 2, check=True),
                                _turn("beta", 1, check=True)])
        self._write("20261021T200000Z-aaaa1111.json", a)
        self._write("20261021T200100Z-bbbb1111.json", b)
        self._write("20261021T200000Z-aaaa1111.summary.json", a)
        output = evals.analyze(self.root)
        self.assertEqual(output["latest_reports_by_suite_model"], 2)
        self.assertEqual(output["models"], ["model-a", "model-b"])
        left = output["summary"][0]
        self.assertEqual(left["scenarios"], 2)
        self.assertEqual(left["scenarios_completed_structurally"], 1)
        self.assertEqual(left["automatic_checks"], {"pass": 1, "human": 1, "fail": 1})
        self.assertEqual(left["median_generation_tokens_per_second"], 8.75)
        self.assertEqual(left["quality_claim"], "not_automatically_assessed")
        pair = output["paired_model_checks"][0]
        self.assertEqual(pair["paired_turns"], 3)
        self.assertEqual(pair["second_only"], 1)
        self.assertEqual(pair["both_structurally_valid"], 2)
        self.assertNotIn("SENHA_PRIVADA_DO_USUARIO", str(output))
        self.assertNotIn("TEXTO_PRIVADO", str(output))
        self.assertNotIn("DADO_PRIVADO", str(output))

    def test_latest_per_model_wins_without_mixing_other_suites(self):
        old = _report("model-a", [_turn("old", 1)])
        newer = _report("model-a", [_turn("new", 1), _turn("new", 2)],
                        finished="2026-10-21T21:00:00+00:00")
        self._write("20261021T190000Z-aaaa1111.json", old)
        self._write("20261021T210000Z-aaaa2222.json", newer)
        self._write("20261021T210100Z-bbbb3333.json", {
            **newer, "suite_id": "other-suite"})
        summary = evals.analyze(self.root)["summary"]
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["turns"], 2)

    def test_skips_bad_json_wrong_format_and_symlink(self):
        self._write("20261021T220000Z-aaab1111.json", {"cases": []})
        (self.root / "20261021T220100Z-aaab1111.json").write_text("{bad}")
        self._write("20261021T220200Z-aaab1111.json", _report(
            "model-b", [{"mode": "dialogue", "question": "bad", "result": {}}]))
        secret = self.root / "private.json"
        secret.write_text(json.dumps(_report("model-a", [_turn("x", 1)])))
        (self.root / "20261021T220300Z-aaab1111.json").symlink_to(secret)
        self.assertEqual(evals.analyze(self.root)["status"], "no_e15_reports")

    def test_rejects_invalid_directory_without_exposing_path(self):
        with self.assertRaises(ValueError):
            evals.analyze(self.root / "not-a-directory")

    def test_statistical_aggregates_ignore_invalid_numbers(self):
        self.assertIsNone(evals._median([None, "2", float("nan"), -1]))
        self.assertEqual(evals._median([1, 2, 3, 4]), 2.5)
        self.assertEqual(evals._p95([1, 2, 3, 4]), 4)


if __name__ == "__main__":
    unittest.main()

"""Garante validade das baterias e análise reprodutível de relatórios privados."""
import json
import tempfile
import unittest
from pathlib import Path

from ops import lab_eval_analysis
from src.api import lab_batches


class EvaluationBatteryTests(unittest.TestCase):
    def test_every_bundled_suite_is_valid_and_has_unique_cases(self):
        suites = sorted(lab_batches.SUITES.glob("*.json"))
        self.assertGreaterEqual(len(suites), 19)
        total = 0
        ids = set()
        for path in suites:
            with self.subTest(suite=path.name):
                data = lab_batches.validate_suite(json.loads(path.read_text(encoding="utf-8")))
                self.assertNotIn(data["id"], ids)
                ids.add(data["id"])
                identifiers = [case["id"] for case in data["cases"]]
                self.assertEqual(len(identifiers), len(set(identifiers)))
                for case in data["cases"]:
                    self.assertLessEqual(len(case["message"]), 1200)
                    self.assertIn(case["mode"], {"direct", "planner"})
                if data["id"] not in ("diagnostico-inicial", "triagem-16-v1",
                                      "diagnostico-geral-192-v1", "segundo-lote-base-v2",
                                      "segundo-lote-naturalidade-v2"):
                    self.assertEqual(len(data["cases"]), 12)
                if data["id"] in ("segundo-lote-base-v2", "segundo-lote-naturalidade-v2"):
                    self.assertEqual(len(data["cases"]), 24)
                if data["id"] == "triagem-16-v1":
                    self.assertEqual(len(data["cases"]), 16)
                if data["id"] == "diagnostico-geral-192-v1":
                    self.assertEqual(len(data["cases"]), 192)
                if data["id"] != "diagnostico-inicial":
                    for case in data["cases"]:
                        self.assertIn(case["split"], {"development", "validation"})
                total += len(data["cases"])
        self.assertGreaterEqual(total, 405)

    def test_report_analysis_never_exposes_raw_replies(self):
        suite = {"id": "exemplo", "cases": [
            {"id": "a", "mode": "direct", "category": "matematica", "split": "development",
             "review_criteria": "Conferir cálculo."},
            {"id": "b", "mode": "planner", "category": "planejamento", "split": "holdout",
             "review_criteria": "Validar restrições."},
        ]}
        report = {"run_id": "run-1", "suite_id": "exemplo", "cases": [
            {"id": "a", "mode": "direct", "result": {"status": "answered",
             "reply": "SEGREDO_DE_TESTE"}, "automatic_pass": True, "elapsed_seconds": 1},
            {"id": "b", "mode": "planner", "result": {"status": "no_valid_decision",
             "reply": "OUTRO_SEGREDO_DE_TESTE"}, "automatic_pass": None, "elapsed_seconds": 49},
        ]}
        summary = lab_eval_analysis.summarize(report, suite)
        self.assertEqual(summary["graded_count"], 1)
        self.assertEqual(summary["ungraded_count"], 1)
        self.assertEqual(summary["accuracy_on_graded"], 1.0)
        self.assertEqual(summary["incidents"]["no_valid_decision"], 1)
        self.assertEqual(summary["incidents"]["slow_execution"], 1)
        self.assertNotIn("SEGREDO_DE_TESTE", json.dumps(summary))
        self.assertNotIn("OUTRO_SEGREDO_DE_TESTE", json.dumps(summary))
        second = dict(summary, run_id="run-2", cases=[
            dict(summary["cases"][0], grade="failed"), summary["cases"][1],
        ])
        compared = lab_eval_analysis.compare(summary, second)
        self.assertEqual(compared["regressions"], ["a"])

    def test_suite_lookup_stays_within_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                lab_eval_analysis._load_suite("../../outside", Path(directory))


if __name__ == "__main__":
    unittest.main()

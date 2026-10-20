"""Esquema, graders e relatórios reproduzíveis para a coleção de avaliações."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api import lab_batches, remote_lab


class ResearchSuiteTests(unittest.TestCase):
    def test_sixteen_new_suites_have_valid_cases_and_review_metadata(self):
        files = list(lab_batches.SUITES.glob("*.json"))
        suites = []
        for path in files:
            item = json.loads(path.read_text(encoding="utf-8"))
            if item.get("methodology_version") != "menor-eval-v1":
                continue
            suites.append(lab_batches.validate_suite(item))
            self.assertEqual(len(item["cases"]), 12, path.name)
            for case in item["cases"]:
                self.assertIn(case["split"], ("development", "validation"))
                self.assertEqual(case["category"], item["id"])
                self.assertIn(case["mode"], ("direct", "planner"))
        self.assertEqual(len(suites), 16)
        self.assertEqual(sum(len(item["cases"]) for item in suites), 192)

    def test_exact_checks_reject_substrings_but_accept_case_and_padding(self):
        case = {"expected_exact": "NÃO", "expected_contains": []}
        self.assertTrue(lab_batches.grade_case(case, {"status": "answered", "reply": " não "}))
        self.assertFalse(lab_batches.grade_case(case, {"status": "answered", "reply": "sim, não"}))
        self.assertFalse(lab_batches.grade_case(case, {"status": "inference_failed", "reply": "não"}))

    def test_open_rubrics_are_ungraded_even_when_inference_fails(self):
        case = {"review_criteria": "Não inventar fatos.", "expected_contains": []}
        self.assertIsNone(lab_batches.grade_case(case, {"status": "inference_failed"}))

    def test_validation_rejects_conflicting_or_malformed_metadata(self):
        case = {"id": "c1", "mode": "direct", "message": "Oi"}
        for metadata in ({"expected_exact": "yes", "expected_contains": ["yes"]},
                         {"expected_exact": ""}, {"split": "test"},
                         {"review_criteria": 123}, {"expected_contains": [""]}):
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                lab_batches.validate_suite({"id": "teste-meta", "cases": [{**case, **metadata}]})

    def test_report_preserves_context_rubric_split_and_failure_status(self):
        suite = {"id": "test-eval-metadata", "methodology_version": "menor-eval-v1",
                 "cases": [
                     {"id": "c1", "category": "contexto", "mode": "direct",
                      "message": "Como se chama?", "expected_exact": "Aurora",
                      "split": "validation", "review_criteria": "Usar histórico",
                      "history": [{"role": "user", "content": "Nome Aurora"}]},
                     {"id": "c2", "mode": "planner", "message": "Planeje um backup."},
                 ]}
        run_id = "20261020T010000Z-11112222"
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(lab_batches, "DATA", Path(tmp)), \
                 patch.dict(os.environ, {"MENOR_LAB_REPORTS_PUBLISH": "0"}), \
                 patch.object(remote_lab, "_direct", return_value={
                     "status": "answered", "reply": "Aurora"}), \
                 patch.object(remote_lab, "_planner", return_value={
                     "status": "no_valid_decision", "reply": ""}):
                lab_batches._run(suite, run_id)
                report = json.loads((Path(tmp) / (run_id + ".json")).read_text(encoding="utf-8"))
        self.assertEqual(report["automatic_passes"], 1)
        self.assertEqual(report["inference_failures"], 1)
        self.assertEqual(report["ungraded"], 1)
        self.assertEqual(report["cases"][0]["split"], "validation")
        self.assertEqual(report["cases"][0]["review_criteria"], "Usar histórico")
        self.assertEqual(report["cases"][0]["history"][0]["content"], "Nome Aurora")


if __name__ == "__main__":
    unittest.main()

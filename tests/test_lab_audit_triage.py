"""Regressões isoladas para triagem offline dos relatórios do laboratório."""
import json
import tempfile
import unittest
from pathlib import Path

from ops.lab_batch_audit import inspect


class AuditTriageTests(unittest.TestCase):
    def test_overlaps_and_technical_grading_are_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            first = {
                "run_id": "20261020T180000Z-11111111", "suite_id": "suite-small",
                "cases": [
                    {"question": "SEGREDO PERGUNTA", "history": [],
                     "automatic_pass": False, "elapsed_seconds": 5,
                     "result": {"status": "answered", "reply": "SEGREDO RESPOSTA"}},
                    {"question": "Pergunta distinta", "history": [],
                     "automatic_pass": False, "elapsed_seconds": 40,
                     "result": {"status": "no_valid_decision",
                                "diagnostics": {"validation_issue": "goal"},
                                "output_limited": True}},
                ],
            }
            second = {
                "run_id": "20261020T180100Z-22222222", "suite_id": "suite-aggregate",
                "cases": [
                    {"question": "SEGREDO PERGUNTA", "history": [],
                     "automatic_pass": True, "elapsed_seconds": 9,
                     "result": {"status": "answered", "reply": "texto"}},
                ],
            }
            for report in (first, second):
                (root / (report["run_id"] + ".json")).write_text(
                    json.dumps(report), encoding="utf-8")
            audit = inspect(root)
            self.assertEqual(audit["cases_executed"], 3)
            self.assertEqual(audit["unique_prompt_history_pairs"], 2)
            self.assertEqual(audit["repeated_prompt_executions"], 1)
            self.assertEqual(audit["graded_failures"], 2)
            self.assertEqual(audit["technical_graded_failures"], 1)
            self.assertEqual(audit["completed_graded_failures"], 1)
            self.assertEqual(audit["technical_failures"], 1)
            self.assertEqual(audit["validation_issues"], {"goal": 1})
            self.assertEqual(audit["priority_suites"][0], "suite-small")
            self.assertEqual(audit["suites"]["suite-small"]["output_limits"], 1)
            self.assertEqual(audit["suites"]["suite-small"]["latency_p50_seconds"], 22.5)
            self.assertEqual(audit["suites"]["suite-small"]["statuses"],
                             {"answered": 1, "no_valid_decision": 1})
            rendered = json.dumps(audit, ensure_ascii=False)
            self.assertNotIn("SEGREDO", rendered)

    def test_unknown_validation_issue_never_leaks(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            report = {"run_id": "20261020T180200Z-33333333",
                      "suite_id": "suite-valid",
                      "cases": [{"question": "x", "history": [],
                                 "automatic_pass": None,
                                 "result": {"status": "no_valid_decision",
                                            "diagnostics": {"validation_issue": "TOKEN-SECRETO"}}}]}
            (root / (report["run_id"] + ".json")).write_text(
                json.dumps(report), encoding="utf-8")
            audit = inspect(root)
            self.assertEqual(audit["validation_issues"], {})
            self.assertNotIn("TOKEN-SECRETO", json.dumps(audit))


if __name__ == "__main__":
    unittest.main()

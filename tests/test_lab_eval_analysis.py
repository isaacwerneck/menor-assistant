"""Regressões de telemetria do laboratório em relatórios malformados."""
import math
import unittest

from ops.lab_eval_analysis import summarize


class LabEvalAnalysisTests(unittest.TestCase):
    def test_infinite_and_nan_latencies_do_not_contaminate_summary(self):
        suite = {"id": "eval-tiny", "cases": [
            {"id": "good", "mode": "direct", "category": "perf"},
            {"id": "inf", "mode": "direct", "category": "perf"},
            {"id": "nan", "mode": "direct", "category": "perf"},
        ]}
        report = {"run_id": "a", "suite_id": "eval-tiny", "cases": [
            {"id": "good", "automatic_pass": True, "elapsed_seconds": 5.0,
             "result": {"status": "answered"}},
            {"id": "inf", "automatic_pass": False, "elapsed_seconds": float("inf"),
             "result": {"status": "answered"}},
            {"id": "nan", "automatic_pass": False, "elapsed_seconds": float("nan"),
             "result": {"status": "answered"}},
        ]}
        analysis = summarize(report, suite)
        self.assertEqual(analysis["median_seconds"], 5.0)
        self.assertEqual([item["elapsed_seconds"] for item in analysis["cases"]],
                         [5.0, None, None])
        self.assertTrue(math.isfinite(analysis["median_seconds"]))
        self.assertNotIn("slow_execution", analysis["incidents"])

    def test_bool_and_negative_duration_are_not_seconds(self):
        suite = {"id": "eval-tiny", "cases": [{"id": "bad", "mode": "direct"}]}
        for elapsed in (True, -1, float("-inf")):
            with self.subTest(elapsed=elapsed):
                result = summarize({
                    "run_id": "b", "suite_id": "eval-tiny",
                    "cases": [{"id": "bad", "automatic_pass": None,
                               "elapsed_seconds": elapsed, "result": {"status": "answered"}}],
                }, suite)
                self.assertIsNone(result["median_seconds"])


if __name__ == "__main__":
    unittest.main()

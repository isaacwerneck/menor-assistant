"""Comparação das medições sem inferência nem rede."""
import unittest

from ops import eval_compare


def report(run_id, cases):
    return {"suite_id": "test", "run_id": run_id, "cases": cases}


def case(case_id, passed, status="answered", seconds=1.0):
    return {"id": case_id, "automatic_pass": passed, "elapsed_seconds": seconds,
            "result": {"status": status}, "split": "development"}


class CompareTests(unittest.TestCase):
    def test_metrics_ignore_manual_reviews_in_pass_rate(self):
        data = report("a", [case("x", True), case("y", False, "inference_failed"),
                            case("z", None, seconds=8)])
        stats = eval_compare.summarize(data)
        self.assertEqual(stats["graded_pass_rate"], 0.5)
        self.assertEqual(stats["ungraded"], 1)
        self.assertEqual(stats["completion_rate"], 0.6667)
        self.assertEqual(stats["latency_p95_seconds"], 8)
        self.assertIn("inference_failed", stats["execution_errors"])
        self.assertTrue(eval_compare.recommendations(data))

    def test_comparison_identifies_regression_and_improvement(self):
        baseline = report("before", [case("one", True), case("two", False), case("three", None)])
        candidate = report("after", [case("one", False), case("two", True), case("three", None)])
        result = eval_compare.compare(baseline, candidate)
        self.assertEqual(result["new_regressions"], ["one"])
        self.assertEqual(result["resolved_failures"], ["two"])
        self.assertEqual(result["graded_pass_delta"], 0)

    def test_different_cases_or_suites_rejected(self):
        old = report("old", [case("a", True)])
        new = report("new", [case("b", True)])
        with self.assertRaises(ValueError):
            eval_compare.compare(old, new)
        new["cases"] = old["cases"]
        new["suite_id"] = "different"
        with self.assertRaises(ValueError):
            eval_compare.compare(old, new)

    def test_empty_report_has_no_false_scores(self):
        stats = eval_compare.summarize(report("empty", []))
        self.assertIsNone(stats["graded_pass_rate"])
        self.assertIsNone(stats["completion_rate"])
        self.assertEqual(stats["total"], 0)


if __name__ == "__main__":
    unittest.main()

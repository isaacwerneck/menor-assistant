"""Métricas locais com privacidade, idempotência e sinalização de falhas."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent.diagnostics import analyze
from src.agent.quality_metrics import DecisionMetrics
from src.agent import runner
from src.agent.tasks import TaskStore
from src.memory.store import BrainStore


class MetricsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = BrainStore(Path(temp.name) / "data")
        self.metrics = DecisionMetrics(self.store)

    def test_empty_read_is_not_a_write(self):
        path = self.store.brain_dir / "memoria" / "decision_metrics.sqlite"
        self.assertEqual(self.metrics.report()["events"], 0)
        self.assertFalse(path.exists())

    def test_only_counters_and_error_type_are_saved(self):
        secret_message = "Documento privado sobre aquisição de uma empresa"
        self.metrics.record("conversation01", "request001", {
            "handled": True, "phase": "goal", "reply": secret_message,
            "artifact": {"prompt": secret_message},
        })
        path = self.store.brain_dir / "memoria" / "decision_metrics.sqlite"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(path) as conn:
            raw = repr(conn.execute("SELECT * FROM decisions").fetchall())
        self.assertNotIn(secret_message, raw)
        self.assertEqual(self.metrics.report()["handled"], 1)
        self.metrics.record("conversation01", "request001", {
            "handled": False, "phase": "failed",
        }, error_type="ValueError")
        self.assertEqual(self.metrics.report()["events"], 1)

    def test_signals_expose_patterns_not_private_text(self):
        for idx in range(5):
            self.metrics.record("conversation01", f"failed{idx:04}", {
                "handled": True, "phase": "failed",
            }, error_type="RuntimeError")
        for idx in range(5):
            self.metrics.record("conversation01", f"missing{idx:04}", {
                "handled": False, "phase": "idle",
            })
        report = self.metrics.report()
        self.assertEqual(report["failed"], 5)
        self.assertEqual(report["unhandled"], 5)
        self.assertIn("repeated_failures", [x["type"] for x in report["review_signals"]])
        self.assertIn("unhandled_requests", [x["type"] for x in report["review_signals"]])
        self.assertEqual(report["error_types"]["RuntimeError"], 5)
        self.assertEqual(analyze(self.store)["decision_quality"]["failed"], 5)

    def test_symlink_database_is_rejected(self):
        folder = self.store._directories(("memoria",))
        outside = self.store.data_dir / "secret.txt"
        outside.write_text("private", encoding="utf-8")
        (folder / "decision_metrics.sqlite").symlink_to(outside)
        with self.assertRaises(ValueError):
            self.metrics.record("conversation01", "request001", {
                "handled": True, "phase": "goal",
            })
        self.assertEqual(outside.read_text(encoding="utf-8"), "private")


class RunnerMetricsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": temp.name, "MENOR_INTELLIGENCE_ENABLED": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.tasks = TaskStore()

    @patch("src.agent.runner.intelligence.decide")
    def test_agent_emits_once_per_unique_turn_and_never_on_cached_retry(self, decide):
        decide.return_value = {
            "move": "answer", "goal": "Dúvida de química",
            "reply": "É uma reação de oxidação.", "question": "",
            "steps": [], "acceptance": [],
        }
        first = runner.run("metricSession1", "metricTurn001", "O que é oxidação?", [], tasks=self.tasks)
        second = runner.run("metricSession1", "metricTurn001", "O que é oxidação?", [], tasks=self.tasks)
        self.assertEqual(first, second)
        self.assertEqual(DecisionMetrics().report()["events"], 1)
        decide.assert_called_once()

    @patch("src.agent.runner.intelligence.decide", side_effect=RuntimeError("secret in error"))
    def test_agent_error_is_recorded_without_exception_details(self, decide):
        runner.run("metricSession1", "metricTurn001", "Dúvida com erro", [], tasks=self.tasks)
        report = DecisionMetrics().report()
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["error_types"], {"RuntimeError": 1})


if __name__ == "__main__":
    unittest.main()

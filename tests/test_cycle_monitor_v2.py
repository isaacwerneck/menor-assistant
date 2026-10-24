import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.agent.cycle_monitor import CycleMonitor
from src.api.main import app
from src.security import auth


class TestCycleMonitorV2(unittest.TestCase):
    def setUp(self):
        self.monitor = CycleMonitor()
        self.client = TestClient(app)

    def test_cycle_monitor_lifecycle(self):
        # 1. Estado inicial
        snap = self.monitor.snapshot()
        self.assertFalse(snap["is_running"])
        self.assertEqual(snap["current_phase"], 0)
        self.assertEqual(snap["progress_percent"], 0)

        # 2. Início do ciclo
        self.monitor.start("Iniciando ciclo de teste")
        snap = self.monitor.snapshot()
        self.assertTrue(snap["is_running"])
        self.assertEqual(snap["current_phase"], 1)
        self.assertGreaterEqual(len(snap["logs"]), 1)
        self.assertIn("Iniciando ciclo de teste", snap["logs"][0]["message"])

        # 3. Avanço de fases e métricas
        self.monitor.set_phase(2, "Estudando tópicos web")
        self.monitor.update_metrics(learnings_count=3, anti_patterns_count=1)
        snap = self.monitor.snapshot()
        self.assertEqual(snap["current_phase"], 2)
        self.assertEqual(snap["metrics"]["learnings_count"], 3)
        self.assertEqual(snap["metrics"]["anti_patterns_count"], 1)

        self.monitor.set_phase(3, "Inspeção AST")
        self.monitor.update_metrics(coverage_percentage=82.5, uncovered_gaps=5)
        snap = self.monitor.snapshot()
        self.assertEqual(snap["metrics"]["coverage_percentage"], 82.5)
        self.assertEqual(snap["metrics"]["uncovered_gaps"], 5)

        self.monitor.set_phase(4, "Auto-crítica")
        self.monitor.update_metrics(judge_score=9.0, golden_example_created=True)
        snap = self.monitor.snapshot()
        self.assertEqual(snap["metrics"]["judge_score"], 9.0)
        self.assertTrue(snap["metrics"]["golden_example_created"])

        # 4. Finalização
        dummy_report = {"report_markdown": "# Relatório de Teste"}
        self.monitor.finish(report=dummy_report)
        snap = self.monitor.snapshot()
        self.assertFalse(snap["is_running"])
        self.assertEqual(snap["current_phase"], 5)
        self.assertEqual(snap["progress_percent"], 100)
        self.assertIn("# Relatório de Teste", snap["last_report_summary"].get("report_markdown", ""))

        # 5. Limpeza de logs
        self.monitor.clear_logs()
        snap = self.monitor.snapshot()
        self.assertEqual(len(snap["logs"]), 0)

    def test_cycle_monitor_interrupted(self):
        self.monitor.start("Iniciando")
        self.monitor.finish(interrupted=True)
        snap = self.monitor.snapshot()
        self.assertFalse(snap["is_running"])
        self.assertTrue(snap["interrupted"])
        self.assertEqual(snap["phase_name"], "Interrompido")

    def test_api_study_live_endpoint(self):
        # Mock owner authentication
        with patch.object(auth, "require_owner", return_value=True):
            resp = self.client.get("/api/study/live")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("is_running", data)
            self.assertIn("current_phase", data)
            self.assertIn("metrics", data)
            self.assertIn("logs", data)

    def test_api_study_clear_logs_endpoint(self):
        with patch.object(auth, "require_owner", return_value=True):
            resp = self.client.post("/api/study/clear-logs")
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.json().get("success"))

    def test_api_study_abort_endpoint_when_not_running(self):
        with patch.object(auth, "require_owner", return_value=True):
            resp = self.client.post("/api/study/abort")
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(resp.json().get("success"))


if __name__ == "__main__":
    unittest.main()

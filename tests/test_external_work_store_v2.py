"""Testes para o Isolamento de Agentes de Código Externos (Pilar 9 - trabalhos.db)."""
import tempfile
import unittest
from pathlib import Path

from src.agent.external_work_store import ExternalWorkStore, get_agent_work_status
from src.memory.store import BrainStore


class TestExternalWorkStoreV2(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = BrainStore(data_dir=self.temp_dir.name)
        self.store.initialize()
        self.work_store = ExternalWorkStore(store=self.store)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_start_and_complete_session(self):
        self.work_store.start_session(
            session_id="sess_123",
            agent_name="antigravity",
            project_path="/home/user/project",
            task_goal="Refatorar testes unitários",
        )
        sessions = self.work_store.get_agent_work_status(session_id="sess_123")
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["status"], "running")
        self.assertEqual(sessions[0]["agent_name"], "antigravity")

        self.work_store.complete_session(session_id="sess_123", status="completed")
        sessions_after = self.work_store.get_agent_work_status(session_id="sess_123")
        self.assertEqual(sessions_after[0]["status"], "completed")
        self.assertIsNotNone(sessions_after[0]["completed_at"])

    def test_record_logs_and_diffs_isolated(self):
        initial_notes_count = len(self.store.list_notes())
        self.work_store.start_session(
            session_id="sess_456",
            agent_name="codex",
            project_path="/workspace",
            task_goal="Adicionar endpoint",
        )
        self.work_store.record_log("sess_456", "Iniciando compilação...", "stdout")
        self.work_store.record_log("sess_456", "Build concluído com sucesso.", "stdout")
        self.work_store.record_diff("sess_456", "src/api.py", "+ @app.get('/new')\n+ def new(): pass")

        sessions = self.work_store.get_agent_work_status(session_id="sess_456")
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["logs_count"], 2)
        self.assertEqual(sessions[0]["diffs_count"], 1)

        # Garante que nada foi gravado na memória pessoal (brain_notes.sqlite)
        notes = self.store.list_notes()
        self.assertEqual(len(notes), initial_notes_count)

    def test_get_agent_work_status_tool(self):
        res = get_agent_work_status()
        self.assertTrue(res["success"])
        self.assertIn("sessions", res)

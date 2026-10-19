"""Recuperação pós-queda sem repetir efeitos de tarefas incompletas."""
import os
import tempfile
import unittest
from unittest.mock import patch

from src.agent import runner
from src.agent.tasks import RunBusy, TaskStore
from test_auth_memory import call


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": temp.name, "MENOR_INTELLIGENCE_ENABLED": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.store = TaskStore()
        self.session = "crashSession01"

    def test_interrupted_turn_becomes_terminal_and_is_never_reexecuted(self):
        payload = {"message": "Crie um projeto"}
        previous, cached = self.store.claim(self.session, "crashTurn001", payload)
        self.assertEqual(previous["phase"], "idle")
        self.assertIsNone(cached)
        with self.assertRaises(RunBusy):
            self.store.claim(self.session, "crashTurn002", {"message": "outra tarefa"})
        with self.assertRaises(ValueError):
            self.store.recover(self.session, confirmed=False)
        restored = TaskStore().recover(self.session, confirmed=True)
        self.assertTrue(restored["recovered"])
        self.assertTrue(restored["state"]["effects_uncertain"])
        self.assertEqual(restored["interrupted_turns"], 1)
        prior, replay = self.store.claim(self.session, "crashTurn001", payload)
        self.assertIsNone(prior)
        self.assertTrue(replay["interrupted"])
        self.assertIn("não vai repeti-la", replay["reply"])
        state, repeat = self.store.claim(self.session, "crashTurn002", {"message": "outra tarefa"})
        self.assertEqual(state["phase"], "failed")
        self.assertIsNone(repeat)
        self.store.finish(self.session, "crashTurn002", {"phase": "idle"}, {"handled": False})

    def test_recovery_never_competes_with_current_process(self):
        self.store.claim(self.session, "crashTurn001", {"message": "execução longa"})
        with self.store.session_lock(self.session):
            with self.assertRaises(RunBusy):
                TaskStore().recover(self.session, confirmed=True)
        self.assertEqual(self.store.inspect(self.session)["phase"], "running")

    def test_previous_goal_is_paused_but_prior_approval_not_restored(self):
        previous_state = {
            "phase": "goal", "goal": "Criar um app de tarefas",
            "goal_id": "a" * 32, "steps": ["Projetar as telas"],
            "acceptance": ["Protótipo testado"], "question": "",
        }
        self.store.claim(self.session, "crashTurn001", {"message": "primeira vez"})
        self.store.finish(self.session, "crashTurn001", previous_state, {"handled": True})
        self.store.claim(self.session, "crashTurn002", {"message": "pode programar?"})
        state = self.store.recover(self.session, confirmed=True)["state"]
        self.assertEqual(state["phase"], "failed")
        self.assertEqual(state["paused_goals"][0]["goal"], "Criar um app de tarefas")
        self.assertNotIn("tool", state)
        self.assertNotIn("arguments", state)

    def test_normal_completed_session_is_unchanged(self):
        self.store.claim(self.session, "crashTurn001", {"message": "oi"})
        self.store.finish(self.session, "crashTurn001", {"phase": "idle"}, {"handled": False})
        restored = self.store.recover(self.session, confirmed=True)
        self.assertFalse(restored["recovered"])
        self.assertEqual(self.store.inspect(self.session)["phase"], "idle")

    @patch("src.agent.runner._advance", return_value=({"phase": "idle"}, {"handled": False}))
    def test_normal_runner_uses_process_lock_and_does_not_leave_backup(self, advance):
        first = runner.run(self.session, "crashTurn001", "oi", [], tasks=self.store)
        self.assertFalse(first["handled"])
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM run_backups").fetchone()[0], 0)
        advance.assert_called_once()


class RecoveryEndpointTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": temp.name})
        env.start()
        self.addCleanup(env.stop)
        from src.security import auth
        auth._attempts.clear()
        status, _, headers = call("/auth/setup", {"password": "senha-longa-para-recovery"})
        self.assertEqual(status, 200)
        self.cookie = headers[b"set-cookie"].decode().split(";", 1)[0]
        TaskStore().claim("crashSession01", "crashTurn001", {"message": "faça algo"})

    def test_owner_confirmation_required_and_not_a_get_side_effect(self):
        path = "/agent/runs/crashSession01/recover"
        self.assertEqual(call(path, {"confirmed": True})[0], 401)
        self.assertEqual(call(path, {"confirmed": False}, cookie=self.cookie)[0], 422)
        self.assertEqual(call("/agent/runs/crashSession01", cookie=self.cookie)[1]["phase"], "running")
        code, outcome, _ = call(path, {"confirmed": True}, cookie=self.cookie)
        self.assertEqual(code, 200, outcome)
        self.assertTrue(outcome["recovered"])
        self.assertTrue(TaskStore().inspect("crashSession01")["effects_uncertain"])


if __name__ == "__main__":
    unittest.main()

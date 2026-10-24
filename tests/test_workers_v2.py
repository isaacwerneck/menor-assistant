import gc
from pathlib import Path
import tempfile
import unittest

from src.agent.workers import TaskQueue


class TestTaskQueue(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_tasks.db"
        self.queue = TaskQueue(db_path=str(self.db_path))

    def tearDown(self):
        del self.queue
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_enqueue_and_get(self):
        task_id = self.queue.enqueue("Construir API de notas", "notas-app")
        self.assertTrue(task_id > 0)

        task = self.queue.get_task(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task["goal"], "Construir API de notas")
        self.assertEqual(task["status"], "pending")

    def test_update_status(self):
        task_id = self.queue.enqueue("Criar testes", "teste-proj")
        self.queue.update_status(task_id, "completed", result="Testes passaram")

        task = self.queue.get_task(task_id)
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"], "Testes passaram")


if __name__ == "__main__":
    unittest.main()

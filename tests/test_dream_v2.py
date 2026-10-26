import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from src.agent.dream import DreamConsolidator
from src.memory.store import BrainStore


class TestDreamV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = BrainStore(data_dir=self.temp_dir)
        self.store.initialize()
        self.dream = DreamConsolidator(store=self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_run_dream_cycle_creates_diary(self):
        # Cria uma nota para consolidar
        self.store.write_note(
            "preferencias/estilo.md",
            "Preferência: sempre usar paleta Dark Minimalist.",
        )

        result = self.dream.run_dream_cycle()
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "completed")
        self.assertTrue(Path(result["diary_path"]).exists())
        self.assertTrue(result["facts_saved"] > 0)

        # Checa conteúdo do diário append-only
        diary_content = Path(result["diary_path"]).read_text(encoding="utf-8")
        self.assertIn("dream_consolidation", diary_content)
        self.assertIn("preferencias/estilo.md", diary_content)

    def test_cooperative_preemption(self):
        abort_event = threading.Event()
        abort_event.set()  # Usuário interagiu

        result = self.dream.run_dream_cycle(abort_event=abort_event)
        self.assertFalse(result["success"])
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["status"], "interrupted_by_user")

    def test_dream_state_persistence(self):
        self.dream.run_dream_cycle()
        state = self.dream.get_state()
        self.assertIn("status", state)
        self.assertEqual(state["status"], "completed")


if __name__ == "__main__":
    unittest.main()

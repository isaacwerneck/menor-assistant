import tempfile
import unittest

from src.memory.store import BrainStore
from src.memory.search import KnowledgeIndex


class TestMemoryStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = BrainStore(data_dir=self.temp_dir.name)
        self.store.initialize()

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_remember_preference(self):
        self.store.remember_preference("Prefiro respostas curtas em português")
        ctx = self.store.preference_context()
        self.assertIn("respostas curtas", ctx)

    def test_list_notes(self):
        self.store.write_note("conhecimentos/nota1.md", "# Teste 1")
        notes = self.store.list_notes()
        self.assertIn("conhecimentos/nota1.md", notes)


class TestKnowledgeIndex(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = BrainStore(data_dir=self.temp_dir.name)
        self.store.initialize()
        self.index = KnowledgeIndex(store=self.store)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_index_and_search(self):
        self.store.remember_knowledge("FastAPI e Python para APIs de alta velocidade")
        res = self.index.search("FastAPI", limit=3)
        self.assertTrue(len(res) > 0)
        self.assertIn("FastAPI", res[0]["content"])


if __name__ == "__main__":
    unittest.main()

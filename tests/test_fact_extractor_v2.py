import shutil
import tempfile
import unittest
from pathlib import Path

from src.memory.fact_extractor import FactExtractor
from src.memory.store import BrainStore


class TestFactExtractorV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = BrainStore(data_dir=self.temp_dir)
        self.store.initialize()
        self.extractor = FactExtractor(store=self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_extract_heuristic_preference(self):
        msg = "Eu prefiro usar Tailwind com CSS modular e animações rápidas."
        facts = self.extractor.extract_facts(msg, "Entendido, vou aplicar Tailwind.")
        self.assertTrue(len(facts) > 0)
        self.assertEqual(facts[0]["category"], "preference")
        self.assertIn("Tailwind", facts[0]["fact"])

    def test_extract_heuristic_constraint(self):
        msg = "Eu odeio interfaces com fundo branco e fontes sem serifa genéricas."
        facts = self.extractor.extract_facts(msg, "Anotado! Somente Dark Minimalist.")
        self.assertTrue(len(facts) > 0)
        self.assertEqual(facts[0]["category"], "constraint")
        self.assertIn("fundo branco", facts[0]["fact"])

    def test_casual_queries_produce_no_facts(self):
        self.assertEqual(self.extractor.extract_facts("opa eai mano", "E aí Isaac!"), [])
        self.assertEqual(self.extractor.extract_facts("tudo bem por aí?", "Tudo suave!"), [])

    def test_store_fact_persists_in_brain(self):
        self.extractor.store_fact("Prefere FastAPI assíncrono em vez de Flask", "preference")
        notes = self.store.list_notes()
        self.assertTrue(any("preferencias" in n for n in notes))

    def test_async_extraction_thread_runs(self):
        thread = self.extractor.extract_and_store_async(
            "Eu prefiro bancos de dados SQLite com WAL mode ativado.",
            "Configurado com sucesso!",
        )
        thread.join(timeout=2.0)
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()

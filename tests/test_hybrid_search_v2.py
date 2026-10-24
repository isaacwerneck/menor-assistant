import tempfile
import unittest

from src.memory.search import (
    KnowledgeIndex,
    compute_vector,
    cosine_similarity,
    contextual_knowledge,
)
from src.memory.store import BrainStore


class TestHybridSearch(unittest.TestCase):
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

    def test_compute_vector_and_cosine_similarity(self):
        v1 = compute_vector("Python FastAPI arquitetura assíncrona")
        v2 = compute_vector("Python FastAPI arquitetura assíncrona")
        sim_same = cosine_similarity(v1, v2)
        self.assertAlmostEqual(sim_same, 1.0, places=4)

        v3 = compute_vector("Culinária bolo de chocolate confeitaria")
        sim_diff = cosine_similarity(v1, v3)
        self.assertLess(sim_diff, 0.4)

    def test_hybrid_search(self):
        self.store.remember_knowledge("Ollama executa modelos locais sem cloud")
        self.store.remember_knowledge("FastAPI gerencia endpoints assíncronos em Python")

        res = self.index.search_hybrid("modelos locais com Ollama", limit=2)
        self.assertTrue(len(res) > 0)
        top = res[0]
        self.assertIn("Ollama", top["content"])
        self.assertIn("score", top)
        self.assertIn("bm25_score", top)
        self.assertIn("vector_score", top)

    def test_deduplicate_and_store(self):
        # 1. Primeira inserção de fato
        res1 = self.index.deduplicate_and_store("Banco de dados SQLite com WAL mode ativo")
        self.assertEqual(res1["action"], "inserted")

        # 2. Inserção de fato quase idêntico com alta similaridade (deve atualizar, não duplicar)
        res2 = self.index.deduplicate_and_store(
            "Banco de dados SQLite configurado com WAL mode ativo",
            threshold=0.80,
        )
        self.assertIn(res2["action"], ("updated", "exact_match"))

        # 3. Inserção de fato completamente distinto (deve inserir novo)
        res3 = self.index.deduplicate_and_store(
            "Frontend moderno com Tailwind e WebSockets para streaming",
            threshold=0.80,
        )
        self.assertEqual(res3["action"], "inserted")

    def test_contextual_knowledge_formatted(self):
        self.store.remember_knowledge("Docker compose orquestra serviços locais")
        ctx = contextual_knowledge("Docker compose", store=self.store)
        self.assertIn("Docker compose", ctx)
        self.assertIn("aprendizados_gerais.md", ctx)


if __name__ == "__main__":
    unittest.main()

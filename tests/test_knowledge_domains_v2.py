"""Testes das 5 Bases de Conhecimento Padrão e Motor de Improve (Fase 2)."""
import tempfile
import unittest

from src.memory.store import BrainStore
from src.tools.core import TOOL_DISPATCHER, get_knowledge, improve_knowledge


class TestKnowledgeDomainsV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = BrainStore(data_dir=self.temp_dir.name)
        self.store.initialize()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_seed_files_and_folders_created(self):
        domains = self.store.list_domains()
        self.assertIn("design", domains)
        self.assertIn("programacao", domains)
        self.assertIn("engenharia_software", domains)
        self.assertIn("musica", domains)
        self.assertIn("game_design", domains)

        # Verifica arquivos seed
        vis = self.store.read_note("conhecimentos/design/estilo_visual.md")
        self.assertIn("Estilo Visual", vis)

        prog = self.store.read_note("conhecimentos/programacao/estilo_isaac.md")
        self.assertIn("Estilo de Programação", prog)

        eng = self.store.read_note("conhecimentos/engenharia_software/arquitetura.md")
        self.assertIn("Engenharia de Software", eng)

        mus = self.store.read_note("conhecimentos/musica/producao_e_sintese.md")
        self.assertIn("Conhecimentos Musicais", mus)

        game = self.store.read_note("conhecimentos/game_design/filosofia_jogos.md")
        self.assertIn("Game Design", game)

    def test_improve_knowledge_append_and_overwrite(self):
        # 1. Overwrite
        res1 = self.store.improve_knowledge(
            domain="design",
            topic="paletas_neon",
            content="- Roxo escuro (#1a0033) e Cyan elétrico (#00f3ff)",
            mode="overwrite",
        )
        self.assertTrue(res1["success"])
        self.assertEqual(res1["domain"], "design")

        content1 = self.store.read_note(res1["path"])
        self.assertIn("Paletas_Neon", content1)
        self.assertIn("Roxo escuro", content1)

        # 2. Append
        res2 = self.store.improve_knowledge(
            domain="design",
            topic="paletas_neon",
            content="- Laranja âmbar (#ffaa00) para acentos secundários",
            mode="append",
        )
        self.assertTrue(res2["success"])
        content2 = self.store.read_note(res2["path"])
        self.assertIn("Roxo escuro", content2)
        self.assertIn("Laranja âmbar", content2)
        self.assertIn("### Atualização", content2)

    def test_list_domain_knowledge(self):
        notes = self.store.list_domain_knowledge("game_design")
        self.assertIsInstance(notes, dict)
        self.assertTrue(any("filosofia_jogos.md" in k for k in notes.keys()))

    def test_tools_improve_and_get_knowledge(self):
        res_improve = improve_knowledge(
            domain="musica",
            topic="escalas_favoritas",
            content="Escala Menor Harmônica e Dórica para atmosferas dark.",
            mode="overwrite",
            store=self.store,
        )
        self.assertTrue(res_improve["success"])

        res_get = get_knowledge(domain="musica", store=self.store)
        self.assertTrue(res_get["success"])
        self.assertGreaterEqual(res_get["total_notes"], 2)
        self.assertTrue(any("escalas_favoritas.md" in k for k in res_get["notes"].keys()))

    def test_tools_registered_in_dispatcher(self):
        self.assertIn("improve_knowledge", TOOL_DISPATCHER)
        self.assertIn("get_knowledge", TOOL_DISPATCHER)
        dispatch_fn = TOOL_DISPATCHER["improve_knowledge"]
        res = dispatch_fn(domain="programacao", topic="test_rule", content="YAGNI estrito", store=self.store)
        self.assertTrue(res.get("success"))


if __name__ == "__main__":
    unittest.main()

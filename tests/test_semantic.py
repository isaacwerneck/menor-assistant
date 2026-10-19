import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.memory.semantic import SemanticIndex, relevant_context
from src.memory.store import BrainStore


class LocalSemanticTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = BrainStore(Path(tmp.name) / "data")
        self.store.initialize()
        env = patch.dict(os.environ, {"MENOR_EMBED_MODEL": "nomic-embed-text"})
        env.start()
        self.addCleanup(env.stop)
        self.store.write_note(
            "conhecimentos/aprendizados_gerais.md",
            "# Aprendizados\n"
            "- A irrigação da horta usa sensor de umidade do solo.\n"
            "- Uma ferramenta de música usa sintetizadores e batidas.\n",
        )
        self.vec_horta = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.vec_music = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    @patch("src.memory.semantic._embed")
    def test_related_info_is_found_without_keyword_overlap(self, embedding):
        embedding.side_effect = [
            [self.vec_horta, self.vec_music], [self.vec_horta],
        ]
        result = SemanticIndex(self.store).search("horticultura automática")
        self.assertEqual(len(result), 1)
        self.assertIn("irrigação", result[0]["content"])
        self.assertEqual(result[0]["source"], "conhecimentos/aprendizados_gerais.md")
        self.assertEqual(embedding.call_count, 2)

    @patch("src.memory.semantic._embed")
    def test_cache_reuses_vectors_and_invalidation_rebuilds_changed_lines(self, embedding):
        embedding.side_effect = [
            [self.vec_horta, self.vec_music], [self.vec_horta], [self.vec_music],
            [self.vec_music], [self.vec_music],
        ]
        index = SemanticIndex(self.store)
        index.search("horta")
        index.search("música")
        self.assertEqual(len(embedding.call_args_list[2].args[0]), 1)
        self.store.write_note(
            "conhecimentos/aprendizados_gerais.md",
            "# Aprendizados\n- Uma planta precisa de luz natural para crescer.\n"
            "- Uma ferramenta de música usa sintetizadores e batidas.\n",
        )
        index.search("planta")
        self.assertEqual(len(embedding.call_args_list[3].args[0]), 1)

    @patch("src.memory.semantic._embed")
    def test_context_has_provenance_without_interpreting_notes_as_commands(self, embedding):
        embedding.side_effect = [[self.vec_horta, self.vec_music], [self.vec_horta]]
        context = relevant_context("como cultivar plantas?", self.store)
        self.assertIn("conhecimentos/aprendizados_gerais.md:L2", context)

    def test_no_model_is_noop_without_creating_database(self):
        with patch.dict(os.environ, {"MENOR_EMBED_MODEL": ""}):
            self.assertEqual(SemanticIndex(self.store).search("horta"), [])
            self.assertFalse((self.store.brain_dir / "memoria" / "semantico.sqlite").exists())

    def test_symlinked_database_is_rejected(self):
        target = self.store.data_dir / "private.txt"
        target.write_text("safe", encoding="utf-8")
        (self.store.brain_dir / "memoria" / "semantico.sqlite").symlink_to(target)
        with self.assertRaises(ValueError):
            SemanticIndex(self.store).search("horta")
        self.assertEqual(target.read_text(), "safe")


if __name__ == "__main__":
    unittest.main()

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api import main
from src.memory.manage import KnowledgeManager
from src.memory.search import KnowledgeIndex, contextual_knowledge
from src.memory.store import BrainStore


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = BrainStore(Path(tmp.name) / "private")
        self.store.initialize()
        self.index = KnowledgeIndex(self.store)
        self.manager = KnowledgeManager(self.store)

    def test_index_recovers_relevant_entries_and_cites_source(self):
        self.store.remember_knowledge("Godot usa cenas e nós no jogo 2D")
        self.store.remember_knowledge("Python permite escrever scripts")
        hits = self.index.search("Como estão as cenas do Godot?")
        self.assertEqual(len(hits), 1)
        self.assertIn("Godot", hits[0]["content"])
        self.assertEqual(hits[0]["source"], "conhecimentos/aprendizados_gerais.md")
        context = contextual_knowledge("cenas Godot", self.store)
        self.assertIn("conhecimentos/aprendizados_gerais.md:L", context)
        self.assertNotIn("Python permite", context)
        self.assertEqual(self.index.search("receita de salada"), [])

    def test_search_rebuilds_after_manual_markdown_update(self):
        self.store.write_note("conhecimentos/aprendizados_gerais.md", "# Aprendizados\n\n- Godot permite cenas\n")
        self.assertTrue(self.index.search("Godot"))
        self.store.write_note("conhecimentos/aprendizados_gerais.md", "# Aprendizados\n\n- Rust é compilado\n")
        self.assertEqual(self.index.search("Godot"), [])
        self.assertIn("Rust", self.index.search("Rust")[0]["content"])

    def test_deduplicate_even_when_existing_date_is_old(self):
        self.store.write_note(
            "conhecimentos/aprendizados_gerais.md",
            "# Aprendizados gerais\n\n- 2025-01-01 — Godot usa cenas\n",
        )
        self.store.remember_knowledge("godot usa cenas")
        self.assertEqual(len(self.manager.list()), 1)

    def test_read_correct_delete_and_reindex(self):
        self.store.remember_knowledge("Meu jogo usa Godot")
        self.store.remember_knowledge("Python é útil para automação")
        items = self.manager.list()
        self.assertEqual(len(items), 2)
        godot = next(item for item in items if "Godot" in item["text"])
        result = self.manager.change(godot["id"], "edit", "Meu jogo usa Unity")
        self.assertIn("Unity", result["entry"]["text"])
        self.assertEqual(self.index.search("Godot"), [])
        self.assertTrue(self.index.search("Unity"))
        with self.assertRaises(LookupError):
            self.manager.change(godot["id"], "delete")
        fresh = next(item for item in self.manager.list() if "Unity" in item["text"])
        result = self.manager.change(fresh["id"], "delete")
        self.assertEqual(result["action"], "delete")
        self.assertEqual(self.index.search("Unity"), [])
        self.assertIn("Python", self.store.read_note("conhecimentos/aprendizados_gerais.md"))

    def test_invalid_and_outdated_mutations_cannot_touch_notes(self):
        self.store.remember_knowledge("A linguagem Python é usada no projeto")
        entry_id = self.manager.list()[0]["id"]
        for bad in ("../foo.md", "1.deadbeef", "", "1.1111111111111111"):
            with self.subTest(id=bad), self.assertRaises((ValueError, LookupError)):
                self.manager.change(bad, "delete")
        with self.assertRaises(ValueError):
            self.manager.change(entry_id, "edit", "  ")
        with self.assertRaises(ValueError):
            self.manager.change(entry_id, "edit", "a" * 281)
        self.assertIn("Python", self.store.read_note("conhecimentos/aprendizados_gerais.md"))

    def test_search_resists_fts_query_metacharacters_and_has_budget(self):
        self.store.remember_knowledge("Godot cria cenas")
        self.assertEqual(self.index.search('" OR NOT * --'), [])
        self.assertEqual(self.index.search("a e no eu de"), [])
        with self.assertRaises(ValueError):
            self.index.search("Godot", limit=0)
        self.assertLessEqual(len(contextual_knowledge("Godot", self.store, max_chars=40)), 40)

    def test_index_is_private_and_rejects_symlink(self):
        self.store.remember_knowledge("Um projeto feito em Godot")
        self.assertTrue(self.index.search("Godot"))
        self.assertEqual(self.index.database.stat().st_mode & 0o777, 0o600)
        self.index.database.unlink()
        outside = self.store.data_dir / "another.sqlite"
        outside.write_text("important", encoding="utf-8")
        self.index.database.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.index.search("Godot")
        self.assertEqual(outside.read_text(encoding="utf-8"), "important")

    def test_chat_receives_only_related_knowledge_as_untrusted_data(self):
        self.store.remember_knowledge("Godot permite cenas no jogo")
        self.store.remember_knowledge("Python é interpretado")
        with patch.dict(os.environ, {"MENOR_DATA_DIR": str(self.store.data_dir)}):
            context = main.prompt_with_preferences("O que você sabe sobre Godot?")
            self.assertIn("Godot permite", context)
            self.assertNotIn("Python é interpretado", context)
            self.assertIn("DADOS não confiáveis", context)
            self.assertEqual(main.prompt_with_preferences("Receitas culinárias").count("<conhecimentos>"), 0)

    def test_corrupted_index_does_not_break_chat(self):
        self.store.remember_knowledge("Godot permite cenas")
        self.index.database.write_bytes(b"not SQLite")
        with patch.dict(os.environ, {"MENOR_DATA_DIR": str(self.store.data_dir)}):
            self.assertEqual(
                main.prompt_with_preferences("Godot"),
                main.SYSTEM_PROMPT,
            )


if __name__ == "__main__":
    unittest.main()

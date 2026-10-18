import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api import main
from src.memory.store import BrainStore, MAX_NOTE_BYTES


class BrainStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / "menor-data"
        self.store = BrainStore(self.base)

    def test_initialize_creates_private_structure_and_survives_restart(self):
        path = self.store.initialize()
        self.assertEqual(path, self.base / "cerebro")
        self.assertTrue((path / "projetos/exemplo-de-projeto/decisoes.md").is_file())
        self.assertEqual(self.base.stat().st_mode & 0o777, 0o700)
        self.assertEqual((path / "identidade/preferencias.md").stat().st_mode & 0o777, 0o600)
        self.store.write_note("identidade/preferencias.md", "# Preferências\n\n- Respostas diretas\n")
        second = BrainStore(self.base)
        second.initialize()
        self.assertIn("Respostas diretas", second.read_note("identidade/preferencias.md"))

    def test_atomic_write_and_read_of_markdown(self):
        self.store.initialize()
        self.store.write_note("conhecimentos/programacao/python.md", "# Python\n\nUma nota.\n")
        self.assertEqual(self.store.read_note("conhecimentos/programacao/python.md"), "# Python\n\nUma nota.\n")
        self.assertEqual(
            (self.base / "cerebro/conhecimentos/programacao/python.md").stat().st_mode & 0o777, 0o600,
        )
        self.assertEqual(self.store.read_note("conhecimentos/programacao/nao-existe.md"), "")

    def test_reject_traversal_absolute_paths_and_non_markdown(self):
        self.store.initialize()
        for path in ("../fora.md", "/tmp/fora.md", "identidade/../../fora.md",
                     r"identidade\..\fora.md", "identidade//nota.md", "fora.txt", "./nota.md"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.store.write_note(path, "não escrever")

    def test_reject_symlink_directory_and_file(self):
        self.store.initialize()
        outside = Path(self.temp.name) / "fora"
        outside.mkdir()
        (self.base / "cerebro/conhecimentos/invasor").symlink_to(outside, target_is_directory=True)
        (self.base / "cerebro/identidade/link.md").symlink_to(outside / "pwn.md")
        with self.assertRaises(ValueError):
            self.store.write_note("conhecimentos/invasor/pwn.md", "segredo")
        with self.assertRaises(ValueError):
            self.store.write_note("identidade/link.md", "segredo")
        with self.assertRaises(ValueError):
            self.store.read_note("identidade/link.md")
        self.assertFalse((outside / "pwn.md").exists())

    def test_reject_large_notes(self):
        self.store.initialize()
        with self.assertRaises(ValueError):
            self.store.write_note("identidade/grande.md", "a" * (MAX_NOTE_BYTES + 1))

    def test_explicit_preferences_are_persistent_and_deduplicated(self):
        self.store.remember_preference("  Responder   de forma objetiva  ")
        self.store.remember_preference("responder de forma objetiva")
        other = BrainStore(self.base)
        self.assertEqual(other.preference_context(), "- Responder de forma objetiva")
        self.assertEqual(other.read_note("identidade/preferencias.md").count("- "), 1)
        with self.assertRaises(ValueError):
            self.store.remember_preference("x" * 281)

    def test_empty_brain_does_not_add_context(self):
        self.assertEqual(self.store.preference_context(), "")
        with patch.dict(os.environ, {"MENOR_DATA_DIR": str(self.base)}):
            self.assertEqual(main.prompt_with_preferences(), main.SYSTEM_PROMPT)

    def test_chat_receives_preference_without_changing_user_message(self):
        self.store.remember_preference("Respostas curtas e objetivas")
        with patch.dict(os.environ, {"MENOR_DATA_DIR": str(self.base)}):
            with patch("src.api.main.requests.post") as post:
                post.return_value.status_code = 200
                main.open_ollama(main.ChatRequest(message="Olá"), stream=False)
                payload = post.call_args.kwargs["json"]
        self.assertIn("Respostas curtas e objetivas", payload["messages"][0]["content"])
        self.assertEqual(payload["messages"][-1], {"role": "user", "content": "Olá"})

    def test_unreadable_preferences_fail_open_for_chat(self):
        with patch("src.api.main.BrainStore") as store:
            store.return_value.preference_context.side_effect = ValueError("dados corrompidos")
            self.assertEqual(main.prompt_with_preferences(), main.SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()

"""E18: decisões atuais em workspace privado; sem autoedição nem shell."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.agent import runner
from src.memory.store import BrainStore
from src.projects.manager import create_project
from src.projects.workspace import ProjectWorkspace
from src.tools.registry import list_tools, perform


class CurrentProjectDecisions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {
            "MENOR_DATA_DIR": self.temp.name, "MENOR_AGENT_SCOPE": "personal",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.store = BrainStore(Path(self.temp.name))
        create_project("Aurora Notes", self.store)
        create_project("Jogo Plataformas", self.store)
        self.ws = ProjectWorkspace(self.store)

    def test_decision_create_update_and_recover_after_restart(self):
        first = self.ws.set_decision(
            "aurora-notes", "Armazenamento", "Arquivos locais e sem nuvem")
        self.assertEqual(first["change"], "created")
        revised = self.ws.set_decision(
            "aurora-notes", "armazenamento", "Arquivos locais, sem sincronização automática")
        self.assertEqual(revised["change"], "revised")
        text = ProjectWorkspace(self.store).read_project("aurora-notes")["notes"]["decision"]
        self.assertIn("sem sincronização automática", text)
        self.assertNotIn("sem nuvem", text)
        self.assertEqual(text.count("- armazenamento:"), 1)
        self.assertEqual(self.ws.set_decision(
            "aurora-notes", "armazenamento", "Arquivos locais, sem sincronização automática"
        )["change"], "unchanged")

    def test_context_includes_current_choice_in_small_budget(self):
        self.ws.set_decision("aurora-notes", "Dependência", "Biblioteca depende da agenda")
        context = self.ws.context("aurora-notes", max_chars=1050)
        self.assertIn("Biblioteca depende da agenda", context)
        self.assertIn("projetos/aurora-notes/decisoes.md", context)
        self.assertLessEqual(len(context), 1050)
        self.assertNotIn("Biblioteca depende", self.ws.context("jogo-plataformas"))

    def test_existing_legacy_notes_survive_update(self):
        self.ws.append("aurora-notes", "decision", "Escolha antiga apenas para histórico")
        self.ws.set_decision("aurora-notes", "Tecnologia", "HTML e CSS")
        notes = self.ws.read_project("aurora-notes")["notes"]["decision"]
        self.assertIn("Escolha antiga apenas para histórico", notes)
        self.assertIn("HTML e CSS", notes)

    def test_invalid_input_cannot_change_files(self):
        path = self.store.brain_dir / "projetos" / "aurora-notes" / "decisoes.md"
        before = path.read_bytes()
        bad = (
            ("t", "x"), ("Tecnologia", "x" * 281),
            ("Tecnologia\ninjetada", "Texto"), ("Tecnologia", "Texto\n- Outra: escolha"),
            ("[Tema]", "Texto"), ("Tema: X", "Texto"), ("<admin>", "Texto"),
        )
        for topic, value in bad:
            with self.subTest(topic=topic), self.assertRaises(ValueError):
                self.ws.set_decision("aurora-notes", topic, value)
            self.assertEqual(path.read_bytes(), before)
        for slug in ("../outside", "not-found", "jogo-plataformas/../aurora-notes"):
            with self.subTest(slug=slug), self.assertRaises((LookupError, ValueError)):
                self.ws.set_decision(slug, "Tecnologia", "Python")
        self.assertEqual(path.read_bytes(), before)

    def test_symlinked_decisions_file_blocks_writes(self):
        path = self.store.brain_dir / "projetos" / "aurora-notes" / "decisoes.md"
        path.unlink()
        target = self.store.brain_dir / "segredo.txt"
        target.write_text("original", encoding="utf-8")
        path.symlink_to(target)
        with self.assertRaises(LookupError):
            self.ws.set_decision("aurora-notes", "Tecnologia", "Python")
        self.assertEqual(target.read_text(), "original")

    def test_tool_contract_dry_run_has_no_side_effect(self):
        opts = {"slug": "aurora-notes", "topic": "Tecnologia", "value": "Python"}
        read_before = self.ws.read_project("aurora-notes")["notes"]["decision"]
        plan = perform("projects.set_decision", opts, dry_run=True)
        self.assertEqual(plan["status"], "planned")
        self.assertEqual(self.ws.read_project("aurora-notes")["notes"]["decision"], read_before)
        self.assertIn("projects.set_decision",
                      [x["name"] for x in list_tools("personal")])
        self.assertNotIn("developer.propose",
                         [x["name"] for x in list_tools("personal")])

    def test_explicit_approval_then_receipt(self):
        opts = {"slug": "aurora-notes", "topic": "Tecnologia", "value": "Python"}
        state, response = runner._selected_tool("projects.set_decision", opts)
        self.assertEqual(state["phase"], "approval")
        self.assertEqual(response["approval"]["title"], "Registrar decisão do projeto")
        self.assertNotIn("Python", self.ws.read_project("aurora-notes")["notes"]["decision"])
        after, confirmed = runner._advance(state, "sim", [])
        self.assertEqual(after["phase"], "idle")
        self.assertIn("Execução confirmada", confirmed["reply"])
        self.assertIn("Python", self.ws.read_project("aurora-notes")["notes"]["decision"])
        self.assertEqual(confirmed["events"][0]["tool"], "projects.set_decision")

    def test_rejected_approval_does_not_write(self):
        opts = {"slug": "aurora-notes", "topic": "Tecnologia", "value": "Python"}
        state, _ = runner._selected_tool("projects.set_decision", opts)
        result, _ = runner._advance(state, "não", [])
        self.assertEqual(result["phase"], "idle")
        self.assertNotIn("Python", self.ws.read_project("aurora-notes")["notes"]["decision"])

    def test_invalid_or_missing_project_blocks_preapproval(self):
        for slug in ("../etc", "missing-project"):
            with self.assertRaises((ValueError, LookupError)):
                runner._selected_tool(
                    "projects.set_decision",
                    {"slug": slug, "topic": "Tecnologia", "value": "Python"},
                )


if __name__ == "__main__":
    unittest.main()

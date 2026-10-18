import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agent.router import classify
from src.memory.store import BrainStore
from src.projects.manager import create_project
from src.projects.workspace import ProjectWorkspace


class ProjectWorkspaceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = BrainStore(Path(tmp.name) / "menor-data")
        self.manager = ProjectWorkspace(self.store)
        create_project("Cidade Noturna", self.store)
        create_project("Jogo de Corrida", self.store)

    def test_list_projects_only_valid_and_excludes_template(self):
        projects = self.manager.list_projects()
        self.assertEqual({p["slug"] for p in projects}, {"cidade-noturna", "jogo-de-corrida"})
        self.assertIn("Cidade Noturna", self.manager.read_project("cidade-noturna")["name"])

    def test_write_tasks_decisions_diary_and_recover_after_restart(self):
        self.manager.append("cidade-noturna", "decision", "Usar Godot e arte pixelada")
        self.manager.append("cidade-noturna", "task", "Criar menu principal")
        saved = self.manager.append("cidade-noturna", "log", "Primeira versão testável pronta")
        self.assertEqual(saved["path"], "projetos/cidade-noturna/diario.md")
        other = ProjectWorkspace(self.store)
        notes = other.read_project("cidade-noturna")["notes"]
        self.assertIn("Usar Godot", notes["decision"])
        self.assertIn("[ ] Criar menu principal", notes["task"])
        self.assertIn("Primeira versão", notes["log"])
        self.assertNotIn("Godot", other.context("jogo-de-corrida"))
        self.assertIn("Godot", other.context("cidade-noturna"))

    def test_never_create_or_overwrite_unselected_projects(self):
        for slug in ("../foo", "/tmp/foo", "exemplo-de-projeto", "projeto-que-nao-existe"):
            with self.subTest(slug=slug), self.assertRaises((ValueError, LookupError)):
                self.manager.append(slug, "task", "Não pode salvar")
        with self.assertRaises(ValueError):
            self.manager.append("cidade-noturna", "context", "Indevido")
        self.assertEqual(self.manager.read_project("cidade-noturna")["notes"]["task"].count("Não pode salvar"), 0)

    def test_context_budget_and_source(self):
        self.manager.append("cidade-noturna", "decision", "Motor de jogo Godot")
        context = self.manager.context("cidade-noturna", max_chars=2400)
        self.assertIn("projetos/cidade-noturna/decisoes.md", context)
        self.assertIn("Godot", context)
        self.assertLessEqual(len(context), 2400)
        self.assertEqual(
            self.manager.context("cidade-noturna", max_chars=10),
            "Projeto ativo: Cidade Noturna (projetos/cidade-noturna/)",
        )

    def test_reject_symlinked_project_root(self):
        other = self.store.brain_dir / "segredo"
        other.mkdir(mode=0o700)
        (self.store.brain_dir / "projetos/cidade-noturna").rename(
            self.store.brain_dir / "projetos/cidade-noturna-antigo"
        )
        (self.store.brain_dir / "projetos/cidade-noturna").symlink_to(other, target_is_directory=True)
        with self.assertRaises(LookupError):
            self.manager.read_project("cidade-noturna")

    @patch("src.agent.router.requests.post")
    def test_router_uses_active_project_for_a_clear_note(self, post):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"message": {"content": (
            '{"decision":"add_project_note","target":"project","note_kind":"decision",'
            '"text":"Usar Godot","confidence":0.99,"question":""}'
        )}}
        post.return_value = response
        routed = classify("A decisão é usar Godot", [], project="cidade-noturna")
        self.assertEqual(routed["decision"], "add_project_note")
        self.assertEqual(routed["note_kind"], "decision")
        sent = post.call_args.kwargs["json"]["messages"]
        self.assertIn("cidade-noturna", sent[1]["content"])

    @patch("src.agent.router.requests.post")
    def test_router_does_not_write_without_active_project(self, post):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"message": {"content": (
            '{"decision":"add_project_note","target":"project","note_kind":"task",'
            '"text":"Criar menu","confidence":0.99,"question":""}'
        )}}
        post.return_value = response
        self.assertEqual(classify("Temos que criar menu", [])["decision"], "chat")
        self.assertEqual(
            classify("Temos que criar menu", [], project="cidade-noturna")["decision"],
            "add_project_note",
        )

    @patch("src.agent.router.requests.post")
    def test_router_selects_existing_project_from_natural_message(self, post):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"message": {"content": (
            '{"decision":"select_project","target":"project","text":"Cidade Noturna",'
            '"confidence":0.99,"question":""}'
        )}}
        post.return_value = response
        result = classify("Vamos continuar no projeto Cidade Noturna", [])
        self.assertEqual(result["decision"], "select_project")
        self.assertEqual(result["text"], "Cidade Noturna")

    @patch("src.agent.router.requests.post")
    def test_router_rejects_hallucinated_notes(self, post):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"message": {"content": (
            '{"decision":"add_project_note","target":"project","note_kind":"task",'
            '"text":"Apagar tudo","confidence":0.99,"question":""}'
        )}}
        post.return_value = response
        self.assertEqual(classify("Vamos continuar amanhã", [], project="cidade-noturna")["decision"], "ask")


if __name__ == "__main__":
    unittest.main()

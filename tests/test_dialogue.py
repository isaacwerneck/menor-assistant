import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.agent.resolve import resolve
from src.memory.store import BrainStore
from src.projects.manager import create_project
from test_auth_memory import call


def model_response(result):
    response = MagicMock()
    response.__enter__.return_value = response
    response.json.return_value = {"message": {"content": json.dumps(result)}}
    return response


class NaturalDialogTests(unittest.TestCase):
    @patch("src.agent.resolve.requests.post")
    def test_natural_answer_to_memory_question_can_choose_tools(self, post):
        post.return_value = model_response({
            "decision": "save", "target": "tool", "note_kind": "none",
            "confidence": 0.99, "question": "",
        })
        result = resolve("Ferramenta de sprites", "Sim, guarda isso nas ferramentas",
                         suggested_target="none", question="Onde quer guardar?")
        self.assertEqual(result["decision"], "save")
        self.assertEqual(result["target"], "tool")
        self.assertIn("Ferramenta de sprites", post.call_args.kwargs["json"]["messages"][-1]["content"])

    @patch("src.agent.resolve.requests.post")
    def test_ambiguous_reply_asks_again_without_writing(self, post):
        post.return_value = model_response({
            "decision": "save", "target": "knowledge", "note_kind": "none",
            "confidence": 0.5, "question": "",
        })
        result = resolve("Ideia de jogo", "Talvez")
        self.assertEqual(result["decision"], "ask")

    @patch("src.agent.resolve.requests.post")
    def test_negative_reply_cancels(self, post):
        post.return_value = model_response({
            "decision": "cancel", "target": "none", "note_kind": "none",
            "confidence": 0.99, "question": "",
        })
        self.assertEqual(resolve("Uma ideia", "Não precisa")["decision"], "cancel")

    @patch("src.agent.resolve.requests.post")
    def test_invalid_model_answer_never_saves(self, post):
        post.return_value.__enter__.return_value.json.return_value = {"message": {"content": "not-json"}}
        self.assertEqual(resolve("Uma ideia", "Sim")["decision"], "ask")
        post.side_effect = __import__("requests").Timeout("offline")
        self.assertEqual(resolve("Uma ideia", "Sim")["decision"], "ask")

    @patch("src.agent.resolve.requests.post")
    def test_project_note_requires_selected_project(self, post):
        post.return_value = model_response({
            "decision": "save", "target": "project", "note_kind": "decision",
            "confidence": 0.99, "question": "",
        })
        self.assertEqual(resolve("Usar Godot", "Salva como decisão no projeto")["decision"], "ask")
        result = resolve("Usar Godot", "Salva como decisão no projeto", project="cidade-noturna")
        self.assertEqual(result["decision"], "save")
        self.assertEqual(result["note_kind"], "decision")


class NaturalDialogEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        from src.security import auth
        auth._attempts.clear()
        code, _, headers = call("/auth/setup", {"password": "senha-super-segura-123"})
        self.assertEqual(code, 200)
        self.cookie = headers[b"set-cookie"].decode().split(";", 1)[0]

    @patch("src.api.main.resolve")
    def test_authenticated_confirmation_saves_markdown_without_modal(self, resolved):
        resolved.return_value = {
            "decision": "save", "target": "knowledge", "note_kind": "none", "question": "",
        }
        body = {
            "message": "Sim, nos conhecimentos",
            "original": "O jogo usa Godot",
            "question": "Onde registro essa ideia?",
            "suggested_target": "none",
        }
        self.assertEqual(call("/agent/resolve", body)[0], 401)
        code, result, _ = call("/agent/resolve", body, cookie=self.cookie)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["memory"]["path"], "conhecimentos/aprendizados_gerais.md")
        self.assertIn("O jogo usa Godot", BrainStore().read_note("conhecimentos/aprendizados_gerais.md"))

    @patch("src.api.main.resolve")
    def test_answer_can_add_note_to_existing_project_only(self, resolved):
        resolved.return_value = {
            "decision": "save", "target": "project", "note_kind": "task", "question": "",
        }
        create_project("Cidade Noturna")
        body = {
            "message": "Anota como tarefa no projeto",
            "original": "Criar menu inicial",
            "suggested_target": "project",
            "project": "cidade-noturna",
        }
        code, result, _ = call("/agent/resolve", body, cookie=self.cookie)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["project_note"]["path"], "projetos/cidade-noturna/tarefas.md")
        self.assertIn("[ ] Criar menu inicial", BrainStore().read_note(result["project_note"]["path"]))
        body["project"] = "desconhecido"
        code, result, _ = call("/agent/resolve", body, cookie=self.cookie)
        self.assertEqual(code, 200)
        self.assertEqual(result["decision"], "ask")

    @patch("src.api.main.resolve")
    def test_cancel_does_not_write(self, resolved):
        resolved.return_value = {"decision": "cancel", "target": "none", "question": ""}
        body = {"message": "Não, deixa", "original": "Uma ideia de sprites"}
        self.assertEqual(call("/agent/resolve", body, cookie=self.cookie)[1]["decision"], "cancel")
        self.assertEqual(BrainStore().read_note("ferramentas/ideias.md"), "")


if __name__ == "__main__":
    unittest.main()

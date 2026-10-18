import os
import tempfile
import unittest
from unittest.mock import patch

from src.agent.short_replies import simple_answer
from src.agent.resolve import resolve
from src.memory.store import BrainStore
from test_auth_memory import call


class ScreenshotRegressions(unittest.TestCase):
    def test_answer_ferramentas_is_direct_and_does_not_call_model(self):
        with patch("src.agent.resolve.requests.post") as post:
            result = resolve(
                "Criar uma ferramenta nova de imagens",
                "ferramentas",
                suggested_target="tool",
                question="Quer que eu anote essa ideia? Em qual pasta?",
            )
            self.assertEqual(result["decision"], "save")
            self.assertEqual(result["target"], "tool")
            post.assert_not_called()

    def test_variants_sim_are_understood_without_llm(self):
        with patch("src.agent.resolve.requests.post") as post:
            for answer in ("sim", "simm", "simmm", "ss", "isso", "claro"):
                result = resolve(
                    "Meu jogo tem design pixelado", answer,
                    suggested_target="none", question="Você tem certeza disso?",
                )
                self.assertEqual(result["decision"], "ask")
                self.assertIn("pasta", result["question"])
            post.assert_not_called()

    def test_sim_with_unambiguous_category_saves(self):
        result = simple_answer("simm", suggested_target="preference",
                               question="Quer que eu salve como preferência?")
        self.assertEqual(result["decision"], "save")
        self.assertEqual(result["target"], "preference")

    def test_negative_answers_do_not_write(self):
        for word in ("não", "nao", "nao precisa", "nn", "deixa", "cancela"):
            self.assertEqual(resolve("uma ideia", word)["decision"], "cancel")

    def test_unknown_reply_uses_model_when_necessary(self):
        self.assertIsNone(simple_answer("acho que isso pode mudar o projeto amanhã"))

    def test_no_guessing_project_when_question_is_vague(self):
        response = resolve(
            "Uma ferramenta de imagem", "sim",
            suggested_target="tool", question="Você tem certeza disso?",
        )
        self.assertEqual(response["decision"], "ask")

    def test_portuguese_normalization(self):
        self.assertEqual(simple_answer("PREFERÊNCIAS", "none")["target"], "preference")
        self.assertEqual(simple_answer("Anota em ferramentas, por favor")["target"], "tool")


class ScreenshotEndpointTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = temp.name
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": self.data})
        env.start()
        self.addCleanup(env.stop)
        from src.security import auth
        auth._attempts.clear()
        code, _, headers = call("/auth/setup", {"password": "senha-de-teste-bem-longa"})
        self.assertEqual(code, 200)
        self.cookie = headers[b"set-cookie"].decode().split(";", 1)[0]

    @patch("src.agent.resolve.requests.post")
    def test_one_word_follow_up_works_even_when_ollama_is_offline(self, post):
        body = {
            "message": "ferramentas",
            "original": "Uma ferramenta nova de criar imagens",
            "question": "Quer anotar essa ideia? Em qual pasta?",
            "suggested_target": "tool",
        }
        code, result, _ = call("/agent/resolve", body, cookie=self.cookie)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["decision"], "save")
        self.assertEqual(result["memory"]["path"], "ferramentas/ideias.md")
        self.assertIn("criar imagens", BrainStore().read_note("ferramentas/ideias.md"))
        post.assert_not_called()

    @patch("src.agent.resolve.requests.post")
    def test_simmm_reply_asks_where_without_server_error(self, post):
        body = {
            "message": "simm",
            "original": "Uma ferramenta nova de criar imagens",
            "question": "Você tem certeza disso?",
            "suggested_target": "tool",
        }
        code, result, _ = call("/agent/resolve", body, cookie=self.cookie)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["decision"], "ask")
        self.assertEqual(BrainStore().read_note("ferramentas/ideias.md"), "")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

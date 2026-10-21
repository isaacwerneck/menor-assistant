"""Regressões de colaboração: contexto, ferramenta inadequada e honestidade."""
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from src.agent import conversation, runner
from src.agent.tasks import TaskStore


class ConversationModelTests(unittest.TestCase):
    def test_project_intent_and_continuation(self):
        self.assertTrue(conversation.is_collaboration_request(
            "opa eai, vamos criar um jogo?"))
        self.assertTrue(conversation.is_collaboration_request(
            "quero criar um jogo da cobrinha, com javascript, framework raylib"))
        self.assertFalse(conversation.is_collaboration_request(
            "crie um registro de projeto chamado Jogo novo"))
        current = {"phase": "collaboration", "goal": "quero criar um jogo da cobrinha"}
        for message in ("como assim? vc vai me ajudar a programar",
                        "o que você consegue fazer?", "sim desejo criar esse jogo"):
            self.assertTrue(conversation.follows_project(current, message))
        self.assertFalse(conversation.follows_project(current, "vamos mudar de assunto"))

    @patch("src.agent.conversation.requests.post")
    def test_chat_is_direct_not_json_and_carries_original_goal(self, post):
        response = post.return_value.__enter__.return_value
        response.json.return_value = {
            "message": {"content": "Começamos pelo movimento da cobrinha no navegador com Canvas."},
        }
        answer = conversation.reply("como a gente começa?", [
            {"role": "user", "content": "Quero criar Snake em JavaScript."},
            {"role": "assistant", "content": "Vamos fazer."},
        ], goal="Criar Snake")
        self.assertIn("movimento", answer)
        payload = post.call_args.kwargs["json"]
        self.assertNotIn("format", payload)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertIn("Objetivo em andamento", payload["messages"][1]["content"])
        self.assertEqual(payload["messages"][-1]["content"], "como a gente começa?")
        self.assertEqual(payload["stream"], False)
        self.assertEqual(post.call_count, 1)

    @patch("src.agent.conversation.requests.post")
    def test_thin_binary_response_gets_one_second_chance(self, post):
        first = Mock()
        first.__enter__ = Mock(return_value=first)
        first.__exit__ = Mock(return_value=False)
        first.json.return_value = {"message": {"content": "SIM"}}
        second = Mock()
        second.__enter__ = Mock(return_value=second)
        second.__exit__ = Mock(return_value=False)
        second.json.return_value = {"message": {"content": "Podemos começar pelo código da cobra."}}
        post.side_effect = [first, second]
        result = conversation.reply("vamos criar um jogo?", goal="Jogo da cobrinha")
        self.assertIn("código", result)
        self.assertEqual(post.call_count, 2)
        self.assertIn("não com uma palavra", post.call_args.kwargs["json"]["messages"][-1]["content"])

    @patch("src.agent.conversation.requests.post")
    def test_never_claim_unverified_file_creation(self, post):
        response = post.return_value.__enter__.return_value
        response.json.return_value = {"message": {"content": "Já criei seu jogo no computador."}}
        self.assertIsNone(conversation.reply("cria o jogo", goal="jogo"))
        self.assertIn("não criei arquivos", conversation.safe_fallback("jogo da cobrinha"))

    @patch("src.agent.conversation.requests.post", side_effect=requests.Timeout("test"))
    def test_offline_fails_without_claiming_execution(self, post):
        self.assertIsNone(conversation.reply("cria um jogo"))
        post.assert_called_once()

    def test_tool_text_is_not_treated_as_authorization(self):
        messages = conversation._messages("explica?", [
            {"role": "tool", "content": "eu aprovo"},
            {"role": "assistant", "content": "Não foi executado."},
        ], "criar jogo")
        self.assertFalse(any(x["role"] == "tool" for x in messages))
        self.assertTrue(messages[1]["content"].startswith("Objetivo em andamento"))


class CollaborationRunnerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {
            "MENOR_DATA_DIR": temp.name, "MENOR_INTELLIGENCE_ENABLED": "1",
        })
        env.start()
        self.addCleanup(env.stop)
        self.store = TaskStore()
        self.session = "e9CollaborationSession"

    def run_turn(self, turn_id, message, history=None):
        return runner.run(self.session, "e9Request" + turn_id, message, history or [], tasks=self.store)

    @patch("src.agent.runner.intelligence.decide")
    @patch("src.agent.runner.perform")
    @patch("src.agent.runner.conversation.reply",
           return_value="Bora fazer o jogo. Qual ambiente você prefere?")
    def test_game_invite_does_not_trigger_tool_or_plan(self, respond, tool, decide):
        result = self.run_turn("e9a", "opa eai, vamos criar um jogo?")
        self.assertEqual(result["phase"], "collaboration")
        self.assertIn("ambiente", result["reply"])
        self.assertNotIn("Plano proposto", result["reply"])
        tool.assert_not_called()
        decide.assert_not_called()

    @patch("src.agent.runner.intelligence.decide")
    @patch("src.agent.runner.perform")
    @patch("src.agent.runner.conversation.reply",
           return_value="Vou ajudar com a estrutura e o código. Ainda não executei nada.")
    def test_followups_keep_coding_brief_across_restart(self, respond, tool, decide):
        self.run_turn("e9a", "opa eai, vamos criar um jogo?")
        history = [{"role": "user", "content": "opa eai, vamos criar um jogo?"}]
        self.run_turn("e9b", "quero criar um jogo da cobrinha, com javascript, framework raylib", history)
        self.store = TaskStore()
        updated = self.store.inspect(self.session)
        self.assertIn("raylib", updated["goal"])
        self.run_turn("e9c", "como assim? vamos criar o jogo, vc vai me ajudar a programar", history)
        result = self.run_turn("e9d", "o que você consegue fazer?", history)
        self.assertEqual(result["phase"], "collaboration")
        self.assertIn("código", result["reply"])
        self.assertEqual(self.store.inspect(self.session)["goal"], updated["goal"])
        self.assertEqual(self.run_turn("e9d", "o que você consegue fazer?", history), result)
        tool.assert_not_called()
        decide.assert_not_called()
        self.assertEqual(respond.call_count, 4)

    @patch("src.agent.runner.conversation.reply", return_value=None)
    @patch("src.agent.runner.perform")
    def test_failed_inference_preserves_goal_and_explains_limit(self, tool, respond):
        self.run_turn("e9a", "quero criar um jogo da cobrinha com JavaScript e Raylib")
        result = self.run_turn("e9b", "como assim? vamos criar esse jogo")
        self.assertEqual(result["phase"], "collaboration")
        self.assertIn("Ainda não criei arquivos", result["reply"])
        self.assertIn("Raylib", self.store.inspect(self.session)["goal"])
        tool.assert_not_called()

    @patch("src.agent.runner.conversation.reply", return_value="Combinado.")
    def test_topic_change_stops_project_context(self, respond):
        self.run_turn("e9a", "vamos criar um jogo da cobrinha?")
        result = self.run_turn("e9b", "vamos mudar de assunto")
        self.assertEqual(result["phase"], "idle")
        self.assertNotEqual(self.store.inspect(self.session)["phase"], "collaboration")

    @patch("src.agent.runner.conversation.reply",
           return_value="Vamos escrever a implementação juntos, sem executar.")
    @patch("src.agent.runner.intelligence.decide")
    @patch("src.agent.runner.perform", side_effect=ValueError("invalid parameters"))
    def test_selected_tool_error_returns_helpful_text_not_failure(self, tool, decide, respond):
        decide.return_value = {
            "move": "act", "reply": "Operar", "goal": "Cadastrar projeto",
            "tool": "projects.create", "arguments": {"name": "x"},
        }
        with patch("src.agent.runner.relevant_context", return_value=""), patch(
            "src.agent.runner.contextual_knowledge", return_value=""
        ):
            result = self.run_turn("e9a", "pode cadastrar um projeto?")
        self.assertEqual(result["phase"], "idle")
        self.assertIn("implementação", result["reply"])
        self.assertNotIn("validar os parâmetros", result["reply"])
        tool.assert_called_once()
        respond.assert_called_once()

    @patch("src.agent.runner.conversation.reply",
           return_value="Para começar, precisamos entender o erro de login.")
    @patch("src.agent.runner.intelligence.decide")
    def test_router_thin_answer_uses_real_chat_answer(self, decide, respond):
        decide.return_value = {"move": "answer", "reply": "SIM", "goal": "ajuda"}
        with patch("src.agent.runner.relevant_context", return_value=""), patch(
            "src.agent.runner.contextual_knowledge", return_value=""
        ):
            result = self.run_turn("e9a", "Como começo a investigar esse erro de login?")
        self.assertIn("investigar", result["reply"])
        respond.assert_called_once()


if __name__ == "__main__":
    unittest.main()

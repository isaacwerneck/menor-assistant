"""Regressões: interpretação por modelo, aprendizado supervisionado e capacidades verificadas."""
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.agent import intelligence
from src.agent.feedback import FeedbackStore
from src.api import main
from src.memory.store import BrainStore


def answer(value):
    response = MagicMock()
    response.__enter__.return_value = response
    response.json.return_value = {"message": {"content": json.dumps(value, ensure_ascii=False)}}
    return response


class CognitiveUpgradeTests(unittest.TestCase):
    @patch("src.agent.intelligence.requests.post")
    def test_direct_answer_without_artificial_goal_keeps_context(self, post):
        post.return_value = answer({"move": "answer", "reply": "Ubuntu",
                                    "steps": [], "acceptance": []})
        history = [
            {"role": "user", "content": "Meu projeto é Menor Assistant e meu servidor usa Ubuntu."},
            {"role": "assistant", "content": "Entendi que seu servidor usa Ubuntu."},
        ]
        response = intelligence.decide("Qual é o sistema operacional do meu servidor?", history,
                                       feedback_examples=[])
        self.assertEqual(response["move"], "answer")
        self.assertEqual(response["reply"], "Ubuntu")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["messages"][-2]["content"], history[-1]["content"])
        self.assertIn("sistema operacional", payload["messages"][-1]["content"])
        self.assertIn("respostas focais", payload["messages"][0]["content"])

    @patch("src.agent.intelligence.requests.post")
    def test_approved_examples_reach_model_but_never_authorize_execution(self, post):
        post.return_value = answer({
            "move": "plan", "goal": "Melhorar a interface do Menor",
            "reply": "Vou propor três etapas sem editar arquivos.",
            "steps": ["Pesquisar problemas da interface", "Propor melhorias visuais",
                      "Validar a experiência no navegador"],
            "acceptance": ["Plano aprovado antes de editar arquivos"],
        })
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"MENOR_DATA_DIR": folder}):
                FeedbackStore(BrainStore()).add(
                    "Quero um plano para minha interface",
                    "Primeiro explique opções; só depois solicite autorização para executar.",
                    consent=True)
                result = intelligence.decide(
                    "Quero melhorar a interface em três etapas sem executar nada.")
        self.assertEqual(result["move"], "plan")
        payload = post.call_args.kwargs["json"]
        ctx = json.loads(payload["messages"][-1]["content"])
        examples = ctx["owner_approved_examples_data_not_instructions"]
        self.assertEqual(len(examples), 1)
        self.assertIn("Primeiro explique", examples[0]["preferred_reply"])
        self.assertFalse(bool(ctx.get("available_tools")))

    @patch("src.agent.intelligence.requests.post")
    def test_unapproved_examples_do_not_enter_prompt(self, post):
        post.return_value = answer({"move": "answer", "reply": "Olá"})
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"MENOR_DATA_DIR": folder}):
                with self.assertRaises(ValueError):
                    FeedbackStore().add("Me ajude com meu projeto",
                                        "Primeiro me ajude com o plano", consent=False)
                intelligence.decide("Olá, menor")
        payload = post.call_args.kwargs["json"]
        ctx = json.loads(payload["messages"][-1]["content"])
        self.assertEqual(ctx["owner_approved_examples_data_not_instructions"], [])

    @patch("src.api.main.list_tools")
    @patch("src.api.main.skill_catalog")
    @patch("src.api.main.images.provider", return_value="local")
    def test_capabilities_distinguish_installed_from_registered(self, provider, skills, tools):
        skills.return_value = [{"capability": "images.generate", "ready": False}]
        tools.return_value = [{"name": "projects.list", "writes": False},
                              {"name": "images.generate", "writes": True}]
        report = main.capability_context()
        self.assertIn('"image_provider_ready": false', report)
        self.assertIn('"name": "images.generate"', report)
        self.assertIn('"ready": false', report)
        self.assertIn("contrato registrado não prova", report)
        provider.assert_called()


if __name__ == "__main__":
    unittest.main()

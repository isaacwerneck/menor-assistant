import json
import unittest
from unittest.mock import MagicMock, patch

from requests import Timeout

from src.agent.planner import plan


class PlannerTests(unittest.TestCase):
    @patch("src.agent.planner.requests.post")
    def test_qwen_produces_bounded_plan_without_executing_actions(self, post):
        response = MagicMock()
        response.json.return_value = {"message": {"content": json.dumps({
            "steps": ["Selecionar modelo local compatível", "Validar imagem PNG produzida"],
            "acceptance": ["Gerar PNG sem chamada a outra API"],
            "limitations": ["CPU pode levar vários minutos"],
        })}}
        post.return_value = response
        result = plan("Criar imagens locais", "Gerar capas para meu jogo", "images.generate")
        self.assertEqual(result["planner"], "ollama-local")
        self.assertEqual(len(result["steps"]), 2)
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["options"]["temperature"], 0)
        self.assertEqual(sent["format"], "json")
        self.assertNotIn("tools", sent)

    @patch("src.agent.planner.requests.post")
    def test_invalid_json_or_hallucinated_long_plan_uses_safe_fallback(self, post):
        response = MagicMock()
        post.return_value = response
        response.json.return_value = {"message": {"content": "malformed"}}
        result = plan("Criar imagens locais", "Gerar capas para meu jogo", "images.generate")
        self.assertEqual(result["planner"], "fallback")
        response.json.return_value = {"message": {"content": json.dumps({
            "steps": ["fazer qualquer coisa"] * 99,
            "acceptance": ["critério verificável"],
            "limitations": ["Limitação razoável"],
        })}}
        self.assertEqual(
            plan("Criar imagens locais", "Gerar capas para meu jogo", "images.generate")["planner"],
            "fallback",
        )

    @patch("src.agent.planner.requests.post", side_effect=Timeout("Ollama lento"))
    def test_ollama_timeout_never_prevents_mission_planning(self, post):
        result = plan("Criar imagens locais", "Gerar capas para meu jogo", "images.generate")
        self.assertEqual(result["planner"], "fallback")
        self.assertTrue(result["acceptance"])
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()

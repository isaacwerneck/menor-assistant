"""Testes do Barramento de Subagentes Especializados (Fase 6)."""
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.agent.subagents import SpecializedSubagent, dispatch_specialized_subagent
from src.memory.store import BrainStore


class TestSubagentsV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = BrainStore(data_dir=self.temp_dir.name)
        self.store.initialize()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_subagent_prompts_and_context_injection(self):
        agent_design = SpecializedSubagent("design", store=self.store)
        prompt_design = agent_design.get_system_prompt()
        self.assertIn("Design e UI/UX", prompt_design)
        self.assertIn("estilo_visual.md", prompt_design)

        agent_music = SpecializedSubagent("musica", store=self.store)
        prompt_music = agent_music.get_system_prompt()
        self.assertIn("Teoria Musical", prompt_music)
        self.assertIn("producao_e_sintese.md", prompt_music)

        agent_game = SpecializedSubagent("game_design", store=self.store)
        prompt_game = agent_game.get_system_prompt()
        self.assertIn("Game Design", prompt_game)
        self.assertIn("filosofia_jogos.md", prompt_game)

    @patch("requests.post")
    def test_execute_with_ollama(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Use paleta #0f172a com contraste #38bdf8 e cantos de 8px."}
        }
        mock_post.return_value = mock_resp

        agent = SpecializedSubagent("design", store=self.store)
        res = agent.execute("Como devo estilizar o card principal?")
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "design")
        self.assertIn("paleta", res["answer"])

    def test_execute_fallback_when_offline(self):
        agent = SpecializedSubagent("musica", store=self.store, ollama_url="http://127.0.0.1:9")
        res = agent.execute("Qual progressão usar para uma trilha cyberpunk?")
        self.assertTrue(res["success"])
        self.assertTrue(res.get("fallback"))
        self.assertIn("Musica", res["answer"])

    def test_tool_dispatch_specialized_subagent(self):
        res = dispatch_specialized_subagent(
            domain="game_design",
            prompt="Explique como otimizar draw calls em UE5",
            store=self.store,
            ollama_url="http://127.0.0.1:9",
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "game_design")


if __name__ == "__main__":
    unittest.main()

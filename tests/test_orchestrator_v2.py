import unittest
from unittest.mock import patch, MagicMock

from src.agent.orchestrator import Orchestrator


class TestOrchestratorV2(unittest.TestCase):
    @patch("src.agent.orchestrator.requests.post")
    def test_run_turn_direct_reply(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "Olá! Como posso ajudar você hoje?",
            }
        }
        mock_post.return_value = mock_resp

        orchestrator = Orchestrator()
        result = orchestrator.run_turn(
            messages=[{"role": "user", "content": "Olá!"}],
            enable_tools=False,
        )

        self.assertTrue(result["success"])
        self.assertIn("Olá!", result["reply"])

    @patch("src.agent.orchestrator.requests.post")
    def test_run_turn_tool_dispatch(self, mock_post):
        # Primeiro turno: modelo solicita execução de ferramenta fs_write
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "fs_write",
                            "arguments": {"filepath": "teste_mock.txt", "content": "ok"},
                        }
                    }
                ],
            }
        }

        # Segundo turno: modelo recebe retorno e responde
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "Arquivo criado com sucesso!",
            }
        }

        mock_post.side_effect = [resp1, resp2]

        orchestrator = Orchestrator()
        result = orchestrator.run_turn(
            messages=[{"role": "user", "content": "Crie o arquivo teste_mock.txt"}],
            enable_tools=True,
        )

        self.assertTrue(result["success"])
        self.assertIn("Arquivo criado", result["reply"])
        self.assertEqual(len(result["tools_executed"]), 1)
        self.assertEqual(result["tools_executed"][0]["tool"], "fs_write")


if __name__ == "__main__":
    unittest.main()

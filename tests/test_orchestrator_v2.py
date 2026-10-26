from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

from src.agent.orchestrator import Orchestrator


class TestOrchestratorV2(unittest.TestCase):
    def tearDown(self):
        mock_file = Path("teste_mock.txt")
        if mock_file.exists():
            mock_file.unlink(missing_ok=True)

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

    @patch("src.agent.orchestrator.requests.post")
    def test_run_turn_tool_400_fallback(self, mock_post):
        import requests
        err_resp = MagicMock()
        err_resp.status_code = 400
        http_err = requests.HTTPError(response=err_resp)

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "Resposta obtida via fallback sem tools com sucesso!",
            }
        }
        mock_post.side_effect = [http_err, success_resp]

        orchestrator = Orchestrator()
        result = orchestrator.run_turn(
            messages=[{"role": "user", "content": "Execute um comando no terminal"}],
            enable_tools=True,
        )

        self.assertTrue(result["success"])
        self.assertIn("Resposta obtida via fallback", result["reply"])

    @patch("src.agent.orchestrator.requests.post")
    def test_run_turn_404_model_fallback(self, mock_post):
        import requests
        err_resp = MagicMock()
        err_resp.status_code = 404
        http_err = requests.HTTPError(response=err_resp)

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "Resposta obtida via fallback para modelo padrão!",
            }
        }
        mock_post.side_effect = [http_err, success_resp]

        orchestrator = Orchestrator(default_model="qwen2.5:14b")
        result = orchestrator.run_turn(
            messages=[{"role": "user", "content": "Olá menor"}],
            model="qwen3.5:4b",
        )

        self.assertTrue(result["success"])
        self.assertIn("Resposta obtida via fallback para modelo padrão", result["reply"])

    @patch("src.tools.core.fs_write")
    @patch("src.agent.orchestrator.requests.post")
    def test_run_turn_intercept_simulated_fs_write(self, mock_post, mock_fs_write):
        mock_fs_write.return_value = {"success": True, "filepath": "index.html"}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": (
                    "Tá, mano! Vamos programar esse site agora mesmo.\n\n"
                    "```python\n"
                    "fs_write(filepath='index.html', "
                    "content='<!DOCTYPE html>\\n<html><body><h1>Site</h1></body></html>')\n"
                    "```\n\n"
                    "Arquivo `index.html` criado com sucesso no diretório atual."
                ),
            }
        }
        mock_post.return_value = mock_resp

        orchestrator = Orchestrator()
        result = orchestrator.run_turn(
            messages=[{"role": "user", "content": "vamos fazer um site"}],
            enable_tools=True,
        )

        self.assertTrue(result["success"])
        mock_fs_write.assert_called_once()
        self.assertIn("fs_write:index.html", result["tools_executed"])
        self.assertNotIn("fs_write(filepath=", result["reply"])
        self.assertIn("```html", result["reply"])

    @patch("src.tools.core.terminal_run")
    @patch("src.agent.orchestrator.requests.post")
    def test_run_turn_intercept_simulated_terminal_run(self, mock_post, mock_term_run):
        mock_term_run.return_value = {"success": True, "exit_code": 0, "stdout": "On branch main\nNothing to commit", "stderr": ""}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": (
                    "Aqui está o comando:\n\n"
                    "```bash\n"
                    "git status && git log -n 1 --oneline\n"
                    "```\n"
                ),
            }
        }
        mock_post.return_value = mock_resp

        orchestrator = Orchestrator()
        result = orchestrator.run_turn(
            messages=[{"role": "user", "content": "Rode no terminal: git status e git log -n 1 --oneline"}],
            enable_tools=True,
        )

        self.assertTrue(result["success"])
        mock_term_run.assert_called_once()
        self.assertTrue(any("terminal_run:git status" in str(t) for t in result["tools_executed"]))
        self.assertIn("On branch main", result["reply"])

    @patch("src.tools.core.fs_write")
    @patch("src.agent.orchestrator.requests.post")
    def test_run_turn_auto_fs_write_from_user_quotes(self, mock_post, mock_fs_write):
        mock_fs_write.return_value = {"success": True, "filepath": "test_e2e_verify.txt"}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "Com certeza! Vou criar o arquivo para você agora mesmo.",
            }
        }
        mock_post.return_value = mock_resp

        orchestrator = Orchestrator()
        result = orchestrator.run_turn(
            messages=[{
                "role": "user",
                "content": "crie um arquivo no workspace chamado test_e2e_verify.txt com o conteudo 'Menor v2 funcionando 100%'",
            }],
            enable_tools=True,
        )

        self.assertTrue(result["success"])
        mock_fs_write.assert_called_once_with(filepath="test_e2e_verify.txt", content="Menor v2 funcionando 100%")
        self.assertIn("fs_write:test_e2e_verify.txt", result["tools_executed"])

    @patch("src.tools.core.fs_read")
    @patch("src.agent.orchestrator.requests.post")
    def test_run_turn_auto_fs_read(self, mock_post, mock_fs_read):
        mock_fs_read.return_value = {"success": True, "filepath": "test_e2e_verify.txt", "content": "Menor v2 funcionando 100%"}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "O usuário está pedindo para ler um arquivo.",
            }
        }
        mock_post.return_value = mock_resp

        orchestrator = Orchestrator()
        result = orchestrator.run_turn(
            messages=[{"role": "user", "content": "leia o arquivo test_e2e_verify.txt"}],
            enable_tools=True,
        )

        self.assertTrue(result["success"])
        mock_fs_read.assert_called_once_with(filepath="test_e2e_verify.txt")
        self.assertIn("fs_read:test_e2e_verify.txt", result["tools_executed"])
        self.assertIn("Menor v2 funcionando 100%", result["reply"])

    @patch("src.tools.core.fs_write")
    @patch("src.agent.orchestrator.requests.post")
    def test_run_turn_auto_fs_write_html_preview_clean_reply(self, mock_post, mock_fs_write):
        mock_fs_write.return_value = {"success": True, "filepath": "index.html"}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": (
                    "Aqui está o código do site:\n\n"
                    "```html\n"
                    "<!DOCTYPE html>\n<html><head><title>SonicWave</title></head><body><h1>Estúdio</h1></body></html>\n"
                    "```\n\n"
                    "Espero que goste!"
                ),
            }
        }
        mock_post.return_value = mock_resp

        orchestrator = Orchestrator()
        result = orchestrator.run_turn(
            messages=[{"role": "user", "content": "Crie o site do estúdio SonicWave com index.html"}],
            enable_tools=True,
        )

        self.assertTrue(result["success"])
        mock_fs_write.assert_called_once()
        self.assertIn("fs_write:index.html", result["tools_executed"])
        # Código cru deve ter sido removido da mensagem direta
        self.assertNotIn("<!DOCTYPE html>", result["reply"])
        # Deve conter link de preview e pasta
        self.assertIn("[Abrir Prévia do Site](/preview/index.html)", result["reply"])
        self.assertIn("index.html", result["reply"])
        self.assertIn("Quer que eu ajuste as cores", result["reply"])


if __name__ == "__main__":
    unittest.main()

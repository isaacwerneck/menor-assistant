import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.main import app
from src.memory.store import BrainStore


class TestApiV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["MENOR_DATA_DIR"] = cls.temp_dir.name
        BrainStore(data_dir=cls.temp_dir.name).initialize()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass
        os.environ.pop("MENOR_DATA_DIR", None)

    def test_health_check(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["service"], "Menor API")
        self.assertEqual(data["api_contract"], 1)

    def test_list_nodes(self):
        resp = self.client.get("/api/nodes")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("server", data)
        self.assertIn("local", data)

    def test_auth_workflow(self):
        # 1. Status inicial
        resp_status = self.client.get("/auth/status")
        self.assertEqual(resp_status.status_code, 200)

        # 2. Setup de senha
        resp_setup = self.client.post("/auth/setup", json={"password": "minhasenhadeproprietario123"})
        self.assertIn(resp_setup.status_code, (200, 409))

        # 3. Login
        resp_login = self.client.post("/auth/login", json={"password": "minhasenhadeproprietario123"})
        self.assertEqual(resp_login.status_code, 200)

    def test_auth_via_trycloudflare_tunnel(self):
        # Garante setup prévio
        self.client.post("/auth/setup", json={"password": "minhasenhadeproprietario123"})

        # Simula acesso mobile externo vindo de túnel Cloudflare HTTPS
        headers = {
            "Host": "swift-ocean-42.trycloudflare.com",
            "Origin": "https://swift-ocean-42.trycloudflare.com",
        }
        resp = self.client.post(
            "/auth/login",
            json={"password": "minhasenhadeproprietario123"},
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200)
        cookie = resp.cookies.get("menor_session")
        self.assertIsNotNone(cookie)

    def test_task_queue_endpoints(self):
        # Autenticar no client
        self.client.post("/auth/setup", json={"password": "minhasenhadeproprietario123"})
        login_resp = self.client.post("/auth/login", json={"password": "minhasenhadeproprietario123"})
        self.assertEqual(login_resp.status_code, 200)
        session_cookie = login_resp.cookies.get("menor_session")

        # Enfileirar tarefa
        resp_enqueue = self.client.post(
            "/api/tasks/enqueue",
            json={"goal": "Criar componente de header", "project_slug": "site-app", "auto_start": False},
            cookies={"menor_session": session_cookie} if session_cookie else {},
        )
        self.assertEqual(resp_enqueue.status_code, 200)
        data = resp_enqueue.json()
        self.assertIn("task_id", data)

        # Listar tarefas
        resp_list = self.client.get(
            "/api/tasks",
            cookies={"menor_session": session_cookie} if session_cookie else {},
        )
        self.assertEqual(resp_list.status_code, 200)
        tasks = resp_list.json().get("tasks", [])
        self.assertTrue(len(tasks) > 0)

        # Consultar tarefa específica
        resp_get = self.client.get(
            f"/api/tasks/{data['task_id']}",
            cookies={"menor_session": session_cookie} if session_cookie else {},
        )
        self.assertEqual(resp_get.status_code, 200)
        task_info = resp_get.json()
        self.assertEqual(task_info["id"], data["task_id"])
        self.assertIn("status", task_info)

    def test_memory_remember_and_search(self):
        self.client.post("/auth/setup", json={"password": "minhasenhadeproprietario123"})
        login_resp = self.client.post("/auth/login", json={"password": "minhasenhadeproprietario123"})
        self.assertEqual(login_resp.status_code, 200)
        session_cookie = login_resp.cookies.get("menor_session")
        cookies = {"menor_session": session_cookie} if session_cookie else {}

        # 1. Salvar preferência
        resp_remember = self.client.post(
            "/memory/remember",
            json={"text": "O Isaac prefere terminal bash ao zsh", "kind": "preference"},
            cookies=cookies,
        )
        self.assertEqual(resp_remember.status_code, 200)
        data_remember = resp_remember.json()
        self.assertTrue(data_remember.get("saved"))

        # 2. Buscar no índice
        resp_search = self.client.post(
            "/memory/search",
            json={"query": "terminal bash", "limit": 3},
            cookies=cookies,
        )
        self.assertEqual(resp_search.status_code, 200)
        data_search = resp_search.json()
        self.assertIn("items", data_search)

    @patch("src.api.main.Orchestrator.run_turn")
    def test_agent_run_local_node_fallback(self, mock_run_turn):
        self.client.post("/auth/setup", json={"password": "minhasenhadeproprietario123"})
        resp_login = self.client.post("/auth/login", json={"password": "minhasenhadeproprietario123"})
        cookies = {"menor_session": resp_login.cookies.get("menor_session")}

        mock_run_turn.return_value = {
            "success": True,
            "reply": "Resposta com modelo ativo do servidor",
            "tools_executed": [],
        }

        resp = self.client.post(
            "/agent/run",
            json={
                "message": "Olá",
                "node": "local",
                "model": "qwen3.5:4b",
                "ollama_url": "http://localhost:11434",
            },
            cookies=cookies,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("handled"))
        self.assertIn("servidor", data.get("reply"))

    def test_diagnose_error_endpoint(self):
        self.client.post("/auth/setup", json={"password": "minhasenhadeproprietario123"})
        resp_login = self.client.post("/auth/login", json={"password": "minhasenhadeproprietario123"})
        cookies = {"menor_session": resp_login.cookies.get("menor_session")}

        resp = self.client.post(
            "/api/agent/diagnose-error",
            json={
                "complaint": "Pô mano, essa porra tá errada, não criou o arquivo",
                "last_bot_reply": "Atualmente não posso criar arquivos.",
            },
            cookies=cookies,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertIn("diagnosis", data)
        self.assertIn("proposed_fix", data)

    def test_preview_file_endpoint(self):
        from src.tools.core import fs_write
        test_html_name = "test_preview_site_temp.html"
        test_content = "<html><body><h1>Parabens Rebelo</h1></body></html>"
        write_res = fs_write(test_html_name, test_content)
        self.assertTrue(write_res["success"])

        try:
            resp = self.client.get(f"/preview/{test_html_name}")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Parabens Rebelo", resp.text)

            # Test 404 for nonexistent file
            resp_404 = self.client.get("/preview/arquivo_que_nao_existe_123456.html")
            self.assertEqual(resp_404.status_code, 404)
        finally:
            from pathlib import Path
            test_file = Path(write_res["filepath"])
            if test_file.exists():
                test_file.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest

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
            json={"goal": "Criar componente de header", "project_slug": "site-app"},
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


if __name__ == "__main__":
    unittest.main()

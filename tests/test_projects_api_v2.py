"""Testes de unidade para o router de Projetos e Workspaces Scoped (Fase 4)."""
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.main import app
from src.memory.store import BrainStore


class TestProjectsApiV2(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self._orig_data_dir = os.environ.get("MENOR_DATA_DIR")
        os.environ["MENOR_DATA_DIR"] = self.temp_dir.name
        self.store = BrainStore(data_dir=self.temp_dir.name)
        self.store.initialize()
        self.client = TestClient(app)

    def tearDown(self):
        if self._orig_data_dir:
            os.environ["MENOR_DATA_DIR"] = self._orig_data_dir
        else:
            os.environ.pop("MENOR_DATA_DIR", None)
        self.temp_dir.cleanup()

    @patch("src.security.auth.require_owner")
    def test_projects_crud_workflow(self, mock_auth):
        mock_auth.return_value = True

        # 1. Criação de projeto
        create_res = self.client.post("/projects", json={
            "name": "App Gestão Mobile",
            "instructions": "Você é o especialista Android Studio em Kotlin.",
        })
        self.assertEqual(create_res.status_code, 200)
        proj_data = create_res.json()["project"]
        slug = proj_data["slug"]
        self.assertEqual(slug, "app-gestao-mobile")

        # 2. Listagem de projetos
        list_res = self.client.get("/projects")
        self.assertEqual(list_res.status_code, 200)
        items = list_res.json()["items"]
        slugs = [it["slug"] for it in items]
        self.assertIn(slug, slugs)

        # 3. Detalhes do projeto
        det_res = self.client.get(f"/projects/{slug}")
        self.assertEqual(det_res.status_code, 200)
        self.assertIn("Android Studio", det_res.json()["context"])

        # 4. Adicionar nota de decisão
        note_res = self.client.post(f"/projects/{slug}/note", json={
            "kind": "decision",
            "text": "Usaremos Jetpack Compose para a interface e Room para o banco local.",
        })
        self.assertEqual(note_res.status_code, 200)
        self.assertTrue(note_res.json()["success"])


if __name__ == "__main__":
    unittest.main()

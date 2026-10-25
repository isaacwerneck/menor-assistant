"""Testes de unidade para o Inspetor do Cérebro do Menor e Changelog (Fase 3)."""
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.main import app
from src.memory.store import BrainStore


class TestBrainWorkspaceV2(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self._orig_env = os.environ.get("MENOR_DATA_DIR")
        os.environ["MENOR_DATA_DIR"] = self.temp_dir.name
        self.store = BrainStore(data_dir=self.temp_dir.name)
        self.store.initialize()
        # Cria notas de exemplo sob cerebro/
        self.store.write_note("preferencias.md", "# Preferências\n- Tema escuro.")
        self.store.write_note("conhecimentos/backend/fastapi.md", "# FastAPI\n- Rápido e assíncrono.")
        self.client = TestClient(app)

    def tearDown(self):
        if self._orig_env is not None:
            os.environ["MENOR_DATA_DIR"] = self._orig_env
        else:
            os.environ.pop("MENOR_DATA_DIR", None)
        self.temp_dir.cleanup()

    @patch("src.security.auth.require_owner")
    def test_get_brain_view_page(self, mock_auth):
        mock_auth.return_value = True
        response = self.client.get("/brain/view")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Cérebro do Menor", response.text)
        self.assertIn("Modificações Recentes", response.text)

    @patch("src.security.auth.require_owner")
    def test_get_brain_tree(self, mock_auth):
        mock_auth.return_value = True
        response = self.client.get("/api/brain/tree")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("tree", data)
        self.assertIsInstance(data["tree"], list)

    @patch("src.security.auth.require_owner")
    def test_note_lifecycle_and_changelog(self, mock_auth):
        mock_auth.return_value = True

        # 1. Leitura de nota sob cerebro/
        read_res = self.client.get("/api/brain/note?path=cerebro/preferencias.md")
        self.assertEqual(read_res.status_code, 200)
        note_data = read_res.json()
        orig_hash = note_data.get("hash")
        self.assertIsNotNone(orig_hash)

        # 2. Gravação com hash esperado
        new_text = "# Preferências\n- Tema escuro atualizado."
        save_res = self.client.post("/api/brain/note", json={
            "path": "cerebro/preferencias.md",
            "content": new_text,
            "expected_hash": orig_hash,
        })
        self.assertEqual(save_res.status_code, 200)
        self.assertTrue(save_res.json()["success"])

        # 3. Consulta de Changelog
        ch_res = self.client.get("/api/brain/changelog")
        self.assertEqual(ch_res.status_code, 200)
        items = ch_res.json()["items"]
        self.assertGreater(len(items), 0)
        self.assertEqual(items[0]["path"], "cerebro/preferencias.md")

    @patch("src.security.auth.require_owner")
    def test_sync_playbooks_endpoint(self, mock_auth):
        mock_auth.return_value = True
        res = self.client.post("/api/brain/sync-playbooks")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertGreater(data["updated_count"], 0)
        self.assertTrue(any("android/arquitetura_mobile.md" in f for f in data["files"]))


if __name__ == "__main__":
    unittest.main()

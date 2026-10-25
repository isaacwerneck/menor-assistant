"""Testes de unidade para o Laboratório de Testes & Auto-Aprimoramento (Fase 1 e Fase 2)."""
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.main import app
from src.lab.eval_engine import DualTierVerifier, LabManager
from src.memory.store import BrainStore


class TestLabV2(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = BrainStore(data_dir=self.temp_dir.name)
        self.store.initialize()
        self.manager = LabManager.get_instance(store=self.store)
        self.client = TestClient(app)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("src.security.auth.require_owner")
    def test_get_lab_view_page(self, mock_auth):
        mock_auth.return_value = True
        response = self.client.get("/lab/view")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Laboratório", response.text)
        self.assertIn("Cockpit de Treino ao Vivo", response.text)

    @patch("src.security.auth.require_owner")
    def test_get_categories(self, mock_auth):
        mock_auth.return_value = True
        response = self.client.get("/api/lab/categories")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("web_preview", data["categories"])
        self.assertIn("architecture_mobile", data["categories"])

    @patch("src.security.auth.require_owner")
    def test_objectives_lifecycle(self, mock_auth):
        mock_auth.return_value = True
        # Ler objetivo inicial
        res1 = self.client.get("/api/lab/objectives")
        self.assertEqual(res1.status_code, 200)
        self.assertIn("Missão", res1.json()["content"])

        # Salvar novo objetivo
        new_obj = "# Novo Objetivo Customizado\n\n- Teste de aceitação rigoroso."
        res2 = self.client.post("/api/lab/objectives", json={"content": new_obj})
        self.assertEqual(res2.status_code, 200)

        # Verificar se persistiu
        res3 = self.client.get("/api/lab/objectives")
        self.assertEqual(res3.json()["content"], new_obj)

    def test_dual_tier_verifier_tier1_pass(self):
        probe = {
            "id": "test_preview",
            "category": "web_preview",
            "expected_preview": True,
            "must_not_contain": ["assistente de voz"],
        }
        valid_reply = (
            "Com certeza! Criei a landing page solicitada.\n\n"
            "Você pode ver a prévia em: [Prévia](/preview/index.html)\n\n"
            "```python\ndef run():\n    return 42\n```"
        )
        t1 = DualTierVerifier.verify_tier1(probe, valid_reply)
        self.assertTrue(t1["tier1_pass"])
        self.assertEqual(t1["tier1_score"], 50)

    def test_dual_tier_verifier_tier1_fail_on_refusal(self):
        probe = {
            "id": "test_refusal",
            "category": "guardrails",
            "must_not_contain": ["como assistente de voz"],
        }
        refusal_reply = "Desculpe, como assistente de voz não posso fazer isso."
        t1 = DualTierVerifier.verify_tier1(probe, refusal_reply)
        self.assertFalse(t1["tier1_pass"])
        self.assertLess(t1["tier1_score"], 50)

    def test_dual_tier_verifier_zero_on_communication_error(self):
        probe = {
            "id": "test_err",
            "category": "web_preview",
            "expected_preview": True,
        }
        err_reply = "Erro de comunicação com o modelo (qwen): 400 Client Error: Bad Request"
        t1 = DualTierVerifier.verify_tier1(probe, err_reply)
        self.assertFalse(t1["tier1_pass"])
        self.assertEqual(t1["tier1_score"], 0)

        t2 = DualTierVerifier.verify_tier2_qualitative(probe, err_reply, "objetivo")
        self.assertEqual(t2["tier2_score"], 0)
        self.assertIn("Nenhum aprendizado gerado", t2["learning"])

    @patch("src.security.auth.require_owner")
    @patch("src.agent.orchestrator.Orchestrator.run_turn")
    def test_battery_start_and_control(self, mock_run_turn, mock_auth):
        mock_auth.return_value = True
        mock_run_turn.return_value = {
            "reply": "Aqui está a solução com link /preview/app.html",
            "tools_executed": [],
            "model_used": "qwen2.5:14b",
        }

        # Dispara bateria com apenas 1 categoria para teste rápido
        run_res = self.client.post("/api/lab/run", json={
            "categories": ["guardrails"],
            "mode": "manual",
            "model": "qwen2.5:14b",
        })
        self.assertEqual(run_res.status_code, 200)

        # Consulta estado
        state_res = self.client.get("/api/lab/state")
        self.assertEqual(state_res.status_code, 200)
        state = state_res.json()
        self.assertIn(state["status"], ["running", "waiting_approval", "completed", "idle"])

        # Teste de controle de pausa e abort
        ctrl_res = self.client.post("/api/lab/control", json={"action": "pause"})
        self.assertEqual(ctrl_res.status_code, 200)

        abort_res = self.client.post("/api/lab/control", json={"action": "abort"})
        self.assertEqual(abort_res.status_code, 200)


if __name__ == "__main__":
    unittest.main()

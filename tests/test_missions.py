import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent.missions import MissionStore
from src.agent.mission_worker import run_once
from src.agent.model_catalog import discover
from src.memory.store import BrainStore
from test_auth_memory import call


class MissionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = BrainStore(Path(tmp.name) / "data")
        self.missions = MissionStore(self.store)

    def test_curated_model_discovery_does_not_install(self):
        result = discover("images.generate")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "openvino-sd15-int8")
        self.assertTrue(result[0]["approval_required"])
        self.assertEqual(discover("music"), [])

    def test_conversation_has_separate_requirements_and_approval(self):
        created = self.missions.begin("images.generate", "Quero uma ferramenta local de imagens")
        self.assertEqual(created["status"], "gathering")
        self.assertTrue(Path(self.missions._path(created["id"])).exists())
        self.assertEqual(self.missions.get(created["id"])["status"], "gathering")
        planned = self.missions.detail(created["id"], "Receber texto e criar imagens 512 por 512")
        self.assertEqual(planned["status"], "awaiting_approval")
        self.assertFalse(planned["approval"])
        self.assertEqual(planned["plan"]["preferred"], "openvino-sd15-int8")
        queued = self.missions.decide(created["id"], True)
        self.assertEqual(queued["status"], "queued")
        self.assertTrue(queued["approval"])
        with self.assertRaises(ValueError):
            self.missions.decide(created["id"], True)
        self.assertEqual(self.missions.list()[0]["id"], created["id"])

    def test_other_capability_never_uses_unknown_installer(self):
        started = self.missions.begin("music", "Quero uma ferramenta local de criar músicas")
        self.missions.detail(started["id"], "Quero música instrumental para um jogo")
        approved = self.missions.decide(started["id"], True)
        self.assertEqual(approved["status"], "blocked")

    def test_reject_fake_id_and_symlink(self):
        with self.assertRaises(ValueError):
            self.missions.get("../secrets")
        obj = self.missions.begin("images.generate", "Criar imagens locais em OpenVINO")
        path = self.missions._path(obj["id"])
        path.unlink()
        target = self.store.data_dir / "outside.txt"
        target.write_text("private")
        path.symlink_to(target)
        with self.assertRaises(LookupError):
            self.missions.get(obj["id"])
        self.assertEqual(target.read_text(), "private")

    @patch("src.agent.mission_worker.review_image")
    @patch("src.agent.mission_worker.local_images.generate")
    @patch("src.agent.mission_worker.local_images.install_approved")
    @patch("src.agent.mission_worker.local_images.ensure_runtime_approved")
    def test_approved_mission_runs_worker_then_smoke_test(self, ensure, install, generate, reviewer):
        reviewer.return_value = {"passed": True, "width": 512, "height": 512}
        install.return_value = {"ready": True}
        generate.return_value = {
            "status": "completed", "id": "a" * 32, "url": "/images/files/" + "a" * 32,
        }
        obj = self.missions.begin("images.generate", "Instalar modelo local de imagens")
        self.missions.detail(obj["id"], "Criar ilustrações de fantasia a partir de texto")
        self.missions.decide(obj["id"], True)
        result = run_once(self.missions)
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["result"]["verified"])
        saved = self.store.read_note("ferramentas/imagens/geracao_local.md")
        self.assertIn("Estado: testada", saved)
        self.assertIn(obj["id"], saved)
        ensure.assert_called_once()
        install.assert_called_once()
        generate.assert_called_once()
        reviewer.assert_called_once()
        self.assertEqual(run_once(self.missions)["status"], "idle")

    @patch("src.agent.mission_worker.local_images.ensure_runtime_approved")
    def test_install_failure_never_marks_capability_ready(self, ensure):
        from src.tools.local_images import LocalImageUnavailable
        ensure.side_effect = LocalImageUnavailable("sem runtime")
        obj = self.missions.begin("images.generate", "Instalar modelo local de imagens")
        self.missions.detail(obj["id"], "Gerar capas quadradas de álbuns localmente")
        self.missions.decide(obj["id"], True)
        result = run_once(self.missions)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["result"]["verified"])


class MissionEndpointTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": tmp.name})
        env.start()
        self.addCleanup(env.stop)
        from src.security import auth
        auth._attempts.clear()
        code, _, headers = call("/auth/setup", {"password": "senha-muito-longa-para-teste"})
        self.assertEqual(code, 200)
        self.cookie = headers[b"set-cookie"].decode().split(";", 1)[0]

    def test_create_clarify_approve_and_check_requires_session(self):
        self.assertEqual(call("/agent/missions")[0], 401)
        goal = {"goal": "Quero criar imagens sem depender de outras IAs",
                "capability": "images.generate"}
        self.assertEqual(call("/agent/missions", goal)[0], 401)
        status, mission, _ = call("/agent/missions", goal, cookie=self.cookie)
        self.assertEqual(status, 200, mission)
        url = "/agent/missions/" + mission["id"]
        self.assertEqual(call(url, cookie=self.cookie)[1]["status"], "gathering")
        status, planned, _ = call(url + "/requirements", {
            "requirements": "Quero criar imagens 512x512 a partir de texto",
        }, cookie=self.cookie)
        self.assertEqual(status, 200, planned)
        self.assertEqual(planned["status"], "awaiting_approval")
        status, accepted, _ = call(url + "/approve", {"approved": True}, cookie=self.cookie)
        self.assertEqual(status, 200, accepted)
        self.assertEqual(accepted["status"], "queued")
        self.assertEqual(call("/agent/missions", cookie=self.cookie)[1]["items"][0]["id"],
                         mission["id"])

    @patch("src.agent.planner.requests.post", side_effect=__import__("requests").Timeout("offline"))
    def test_question_endpoint_never_approves_and_requires_auth(self, post):
        goal = {"goal": "Criar ferramenta de pixel art", "capability": "images.generate"}
        mission = call("/agent/missions", goal, cookie=self.cookie)[1]
        url = "/agent/missions/" + mission["id"]
        call(url + "/requirements", {"requirements": "Receber texto e criar PNG."}, cookie=self.cookie)
        before = call(url, cookie=self.cookie)[1]
        question = {"message": "como assim cpu pode ser lenta?"}
        self.assertEqual(call(url + "/question", question)[0], 401)
        self.assertEqual(call(url + "/question", question, cookie=self.cookie,
                              origin="http://evil.invalid")[0], 403)
        code, result, _ = call(url + "/question", question, cookie=self.cookie)
        self.assertEqual(code, 200, result)
        self.assertIn("CPU", result["reply"])
        self.assertEqual(call(url, cookie=self.cookie)[1], before)
        post.side_effect = None
        post.return_value.__enter__.return_value.json.return_value = {
            "message": {"content": "O modelo transforma descrições em pixels."},
        }
        reply = call(url + "/question", {"message": "Explique o modelo"}, cookie=self.cookie)[1]["reply"]
        self.assertIn("O modelo transforma", reply)
        self.assertIn("A aprovação continua pendente", reply)
        call(url + "/question", {"message": "sim"}, cookie=self.cookie)
        self.assertEqual(call(url, cookie=self.cookie)[1], before)

    def test_mission_approval_origin_protection(self):
        goal = {"goal": "Fazer imagens locais para o meu jogo",
                "capability": "images.generate"}
        mission = call("/agent/missions", goal, cookie=self.cookie)[1]
        url = "/agent/missions/" + mission["id"]
        self.assertEqual(call(url + "/requirements", {
            "requirements": "Gerar figuras de um jogo",
        }, cookie=self.cookie, origin="http://evil.invalid")[0], 403)


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent.delegation import generate_image
from src.agent.missions import MissionStore
from src.agent.skills import capability_status, catalog, document_verified_skill
from src.memory.store import BrainStore
from src.tools.images import ImageUnavailable
from test_auth_memory import call


class SkillsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = BrainStore(Path(tmp.name) / "data")
        self.missions = MissionStore(self.store)

    def _verified_mission(self):
        mission = self.missions.begin("images.generate", "Criar arte localmente no chat")
        self.missions.detail(mission["id"], "Aceitar prompts e criar imagens PNG no CPU")
        self.missions.decide(mission["id"], True)
        self.missions.transition(mission["id"], "queued", "installing")
        result = {
            "worker": "openvino-sd15-int8", "verified": True,
            "test_image": "/images/files/" + "a" * 32,
        }
        self.missions.transition(mission["id"], "installing", "ready", result)
        return self.missions.get(mission["id"])

    @patch("src.agent.skills.local_images.status")
    def test_skills_do_not_claim_ready_just_because_a_mission_exists(self, status):
        status.return_value = {"ready": False}
        self._verified_mission()
        skill = capability_status("images.generate", self.missions)
        self.assertEqual(skill["status"], "needs_verification")
        self.assertFalse(skill["ready"])
        self.assertEqual(capability_status("music", self.missions)["status"], "missing")

    @patch("src.agent.skills.local_images.status")
    def test_capability_ready_requires_runtime_and_verified_mission(self, status):
        status.return_value = {"ready": True}
        self.assertFalse(capability_status("images.generate", self.missions)["ready"])
        mission = self._verified_mission()
        skill = capability_status("images.generate", self.missions)
        self.assertTrue(skill["ready"])
        self.assertEqual(skill["mission_id"], mission["id"])
        self.assertTrue(any(row["capability"] == "design" for row in catalog(self.missions)))

    def test_skill_manual_only_after_approved_verified_job(self):
        mission = self.missions.begin("images.generate", "Criar arte localmente no chat")
        with self.assertRaises(ValueError):
            document_verified_skill(mission, self.store)
        verified = self._verified_mission()
        location = document_verified_skill(verified, self.store)
        note = self.store.read_note(location)
        self.assertIn("Estado: testada", note)
        self.assertIn("OpenVINO", note)
        self.assertIn("Não há revisão estética", note)

    @patch("src.agent.delegation.review_image")
    @patch("src.agent.delegation.local_images.generate")
    @patch("src.agent.skills.local_images.status")
    @patch("src.agent.delegation.images.provider")
    def test_delegation_retries_then_only_accepts_reviewed_image(
        self, provider, runtime, generate, review,
    ):
        provider.return_value = "local"
        runtime.return_value = {"ready": True}
        self._verified_mission()
        generate.return_value = {
            "status": "completed", "id": "b" * 32,
            "url": "/images/files/" + "b" * 32,
        }
        review.side_effect = [
            {"passed": False, "reason": "Imagem pequena"},
            {"passed": True, "reason": "Arquivo válido", "width": 512, "height": 512},
        ]
        result = generate_image("Um gato no parque em dia ensolarado", self.missions)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(generate.call_count, 2)
        self.assertTrue(result["review"]["passed"])

    @patch("src.agent.delegation.local_images.generate")
    @patch("src.agent.skills.local_images.status")
    @patch("src.agent.delegation.images.provider")
    def test_absent_worker_never_invokes_model(self, provider, runtime, generate):
        provider.return_value = "local"
        runtime.return_value = {"ready": False}
        with self.assertRaises(ImageUnavailable):
            generate_image("Uma estrada à noite com néon azul", self.missions)
        generate.assert_not_called()

    @patch("src.agent.delegation.review_image")
    @patch("src.agent.delegation.local_images.generate")
    @patch("src.agent.skills.local_images.status")
    @patch("src.agent.delegation.images.provider")
    def test_two_bad_outputs_cannot_be_reported_as_completed(
        self, provider, runtime, generate, review,
    ):
        provider.return_value = "local"
        runtime.return_value = {"ready": True}
        self._verified_mission()
        generate.return_value = {"status": "completed", "id": "b" * 32}
        review.return_value = {"passed": False, "reason": "Formato inválido"}
        with self.assertRaises(ImageUnavailable):
            generate_image("Uma paisagem montanhosa cinematográfica", self.missions)
        self.assertEqual(generate.call_count, 2)


class SkillsEndpointTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": temp.name})
        env.start()
        self.addCleanup(env.stop)
        from src.security import auth
        auth._attempts.clear()
        code, _, headers = call("/auth/setup", {"password": "senha-muito-longa-para-teste"})
        self.assertEqual(code, 200)
        self.cookie = headers[b"set-cookie"].decode().split(";", 1)[0]

    def test_catalog_requires_authentication(self):
        self.assertEqual(call("/agent/skills")[0], 401)
        code, data, _ = call("/agent/skills", cookie=self.cookie)
        self.assertEqual(code, 200)
        images = next(x for x in data["items"] if x["capability"] == "images.generate")
        self.assertFalse(images["ready"])


if __name__ == "__main__":
    unittest.main()

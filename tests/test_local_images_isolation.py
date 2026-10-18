import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agent.missions import MissionStore
from src.memory.store import BrainStore
from src.tools import local_images


class LocalImageIsolationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = BrainStore(Path(tmp.name) / "data")

    def _model(self):
        folder = local_images.model_directory(self.store)
        for relative in local_images.REQUIRED_MODELS:
            file = folder / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(
                b'{"_class_name":"StableDiffusionPipeline"}'
                if relative == "model_index.json" else b"model"
            )
        return folder

    def test_missing_bin_or_empty_model_does_not_claim_installed(self):
        folder = self._model()
        self.assertTrue(local_images._model_ready(folder))
        (folder / "unet/openvino_model.bin").unlink()
        self.assertFalse(local_images._model_ready(folder))
        (folder / "unet/openvino_model.bin").write_bytes(b"")
        self.assertFalse(local_images._model_ready(folder))

    def test_symlink_to_external_model_is_rejected(self):
        target = self._model()
        link = target.parent / "unused"
        link.symlink_to(target, target_is_directory=True)
        self.assertFalse(local_images._model_ready(link))
        part = target / "unet/openvino_model.bin"
        part.unlink()
        part.symlink_to(target / "model_index.json")
        self.assertFalse(local_images._model_ready(target))

    @patch("src.tools.local_images.shutil.disk_usage")
    def test_preflight_reports_insufficient_disk_without_installing(self, disk):
        disk.return_value = MagicMock(free=1024 * 1024)
        info = local_images.preflight(self.store)
        self.assertFalse(info["ready"])
        self.assertFalse(info["enough_disk"])
        self.assertTrue(info["runtime_isolated"])
        self.assertFalse(local_images._runtime_python(self.store).exists())

    def test_child_environment_does_not_inherit_secrets(self):
        with patch.dict(os.environ, {
            "MENOR_IMAGE_API_KEY": "secret-one",
            "MENOR_GITHUB_TOKEN": "secret-two",
            "OLLAMA_URL": "http://example.com",
        }):
            child = local_images._child_env(self.store)
        self.assertNotIn("MENOR_IMAGE_API_KEY", child)
        self.assertNotIn("MENOR_GITHUB_TOKEN", child)
        self.assertNotIn("OLLAMA_URL", child)
        self.assertEqual(child["MENOR_DATA_DIR"], str(self.store.data_dir))

    def test_child_never_executes_unlisted_actions(self):
        with self.assertRaises(ValueError):
            local_images._run_child("shell", store=self.store)

    @patch("src.tools.local_images._runtime_ready", return_value=True)
    @patch("src.tools.local_images.subprocess.run")
    def test_generation_uses_only_allowed_interpreter_and_json(self, call, ready):
        interpreter = local_images._runtime_python(self.store)
        interpreter.parent.mkdir(parents=True, exist_ok=True)
        interpreter.write_text("")
        call.return_value = MagicMock(
            returncode=0, stdout=json.dumps({
                "status": "completed", "id": "a" * 32,
            }),
        )
        result = local_images._run_child(
            "generate", {"prompt": "Uma floresta à noite", "steps": 12}, store=self.store,
        )
        self.assertEqual(result["status"], "completed")
        sent = call.call_args
        self.assertEqual(sent.args[0][0], str(interpreter))
        self.assertEqual(sent.args[0][-2:], ["src.tools.image_runner", "generate"])
        self.assertLessEqual(sent.kwargs["timeout"], local_images.INFERENCE_TIMEOUT)
        self.assertNotIn("MENOR_IMAGE_API_KEY", sent.kwargs["env"])

    @patch("src.tools.local_images._runtime_ready", return_value=True)
    @patch("src.tools.local_images.subprocess.run")
    def test_child_timeout_fails_cleanly(self, call, ready):
        call.side_effect = subprocess.TimeoutExpired(cmd="image-runner", timeout=1)
        with self.assertRaises(local_images.LocalImageUnavailable):
            local_images._run_child("generate", {"steps": 2}, store=self.store)

    @patch("src.tools.local_images.preflight")
    def test_mission_approval_does_not_download_without_space(self, preflight):
        preflight.return_value = {"enough_disk": False}
        missions = MissionStore(self.store)
        mission = missions.begin("images.generate", "Quero um gerador de imagens local")
        missions.detail(mission["id"], "Receber descrição e gerar ilustração sem API")
        result = missions.decide(mission["id"], True)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["result"]["error"], "insufficient_disk")

    def test_runner_rejects_arbitrary_command(self):
        from src.tools.image_runner import main
        self.assertEqual(main(["shell"]), 2)


if __name__ == "__main__":
    unittest.main()

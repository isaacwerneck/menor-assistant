import asyncio
import io
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from fastapi import UploadFile

from src.agent import runner
from src.agent.missions import MissionStore
from src.agent.skills import capability_status
from src.agent.tasks import RunBusy, TaskStore
from src.api import main
from src.memory.store import BrainStore


class HarnessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": temporary.name, "MENOR_INTELLIGENCE_ENABLED": "0"})
        env.start()
        self.addCleanup(env.stop)
        self.store = TaskStore()
        self.session = "conversation01"

    def run_turn(self, message, turn="request01"):
        return runner.run(self.session, turn, message, [], tasks=self.store)

    def test_claim_is_atomic_and_replays_completed_turn(self):
        state, cached = self.store.claim(self.session, "request01", {"message": "oi"})
        self.assertEqual(state["phase"], "idle")
        self.assertIsNone(cached)
        with self.assertRaises(RunBusy):
            self.store.claim(self.session, "request02", {"message": "outro"})
        response = {"handled": True, "reply": "ok"}
        self.store.finish(self.session, "request01", {"phase": "idle"}, response)
        reopened = TaskStore()
        self.assertEqual(reopened.claim(self.session, "request01", {"message": "oi"})[1], response)
        with self.assertRaises(ValueError):
            reopened.claim(self.session, "request01", {"message": "diferente"})

    @patch("src.agent.runner._model_step")
    def test_read_tools_loop_observes_real_receipt(self, model):
        model.side_effect = [
            {"action": "tool", "tool": "projects.list", "arguments": {}},
            {"action": "answer", "reply": "Consulta concluída."},
        ]
        result = self.run_turn("Liste meus projetos")
        self.assertEqual(result["events"], [{"tool": "projects.list", "status": "executed"}])
        self.assertIn("Concluí as operações de leitura", result["reply"])
        self.assertNotIn("projects.list", result["reply"])
        self.assertEqual(model.call_args.args[2][0]["status"], "executed")

    @patch("src.agent.runner.perform")
    @patch("src.agent.runner._model_step")
    def test_approval_survives_restart_and_duplicate_does_not_execute_twice(self, model, execute):
        model.return_value = {
            "action": "tool", "tool": "projects.create", "arguments": {"name": "Jogo azul"},
            "reply": "Criar um projeto de jogo.",
        }
        execute.return_value = {"status": "planned"}
        first = self.run_turn("Crie um projeto Jogo azul")
        self.assertEqual(first["phase"], "approval")
        execute.assert_called_once_with("projects.create", {"name": "Jogo azul"}, dry_run=True)
        self.store = TaskStore()
        execute.reset_mock()
        execute.return_value = {"status": "executed", "tool": "projects.create", "result": {"created": True}}
        approved = self.run_turn("sim", "request02")
        self.assertEqual(self.run_turn("sim", "request02"), approved)
        execute.assert_called_once_with("projects.create", {"name": "Jogo azul"}, dry_run=False)

    @patch("src.agent.runner._model_step")
    def test_refusal_executes_nothing_and_unknown_tool_is_rejected(self, model):
        model.return_value = {"action": "tool", "tool": "projects.create", "arguments": {"name": "Jogo azul"}}
        self.run_turn("Crie um projeto Jogo azul")
        self.assertIn("cancelada", self.run_turn("não", "request02")["reply"])
        self.assertFalse((BrainStore().brain_dir / "projetos/jogo-azul").exists())
        model.return_value = {"action": "tool", "tool": "shell.exec", "arguments": {"cmd": "anything"}}
        self.assertEqual(self.run_turn("Liste projetos", "request03")["phase"], "failed")

    @patch("src.agent.runner._model_step")
    def test_loop_stops_on_repeated_action(self, model):
        model.return_value = {"action": "tool", "tool": "projects.list", "arguments": {}}
        result = self.run_turn("Liste projetos")
        self.assertEqual(result["phase"], "blocked")
        self.assertEqual(model.call_count, 2)

    @patch("src.agent.runner.capability_status", return_value={"ready": False})
    def test_screenshot_image_question_offers_real_capability(self, capability):
        result = self.run_turn("eai mano, conseguimos fazer uma imagem?")
        self.assertEqual(result["phase"], "image_offer")
        self.assertIn("ferramenta", result["reply"])
        self.assertNotIn("incapaz", result["reply"])
        with patch("src.agent.runner.MissionStore") as missions:
            missions.return_value.begin.return_value = {"id": "a" * 32, "question": "Como deve funcionar?"}
            response = self.run_turn("não conseguimos fazer uma ferramenta?", "request02")
            self.assertEqual(response["phase"], "mission")
            missions.return_value.begin.assert_called_once()
            self.assertEqual(missions.return_value.begin.call_args.args[0], "images.generate")
            missions.return_value.decide.assert_not_called()

    @patch("src.agent.runner.requests.post")
    def test_planner_uses_ollama_schema_and_rejects_literal_action_template(self, post):
        response = post.return_value.__enter__.return_value
        response.json.return_value = {"message": {"content": '{"action":"tool|answer","arguments":[]}'}}
        with self.assertRaises(ValueError):
            runner._model_step("Liste projetos.", [], [])
        payload = post.call_args.kwargs["json"]
        choices = payload["format"]["oneOf"]
        project = next(item for item in choices if item["properties"].get("tool") == {"const": "projects.list"})
        self.assertEqual(project["properties"]["arguments"]["type"], "object")
        self.assertEqual(project["properties"]["action"], {"const": "tool"})
        self.assertNotIn("tool|answer", payload["messages"][0]["content"])

    @patch("src.agent.runner.capability_status", return_value={"ready": False})
    @patch("src.agent.planner.requests.post", side_effect=__import__("requests").Timeout("offline"))
    def test_pixel_art_mission_answers_questions_without_approving(self, post, capability):
        self.assertEqual(self.run_turn("queria criar uma pixel art, vc consegue me ajudar?")["phase"],
                         "image_offer")
        self.run_turn("quero que vc crie uma ferramenta de criar pixel art!", "request02")
        state = self.store.inspect(self.session)
        missions = MissionStore()
        self.assertEqual(missions.get(state["mission_id"])["capability"], "images.generate")
        self.run_turn("Receber minha descrição e devolver pixel art em PNG.", "request03")
        before = missions.get(state["mission_id"])
        for turn, question in (("request04", "como assim cpu pode ser lenta?"),
                               ("request05", "quero q vc me explique melhor do modelo")):
            result = self.run_turn(question, turn)
            self.assertIn("CPU", result["reply"])
            self.assertIn("A aprovação continua pendente", result["reply"])
            self.assertEqual(missions.get(state["mission_id"]), before)
        self.run_turn("não", "request06")
        self.assertEqual(missions.get(state["mission_id"])["status"], "cancelled")
        self.assertFalse(missions.get(state["mission_id"])["approval"])

    def test_conversation_state_is_private_and_validated(self):
        with self.assertRaises(ValueError):
            self.store.inspect("../outside")
        self.run_turn("olá")
        self.assertEqual(TaskStore().inspect(self.session)["phase"], "idle")
        self.assertEqual(TaskStore().inspect("another01")["phase"], "idle")


class HarnessEndpointTests(unittest.TestCase):
    setUp = HarnessTests.setUp

    def test_auth_and_contract(self):
        from test_auth_memory import call
        body = {"session_id": self.session, "turn_id": "request01", "message": "olá"}
        self.assertEqual(call("/agent/run", body)[0], 401)
        code, _, headers = call("/auth/setup", {"password": "senha-longa-de-teste-123"})
        self.assertEqual(code, 200)
        cookie = headers[b"set-cookie"].decode().split(";", 1)[0]
        self.assertEqual(call("/agent/run", body, cookie=cookie)[1], {"handled": False})
        self.assertEqual(call("/agent/runs/" + self.session, cookie=cookie)[1]["phase"], "idle")
        self.assertEqual(call("/agent/run", {**body, "session_id": "../bad"}, cookie=cookie)[0], 422)
        self.assertEqual(call("/health")[1]["api_contract"], 1)


class OperationRegressionTests(unittest.TestCase):
    def test_pending_queue_is_filtered_before_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            missions = MissionStore(BrainStore(directory))
            root = missions._root()
            for index in range(61):
                item = {
                    "id": f"{index:032x}", "status": "queued" if index == 0 else "gathering",
                    "updated_at": str(index).zfill(4),
                }
                (root / (item["id"] + ".json")).write_text(json.dumps(item), encoding="utf-8")
            pending = missions.list(limit=50, statuses={"queued", "installing"}, oldest_first=True)
            self.assertEqual([item["id"] for item in pending], ["0" * 32])

    def test_new_mission_does_not_remove_verified_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            missions = MissionStore(BrainStore(directory))
            root = missions._root()
            items = [
                {"id": "a" * 32, "status": "ready", "updated_at": "1", "capability": "images.generate",
                 "result": {"verified": True}},
                {"id": "b" * 32, "status": "gathering", "updated_at": "2", "capability": "images.generate"},
            ]
            for item in items:
                (root / (item["id"] + ".json")).write_text(json.dumps(item), encoding="utf-8")
            with patch("src.agent.skills.local_images.status", return_value={"ready": True}):
                self.assertTrue(capability_status("images.generate", missions)["ready"])
            with patch("src.agent.skills.local_images.status", return_value={"ready": False}):
                self.assertFalse(capability_status("images.generate", missions)["ready"])


class ImageConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_edit_does_not_block_event_loop(self):
        started, release = threading.Event(), threading.Event()

        def blocking_edit(*args):
            started.set()
            release.wait(2)
            return {"status": "completed"}

        with patch.object(main.auth, "require_owner"), patch.object(main, "record"):
            with patch.object(main.images, "edit", side_effect=blocking_edit):
                task = asyncio.create_task(main.images_edit(
                    None, prompt="Imagem de teste", file=UploadFile(file=io.BytesIO(b"image")),
                ))
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait, 2))
                    self.assertFalse(task.done())
                finally:
                    release.set()
                    await task


if __name__ == "__main__":
    unittest.main()

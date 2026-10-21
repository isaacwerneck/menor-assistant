"""E10: valida manifestos de aceitação e continuidade real sem inferência."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import runner
from src.agent.tasks import TaskStore

MANIFEST = Path(__file__).resolve().parents[1] / "lab" / "scenarios" / "e10-e2e-workflows.json"


class E10WorkflowTests(unittest.TestCase):
    def test_scenarios_are_manual_and_cover_every_step(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], "e10-workflows-v1")
        self.assertTrue(data["requires_owner_review"])
        self.assertFalse(data["autostart"])
        self.assertEqual(len(data["scenarios"]), 8)
        ids = set()
        for scenario in data["scenarios"]:
            with self.subTest(scenario=scenario["id"]):
                self.assertNotIn(scenario["id"], ids)
                ids.add(scenario["id"])
                self.assertEqual(scenario["execution_mode"], "manual-authenticated-chat")
                self.assertEqual(len(scenario["turns"]), 5)
                self.assertIn("ollama.token_generation_ms", scenario["measurement"])
                for n, turn in enumerate(scenario["turns"], 1):
                    self.assertEqual(turn["turn"], n)
                    self.assertGreater(len(turn["message"]), 20)
                    self.assertGreater(len(turn["expected"]), 20)
                    self.assertTrue(turn["requires_human_review"])

    def test_raylib_choice_survives_many_followups(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"MENOR_DATA_DIR": root}):
            store = TaskStore()
            session = "e10ScenarioSession"
            messages = [
                "bora fazer um jogo de plataforma?",
                "quero usar raylib javascript e uma fase",
                "adiciona pontuacao quando chegar ao final",
                "adiciona feedback visual nos intervalos",
                "tenta dnv",
                "agora vamos revisar antes de criar os arquivos",
            ]
            with (
                patch.object(runner.conversation, "reply", return_value="Plano do jogo válido.") as respond,
                patch.object(runner.intelligence, "decide") as decide,
            ):
                for n, message in enumerate(messages):
                    result = runner.run(session, "e10ScenarioTurn" + str(n), message, [],
                                        tasks=store)
                    self.assertEqual(result["phase"], "collaboration")
                state = store.inspect(session)
                self.assertIn("Raylib", state["technology"])
                self.assertIn("raylib javascript", respond.call_args.kwargs["goal"].lower())
                decide.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Garantias de comunicação de estado de missões sem confundir domínios."""
import os
import tempfile
import unittest
from unittest.mock import patch

from src.agent import runner


class MissionProgressTests(unittest.TestCase):
    def test_queued_never_claims_installation(self):
        with patch("src.agent.runner.MissionStore") as store:
            store.return_value.get.return_value = {
                "id": "mission", "capability": "audio.generate",
                "status": "queued", "question": "Preparar gerador de áudio",
            }
            state, response = runner._mission_turn(
                {"phase": "mission", "mission_id": "mission"}, "qual o andamento?"
            )
        self.assertEqual(state["phase"], "mission")
        self.assertIn("executor", response["reply"])
        self.assertNotIn("modelo local", response["reply"])
        self.assertNotIn("imagem", response["reply"])
        self.assertNotIn("concluí", response["reply"])

    def test_testing_stage_is_not_assumed_visual(self):
        with patch("src.agent.runner.MissionStore") as store:
            store.return_value.get.return_value = {
                "id": "mission", "capability": "documents.read",
                "status": "installing", "stage": "testing",
                "question": "Validar extração de PDF",
            }
            _, response = runner._mission_turn(
                {"phase": "mission", "mission_id": "mission"}, "andamento?"
            )
        self.assertIn("testes", response["reply"])
        self.assertNotIn("imagem", response["reply"])


if __name__ == "__main__":
    unittest.main()

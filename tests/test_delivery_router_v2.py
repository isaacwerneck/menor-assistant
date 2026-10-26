import shutil
import tempfile
import unittest
from pathlib import Path

from src.agent.delivery_router import TwoWayDeliveryRouter
from src.memory.store import BrainStore


class TestDeliveryRouterV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = BrainStore(data_dir=self.temp_dir)
        self.store.initialize()
        self.router = TwoWayDeliveryRouter(store=self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_two_way_routing_timeout(self):
        result = self.router.route_error(
            technical_error="Connection timed out after 15000ms: Errno 110",
            user_facing_intent="Consultar status da API externa",
            channel="voice",
        )

        self.assertTrue(result["technical_logged"])
        self.assertNotIn("Errno 110", result["human_message"])
        self.assertIn("demorou um pouco além do esperado", result["human_message"])

        # Checa persistência no log técnico
        self.assertTrue(self.router.system_chat_log.exists())
        log_content = self.router.system_chat_log.read_text(encoding="utf-8")
        self.assertIn("Errno 110", log_content)
        self.assertIn("erro_tecnico", log_content)

    def test_two_way_routing_file_not_found(self):
        result = self.router.route_error(
            technical_error="FileNotFoundError: [Errno 2] No such file or directory: 'teste.gd'",
            user_facing_intent="Ler arquivo de script Godot",
            channel="web",
        )
        self.assertNotIn("FileNotFoundError", result["human_message"])
        self.assertIn("Não encontrei esse arquivo", result["human_message"])


if __name__ == "__main__":
    unittest.main()

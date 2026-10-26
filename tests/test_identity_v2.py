import shutil
import tempfile
import unittest
from pathlib import Path

from src.memory.identity import IdentityManager, DEFAULT_SOUL, DEFAULT_SELF, DEFAULT_RELATION
from src.memory.agora import AgoraLayer
from src.memory.store import BrainStore


class TestIdentityV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = BrainStore(data_dir=self.temp_dir)
        self.store.initialize()
        self.id_mgr = IdentityManager(self.store)
        self.agora = AgoraLayer(self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_identity_seeding(self):
        soul = self.id_mgr.get_soul()
        self_desc = self.id_mgr.get_self()
        relation = self.id_mgr.get_relation()

        self.assertIn("Menor v2", soul)
        self.assertIn("Isaac Werneck", soul)
        self.assertIn("Hub Central", self_desc)
        self.assertIn("Desenvolvedor", relation)

    def test_format_canonical_identity_compact_and_full(self):
        compact = self.id_mgr.format_canonical_identity(compact=True)
        self.assertTrue(len(compact) < 300)
        self.assertIn("Menor v2", compact)

        full = self.id_mgr.format_canonical_identity(compact=False)
        self.assertIn("[IDENTIDADE CANÔNICA - SOUL]", full)
        self.assertIn("[AUTOPERCEPÇÃO - SELF]", full)
        self.assertIn("[VÍNCULO COM OPERADOR - RELATION]", full)

    def test_update_self_and_relation(self):
        self.id_mgr.update_self("Novo autoperfil atualizado.")
        self.assertEqual(self.id_mgr.get_self(), "Novo autoperfil atualizado.")

        self.id_mgr.update_relation("Parceria refinada.")
        self.assertEqual(self.id_mgr.get_relation(), "Parceria refinada.")

    def test_agora_layer_generation(self):
        agora_data = self.agora.get_agora(channel="voice", presence="online", current_goal="Testar áudio")
        self.assertEqual(agora_data["canal"], "voice")
        self.assertEqual(agora_data["presenca"], "online")
        self.assertEqual(agora_data["objetivo_imediato"], "Testar áudio")
        self.assertIn("America/Sao_Paulo", agora_data["timezone"])

        context_str = self.agora.format_agora_context(channel="voice", current_goal="Testar áudio")
        self.assertIn("[CAMADA DO AGORA - CONTEXTO TEMPORAL]", context_str)
        self.assertIn("voice", context_str)


if __name__ == "__main__":
    unittest.main()

import shutil
import tempfile
import unittest
from pathlib import Path

from src.agent.context_engine import (
    ContextBudgetManager,
    estimate_tokens,
    is_casual_query,
    compute_overlap_score,
)
from src.memory.identity import IdentityManager
from src.memory.agora import AgoraLayer
from src.memory.store import BrainStore


class TestContextBudgetV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = BrainStore(data_dir=self.temp_dir)
        self.store.initialize()
        self.id_mgr = IdentityManager(self.store)
        self.agora = AgoraLayer(self.store)
        self.budget_mgr = ContextBudgetManager()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertTrue(estimate_tokens("Olá mundo, este é um teste") > 3)

    def test_is_casual_query(self):
        self.assertTrue(is_casual_query("opa eai"))
        self.assertTrue(is_casual_query("bom dia mano"))
        self.assertTrue(is_casual_query("tudo bem?"))
        self.assertFalse(is_casual_query("crie um arquivo index.html com canvas 2d"))
        self.assertFalse(is_casual_query("qual a arquitetura do nosso banco sqlite?"))

    def test_assemble_system_prompt_casual_vs_technical(self):
        # 1. Casual: prompt compacto sem projetos
        prompt_casual, meta_casual = self.budget_mgr.assemble_system_prompt(
            user_message="opa eai",
            identity_manager=self.id_mgr,
            agora_layer=self.agora,
            store=self.store,
            channel="web",
        )
        self.assertTrue(meta_casual["is_casual"])
        self.assertEqual(len(meta_casual["injected_notes"]), 0)
        self.assertTrue(meta_casual["total_system_tokens"] < 350)
        self.assertIn("Menor v2", prompt_casual)

        # 2. Técnico com nota relevante
        self.store.write_note(
            "projetos/audio_dsp.md",
            "# Projeto Áudio DSP\nSíntese FM com Web Audio API e buffers PCM de 16kHz.",
        )
        prompt_tech, meta_tech = self.budget_mgr.assemble_system_prompt(
            user_message="como funciona a síntese FM no nosso projeto de audio dsp?",
            identity_manager=self.id_mgr,
            agora_layer=self.agora,
            store=self.store,
            channel="web",
        )
        self.assertFalse(meta_tech["is_casual"])
        self.assertIn("projetos/audio_dsp.md", meta_tech["injected_notes"])
        self.assertIn("Síntese FM", prompt_tech)

    def test_compaction_rule_80_percent(self):
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"Mensagem de teste longa {i} " * 40}
            for i in range(20)
        ]
        # Com compaction_threshold baixo (ex: 200 tokens) para disparar
        mgr = ContextBudgetManager(compaction_threshold=200)
        compacted, was_compacted = mgr.compact_history_if_needed(history, system_tokens=50)

        self.assertTrue(was_compacted)
        self.assertEqual(len(compacted), 9)  # 1 resumo + 8 turnos recentes
        self.assertEqual(compacted[0]["role"], "system")
        self.assertIn("[RESUMO DE CONTEXTO ANTERIOR CONDENSADO]", compacted[0]["content"])


if __name__ == "__main__":
    unittest.main()

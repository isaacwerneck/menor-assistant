"""Regressões de contaminação entre objetivos e aprovação de missões."""
import os
import tempfile
import unittest
from unittest.mock import patch

from src.agent import runner
from src.agent.missions import MissionStore
from src.agent.tasks import TaskStore


class DomainIsolationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {
            "MENOR_DATA_DIR": tmp.name, "MENOR_INTELLIGENCE_ENABLED": "1",
        })
        env.start()
        self.addCleanup(env.stop)

    @patch("src.agent.runner.intelligence.decide")
    def test_document_analysis_plan_is_not_image_generation(self, decide):
        decide.return_value = {
            "move": "plan", "goal": "Analisar PDF e fotos",
            "reply": "Precisamos de extração de documentos e visão local.",
            "question": "", "steps": ["Extrair texto e tabelas", "Testar interpretação visual"],
            "acceptance": ["Perguntas respondidas com evidências"],
        }
        history = [{"role": "user", "content": "Crie uma pixel art"},
                   {"role": "assistant", "content": "Podemos gerar imagens."}]
        result = runner.run("isolation001", "turn00001",
                            "Vamos criar uma ferramenta para analisar PDFs, JPEG e XLSX",
                            history, tasks=TaskStore())
        self.assertEqual(result["phase"], "goal")
        self.assertIn("extração", result["reply"])
        self.assertNotIn("Stable Diffusion", result["reply"])

    @patch("src.agent.runner.intelligence.decide", return_value=None)
    @patch("src.agent.runner.MissionStore")
    def test_unavailable_reasoner_does_not_start_mission(self, missions, decide):
        result = runner.run("isolation002", "turn00001",
                            "Vamos criar uma ferramenta para analisar PDFs e imagens",
                            [{"role": "user", "content": "pixel art"}], tasks=TaskStore())
        self.assertTrue(result["handled"])
        self.assertIn("Não executei ferramentas", result["reply"])
        missions.assert_not_called()

    def test_non_image_mission_never_proposes_sd_installation(self):
        mission = MissionStore().begin("music", "Criar um sintetizador musical local")
        with patch("src.agent.missions.plan", return_value={
            "steps": ["Definir formato de áudio"], "acceptance": ["Gerar áudio válido"],
        }):
            detailed = MissionStore().detail(mission["id"], "Entrada MIDI, saída WAV local")
        self.assertNotIn("Stable Diffusion", detailed["question"])
        self.assertNotIn("INT8", detailed["question"])
        explanation = MissionStore().explain(mission["id"], "Que aprovação?")
        self.assertNotIn("modelo de imagens", explanation)
        self.assertIn("music", explanation)


if __name__ == "__main__":
    unittest.main()

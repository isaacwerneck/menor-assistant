"""Testes para o Subagente Game & App Studio (Pilar 10 - GDD, Arch, Dev, Verify)."""
import tempfile
import unittest
from pathlib import Path

from src.agent.game_studio import GameStudioSubagent


class TestGameStudioV2(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.studio = GameStudioSubagent(workspace_dir=Path(self.temp_dir.name))

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_create_gdd_structure(self):
        gdd = self.studio.create_gdd(
            title="Nave Cósmica 2D",
            genre="Space Shooter",
            mechanics=["Mover nave", "Atirar lasers", "Desviar de asteroides"],
        )
        self.assertIn("# GDD: Nave Cósmica 2D", gdd)
        self.assertIn("Core Mechanics", gdd)
        self.assertIn("Controles", gdd)
        self.assertIn("Vitória / Derrota", gdd)

    def test_build_canvas_game_and_quality_gate(self):
        project_name = "test_space_invader"
        res = self.studio.build_canvas_game(
            project_name=project_name,
            title="Space Invader 2D",
            width=640,
            height=480,
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["preview_url"], f"/preview/{project_name}.html")

        # Verifica Quality Gate de 60 FPS
        gate = res["quality_gate"]
        self.assertTrue(gate["uses_request_animation_frame"])
        self.assertTrue(gate["has_delta_time_dt"])
        self.assertTrue(gate["has_dt_clamp"])
        self.assertTrue(gate["target_60_fps_ready"])

        # Limpeza do arquivo gerado
        html_file = Path(f"{project_name}.html")
        if html_file.exists():
            html_file.unlink()

    def test_verify_quality_gate_rejects_bad_code(self):
        bad_code = "while(true) { render(); }"
        gate = self.studio.verify_quality_gate(bad_code)
        self.assertFalse(gate["uses_request_animation_frame"])
        self.assertFalse(gate["has_delta_time_dt"])
        self.assertFalse(gate["target_60_fps_ready"])

    def test_scaffold_godot_project(self):
        res = self.studio.scaffold_godot_project("meu_jogo_godot")
        self.assertTrue(res["success"])
        self.assertIn("meu_jogo_godot/project.godot", res["files_created"])
        self.assertIn("meu_jogo_godot/main.gd", res["files_created"])

        # Limpeza dos arquivos gerados
        p_godot = Path("meu_jogo_godot/project.godot")
        m_gd = Path("meu_jogo_godot/main.gd")
        if p_godot.exists():
            p_godot.unlink()
        if m_gd.exists():
            m_gd.unlink()
        godot_dir = Path("meu_jogo_godot")
        if godot_dir.exists():
            godot_dir.rmdir()

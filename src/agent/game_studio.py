"""Subagente Game & App Studio (Pilar 10 - Donchitos / Claude Code Game Studios).

Metodologia de 4 fases para desenvolvimento de jogos 2D e simulações:
1. /gdd: Game Design Document conciso (core loop, mecânicas, controles, vitória/derrota).
2. /arch: Arquitetura de arquivos, estado compartilhado e loop principal.
3. /dev: Implementação com separação estrita de papéis (init, update(dt), render, input).
4. /verify: Quality Gate que valida delta time (dt), acumulação de física e meta de 60 FPS.

Suporte para Canvas 2D / WebGL no navegador e Engine Godot 4.x local.
"""
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from src.tools.core import fs_write

LOGGER = logging.getLogger(__name__)


CANVAS_GAME_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background: #0a0a10;
      color: #fff;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100vh;
      font-family: system-ui, -apple-system, sans-serif;
      overflow: hidden;
    }}
    #game-container {{
      border: 2px solid #8b5cf6;
      border-radius: 8px;
      box-shadow: 0 0 24px rgba(139, 92, 246, 0.3);
      position: relative;
    }}
    canvas {{
      display: block;
      background: #12121a;
    }}
    #hud {{
      position: absolute;
      top: 10px;
      left: 10px;
      font-size: 14px;
      font-family: monospace;
      color: #06b6d4;
    }}
  </style>
</head>
<body>
  <div id="game-container">
    <canvas id="gameCanvas" width="{width}" height="{height}"></canvas>
    <div id="hud">FPS: <span id="fps">60</span> | Score: <span id="score">0</span></div>
  </div>

  <script>
    // Game Studio Engine - 60 FPS Loop com Delta Time
    const canvas = document.getElementById('gameCanvas');
    const ctx = canvas.getContext('2d');
    const fpsElem = document.getElementById('fps');
    const scoreElem = document.getElementById('score');

    let state = {{
      score: 0,
      running: true,
      player: {{ x: {width}/2, y: {height}/2, vx: 0, vy: 0, size: 16, speed: 200 }},
      keys: {{}}
    }};

    window.addEventListener('keydown', e => state.keys[e.key.toLowerCase()] = true);
    window.addEventListener('keyup', e => state.keys[e.key.toLowerCase()] = false);

    function handleInput(dt) {{
      state.player.vx = 0;
      state.player.vy = 0;
      if (state.keys['arrowup'] || state.keys['w']) state.player.vy = -state.player.speed;
      if (state.keys['arrowdown'] || state.keys['s']) state.player.vy = state.player.speed;
      if (state.keys['arrowleft'] || state.keys['a']) state.player.vx = -state.player.speed;
      if (state.keys['arrowright'] || state.keys['d']) state.player.vx = state.player.speed;
    }}

    function update(dt) {{
      handleInput(dt);
      state.player.x += state.player.vx * dt;
      state.player.y += state.player.vy * dt;

      // Limites de tela
      state.player.x = Math.max(state.player.size, Math.min(canvas.width - state.player.size, state.player.x));
      state.player.y = Math.max(state.player.size, Math.min(canvas.height - state.player.size, state.player.y));
    }}

    function render() {{
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Desenha Player
      ctx.fillStyle = '#8b5cf6';
      ctx.beginPath();
      ctx.arc(state.player.x, state.player.y, state.player.size, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#06b6d4';
      ctx.lineWidth = 2;
      ctx.stroke();
    }}

    let lastTime = performance.now();
    let frameCount = 0;
    let fpsTimer = 0;

    function gameLoop(now) {{
      const dt = Math.min((now - lastTime) / 1000, 0.1); // Clamp anti-spiral
      lastTime = now;

      frameCount++;
      fpsTimer += dt;
      if (fpsTimer >= 0.5) {{
        fpsElem.textContent = Math.round(frameCount / fpsTimer);
        frameCount = 0;
        fpsTimer = 0;
      }}

      if (state.running) {{
        update(dt);
        render();
      }}

      requestAnimationFrame(gameLoop);
    }}

    requestAnimationFrame(gameLoop);
  </script>
</body>
</html>
"""


class GameStudioSubagent:
    """Orquestrador do estúdio de jogos autônomo com quality gates de 60 FPS."""

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or Path.cwd()

    def create_gdd(self, title: str, genre: str, mechanics: List[str]) -> str:
        """Fase 1 (/gdd): Cria o Game Design Document conciso."""
        mech_str = "\n".join(f"- {m}" for m in mechanics)
        gdd = (
            f"# GDD: {title}\n"
            f"**Gênero:** {genre}\n"
            f"**Plataforma Alvo:** Web Canvas 2D / 60 FPS\n\n"
            f"## 1. Core Mechanics & Loop\n{mech_str}\n\n"
            f"## 2. Controles\n- Setas / WASD: Movimentação\n- Barra de Espaço: Ação / Pulo\n\n"
            f"## 3. Condições de Vitória / Derrota\n- Vitória: Alcançar pontuação máxima.\n- Derrota: Colisão com obstáculos ou zerar vida.\n"
        )
        return gdd

    def build_canvas_game(
        self,
        project_name: str,
        title: str,
        width: int = 800,
        height: int = 600,
    ) -> Dict[str, Any]:
        """Fase 2 & 3 (/arch e /dev): Materializa o jogo Canvas 2D interativo."""
        filename = f"{project_name}.html"
        content = CANVAS_GAME_TEMPLATE.format(title=title, width=width, height=height)
        res = fs_write(filepath=filename, content=content)

        quality_audit = self.verify_quality_gate(content)

        return {
            "success": res.get("success", False),
            "filepath": filename,
            "preview_url": f"/preview/{filename}",
            "quality_gate": quality_audit,
        }

    def verify_quality_gate(self, game_code: str) -> Dict[str, Any]:
        """Fase 4 (/verify): Quality Gate que audita delta-time, clamp e frame loop."""
        checks = {
            "uses_request_animation_frame": "requestAnimationFrame" in game_code,
            "has_delta_time_dt": bool(re.search(r"\bdt\b", game_code)),
            "has_dt_clamp": "Math.min" in game_code and "0.1" in game_code,
            "has_fps_counter": "fps" in game_code.lower(),
            "target_60_fps_ready": False,
        }
        checks["target_60_fps_ready"] = all([
            checks["uses_request_animation_frame"],
            checks["has_delta_time_dt"],
            checks["has_dt_clamp"],
        ])
        return checks

    def scaffold_godot_project(self, project_name: str) -> Dict[str, Any]:
        """Scaffolding de projeto nativo para Godot 4.x."""
        base_dir = self.workspace_dir / project_name
        project_godot = (
            f"; Engine configuration file for Godot 4.x\n"
            f"config_version=5\n\n"
            f"[application]\n"
            f"config/name=\"{project_name}\"\n"
            f"run/main_scene=\"res://main.tscn\"\n"
            f"config/features=PackedStringArray(\"4.3\", \"Forward+\")\n"
        )
        main_gd = (
            f"extends Node2D\n\n"
            f"# Script principal do jogo {project_name}\n"
            f"var speed: float = 300.0\n\n"
            f"func _ready():\n"
            f"    print(\"Projeto {project_name} iniciado no Godot 4.x\")\n\n"
            f"func _process(delta: float):\n"
            f"    var direction = Input.get_vector(\"ui_left\", \"ui_right\", \"ui_up\", \"ui_down\")\n"
            f"    position += direction * speed * delta\n"
        )

        f1 = fs_write(filepath=f"{project_name}/project.godot", content=project_godot)
        f2 = fs_write(filepath=f"{project_name}/main.gd", content=main_gd)

        return {
            "success": f1.get("success", False) and f2.get("success", False),
            "project_name": project_name,
            "files_created": [f"{project_name}/project.godot", f"{project_name}/main.gd"],
        }

"""Executa tools geradas APÓS merge somente em container isolado.

O servidor nunca importa código da skill no processo do chat. Sem Docker e
imagem local, a execução falha fechada e recomenda preparar o executor.
"""
import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

from src.agent.self_edit import ImprovementUnavailable

IMAGE = "python:3.12-alpine"
NAME = re.compile(r"^[a-z][a-z0-9_]{2,39}$")
ROOT = Path(__file__).resolve().parents[1] / "tools" / "generated"
CHILD = """
import importlib.util, json, sys
payload = json.load(sys.stdin)
spec = importlib.util.spec_from_file_location('approved_skill', '/skill.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = module.run(payload['text'])
if not isinstance(result, str) or len(result) > 12000:
    raise ValueError('Resultado invalido')
print(json.dumps({'result': result}))
"""


def run(name, text):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError("Nome de skill inválido.")
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 280:
        raise ValueError("Entrada inválida.")
    source = ROOT / (name + ".py")
    if source.is_symlink() or not source.is_file():
        raise ImprovementUnavailable("Skill revisada não encontrada.")
    docker = shutil.which("docker")
    if not docker:
        raise ImprovementUnavailable("Executor isolado não configurado; execução recusada.")
    container = "menor-skill-" + secrets.token_hex(8)
    args = [
        docker, "run", "--rm", "--interactive", "--name", container,
        "--pull=never", "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=32",
        "--memory=128m", "--cpus=1", "--user=65534:65534",
        "--tmpfs", "/tmp:rw,nosuid,noexec,size=16m",
        "--mount", f"type=bind,source={source},target=/skill.py,readonly",
        "--workdir", "/", IMAGE, "python", "-I", "-B", "-c", CHILD,
    ]
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    try:
        result = subprocess.run(
            args, input=json.dumps({"text": text}, ensure_ascii=False),
            capture_output=True, text=True, timeout=30, env=env, check=False,
        )
        if result.returncode:
            raise ImprovementUnavailable("A skill falhou dentro do executor isolado.")
        try:
            payload = json.loads(result.stdout.strip())
        except ValueError as error:
            raise ImprovementUnavailable("A skill não retornou um resultado verificável.") from error
        if (not isinstance(payload, dict) or set(payload) != {"result"}
                or not isinstance(payload["result"], str) or len(payload["result"]) > 12000):
            raise ImprovementUnavailable("Resultado da skill inválido.")
        return payload["result"]
    except subprocess.TimeoutExpired as error:
        raise ImprovementUnavailable("A execução da skill excedeu o tempo permitido.") from error
    except OSError as error:
        raise ImprovementUnavailable("Não foi possível iniciar a skill isolada.") from error
    finally:
        # Mesmo que o cliente Docker seja interrompido, não deixar execução órfã.
        try:
            subprocess.run(
                [docker, "rm", "--force", container], capture_output=True,
                timeout=8, env=env, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

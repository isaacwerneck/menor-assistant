"""Testa propostas puras em container descartável, sem segredos ou rede."""
import os
import re
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

from src.agent.self_edit import ImprovementUnavailable
from src.memory.store import BrainStore

IMAGE = "python:3.12-alpine"


def verify(name, source, tests):
    docker = shutil.which("docker")
    if not docker:
        raise ImprovementUnavailable("Docker não está disponível para testar a ferramenta antes de criar a branch.")
    container = "menor-test-" + secrets.token_hex(8)
    store = BrainStore()
    store._require_directory(store.data_dir)
    parent = store.data_dir / "sandboxes"
    store._require_directory(parent)
    # PrivateTmp do systemd impede o daemon Docker de enxergar /tmp do serviço.
    with tempfile.TemporaryDirectory(prefix="menor-code-", dir=parent) as directory:
        root = Path(directory)
        root.chmod(0o755)
        module = root / "src" / "tools" / "generated"
        module.mkdir(parents=True)
        suite = root / "tests"
        suite.mkdir()
        (module / (name + ".py")).write_text(source, encoding="utf-8")
        (suite / ("test_" + name + ".py")).write_text(tests, encoding="utf-8")
        for path in root.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        environment = {key: value for key, value in os.environ.items()
                       if key in ("PATH", "SYSTEMROOT", "TEMP", "TMP")}
        environment["DOCKER_CONFIG"] = str(root / "docker-config")
        command = [
            docker, "run", "--detach", "--name", container, "--pull=never",
            "--log-driver=local", "--log-opt=max-size=1m", "--log-opt=max-file=1",
            "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--pids-limit=32", "--memory=128m", "--cpus=1", "--user=65534:65534",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
            "--mount", f"type=bind,source={directory},target=/workspace,readonly",
            "--workdir", "/workspace", IMAGE,
            "python", "-B", "-m", "unittest", "discover", "-s", "tests", "-v",
        ]

        def execute(arguments, timeout=10):
            return subprocess.run(arguments, capture_output=True, text=True,
                                  timeout=timeout, env=environment, check=False)

        started = False
        try:
            launch = execute(command)
            if launch.returncode:
                raise ImprovementUnavailable("Não consegui iniciar o container; prepare a imagem python:3.12-alpine.")
            started = True
            result = execute([docker, "wait", container], timeout=25)
            logs = execute([docker, "logs", "--tail=100", container])
            log = (logs.stdout + logs.stderr)[:8000]
            summary = re.search(r"Ran [1-9][0-9]* tests? in ", log)
            if result.returncode or logs.returncode or result.stdout.strip() != "0" or not summary:
                raise ImprovementUnavailable("Os testes falharam no sandbox; nenhuma branch foi criada.")
            return {"status": "passed", "command": "unittest discover", "log": log}
        except subprocess.TimeoutExpired as error:
            raise ImprovementUnavailable("Tempo de teste excedido; nenhuma branch foi criada.") from error
        except OSError as error:
            raise ImprovementUnavailable("Não foi possível iniciar o sandbox de testes.") from error
        finally:
            if started:
                cleanup = execute([docker, "rm", "--force", container])
                if cleanup.returncode:
                    raise ImprovementUnavailable("Não consegui remover o container " + container + ".")

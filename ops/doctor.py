"""Diagnóstico local e somente de leitura do Menor (biblioteca padrão)."""

import argparse
import http.client
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

_MIB = 1024 * 1024
_GIB = 1024 * _MIB
_MAX_HEALTH_BYTES = 8192


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def check_api(port=8000, timeout=2.0):
    """Consulta apenas o loopback; nunca segue redirects ou acessa a rede pública."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", "/health", headers={"Accept": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("HTTP inesperado")
        payload = response.read(_MAX_HEALTH_BYTES + 1)
        if len(payload) > _MAX_HEALTH_BYTES:
            raise ValueError("resposta acima do limite")
        health = json.loads(payload)
        if not isinstance(health, dict) or health.get("status") != "online" or health.get("service") != "Menor API":
            raise ValueError("contrato de saúde inválido")
    except (OSError, http.client.HTTPException, ValueError, UnicodeError) as error:
        return [
            Check("api", "critical", "API inacessível ou /health inválido (" + type(error).__name__ + ")."),
            Check("ollama", "skipped", "O estado do Ollama depende da resposta da API."),
        ]
    finally:
        connection.close()

    api = Check("api", "ok", "API local respondeu com /health válido.")
    ollama_state = health.get("ollama_status")
    if ollama_state == "online":
        ollama = Check("ollama", "ok", "Ollama acessível segundo /health.")
    elif ollama_state in ("offline", "degraded"):
        ollama = Check("ollama", "warning", "Ollama " + ollama_state + " segundo /health.")
    else:
        ollama = Check("ollama", "warning", "Estado do Ollama ausente ou desconhecido.")
    return [api, ollama]


def check_service():
    """Consulta o systemd do usuário sem reiniciar serviços."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "menor-api.service"],
            capture_output=True, text=True, timeout=2, check=False,
        )
    except FileNotFoundError:
        return Check("service", "skipped", "systemctl indisponível neste ambiente.")
    except (OSError, subprocess.TimeoutExpired):
        return Check("service", "warning", "Não foi possível consultar o serviço systemd.")
    if result.returncode == 0 and result.stdout.strip() == "active":
        return Check("service", "ok", "menor-api.service está ativo.")
    return Check("service", "warning", "menor-api.service não está ativo ou systemd indisponível.")


def check_disk():
    """Verifica somente espaço livre no volume dos dados, sem listar arquivos."""
    raw = os.environ.get("MENOR_DATA_DIR")
    base = Path(raw).expanduser() if raw else Path.home() / "menor-data"
    while not base.exists() and base != base.parent:
        base = base.parent
    try:
        free = shutil.disk_usage(base).free
    except OSError:
        return Check("disk", "warning", "Não foi possível medir o espaço livre.")
    if free < 512 * _MIB:
        return Check("disk", "critical", "Menos de 512 MiB livres no volume de dados.")
    if free < 2 * _GIB:
        return Check("disk", "warning", "Menos de 2 GiB livres no volume de dados.")
    return Check("disk", "ok", "Pelo menos 2 GiB livres no volume de dados.")


def check_memory():
    """Lê apenas MemAvailable em Linux; não examina processos ou dados privados."""
    try:
        lines = Path("/proc/meminfo").read_text(encoding="ascii").splitlines()
        available = next(int(row.split()[1]) * 1024 for row in lines if row.startswith("MemAvailable:"))
    except (OSError, StopIteration, ValueError, IndexError):
        return Check("memory", "skipped", "MemAvailable indisponível neste sistema.")
    if available < _GIB:
        return Check("memory", "warning", "Menos de 1 GiB de memória disponível.")
    return Check("memory", "ok", "Pelo menos 1 GiB de memória disponível.")


def run_checks(port=8000, timeout=2.0):
    checks = [*check_api(port=port, timeout=timeout), check_service(), check_disk(), check_memory()]
    statuses = {check.status for check in checks}
    overall = "critical" if "critical" in statuses else "warning" if "warning" in statuses else "ok"
    return {"status": overall, "read_only": True, "checks": [asdict(item) for item in checks]}


def _port(value):
    number = int(value)
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("a porta deve estar entre 1 e 65535")
    return number


def _timeout(value):
    number = float(value)
    if not 0.1 <= number <= 10.0:
        raise argparse.ArgumentTypeError("timeout deve estar entre 0.1 e 10 segundos")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description="Diagnóstico local e somente de leitura do Menor")
    parser.add_argument("--port", type=_port, default=8000, help="porta local da API (padrão: 8000)")
    parser.add_argument("--timeout", type=_timeout, default=2.0, help="timeout HTTP em segundos")
    parser.add_argument("--json", action="store_true", help="relatório JSON sem caminhos ou segredos")
    args = parser.parse_args(argv)
    report = run_checks(port=args.port, timeout=args.timeout)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        for check in report["checks"]:
            print(f"[{check['status'].upper()}] {check['name']}: {check['detail']}")
        print("Resultado:", report["status"].upper())
    return {"ok": 0, "warning": 1, "critical": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())

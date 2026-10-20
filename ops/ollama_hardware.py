"""Diagnóstico LOCAL e consultivo da execução Ollama: sem prompts, tokens nem ajustes automáticos.

python3 -m ops.ollama_hardware
"""
import json
import os
import shutil
import subprocess
import sys

import requests

from ops.model_latency import local_endpoint


def _memory():
    fields = {}
    try:
        with open("/proc/meminfo", encoding="ascii") as source:
            for line in source:
                key, _, value = line.partition(":")
                if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                    parts = value.split()
                    if len(parts) == 2 and parts[1] == "kB" and parts[0].isdigit():
                        fields[key] = round(int(parts[0]) / (1024 * 1024), 2)
    except OSError:
        return {"status": "unavailable"}
    return {"status": "measured", "units": "GiB", "total": fields.get("MemTotal"),
            "available": fields.get("MemAvailable"),
            "swap_total": fields.get("SwapTotal"),
            "swap_free": fields.get("SwapFree")}


def _gpu_devices(run=subprocess.run, which=shutil.which):
    """Só consulta modelo de GPU local, nunca solicita identificadores únicos."""
    if not which("lspci"):
        return {"status": "unavailable", "reason": "lspci_not_installed"}
    try:
        result = run(["lspci"], capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unavailable", "reason": "lspci_failed"}
    if result.returncode:
        return {"status": "unavailable", "reason": "lspci_failed"}
    devices = []
    for line in result.stdout.splitlines():
        if any(tag in line for tag in ("VGA compatible controller:", "3D controller:", "Display controller:")):
            vendor_device = line.split(": ", 1)[-1]
            devices.append(vendor_device[:160])
    return {"status": "reported", "devices": devices[:8],
            "note": "Detectar uma GPU não comprova que o Ollama esteja usando aceleração."}


def _loaded_models(get, endpoint):
    with get(endpoint.rsplit("/api/chat", 1)[0] + "/api/ps", timeout=(2, 5)) as response:
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise ValueError("Resposta /api/ps inválida.")
    models = []
    for item in payload["models"][:12]:
        if not isinstance(item, dict):
            continue
        size, vram = item.get("size"), item.get("size_vram")
        if type(size) is not int or type(vram) is not int or not 0 <= vram <= size:
            continue
        models.append({"model": str(item.get("name", ""))[:90],
                       "weights_gib": round(size / (1024 ** 3), 2),
                       "vram_gib": round(vram / (1024 ** 3), 2),
                       "placement": ("gpu_partial_or_full" if vram else "cpu_ram"),
                       "context_length": item.get("context_length")
                       if type(item.get("context_length")) is int else None})
    return models


def inspect(get=requests.get, run=subprocess.run, which=shutil.which):
    """Snapshot de memória e modelos, sem inferência nem qualquer operação de escrita."""
    result = {
        "contract": "menor.ollama.hardware.v1", "read_only": True,
        "cpu_logical": os.cpu_count(), "memory": _memory(),
        "gpu_devices": _gpu_devices(run, which),
        "model_state": "unknown", "models": [],
        "interpretation": (
            "Pesos residentes em RAM/VRAM quando o modelo está ocioso são esperados com keep_alive; "
            "mais RAM ocupada não implica mais velocidade. "
            "Para medir desempenho real, execute model_latency --live quando o sistema estiver livre."
        ),
    }
    try:
        endpoint = local_endpoint(os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
        result["models"] = _loaded_models(get, endpoint)
        result["model_state"] = "measured"
    except (ValueError, requests.RequestException, OSError):
        result["model_state"] = "unavailable"
    return result


def main():
    print(json.dumps(inspect(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

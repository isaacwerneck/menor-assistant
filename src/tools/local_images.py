"""Subagente OpenVINO isolado do processo e dependências do chat.

As dependências e pesos só são baixados após aprovação da missão.
O filho recebe ações predefinidas, nunca comandos ou caminhos livres do LLM.
"""
import hashlib
import json
import os
import shutil
import subprocess
import threading
import venv
from pathlib import Path

from src.agent.model_catalog import MODEL_IMAGE_REPO
from src.memory.store import BrainStore

_lock = threading.RLock()
MIN_FREE_BYTES = 5 * 1024**3
ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "requirements-local-images.txt"
REQUIRED_MODELS = (
    "model_index.json",
    "unet/openvino_model.xml",
    "unet/openvino_model.bin",
    "text_encoder/openvino_model.xml",
    "text_encoder/openvino_model.bin",
    "vae_decoder/openvino_model.xml",
    "vae_decoder/openvino_model.bin",
)
INSTALL_TIMEOUT = 3600
INFERENCE_TIMEOUT = 900


class LocalImageUnavailable(RuntimeError):
    pass


def model_directory(store=None):
    store = store or BrainStore()
    store._require_directory(store.data_dir)
    models = store.data_dir / "models"
    store._require_directory(models)
    target = models / "openvino-sd15-int8"
    if target.is_symlink():
        raise ValueError("Modelo não pode ser link simbólico.")
    return target


def _runtime_dir(store=None):
    store = store or BrainStore()
    store._require_directory(store.data_dir)
    directory = store.data_dir / "runtimes"
    store._require_directory(directory)
    target = directory / "openvino-image"
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError("Runtime inválido.")
    return target


def _runtime_python(store=None):
    return _runtime_dir(store) / "bin" / "python"


def _digest():
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def _runtime_ready(store=None):
    base = _runtime_dir(store)
    marker = base / ".menor-requirements.sha256"
    if marker.is_symlink() or not marker.is_file():
        return False
    python = _runtime_python(store)
    if python.is_symlink() or not python.is_file():
        return False
    return marker.read_text(encoding="ascii").strip() == _digest()


def _model_ready(folder):
    if not folder.is_dir() or folder.is_symlink():
        return False
    for relative in REQUIRED_MODELS:
        path = folder / relative
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            return False
    try:
        manifest = json.loads((folder / "model_index.json").read_text(encoding="utf-8"))
        return manifest.get("_class_name") == "StableDiffusionPipeline"
    except (OSError, ValueError, AttributeError):
        return False


def preflight(store=None):
    """Consulta recursos sem baixar arquivos e sem acessar APIs de IA."""
    store = store or BrainStore()
    folder = model_directory(store)
    disk = shutil.disk_usage(folder.parent)
    model_ok = _model_ready(folder)
    runtime_ok = _runtime_ready(store)
    return {
        "provider": "openvino-local",
        "model": MODEL_IMAGE_REPO,
        "installed": model_ok,
        "runtime_available": runtime_ok,
        "ready": model_ok and runtime_ok,
        "required_free_gb": 5,
        "free_disk_gb": round(disk.free / 1024**3, 1),
        "enough_disk": model_ok or disk.free >= MIN_FREE_BYTES,
        "offline_inference": True,
        "requires_download_approval": not model_ok,
        "runtime_isolated": True,
    }


def status(store=None):
    return preflight(store)


def _install_environment(store=None):
    base = _runtime_dir(store)
    with _lock:
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        if _runtime_ready(store):
            return
        python = _runtime_python(store)
        if not python.is_file():
            venv.EnvBuilder(with_pip=True, symlinks=False).create(base)
        try:
            result = subprocess.run(
                [str(python), "-m", "pip", "install", "--disable-pip-version-check",
                 "-r", str(REQUIREMENTS)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=1800, check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise LocalImageUnavailable("Instalação das dependências excedeu o tempo.") from error
        if result.returncode:
            raise LocalImageUnavailable("Não foi possível instalar o runtime isolado.")
        check = subprocess.run(
            [str(python), "-c", "import openvino_genai, huggingface_hub, PIL, requests"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=60, check=False,
        )
        if check.returncode:
            raise LocalImageUnavailable("Runtime isolado não passou no teste de importação.")
        marker = base / ".menor-requirements.sha256"
        if marker.is_symlink():
            raise ValueError("Marcador do runtime inválido.")
        marker.write_text(_digest(), encoding="ascii")
        marker.chmod(0o600)


def ensure_runtime_approved(store=None):
    """Executada exclusivamente pelo worker, após aprovação da missão."""
    if not preflight(store)["enough_disk"]:
        raise LocalImageUnavailable("Não há 5 GiB livres para preparar o modelo.")
    _install_environment(store)


def _child_env(store=None):
    store = store or BrainStore()
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(Path.home()),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "MENOR_DATA_DIR": str(store.data_dir),
        "PYTHONPATH": str(ROOT),
        "HF_HOME": str(store.data_dir / "hf-cache"),
        "HF_HUB_DISABLE_TELEMETRY": "1",
    }


def _run_child(command, data=None, store=None, timeout=INFERENCE_TIMEOUT):
    if command not in ("install", "generate"):
        raise ValueError("Ação de subagente inválida.")
    if not _runtime_ready(store):
        raise LocalImageUnavailable("Runtime local ainda não está instalado.")
    try:
        result = subprocess.run(
            [str(_runtime_python(store)), "-m", "src.tools.image_runner", command],
            input=json.dumps(data or {}, ensure_ascii=False),
            capture_output=True, text=True, cwd=ROOT, env=_child_env(store),
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise LocalImageUnavailable("Subagente local excedeu o limite de tempo.") from error
    if result.returncode:
        raise LocalImageUnavailable("Execução do subagente falhou; consulte o estado da missão.")
    try:
        payload = json.loads(result.stdout.strip())
    except ValueError as error:
        raise LocalImageUnavailable("Subagente não retornou resultado verificável.") from error
    if not isinstance(payload, dict):
        raise LocalImageUnavailable("Resposta do subagente inválida.")
    return payload


def install_approved(store=None):
    folder = model_directory(store)
    if not _model_ready(folder) and not preflight(store)["enough_disk"]:
        raise LocalImageUnavailable("Espaço em disco insuficiente para o modelo.")
    _run_child("install", store=store, timeout=INSTALL_TIMEOUT)
    detail = status(store)
    if not detail["ready"]:
        raise LocalImageUnavailable("Modelo incompleto ou runtime indisponível.")
    return detail


def generate(prompt, store=None, steps=20):
    from src.tools.images import _prompt

    prompt = _prompt(prompt)
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 40:
        raise ValueError("Número de passos inválido.")
    if not status(store)["ready"]:
        raise LocalImageUnavailable("Modelo local não instalado ou dependências ausentes.")
    result = _run_child("generate", {"prompt": prompt, "steps": steps}, store=store)
    if result.get("status") != "completed" or not result.get("id"):
        raise LocalImageUnavailable("Modelo não confirmou a geração.")
    return result

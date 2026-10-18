"""Subagente local de imagens com OpenVINO GenAI; nenhum endpoint de IA externo.

A instalação baixa pesos somente de um repositório pré-aprovado e exige
autorização do proprietário. Após o download, a inferência é offline.
"""

import importlib
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import threading
from pathlib import Path

from src.agent.model_catalog import MODEL_IMAGE_REPO
from src.memory.store import BrainStore

_lock = threading.RLock()
MIN_FREE_BYTES = 5 * 1024**3


class LocalImageUnavailable(RuntimeError):
    pass


def model_directory(store=None):
    store = store or BrainStore()
    store._require_directory(store.data_dir)
    models = store.data_dir / "models"
    store._require_directory(models)
    target = models / "openvino-sd15-int8"
    if target.is_symlink():
        raise ValueError("Modelos não podem usar link simbólico na raiz.")
    return target


def status(store=None):
    folder = model_directory(store)
    installed = (
        folder.is_dir()
        and not folder.is_symlink()
        and (folder / "model_index.json").is_file()
        and (folder / "unet" / "openvino_model.xml").is_file()
    )
    available = importlib.util.find_spec("openvino_genai") is not None
    return {
        "provider": "openvino-local",
        "model": "openvino-sd15-int8",
        "installed": installed,
        "runtime_available": available,
        "ready": installed and available,
        "offline_inference": True,
        "requires_download_approval": not installed,
    }


def ensure_runtime_approved():
    """Instala apenas requisitos revisados no venv atual, sem shell e após aprovação."""
    required = ("openvino_genai", "huggingface_hub")
    if all(importlib.util.find_spec(name) is not None for name in required):
        return
    if sys.prefix == sys.base_prefix:
        raise LocalImageUnavailable("Instalação bloqueada fora de um ambiente virtual.")
    requirements = Path(__file__).resolve().parents[2] / "requirements-local-images.txt"
    if not requirements.is_file():
        raise LocalImageUnavailable("Requisitos do subagente não encontrados.")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
         "-r", str(requirements)],
        capture_output=True, text=True, timeout=1800, check=False,
    )
    if result.returncode != 0:
        raise LocalImageUnavailable("Não foi possível instalar as dependências locais.")
    importlib.invalidate_caches()
    if not all(importlib.util.find_spec(name) is not None for name in required):
        raise LocalImageUnavailable("Dependências instaladas não ficaram disponíveis.")


def install_approved(store=None):
    """Faz download de UM modelo fixo. Não instala pacotes nem executa scripts remotos."""
    folder = model_directory(store)
    if importlib.util.find_spec("huggingface_hub") is None:
        raise LocalImageUnavailable("Falta huggingface_hub no ambiente de imagens.")
    if shutil.disk_usage(folder.parent).free < MIN_FREE_BYTES:
        raise LocalImageUnavailable("Pouco espaço em disco para o modelo local.")
    from huggingface_hub import snapshot_download

    with _lock:
        if folder.is_symlink():
            raise ValueError("Diretório do modelo inválido.")
        if folder.exists() and not folder.is_dir():
            raise ValueError("Diretório do modelo inválido.")
        folder.mkdir(mode=0o700, exist_ok=True)
        folder.chmod(0o700)
        # Apenas pesos e metadados; nunca aceita .py ou scripts remotos.
        snapshot_download(
            repo_id=MODEL_IMAGE_REPO,
            local_dir=str(folder),
            allow_patterns=["*.xml", "*.bin", "*.json", "*.txt", "*.model", "*.vocab"],
            ignore_patterns=["*.py", "*.pickle", "*.pkl", "*.pt", "*.pth"],
        )
        for path in folder.rglob("*"):
            if path.is_symlink():
                raise ValueError("Download contém link simbólico inesperado.")
            if path.is_file():
                path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        if not status(store)["installed"]:
            raise LocalImageUnavailable("Download incompleto; modelo ainda não está pronto.")
    return status(store)


def generate(prompt, store=None, steps=20):
    """Inferência local com um modelo já instalado; nunca baixa durante a geração."""
    from src.tools.images import _prompt, _save

    prompt = _prompt(prompt)
    if not isinstance(steps, int) or not 1 <= steps <= 40:
        raise ValueError("Número de passos inválido.")
    detail = status(store)
    if not detail["ready"]:
        raise LocalImageUnavailable("Modelo local não instalado ou dependências ausentes.")
    from openvino_genai import Text2ImagePipeline
    from PIL import Image
    import io

    folder = model_directory(store)
    with _lock:
        pipeline = Text2ImagePipeline(str(folder), "CPU")
        tensor = pipeline.generate(prompt, num_inference_steps=steps)
        picture = Image.fromarray(tensor.data[0])
        output = io.BytesIO()
        picture.save(output, format="PNG")
        result = _save(output.getvalue())
    return {"status": "completed", "kind": "generate", "prompt": prompt, **result}

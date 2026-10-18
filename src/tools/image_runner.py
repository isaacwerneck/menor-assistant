"""Processo filho com duas operações fixas: baixar modelo aprovado e gerar PNG.

Executa em um venv próprio, sem token da API de IA e sem acesso a Git.
Não aceita paths nem comandos enviados pelo modelo de texto.
"""
import io
import json
import stat
import sys

from PIL import Image

from src.agent.model_catalog import MODEL_IMAGE_REPO
from src.tools import local_images
from src.tools.images import _prompt, _save

ALLOW = ("*.xml", "*.bin", "*.json", "*.txt", "*.vocab", "*.model", "*.safetensors")


def install():
    from huggingface_hub import snapshot_download

    folder = local_images.model_directory()
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError("Pasta de modelo inválida.")
    folder.mkdir(mode=0o700, exist_ok=True)
    folder.chmod(0o700)
    snapshot_download(
        repo_id=MODEL_IMAGE_REPO,
        local_dir=str(folder),
        allow_patterns=list(ALLOW),
        ignore_patterns=["*.py", "*.pkl", "*.pickle", "*.pth", "*.pt"],
        max_workers=2,
    )
    for part in folder.rglob("*"):
        if part.is_symlink():
            raise ValueError("Download contém link simbólico inesperado.")
        if part.is_file():
            part.chmod(stat.S_IRUSR | stat.S_IWUSR)
    if not local_images._model_ready(folder):
        raise ValueError("Modelo incompleto, faltam pesos ou configuração.")
    return {"installed": True}


def generate(arguments):
    if not isinstance(arguments, dict) or set(arguments) != {"prompt", "steps"}:
        raise ValueError("Argumentos inválidos.")
    prompt = _prompt(arguments["prompt"])
    steps = arguments["steps"]
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 40:
        raise ValueError("Passos inválidos.")
    folder = local_images.model_directory()
    if not local_images._model_ready(folder):
        raise ValueError("Modelo não está completo.")
    from openvino_genai import Text2ImagePipeline

    pipeline = Text2ImagePipeline(str(folder), "CPU")
    tensor = pipeline.generate(prompt, width=512, height=512,
                               num_inference_steps=steps, num_images_per_prompt=1)
    picture = Image.fromarray(tensor.data[0])
    output = io.BytesIO()
    picture.save(output, format="PNG")
    return {
        "status": "completed", "kind": "generate", "prompt": prompt,
        **_save(output.getvalue()),
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in ("install", "generate"):
        return 2
    try:
        if argv[0] == "install":
            result = install()
        else:
            request = sys.stdin.read(3000)
            if len(request) > 2500:
                raise ValueError("Pedido acima do limite.")
            result = generate(json.loads(request))
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, ImportError):
        # Mensagens internas e paths não atravessam o processo.
        return 1


if __name__ == "__main__":
    sys.exit(main())

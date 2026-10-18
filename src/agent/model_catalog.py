"""Catálogo auditável de subagentes/modelos locais.

A descoberta inicial é limitada a modelos pré-avaliados. O Menor pode
comparar candidatos, mas nunca executar instaladores arbitrários da web.
"""

from dataclasses import dataclass

MODEL_IMAGE_REPO = "OpenVINO/stable-diffusion-v1-5-int8-ov"


@dataclass(frozen=True)
class Candidate:
    id: str
    task: str
    backend: str
    origin: str
    license: str
    disk_gb: int
    requires_approval: bool = True


CANDIDATES = (
    Candidate(
        id="openvino-sd15-int8",
        task="images.generate",
        backend="openvino-genai",
        origin=MODEL_IMAGE_REPO,
        license="creativeml-openrail-m",
        disk_gb=5,  # reserva de instalação, não tamanho exato do download
    ),
)


def discover(task, available_backends=None):
    """Retorna somente candidatos conhecidos; não instala nem chama APIs."""
    if not isinstance(task, str) or len(task) > 80:
        raise ValueError("Capacidade inválida.")
    supported = set(available_backends or ("openvino-genai",))
    return [
        {
            "id": item.id,
            "task": item.task,
            "backend": item.backend,
            "origin": item.origin,
            "license": item.license,
            "reserved_disk_gb": item.disk_gb,
            "approval_required": item.requires_approval,
        }
        for item in CANDIDATES if item.task == task and item.backend in supported
    ]

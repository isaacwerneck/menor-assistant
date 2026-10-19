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


# Candidatos para COMPARAR, não para instalar. Um executor auditado hoje
# existe somente para OpenVINO SD1.5 INT8; jamais afirmar que "só existe ele".
# Fontes oficiais verificadas em 2026-10-18.
OPTIONS = (
    {
        "id": "openvino-sd15-int8",
        "model": MODEL_IMAGE_REPO,
        "url": "https://huggingface.co/OpenVINO/stable-diffusion-v1-5-int8-ov",
        "license": "creativeml-openrail-m",
        "benefit": "Compressão INT8 para Intel e execução local CPU com OpenVINO",
        "caveat": "Não é especializado em sprites ou pixel art; resultado deve ser avaliado",
        "install_supported": True,
        "status": "integrated_not_quality_validated",
    },
    {
        "id": "openvino-sd15-fp16",
        "model": "OpenVINO/stable-diffusion-v1-5-fp16-ov",
        "url": "https://huggingface.co/OpenVINO/stable-diffusion-v1-5-fp16-ov",
        "license": "creativeml-openrail-m",
        "benefit": "Alternativa OpenVINO FP16 para comparar fidelidade",
        "caveat": "Requer benchmark de memória/desempenho e integração separada",
        "install_supported": False,
        "status": "research_required",
    },
    {
        "id": "sd-turbo",
        "model": "stabilityai/sd-turbo",
        "url": "https://huggingface.co/stabilityai/sd-turbo",
        "license": "Verificar condições na documentação oficial",
        "benefit": "Modelo destilado para poucas etapas de geração",
        "caveat": "Integração e qualidade em CPU não avaliadas; licença depende do uso",
        "install_supported": False,
        "status": "research_required",
    },
    {
        "id": "flux-schnell",
        "model": "black-forest-labs/FLUX.1-schnell",
        "url": "https://huggingface.co/black-forest-labs/FLUX.1-schnell",
        "license": "apache-2.0",
        "benefit": "Família mais moderna para investigar fidelidade de prompts",
        "caveat": "Requisitos de memória provavelmente superiores; não avaliado em Intel 32 GB",
        "install_supported": False,
        "status": "research_required",
    },
)


def comparison(task):
    """Relatório de alternativas com proveniência, sem executar pesquisa nem download."""
    if task != "images.generate":
        return []
    return [dict(item) for item in OPTIONS]

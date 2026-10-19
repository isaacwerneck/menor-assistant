"""Worker OCR para uma página PDF. Recebe bytes pelo stdin, nunca um path.

Isolamento parcial: processos limitados e diretório temporário privado.
Executáveis do sistema devem ser instalados apenas com autorização do dono.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from src.tools.file_analysis.contracts import MAX_BYTES, MAX_PAGES

MAX_OUTPUT_BYTES = 12000


def _limits():
    if sys.platform != "linux":
        return
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (22, 23))
    resource.setrlimit(resource.RLIMIT_AS, (1200 * 1024**2, 1200 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (20 * 1024**2, 20 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    if hasattr(resource, "RLIMIT_CORE"):
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _run(argv, timeout):
    output = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    if output.returncode:
        raise ValueError("Processamento OCR local falhou.")
    if len(output.stdout) > MAX_OUTPUT_BYTES:
        raise ValueError("Saída OCR excede o limite de segurança.")
    return output.stdout


def run(page, language, pdf_data):
    if type(page) is not int or not 1 <= page <= MAX_PAGES:
        raise ValueError("Página OCR inválida.")
    if language not in ("por", "eng", "por+eng"):
        raise ValueError("Idioma OCR inválido.")
    if not isinstance(pdf_data, bytes) or not 1 <= len(pdf_data) <= MAX_BYTES:
        raise ValueError("Arquivo PDF vazio ou grande demais.")
    if not pdf_data[:1024].lstrip().startswith(b"%PDF-"):
        raise ValueError("Arquivo não é PDF.")
    with tempfile.TemporaryDirectory(prefix="menor-ocr-") as directory:
        folder = Path(directory)
        original = folder / "input.pdf"
        with original.open("xb") as stream:
            stream.write(pdf_data)
        image_prefix = folder / "page"
        _run([
            "pdftoppm", "-f", str(page), "-l", str(page),
            "-singlefile", "-gray", "-r", "150", "-scale-to", "1600",
            str(original), str(image_prefix),
        ], timeout=18)
        image = folder / "page.pgm"
        if not image.is_file() or image.stat().st_size > 12 * 1024**2:
            raise ValueError("Página renderizada indisponível ou muito grande.")
        output = _run(["tesseract", str(image), "stdout",
                       "-l", language, "--psm", "3"], timeout=18)
    text = output.decode("utf-8", errors="replace").strip()
    return {"status": "executed", "page": page,
            "text": text[:6000], "truncated": len(text) > 6000}


def main():
    _limits()
    if len(sys.argv) != 3:
        raise ValueError("Argumentos inválidos.")
    try:
        page = int(sys.argv[1])
    except ValueError as exc:
        raise ValueError("Página inválida.") from exc
    data = sys.stdin.buffer.read(MAX_BYTES + 1)
    return run(page, sys.argv[2], data)


if __name__ == "__main__":
    try:
        payload = main()
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        payload = {"status": "failed", "error": type(exc).__name__}
    except Exception:
        payload = {"status": "failed", "error": "unexpected_error"}
    # Nunca incluir caminhos privados, stack trace, stdout bruto das ferramentas.
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))

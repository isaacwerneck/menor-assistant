"""Worker de parsing com limites de recursos; recebe somente bytes pelo stdin."""
import json
import sys


def _limits():
    if sys.platform != "linux":
        return
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (12, 13))
    resource.setrlimit(resource.RLIMIT_AS, (900 * 1024**2, 900 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024**2, 2 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    if hasattr(resource, "RLIMIT_CORE"):
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main():
    _limits()
    from src.tools.file_analysis.contracts import MAX_BYTES, FileRejected
    from src.tools.file_analysis.extractors import extract

    if len(sys.argv) != 2:
        raise FileRejected("Formato de chamada inválido.")
    data = sys.stdin.buffer.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise FileRejected("Arquivo excede o limite.")
    return extract(data, sys.argv[1])


if __name__ == "__main__":
    try:
        value = main()
        response = {"status": "executed", "analysis": value}
    except Exception as exc:
        # Não expor stack, caminhos nem dados do documento em mensagens.
        from src.tools.file_analysis.contracts import FileRejected
        message = str(exc) if isinstance(exc, FileRejected) else (
            "Biblioteca opcional ausente." if isinstance(exc, ImportError)
            else "Documento inválido ou não foi possível extrair o conteúdo."
        )
        response = {"status": "failed", "error": message[:175]}
    sys.stdout.write(json.dumps(response, ensure_ascii=False, allow_nan=False))

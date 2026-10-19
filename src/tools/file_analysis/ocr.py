"""OCR explícito e local, página a página, para PDFs digitalizados.

Dependências externas opcionais: Poppler pdftoppm e Tesseract + idioma.
Nenhuma instalação, rede ou reconhecimento de conteúdo visual é presumido.
"""
import json
import os
import shutil
import subprocess
import sys

from src.tools.file_analysis import service
from src.tools.file_analysis.contracts import FILE_ID, FileRejected, MAX_BYTES, MAX_PAGES

VERSION = "1.0.0"
WALL_TIMEOUT = 40
MAX_OUTPUT = 18_000
MAX_OCR_CHARS = 6000
LANGUAGES = {"por": ("por",), "eng": ("eng",), "por+eng": ("por", "eng")}


def _environment():
    # Nenhuma credencial do servidor é fornecida ao renderizador/OCR.
    return {
        "PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "PYTHONPATH": str(service.PROJECT_ROOT),
        "PYTHONIOENCODING": "utf-8",
    }


def status(language="por"):
    if language not in LANGUAGES:
        raise ValueError("Idioma OCR não permitido.")
    renderer = shutil.which("pdftoppm", path=os.defpath)
    engine = shutil.which("tesseract", path=os.defpath)
    base = {
        "tool": "files.ocr", "version": VERSION, "language": language,
        "installed": False, "quality_validated": False, "operational": False,
        "limits": {"pages_per_call": 1, "max_page": MAX_PAGES, "seconds": WALL_TIMEOUT},
    }
    if not renderer or not engine:
        return {**base, "status": "missing_dependency", "reason": (
            "OCR local requer Poppler pdftoppm, Tesseract e dados do idioma; instalação supervisionada."
        )}
    try:
        check = subprocess.run(
            [engine, "--list-langs"], capture_output=True, env=_environment(),
            timeout=5, check=False,
        )
        if check.returncode != 0 or len(check.stdout) + len(check.stderr) > 8192:
            raise ValueError("Falha no catálogo de idiomas.")
        present = set(check.stdout.decode("utf-8", "replace").splitlines())
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {**base, "status": "unavailable", "reason": "Não foi possível consultar idiomas OCR."}
    missing = set(LANGUAGES[language]) - present
    if missing:
        return {**base, "status": "missing_language", "reason": (
            "Tesseract não tem o idioma solicitado: " + ", ".join(sorted(missing))
        )}
    return {
        **base, "status": "dependencies_detected", "installed": True,
        "reason": "Executáveis e idioma detectados; OCR real e precisão ainda não validados.",
    }


def _failed(meta, page, code, message):
    return {
        "tool": "files.ocr", "version": VERSION, "status": "failed",
        "file_id": meta["file_id"], "page": page,
        "error": {"code": code, "message": message},
        "text": "", "evidence": [],
        "validation": {"file_verified": True, "ocr_quality_verified": False},
    }


def ocr_page(file_id, page=1, language="por", *, root=None):
    """Executa OCR só após validar origem e limites; não adiciona texto à memória."""
    if not isinstance(file_id, str) or not FILE_ID.fullmatch(file_id):
        raise FileRejected("Identificador privado de arquivo inválido.")
    if type(page) is not int or not 1 <= page <= MAX_PAGES:
        raise ValueError("Página OCR fora do limite.")
    if language not in LANGUAGES:
        raise ValueError("Idioma OCR não permitido.")
    # Validação anterior ao subprocesso limita o arquivo aos IDs privados.
    meta, data = service._load(file_id, root)
    if meta["format"] != "pdf":
        raise FileRejected("OCR deste executor aceita somente PDF.")
    installed = status(language)
    if not installed["installed"]:
        return {
            "tool": "files.ocr", "version": VERSION, "status": "unavailable",
            "file_id": file_id, "page": page, "dependency_status": installed,
            "text": "", "evidence": [],
            "validation": {"file_verified": True, "ocr_quality_verified": False},
        }
    # Confirma PDF legível e número de páginas no parser protegido.
    structured = service.inspect(file_id, root=root)
    if structured["status"] != "executed":
        return _failed(meta, page, "pdf_parse_failed",
                       "Não foi possível verificar a estrutura do PDF.")
    total = structured.get("metadata", {}).get("pages_total", 0)
    if type(total) is not int or not 1 <= page <= total:
        raise ValueError("Página não existe no PDF.")
    if len(data) > MAX_BYTES:
        raise FileRejected("Arquivo excede o limite.")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "src.tools.file_analysis.ocr_worker",
             str(page), language],
            input=data, capture_output=True, cwd=service.PROJECT_ROOT,
            env=_environment(), timeout=WALL_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired:
        return _failed(meta, page, "timeout", "OCR excedeu o limite de tempo.")
    except OSError:
        return _failed(meta, page, "worker_unavailable", "Executor OCR indisponível.")
    if proc.returncode != 0 or len(proc.stdout) > MAX_OUTPUT:
        return _failed(meta, page, "worker_failed", "OCR não concluiu o processamento.")
    try:
        parsed = json.loads(proc.stdout)
    except (ValueError, UnicodeDecodeError):
        return _failed(meta, page, "invalid_result", "OCR retornou resposta inválida.")
    if (not isinstance(parsed, dict) or parsed.get("status") != "executed"
            or type(parsed.get("page")) is not int or parsed["page"] != page
            or not isinstance(parsed.get("text"), str)
            or len(parsed["text"]) > MAX_OCR_CHARS):
        return _failed(meta, page, "invalid_result", "OCR não retornou texto no contrato.")
    text = parsed["text"]
    return {
        "tool": "files.ocr", "version": VERSION, "status": "executed",
        "file": {"file_id": file_id, "sha256": meta["sha256"],
                 "filename": meta["filename"], "format": "pdf"},
        "page": page, "language": language, "text": text,
        "evidence": [{"kind": "ocr_pdf_page", "page": page,
                      "renderer": "poppler-pdftoppm", "engine": "tesseract",
                      "sha256": meta["sha256"]}],
        "validation": {"file_verified": True, "ocr_quality_verified": False},
        "truncated": parsed.get("truncated") is True,
        "limitations": [
            "Texto OCR é reconhecimento automático, não transcrição verificada.",
            "Acentos, tabelas, orientação, números e layout podem estar incorretos.",
            "Página sem texto OCR não comprova que a página esteja vazia.",
        ],
    }

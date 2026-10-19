"""Contratos de arquivo e inspeção de formatos; sem acesso à rede."""
import importlib.util
import io
from pathlib import PurePath
import re
import zipfile

VERSION = "1.0.0"
MAX_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_FILES = 400
MAX_ARCHIVE_UNCOMPRESSED = 48 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250
MAX_PAGES = 40
MAX_TEXT = 70_000
MAX_SHEETS = 16
MAX_ROWS = 200
MAX_COLS = 24
MAX_PIXELS = 24_000_000
FILE_ID = re.compile(r"^[a-f0-9]{32}$")
EXTENSIONS = {
    ".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx",
    ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp",
    ".gif": "gif", ".bmp": "bmp", ".txt": "text", ".md": "markdown", ".csv": "csv",
}
DEPENDENCIES = {
    "pdf": "pypdf", "docx": "docx", "xlsx": "openpyxl",
    "png": "PIL", "jpeg": "PIL", "webp": "PIL", "gif": "PIL", "bmp": "PIL",
}


class FileRejected(ValueError):
    """Arquivo inválido, grande demais ou formato não suportado."""


def clean_filename(filename):
    if (not isinstance(filename, str) or not 1 <= len(filename) <= 120
            or "/" in filename or "\\" in filename or filename in (".", "..")
            or any(ord(ch) < 32 for ch in filename)):
        raise FileRejected("Nome de arquivo inválido.")
    ext = PurePath(filename).suffix.lower()
    if ext not in EXTENSIONS:
        raise FileRejected("Formato não suportado.")
    return ext


def inspect_archive(data):
    """Recusa ZIP suspeito antes de acionar parsers OOXML."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_ARCHIVE_FILES:
                raise FileRejected("Documento com entradas demais.")
            total = 0
            names = set()
            for item in members:
                name = item.filename
                if (not name or name.startswith("/") or "\\" in name
                        or ".." in name.split("/") or name in names):
                    raise FileRejected("Estrutura de documento inválida.")
                names.add(name)
                if item.flag_bits & 1 or (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise FileRejected("Documento contém entrada não permitida.")
                total += item.file_size
                if (total > MAX_ARCHIVE_UNCOMPRESSED
                        or item.file_size > MAX_ARCHIVE_UNCOMPRESSED
                        or item.file_size > MAX_COMPRESSION_RATIO * max(1, item.compress_size)):
                    raise FileRejected("Documento excede os limites de expansão.")
            if "[Content_Types].xml" not in names:
                raise FileRejected("Documento Office sem estrutura válida.")
            return names
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise FileRejected("Documento Office corrompido.") from exc


def detect(data, filename):
    ext = clean_filename(filename)
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_BYTES:
        raise FileRejected("Arquivo vazio ou maior que 8 MB.")
    expected = EXTENSIONS[ext]
    if expected in ("text", "markdown", "csv"):
        if b"\x00" in data:
            raise FileRejected("Texto contém bytes binários.")
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise FileRejected("Texto deve estar em UTF-8.") from exc
        return expected
    if expected == "pdf":
        if not data[:1024].lstrip().startswith(b"%PDF-"):
            raise FileRejected("Conteúdo não corresponde a PDF.")
        return expected
    if expected in ("docx", "xlsx"):
        if not data.startswith(b"PK"):
            raise FileRejected("Conteúdo não corresponde a documento Office.")
        names = inspect_archive(data)
        marker = "word/document.xml" if expected == "docx" else "xl/workbook.xml"
        if marker not in names:
            raise FileRejected("Documento Office não corresponde à extensão.")
        return expected
    signature = {
        "png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "jpeg": data.startswith(b"\xff\xd8\xff"),
        "webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
        "gif": data.startswith((b"GIF87a", b"GIF89a")),
        "bmp": data.startswith(b"BM"),
    }
    if not signature[expected]:
        raise FileRejected("Conteúdo de imagem não corresponde à extensão.")
    return expected


def capabilities():
    formats = {}
    for fmt in sorted(set(EXTENSIONS.values())):
        dependency = DEPENDENCIES.get(fmt)
        available = dependency is None or importlib.util.find_spec(dependency) is not None
        formats[fmt] = {"status": "available" if available else "missing_dependency",
                        "dependency": dependency}
    return {
        "name": "files.inspect", "version": VERSION,
        "input": {"ingest": ["bytes", "filename"], "inspect": ["file_id"]},
        "limits": {"bytes": MAX_BYTES, "pages": MAX_PAGES, "sheets": MAX_SHEETS,
                   "rows_per_sheet": MAX_ROWS, "image_pixels": MAX_PIXELS},
        "formats": formats, "visual_understanding": "not_integrated",
        "ocr": "not_integrated", "writes": "private_attachment_only",
        "result_statuses": ["executed", "failed"],
    }

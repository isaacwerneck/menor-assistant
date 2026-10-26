"""PathSentinel: Validador de segurança defensiva contra path traversal e acessos indevidos.

Garante que qualquer leitura ou gravação de arquivos feita pelo assistente,
pelo laboratório ou pela API permaneça estritamente contida dentro do diretório permitido.
"""
import os
from pathlib import Path
from typing import Optional, Set

MAX_SAFE_FILE_SIZE = 10 * 1024 * 1024  # 10 MiB


class SecurityPathError(ValueError):
    """Exceção levantada quando um caminho viola regras de segurança."""
    pass


class PathSentinel:
    """Sentinela de caminhos seguros do sistema de arquivos."""

    def __init__(self, allowed_base: Optional[Path] = None, allowed_extensions: Optional[Set[str]] = None):
        base = allowed_base or Path(os.environ.get("MENOR_DATA_DIR", "~/menor-data"))
        self.allowed_base = Path(base).expanduser().resolve()
        self.allowed_extensions = allowed_extensions

    def resolve_safe_path(self, relative_path: str, must_exist: bool = False) -> Path:
        """Resolve e valida rigorosamente um caminho relativo contra traversal e symlinks."""
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise SecurityPathError("Caminho não pode ser vazio ou nulo.")

        # Rejeitar caracteres perigosos como null bytes
        if "\0" in relative_path or any(ord(c) < 32 for c in relative_path if c not in "\t\n\r"):
            raise SecurityPathError("Caminho contém caracteres de controle inválidos.")

        clean_rel = relative_path.strip().replace("\\", "/").lstrip("/")

        # Detecção explícita de componentes '..'
        parts = clean_rel.split("/")
        if ".." in parts or "." in parts:
            clean_parts = [p for p in parts if p not in ("", ".")]
            if ".." in clean_parts:
                raise SecurityPathError("Tentativa de path traversal ('..') detectada.")
            clean_rel = "/".join(clean_parts)

        raw_target = self.allowed_base / clean_rel
        cur = raw_target
        while cur != self.allowed_base and cur != cur.parent:
            if cur.is_symlink():
                raise SecurityPathError("Acesso através de links simbólicos é estritamente proibido.")
            cur = cur.parent

        target = raw_target.resolve()

        # O caminho resolvido DEVE começar com o allowed_base
        try:
            target.relative_to(self.allowed_base)
        except ValueError:
            raise SecurityPathError(f"Caminho escapa da raiz permitida: {target}")

        # Bloqueio estrito de links simbólicos (symlink traversal attack)
        if raw_target.is_symlink() or target.is_symlink():
            raise SecurityPathError("Acesso através de links simbólicos é estritamente proibido.")

        # Validação de extensões permitidas se configurada
        if self.allowed_extensions:
            ext = target.suffix.lower()
            if ext not in self.allowed_extensions:
                raise SecurityPathError(f"Extensão de arquivo '{ext}' não permitida.")

        if must_exist and not target.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {clean_rel}")

        return target

    def safe_read_text(self, relative_path: str, max_bytes: int = MAX_SAFE_FILE_SIZE) -> str:
        """Lê arquivo de forma segura após validar caminho e tamanho."""
        target = self.resolve_safe_path(relative_path, must_exist=True)
        if not target.is_file():
            raise SecurityPathError(f"Caminho não aponta para um arquivo regular: {relative_path}")

        size = target.stat().st_size
        if size > max_bytes:
            raise SecurityPathError(f"Arquivo excede o limite seguro de {max_bytes} bytes.")

        return target.read_text(encoding="utf-8", errors="replace")

    def safe_write_text(self, relative_path: str, content: str) -> int:
        """Escreve arquivo atomicamente após validar caminho."""
        if not isinstance(content, str):
            raise SecurityPathError("Conteúdo precisa ser uma string.")

        target = self.resolve_safe_path(relative_path, must_exist=False)
        target.parent.mkdir(parents=True, exist_ok=True)

        tmp_file = target.with_suffix(f"{target.suffix}.tmp.{os.getpid()}")
        try:
            tmp_file.write_text(content, encoding="utf-8")
            tmp_file.replace(target)
            return len(content.encode("utf-8"))
        except Exception as e:
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except OSError:
                    pass
            raise e

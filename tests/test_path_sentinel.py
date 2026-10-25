"""Testes de unidade para PathSentinel (prevenção de Path Traversal e Symlink attacks)."""
import os
import tempfile
import unittest
from pathlib import Path

from src.security.path_sentinel import PathSentinel, SecurityPathError


class TestPathSentinel(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.sentinel = PathSentinel(allowed_base=self.base_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_safe_write_and_read(self):
        rel_path = "notas/test.md"
        content = "# Teste de Segurança\nConteúdo seguro."
        written = self.sentinel.safe_write_text(rel_path, content)
        self.assertGreater(written, 0)

        read_content = self.sentinel.safe_read_text(rel_path)
        self.assertEqual(read_content, content)

    def test_reject_traversal_double_dot(self):
        with self.assertRaises(SecurityPathError):
            self.sentinel.resolve_safe_path("../secret.txt")

        with self.assertRaises(SecurityPathError):
            self.sentinel.resolve_safe_path("pasta/../../etc/passwd")

    def test_reject_null_byte(self):
        with self.assertRaises(SecurityPathError):
            self.sentinel.resolve_safe_path("arquivo\0.txt")

    def test_extension_allowlist(self):
        strict_sentinel = PathSentinel(allowed_base=self.base_path, allowed_extensions={".md", ".txt"})
        safe_path = strict_sentinel.resolve_safe_path("docs/readme.md")
        self.assertTrue(str(safe_path).endswith("readme.md"))

        with self.assertRaises(SecurityPathError):
            strict_sentinel.resolve_safe_path("malicioso.py")

    def test_symlink_rejection(self):
        if os.name == "nt":
            # Em Windows, symlinks requerem permissão de desenvolvedor
            return
        real_file = self.base_path / "real.txt"
        real_file.write_text("ok")
        sym_file = self.base_path / "link.txt"
        sym_file.symlink_to(real_file)

        with self.assertRaises(SecurityPathError):
            self.sentinel.resolve_safe_path("link.txt")


if __name__ == "__main__":
    unittest.main()

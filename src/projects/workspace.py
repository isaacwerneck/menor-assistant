"""Projetos Markdown: listagem, retomada de contexto e anotações por seção.

As ações só operam nas quatro notas predefinidas, dentro de projetos existentes.
A escolha do projeto ativo pertence à conversa; não se infere o projeto global.
"""

import re
from datetime import datetime, timezone

from src.memory.store import BrainStore, _write_lock

SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,62}[a-z0-9])$")
FILES = {
    "context": "contexto.md",
    "decision": "decisoes.md",
    "task": "tarefas.md",
    "log": "diario.md",
}
SOURCES = ("context", "decision", "task", "log")


class ProjectWorkspace:
    def __init__(self, store=None):
        self.store = store if store is not None else BrainStore()

    @staticmethod
    def _slug(slug):
        if not isinstance(slug, str) or not SLUG.fullmatch(slug) or slug == "exemplo-de-projeto":
            raise ValueError("Projeto inválido.")
        return slug

    def _path(self, slug, section):
        return f"projetos/{self._slug(slug)}/{FILES[section]}"

    def _check_project(self, slug):
        slug = self._slug(slug)
        root = self.store.brain_dir / "projetos" / slug
        if root.is_symlink() or not root.is_dir():
            raise LookupError("Projeto não encontrado.")
        for filename in FILES.values():
            target = root / filename
            if target.is_symlink() or not target.is_file():
                raise LookupError("Projeto incompleto ou inválido.")
        return root

    def list_projects(self):
        root = self.store.brain_dir / "projetos"
        if not root.exists():
            return []
        if root.is_symlink() or not root.is_dir():
            raise ValueError("Pasta de projetos inválida.")
        projects = []
        for child in root.iterdir():
            try:
                self._check_project(child.name)
                content = self.store.read_note(f"projetos/{child.name}/contexto.md")
            except (ValueError, LookupError, OSError):
                continue
            title = next((line[2:].strip() for line in content.splitlines() if line.startswith("# ")), "")
            projects.append({"slug": child.name, "name": title[:80] or child.name})
        return sorted(projects, key=lambda item: item["name"].casefold())[:100]

    def read_project(self, slug):
        self._check_project(slug)
        files = {name: self.store.read_note(self._path(slug, name)) for name in SOURCES}
        title = next((line[2:].strip() for line in files["context"].splitlines() if line.startswith("# ")), slug)
        return {"slug": slug, "name": title[:80], "notes": files}

    def append(self, slug, kind, text, origin="chat"):
        if kind not in ("decision", "task", "log"):
            raise ValueError("Essa seção não permite novas anotações.")
        if origin not in ("chat", "painel"):
            raise ValueError("Origem desconhecida.")
        value = self.store._memory_text(text)
        with _write_lock:
            self._check_project(slug)
            path = self._path(slug, kind)
            current = self.store.read_note(path)
            if kind == "task":
                line = "- [ ] " + value
            else:
                date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                line = f"- {date} — {value} (origem: {origin})"
            if line not in current.splitlines():
                self.store.write_note(path, current.rstrip() + "\n\n" + line + "\n")
        return {"project": slug, "section": kind, "path": path, "saved": line}

    def context(self, slug, max_chars=2400):
        """Gera dados delimitados e com fonte, dentro do orçamento de contexto."""
        project = self.read_project(slug)
        lines = [f"Projeto ativo: {project['name']} (projetos/{slug}/)"]
        length = len(lines[0])
        for section in SOURCES:
            document = project["notes"][section]
            # Captura cabeçalho e anotações finais, preservando decisões recentes.
            head = document[:450] if section == "context" else document[-850:]
            item = f"[projetos/{slug}/{FILES[section]}]\n{head.strip()}"
            if length + len(item) + 2 > max_chars:
                continue
            lines.append(item)
            length += len(item) + 2
        return "\n\n".join(lines)

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
        projects = self.store.brain_dir / "projetos"
        if self.store.data_dir.is_symlink() or self.store.brain_dir.is_symlink():
            raise ValueError("Diretório privado inválido.")
        if projects.is_symlink() or not projects.is_dir():
            raise LookupError("Diretório de projetos indisponível.")
        root = projects / slug
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
        if self.store.brain_dir.is_symlink() or root.is_symlink() or not root.is_dir():
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

    DECISION_BEGIN = "<!-- menor:active-decisions:start -->"
    DECISION_END = "<!-- menor:active-decisions:end -->"

    @staticmethod
    def _decision_entry(topic, value):
        if (not isinstance(topic, str) or not 3 <= len(topic.strip()) <= 60
                or any(c in topic for c in "\n\r\t*#<>[]|\\:")):
            raise ValueError("Tema da decisão inválido.")
        if (not isinstance(value, str) or not 1 <= len(value.strip()) <= 280
                or any(ord(c) < 32 for c in value)):
            raise ValueError("Conteúdo de decisão inválido.")
        label = " ".join(topic.split())
        content = " ".join(value.split())
        if not label or not content:
            raise ValueError("Decisão vazia.")
        return label, content

    @classmethod
    def _split_decisions(cls, document):
        begin = document.find(cls.DECISION_BEGIN)
        end = document.find(cls.DECISION_END)
        if begin == end == -1:
            return document.rstrip() + "\n\n", [], ""
        if (begin < 0 or end < begin or document.count(cls.DECISION_BEGIN) != 1
                or document.count(cls.DECISION_END) != 1):
            raise ValueError("Bloco de decisões inválido.")
        prefix = document[:begin]
        interior = document[begin + len(cls.DECISION_BEGIN):end]
        suffix = document[end + len(cls.DECISION_END):]
        lines = [line for line in interior.splitlines() if line.strip()]
        if len(lines) > 100:
            raise ValueError("Limite de decisões atingido.")
        entries = []
        for line in lines:
            if not line.startswith("- ") or ": " not in line:
                raise ValueError("Decisão armazenada inválida.")
            topic, value = line[2:].split(": ", 1)
            label, content = cls._decision_entry(topic, value)
            if any(old[0].casefold() == label.casefold() for old in entries):
                raise ValueError("Decisões duplicadas.")
            entries.append((label, content))
        return prefix, entries, suffix

    def set_decision(self, slug, topic, value):
        """Registra uma escolha atual; correções substituem a escolha anterior."""
        label, content = self._decision_entry(topic, value)
        if len(label) + len(content) > 300:
            raise ValueError("Decisão extensa demais.")
        with _write_lock:
            self._check_project(slug)
            path = self._path(slug, "decision")
            current = self.store.read_note(path)
            prefix, entries, suffix = self._split_decisions(current)
            previous = next((v for t, v in entries if t.casefold() == label.casefold()), None)
            if previous == content:
                return {"project": slug, "section": "decision", "path": path,
                        "topic": label, "value": content, "change": "unchanged"}
            entries = [(t, v) for t, v in entries if t.casefold() != label.casefold()]
            if len(entries) >= 100:
                raise ValueError("Limite de decisões atingido.")
            entries.append((label, content))
            updated = (prefix.rstrip() + "\n\n" + self.DECISION_BEGIN + "\n"
                       + "\n".join(f"- {t}: {v}" for t, v in entries) + "\n"
                       + self.DECISION_END + "\n" + suffix.lstrip("\n"))
            self.store.write_note(path, updated)
        return {"project": slug, "section": "decision", "path": path,
                "topic": label, "value": content,
                "change": "revised" if previous is not None else "created"}

    def context(self, slug, max_chars=2400):
        """Gera dados delimitados e com fonte, dentro do orçamento de contexto."""
        project = self.read_project(slug)
        lines = [f"Projeto ativo: {project['name']} (projetos/{slug}/)"]
        length = len(lines[0])
        # Prioridade ao que foi decidido mais recentemente; o contexto
        # descritivo vem depois, sem ocultar decisões por excesso de tokens.
        for section in ("decision", "context", "task", "log"):
            document = project["notes"][section]
            # Decisões vigentes têm precedência sobre notas históricas; os dois
            # fragmentos são dados de projeto, não instruções ao agente.
            if section == "decision":
                _, active, _ = self._split_decisions(document)
                current = "\n".join(f"- {topic}: {value}" for topic, value in active[-8:])
                head = (("Decisões atuais:\n" + current)[:min(520, max_chars // 2)]
                        if current else document[-min(350, max_chars // 2):])
            else:
                head = document[:450] if section == "context" else document[-850:]
            item = f"[projetos/{slug}/{FILES[section]}]\n{head.strip()}"
            if length + len(item) + 2 > max_chars:
                continue
            lines.append(item)
            length += len(item) + 2
        return "\n\n".join(lines)

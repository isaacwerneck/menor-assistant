"""Leitura, edição e remoção controladas de aprendizados Markdown.

Somente a nota de conhecimentos gerais é modificada. IDs são derivados
da linha atual para rejeitar edições obsoletas (outro navegador/edição manual).
"""

import hashlib
import re

from src.memory.store import BrainStore, _write_lock

SOURCE = "conhecimentos/aprendizados_gerais.md"
ENTRY_ID = re.compile(r"^([1-9][0-9]{0,5})\.([0-9a-f]{16})$")
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2} — )(.*)$")


def _identifier(line_number, raw):
    stamp = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{line_number}.{stamp}"


def _entry(line_number, raw):
    if not raw.startswith("- "):
        return None
    text = raw[2:].strip()
    if not text:
        return None
    match = DATE_PREFIX.match(text)
    return {
        "id": _identifier(line_number, raw),
        "text": match.group(2) if match else text,
        "date": match.group(1)[:10] if match else None,
        "source": SOURCE,
    }


class KnowledgeManager:
    def __init__(self, store=None):
        self.store = store or BrainStore()

    def list(self, limit=100):
        if not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("Limite inválido.")
        if not self.store.brain_dir.exists():
            return []
        with _write_lock:
            return [
                entry for n, line in enumerate(self.store.read_note(SOURCE).splitlines(), start=1)
                if (entry := _entry(n, line))
            ][-limit:][::-1]

    def change(self, entry_id, action, value=None):
        if not isinstance(entry_id, str) or not ENTRY_ID.fullmatch(entry_id):
            raise ValueError("Identificador de conhecimento inválido.")
        if action not in ("edit", "delete"):
            raise ValueError("Ação inválida.")
        if action == "edit":
            value = self.store._memory_text(value)
        with _write_lock:
            lines = self.store.read_note(SOURCE).splitlines()
            index = int(entry_id.split(".", 1)[0]) - 1
            if not 0 <= index < len(lines) or _identifier(index + 1, lines[index]) != entry_id:
                raise LookupError("A anotação mudou; atualize a lista e tente novamente.")
            previous = _entry(index + 1, lines[index])
            if not previous:
                raise LookupError("Anotação não encontrada.")
            if action == "delete":
                del lines[index]
                updated = None
            else:
                old_text = lines[index][2:]
                date = DATE_PREFIX.match(old_text)
                prefix = date.group(1) if date else ""
                lines[index] = "- " + prefix + value
                updated = _entry(index + 1, lines[index])
            self.store.write_note(SOURCE, "\n".join(lines).rstrip() + "\n")
        return {"action": action, "entry": updated, "previous": previous}

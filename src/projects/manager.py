"""Criação controlada de pastas e documentos de projetos no cérebro."""

import re
import unicodedata
from pathlib import Path

from src.memory.store import BrainStore, _write_lock


def slugify(name):
    if not isinstance(name, str) or not 3 <= len(name.strip()) <= 64:
        raise ValueError("Nome de projeto precisa ter de 3 a 64 caracteres.")
    if any(not (c.isalnum() or c in " -_") for c in name):
        raise ValueError("Nome contém caracteres não permitidos.")
    name = name.strip()
    folded = unicodedata.normalize("NFKD", name.casefold())
    ascii_name = "".join(c for c in folded if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    if len(slug) < 3 or len(slug) > 64 or slug in ("exemplo-de-projeto", "arquivados"):
        raise ValueError("Nome de projeto inválido.")
    return slug


def create_project(name, store=None):
    """Cria projeto nomeado; nunca altera pastas fora do cérebro nem sobrescreve arquivos."""
    store = store if store is not None else BrainStore()
    slug = slugify(name)
    store.initialize()
    root = f"projetos/{slug}"
    files = {
        "contexto.md": f"# {name}\n\n## Objetivo\n\nA definir.\n\n## Estado\n\nIniciado.\n",
        "decisoes.md": "# Decisões\n\n",
        "tarefas.md": "# Tarefas\n\n- [ ] Definir o primeiro passo.\n",
        "diario.md": "# Diário\n\n",
    }
    with _write_lock:
        directory = store.brain_dir / Path(root)
        if directory.exists() or directory.is_symlink():
            raise ValueError("Já existe um projeto com esse nome.")
        store._directories(("projetos", slug, "arquivos"))
        for filename, contents in files.items():
            store.write_note(f"{root}/{filename}", contents)
    return {"name": name, "slug": slug, "path": root, "files": list(files)}

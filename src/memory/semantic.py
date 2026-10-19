"""Busca semântica privada com embeddings do Ollama. Sem API externa.

Só ativa quando MENOR_EMBED_MODEL é configurado; caso contrário FTS5 continua
operando. Índice reconstruível, fontes limitadas e nenhuma execução de textos.
"""
from contextlib import closing
import hashlib
import json
import math
import os
import re
import sqlite3
import threading

import requests

from src.memory.store import BrainStore

_LOCK = threading.RLock()
MAX_ENTRIES = 150


def _chunks(store):
    entries = []
    sources = ["conhecimentos/aprendizados_gerais.md"]
    root = store.brain_dir / "conhecimentos"
    for note in sorted(root.glob("*/estudo-*.md")):
        path = note.relative_to(store.brain_dir).as_posix()
        if re.fullmatch(r"conhecimentos/[a-z0-9-]+/estudo-[0-9a-f]{16}\.md", path):
            sources.append(path)
    for source in sources[:200]:
        note = store.read_note(source)
        for line, text in enumerate(note.splitlines(), 1):
            trimmed = text.strip().lstrip("- ").strip()
            if 18 <= len(trimmed) <= 850 and not trimmed.startswith("#"):
                entries.append((source, line, trimmed))
                if len(entries) >= MAX_ENTRIES:
                    return entries
    return entries


def _embed(items):
    model = os.environ.get("MENOR_EMBED_MODEL", "").strip()
    if not model:
        raise ValueError("Modelo de embeddings local não configurado.")
    endpoint = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    result = requests.post(endpoint + "/api/embed", json={
        "model": model, "input": items, "truncate": True,
    }, timeout=(3, 35))
    result.raise_for_status()
    vectors = result.json().get("embeddings")
    if not isinstance(vectors, list) or len(vectors) != len(items):
        raise ValueError("Embeddings ausentes.")
    width = len(vectors[0]) if vectors else 0
    if not 8 <= width <= 4096:
        raise ValueError("Dimensão de vetor inesperada.")
    for vector in vectors:
        if (not isinstance(vector, list) or len(vector) != width
                or any(type(n) not in (float, int) or not math.isfinite(n) for n in vector)):
            raise ValueError("Vetor de embedding inválido.")
        if sum(x * x for x in vector) == 0:
            raise ValueError("Vetor vazio.")
    return vectors


class SemanticIndex:
    def __init__(self, store=None):
        self.store = store if store is not None else BrainStore()
        self.path = self.store.brain_dir / "memoria" / "semantico.sqlite"

    def _connect(self):
        self.store._directories(("memoria",))
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise ValueError("Índice semântico inválido.")
        if not self.path.exists():
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
            try:
                fd = os.open(self.path, flags, 0o600)
                os.close(fd)
            except FileExistsError:
                if self.path.is_symlink():
                    raise ValueError("Índice semântico inválido.") from None
        self.path.chmod(0o600)
        conn = sqlite3.connect(self.path, timeout=6)
        conn.execute("CREATE TABLE IF NOT EXISTS chunks ("
                     "source TEXT, line INTEGER, checksum TEXT, content TEXT, vector TEXT, "
                     "PRIMARY KEY(source, line))")
        return conn

    def search(self, query, limit=3):
        if not os.environ.get("MENOR_EMBED_MODEL", "").strip():
            return []
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1500:
            raise ValueError("Consulta semântica inválida.")
        if not isinstance(limit, int) or not 1 <= limit <= 5:
            raise ValueError("Limite inválido.")
        with _LOCK:
            passages = _chunks(self.store)
            with closing(self._connect()) as conn:
                keys = set((source, line) for source, line, _ in passages)
                with conn:
                    for source, line in conn.execute("SELECT source, line FROM chunks").fetchall():
                        if (source, line) not in keys:
                            conn.execute("DELETE FROM chunks WHERE source=? AND line=?", (source, line))
                cached = {
                    (source, line): (checksum, vector)
                    for source, line, checksum, vector in conn.execute(
                        "SELECT source,line,checksum,vector FROM chunks"
                    )
                }
                missing = [
                    (source, line, text, hashlib.sha256(text.encode("utf-8")).hexdigest())
                    for source, line, text in passages
                    if (source, line) not in cached
                    or cached[(source, line)][0] != hashlib.sha256(text.encode("utf-8")).hexdigest()
                ]
                for i in range(0, len(missing), 16):
                    batch = missing[i:i + 16]
                    vectors = _embed([item[2] for item in batch])
                    with conn:
                        conn.executemany(
                            "INSERT INTO chunks VALUES (?,?,?,?,?) ON CONFLICT(source,line)"
                            " DO UPDATE SET checksum=excluded.checksum, content=excluded.content,"
                            " vector=excluded.vector",
                            [(src, line, sha, text, json.dumps(vec))
                             for (src, line, text, sha), vec in zip(batch, vectors)],
                        )
                if not passages:
                    return []
                query_vec = _embed([query[:1500]])[0]
                n_query = math.sqrt(sum(x*x for x in query_vec))
                scored = []
                for source, line, content, vector in conn.execute(
                    "SELECT source,line,content,vector FROM chunks"
                ):
                    values = json.loads(vector)
                    if len(values) != len(query_vec):
                        continue
                    denom = n_query * math.sqrt(sum(x*x for x in values))
                    score = sum(a*b for a, b in zip(query_vec, values)) / denom if denom else 0
                    if score >= 0.28:
                        scored.append((score, source, line, content))
        scored.sort(reverse=True)
        return [
            {"score": round(score, 3), "source": source, "line": line, "content": content}
            for score, source, line, content in scored[:limit]
        ]


def relevant_context(query, store=None, max_chars=1200):
    if not os.environ.get("MENOR_EMBED_MODEL", "").strip():
        return ""
    matches = SemanticIndex(store).search(query)
    lines = []
    for entry in matches:
        rendered = f"- {entry['content']} ({entry['source']}:L{entry['line']})"
        if len("\n".join(lines + [rendered])) > max_chars:
            break
        lines.append(rendered)
    return "\n".join(lines)

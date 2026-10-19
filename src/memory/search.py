"""Índice textual reconstruível de conhecimentos Markdown, sem cloud nem embeddings."""

import hashlib
from contextlib import closing
import os
import re
import sqlite3
import stat
import threading
import unicodedata

from src.memory.store import BrainStore

_INDEX_LOCK = threading.RLock()
_SOURCE = "conhecimentos/aprendizados_gerais.md"
_STOPWORDS = frozenset((
    "a", "as", "o", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "sobre", "ao",
    "e", "ou", "que", "se", "eu", "tu", "ele", "ela", "voce", "voces", "meu",
    "minha", "meus", "minhas", "seu", "seus", "sua", "suas", "esse", "essa",
    "isso", "disto", "disso", "aqui", "ali", "qual", "quais", "como", "quando",
    "onde", "porque", "mais", "menos", "agora", "depois", "antes", "muito",
    "muita", "pode", "posso", "quero", "queria", "fazer", "falou", "falar",
    "diz", "disse", "diga", "lembra", "lembrar", "lembre", "sabe", "sabemos",
    "aprendeu", "aprendemos", "menor", "projeto", "projetos", "jogo", "jogos",
    "usar", "usamos", "uso", "tem", "tenho", "ficou", "ficar", "ser", "esta",
    "estou", "estamos", "era", "foi", "sao", "sou", "tambem", "minha",
))


def _tokens(value):
    """Termos significativos, normalizados para PT-BR e seguros para MATCH."""
    folded = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(char for char in folded if not unicodedata.combining(char))
    tokens = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
    return list(dict.fromkeys(
        term for term in tokens if len(term) >= 3 and term not in _STOPWORDS and len(term) <= 36
    ))


class KnowledgeIndex:
    """Mantém cache FTS5 sincronizado com as notas, sem dependências externas."""

    def __init__(self, store=None):
        self.store = store if store is not None else BrainStore()
        self.database = self.store.brain_dir / "memoria" / "indice.sqlite"

    def _prepare_database(self):
        self.store._directories(("memoria",))
        if self.database.is_symlink():
            raise ValueError("Índice de memória não pode ser link simbólico.")
        if self.database.exists():
            mode = self.database.lstat().st_mode
            if not stat.S_ISREG(mode):
                raise ValueError("Índice de memória deve ser arquivo regular.")
        else:
            try:
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
                flags |= getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(self.database, flags, 0o600)
                os.close(fd)
            except FileExistsError:
                if self.database.is_symlink() or not self.database.is_file():
                    raise ValueError("Índice de memória inválido.") from None
        self.database.chmod(0o600)

    @staticmethod
    def _entries(markdown):
        for line_number, raw in enumerate(markdown.splitlines(), start=1):
            if not raw.startswith("- "):
                continue
            text = raw[2:].strip()
            text = re.sub(r"^\d{4}-\d{2}-\d{2} — ", "", text)
            if text and len(text) <= 2000:
                yield text, line_number

    def _connect(self):
        self._prepare_database()
        conn = sqlite3.connect(self.database, timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("CREATE TABLE IF NOT EXISTS snapshot (source TEXT PRIMARY KEY, checksum TEXT NOT NULL)")
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING "
            "fts5(content, source UNINDEXED, line UNINDEXED, tokenize='unicode61 remove_diacritics 2')"
        )
        return conn

    def _sync(self, conn):
        sources = [_SOURCE]
        folder = self.store.brain_dir / "conhecimentos"
        for note in sorted(folder.glob("*/estudo-*.md")):
            relative = note.relative_to(self.store.brain_dir).as_posix()
            if re.fullmatch(r"conhecimentos/[a-z0-9-]+/estudo-[0-9a-f]{16}\.md", relative):
                sources.append(relative)
            if len(sources) > 200:
                raise ValueError("Índice excedeu o limite de 200 notas; revise o acervo.")
        with conn:
            for (stale,) in conn.execute("SELECT source FROM snapshot").fetchall():
                if stale not in sources:
                    conn.execute("DELETE FROM knowledge_fts WHERE source=?", (stale,))
                    conn.execute("DELETE FROM snapshot WHERE source=?", (stale,))
            for source in sources:
                markdown = self.store.read_note(source)
                checksum = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
                existing = conn.execute("SELECT checksum FROM snapshot WHERE source=?", (source,)).fetchone()
                if existing and existing[0] == checksum:
                    continue
                conn.execute("DELETE FROM knowledge_fts WHERE source=?", (source,))
                conn.executemany(
                    "INSERT INTO knowledge_fts(content, source, line) VALUES (?, ?, ?)",
                    [(text, source, line) for text, line in self._entries(markdown)],
                )
                conn.execute(
                    "INSERT INTO snapshot(source, checksum) VALUES (?, ?) "
                    "ON CONFLICT(source) DO UPDATE SET checksum=excluded.checksum", (source, checksum),
                )

    def search(self, query, limit=3):
        """Busca só aprendizados relacionados. Retorna texto, origem e linha."""
        if not isinstance(query, str) or not isinstance(limit, int) or not 1 <= limit <= 5:
            raise ValueError("Consulta de memória inválida.")
        terms = _tokens(query[:2000])[:12]
        if not terms:
            return []
        expression = " OR ".join(f'"{term}"' for term in terms)
        minimum_overlap = 2 if len(terms) >= 5 else 1
        with _INDEX_LOCK:
            with closing(self._connect()) as conn:
                self._sync(conn)
                candidates = conn.execute(
                    "SELECT content, source, line FROM knowledge_fts "
                    "WHERE knowledge_fts MATCH ? ORDER BY bm25(knowledge_fts) LIMIT 30",
                    (expression,),
                ).fetchall()
        found = []
        for text, source, line in candidates:
            if len(set(_tokens(text)).intersection(terms)) < minimum_overlap:
                continue
            found.append({"content": text, "source": source, "line": int(line)})
            if len(found) == limit:
                break
        return found


def contextual_knowledge(query, store=None, max_chars=1200):
    """Retorna trechos com fonte para consulta; não são instruções ao modelo."""
    matches = KnowledgeIndex(store).search(query)
    lines = []
    length = 0
    for entry in matches:
        item = f"- {entry['content']} ({entry['source']}:L{entry['line']})"
        if length + len(item) + 1 > max_chars:
            break
        lines.append(item)
        length += len(item) + 1
    return "\n".join(lines)

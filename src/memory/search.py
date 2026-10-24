"""Índice híbrido reconstruível de conhecimentos: FTS5 + Embeddings com similaridade cosseno.

Sem cloud nem dependências externas pesadas: suporta embeddings locais do Ollama
e fallback determinístico para busca semântica e deduplicação estilo Mem0.
"""

from contextlib import closing
import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import threading
from typing import Any, Dict, List, Optional
import unicodedata

import requests

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


def _tokens(value: str) -> List[str]:
    """Termos significativos, normalizados para PT-BR e seguros para MATCH."""
    folded = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(char for char in folded if not unicodedata.combining(char))
    tokens = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
    return list(dict.fromkeys(
        term for term in tokens if len(term) >= 3 and term not in _STOPWORDS and len(term) <= 36
    ))


def compute_vector(text: str, dimension: int = 64) -> List[float]:
    """Gera vetor determinístico normalizado (L2) a partir de termos e n-grams."""
    vec = [0.0] * dimension
    tokens = _tokens(text)
    if not tokens:
        clean = re.sub(r"\s+", "", text.lower())
        tokens = [clean[i:i + 3] for i in range(len(clean) - 2)] or [clean]
    for token in tokens:
        idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dimension
        vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0.0:
        return [x / norm for x in vec]
    return vec


def get_embedding(text: str, ollama_url: Optional[str] = None) -> List[float]:
    """Obtém embedding de modelo local Ollama ou fallback determinístico."""
    if ollama_url:
        try:
            resp = requests.post(
                f"{ollama_url.rstrip('/')}/api/embeddings",
                json={"model": "nomic-embed-text", "prompt": text[:2000]},
                timeout=2,
            )
            if resp.status_code == 200:
                emb = resp.json().get("embedding")
                if emb and isinstance(emb, list) and len(emb) > 0:
                    norm = math.sqrt(sum(float(x) * float(x) for x in emb))
                    if norm > 0.0:
                        return [float(x) / norm for x in emb]
                    return [float(x) for x in emb]
        except Exception:
            pass
    return compute_vector(text)


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calcula a similaridade cosseno entre dois vetores unitários."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    return max(0.0, min(1.0, dot))


class KnowledgeIndex:
    """Mantém cache FTS5 e vetores sincronizados com as notas Markdown."""

    def __init__(self, store: Optional[BrainStore] = None, ollama_url: Optional[str] = None):
        self.store = store if store is not None else BrainStore()
        self.ollama_url = ollama_url or os.environ.get("OLLAMA_URL")
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
    def _entries(markdown: str):
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
        conn.execute(
            "CREATE TABLE IF NOT EXISTS memory_vectors ("
            "id TEXT PRIMARY KEY, source TEXT, content TEXT, embedding TEXT, updated_at TIMESTAMP"
            ")"
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
                    conn.execute("DELETE FROM memory_vectors WHERE source=?", (stale,))
                    conn.execute("DELETE FROM snapshot WHERE source=?", (stale,))
            for source in sources:
                markdown = self.store.read_note(source)
                checksum = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
                existing = conn.execute("SELECT checksum FROM snapshot WHERE source=?", (source,)).fetchone()
                if existing and existing[0] == checksum:
                    continue
                conn.execute("DELETE FROM knowledge_fts WHERE source=?", (source,))
                conn.execute("DELETE FROM memory_vectors WHERE source=?", (source,))
                entries = list(self._entries(markdown))
                conn.executemany(
                    "INSERT INTO knowledge_fts(content, source, line) VALUES (?, ?, ?)",
                    [(text, source, line) for text, line in entries],
                )
                vector_rows = []
                for text, line in entries:
                    row_id = hashlib.sha256(f"{source}:{line}:{text}".encode("utf-8")).hexdigest()[:16]
                    vec = get_embedding(text, self.ollama_url)
                    vector_rows.append((row_id, source, text, json.dumps(vec)))
                if vector_rows:
                    conn.executemany(
                        "INSERT OR REPLACE INTO memory_vectors(id, source, content, embedding, updated_at) "
                        "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                        vector_rows,
                    )
                conn.execute(
                    "INSERT INTO snapshot(source, checksum) VALUES (?, ?) "
                    "ON CONFLICT(source) DO UPDATE SET checksum=excluded.checksum", (source, checksum),
                )

    def search(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Busca textual FTS5 em aprendizados. Retorna texto, origem e linha."""
        if not isinstance(query, str) or not isinstance(limit, int) or not 1 <= limit <= 10:
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

    def search_hybrid(self, query: str, limit: int = 3, alpha: float = 0.5) -> List[Dict[str, Any]]:
        """Busca híbrida combinando BM25 (FTS5) com similaridade cosseno de vetores."""
        if not isinstance(query, str) or not (0.0 <= alpha <= 1.0):
            raise ValueError("Parâmetros de busca híbrida inválidos.")
        with _INDEX_LOCK:
            with closing(self._connect()) as conn:
                self._sync(conn)
                fts_matches = self.search(query, limit=10)
                fts_dict = {}
                for rank, item in enumerate(fts_matches):
                    fts_dict[item["content"]] = max(0.1, 1.0 - (rank * 0.1))

                q_vec = get_embedding(query, self.ollama_url)
                rows = conn.execute("SELECT content, source, embedding FROM memory_vectors").fetchall()
                candidates = {}
                for content, source, emb_json in rows:
                    try:
                        emb = json.loads(emb_json)
                        vec_sim = cosine_similarity(q_vec, emb)
                    except Exception:
                        vec_sim = 0.0

                    bm25_sim = fts_dict.get(content, 0.0)
                    hybrid_score = (alpha * bm25_sim) + ((1.0 - alpha) * vec_sim)
                    candidates[content] = {
                        "content": content,
                        "source": source,
                        "bm25_score": round(bm25_sim, 3),
                        "vector_score": round(vec_sim, 3),
                        "score": round(hybrid_score, 4),
                    }

        sorted_results = sorted(candidates.values(), key=lambda x: x["score"], reverse=True)
        return [r for r in sorted_results if r["score"] > 0.05][:limit]

    def deduplicate_and_store(
        self,
        text: str,
        source: str = _SOURCE,
        threshold: float = 0.85,
    ) -> Dict[str, Any]:
        """Evita duplicação de fatos redundantes ou atualiza fatos semelhantes no cérebro."""
        clean_text = self.store._memory_text(text)
        q_vec = get_embedding(clean_text, self.ollama_url)
        with _INDEX_LOCK:
            with closing(self._connect()) as conn:
                self._sync(conn)
                rows = conn.execute(
                    "SELECT id, source, content, embedding FROM memory_vectors WHERE source=?",
                    (source,),
                ).fetchall()
                best_match = None
                best_sim = 0.0
                for row_id, r_source, r_content, emb_json in rows:
                    try:
                        emb = json.loads(emb_json)
                        sim = cosine_similarity(q_vec, emb)
                        if sim > best_sim:
                            best_sim = sim
                            best_match = (row_id, r_source, r_content)
                    except Exception:
                        continue

                if best_match and best_sim >= threshold:
                    old_id, old_src, old_content = best_match
                    if old_content.strip() == clean_text.strip():
                        return {"action": "exact_match", "id": old_id, "similarity": best_sim, "content": clean_text}

                    markdown = self.store.read_note(source)
                    new_markdown = markdown.replace(old_content, clean_text)
                    if new_markdown != markdown:
                        self.store.write_note(source, new_markdown)
                    emb_str = json.dumps(q_vec)
                    conn.execute(
                        "UPDATE memory_vectors SET content=?, embedding=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (clean_text, emb_str, old_id),
                    )
                    conn.commit()
                    return {
                        "action": "updated",
                        "id": old_id,
                        "similarity": round(best_sim, 3),
                        "content": clean_text,
                    }
                else:
                    if source == _SOURCE:
                        self.store.remember_knowledge(clean_text)
                    else:
                        cur = self.store.read_note(source)
                        self.store.write_note(source, cur.rstrip() + f"\n- {clean_text}\n")
                    self._sync(conn)
                    new_id = hashlib.sha256(f"{source}:{clean_text}".encode("utf-8")).hexdigest()[:16]
                    emb_str = json.dumps(q_vec)
                    conn.execute(
                        "INSERT OR REPLACE INTO memory_vectors(id, source, content, embedding, updated_at) "
                        "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                        (new_id, source, clean_text, emb_str),
                    )
                    conn.commit()
                    return {
                        "action": "inserted",
                        "id": new_id,
                        "similarity": round(best_sim, 3),
                        "content": clean_text,
                    }


def contextual_knowledge(query: str, store: Optional[BrainStore] = None, max_chars: int = 1200) -> str:
    """Retorna trechos com fonte para consulta através de busca híbrida."""
    matches = KnowledgeIndex(store).search_hybrid(query)
    lines = []
    length = 0
    for entry in matches:
        item = f"- {entry['content']} ({entry['source']})"
        if length + len(item) + 1 > max_chars:
            break
        lines.append(item)
        length += len(item) + 1
    return "\n".join(lines)

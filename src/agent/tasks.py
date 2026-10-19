"""Estado e recibos do agente no SQLite privado; nenhuma aprovação vem do cliente."""
from contextlib import closing
import hashlib
import json
import os
import re
import sqlite3

from src.memory.store import BrainStore

IDENTIFIER = re.compile(r"^[a-zA-Z0-9_-]{8,80}$")


class RunBusy(ValueError):
    pass


class TaskStore:
    def __init__(self, store=None):
        self.store = store or BrainStore()

    def _connect(self):
        path = self.store._directories(("memoria",)) / "agent.sqlite"
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("Banco de tarefas inválido.")
        if not path.exists():
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
                os.close(fd)
            except FileExistsError:
                if path.is_symlink() or not path.is_file():
                    raise ValueError("Banco de tarefas inválido.") from None
        path.chmod(0o600)
        db = sqlite3.connect(path, timeout=5)
        db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, state TEXT NOT NULL)")
        db.execute(
            "CREATE TABLE IF NOT EXISTS turns (session TEXT, id TEXT, fingerprint TEXT, result TEXT, "
            "PRIMARY KEY(session,id))"
        )
        return db

    @staticmethod
    def _id(value):
        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
            raise ValueError("Identificador de conversa ou turno inválido.")

    def claim(self, session, turn, payload):
        self._id(session)
        self._id(turn)
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT fingerprint,result FROM turns WHERE session=? AND id=?", (session, turn),
            ).fetchone()
            if existing:
                if existing[0] != fingerprint:
                    raise ValueError("O turno já existe com outro conteúdo.")
                if existing[1] is None:
                    raise RunBusy("Este turno está em execução ou foi interrompido; não vou repetir seus efeitos.")
                return None, json.loads(existing[1])
            previous = db.execute("SELECT state FROM sessions WHERE id=?", (session,)).fetchone()
            state = json.loads(previous[0]) if previous else {"phase": "idle"}
            if state["phase"] == "running":
                raise RunBusy("Há uma execução em andamento ou interrompida. Consulte o estado antes de repetir.")
            db.execute("INSERT INTO turns VALUES (?,?,?,NULL)", (session, turn, fingerprint))
            db.execute(
                "INSERT INTO sessions VALUES (?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                (session, json.dumps({"phase": "running", "step": "Consultando contexto e capacidades"})),
            )
            return state, None

    def finish(self, session, turn, state, result):
        encoded = json.dumps(result, ensure_ascii=False)
        if len(encoded.encode()) > 64000:
            raise ValueError("Resultado excedeu o limite de armazenamento.")
        with closing(self._connect()) as db, db:
            db.execute("UPDATE sessions SET state=? WHERE id=?", (json.dumps(state), session))
            db.execute("UPDATE turns SET result=? WHERE session=? AND id=?", (encoded, session, turn))

    def record_artifact(self, session, receipt):
        """Guarda recibo produzido no backend mesmo se a imagem veio por outra rota."""
        self._id(session)
        if (not isinstance(receipt, dict) or receipt.get("kind") != "image"
                or not isinstance(receipt.get("id"), str)
                or len(receipt["id"]) != 32):
            raise ValueError("Recibo inválido.")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM sessions WHERE id=?", (session,)).fetchone()
            state = json.loads(row[0]) if row else {"phase": "idle"}
            if state.get("phase") == "running":
                raise RunBusy("Conversa está executando outra tarefa.")
            state["last_result"] = receipt
            db.execute(
                "INSERT INTO sessions VALUES (?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                (session, json.dumps(state, ensure_ascii=False)),
            )
        return receipt

    def inspect(self, session):
        self._id(session)
        with closing(self._connect()) as db:
            row = db.execute("SELECT state FROM sessions WHERE id=?", (session,)).fetchone()
        return json.loads(row[0]) if row else {"phase": "idle"}

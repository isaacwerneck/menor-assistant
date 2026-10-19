"""Estado e recibos do agente no SQLite privado; nenhuma aprovação vem do cliente."""
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import stat

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
        db.execute(
            "CREATE TABLE IF NOT EXISTS run_backups ("
            "session TEXT, turn TEXT, state TEXT NOT NULL, PRIMARY KEY(session, turn))"
        )
        return db

    @staticmethod
    def _id(value):
        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
            raise ValueError("Identificador de conversa ou turno inválido.")

    @contextmanager
    def session_lock(self, session):
        """Flock entre processos: recuperação jamais concorre com execução ativa."""
        self._id(session)
        directory = self.store._directories(("memoria", "session_locks"))
        path = directory / (hashlib.sha256(session.encode()).hexdigest() + ".lock")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Lock de sessão inválido.")
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RunBusy("Outra operação desta conversa ainda está ativa.") from error
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

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
                "INSERT INTO run_backups VALUES (?,?,?)",
                (session, turn, json.dumps(state, ensure_ascii=False)),
            )
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
            db.execute("DELETE FROM run_backups WHERE session=? AND turn=?", (session, turn))

    @staticmethod
    def _interrupted_state(previous):
        if not isinstance(previous, dict):
            previous = {"phase": "idle"}
        preserved = {
            "phase": "failed", "interrupted": True, "effects_uncertain": True,
            "previous_phase": previous.get("phase", "unknown"),
        }
        for key in ("paused_goals", "goal_decisions", "last_result"):
            if key in previous:
                preserved[key] = previous[key]
        goal = previous if previous.get("phase") == "goal" else previous.get("return_goal")
        if isinstance(goal, dict) and goal.get("goal_id") and goal.get("goal"):
            archived = preserved.get("paused_goals", [])
            if not isinstance(archived, list):
                archived = []
            archived.append({
                "id": goal["goal_id"], "goal": goal["goal"],
                "steps": goal.get("steps", []), "acceptance": goal.get("acceptance", []),
                "question": goal.get("question", ""), "status": "paused",
            })
            preserved["paused_goals"] = archived[-6:]
        return preserved

    def recover(self, session, confirmed=False):
        """Liberar sessão após interrupção sem repetir efeitos desconhecidos.

        Um lock ativo bloqueia o procedimento. A execução antiga vira recibo
        terminal de incerteza; nenhuma autorização antiga é restaurada.
        """
        self._id(session)
        if confirmed is not True:
            raise ValueError("A recuperação exige confirmação explícita.")
        with self.session_lock(session):
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                item = db.execute("SELECT state FROM sessions WHERE id=?", (session,)).fetchone()
                if not item:
                    return {"recovered": False, "state": {"phase": "idle"}}
                state = json.loads(item[0])
                if state.get("phase") != "running":
                    return {"recovered": False, "state": state}
                pending = db.execute(
                    "SELECT id FROM turns WHERE session=? AND result IS NULL", (session,),
                ).fetchall()
                original = db.execute(
                    "SELECT state FROM run_backups WHERE session=? ORDER BY rowid DESC LIMIT 1",
                    (session,),
                ).fetchone()
                previous = json.loads(original[0]) if original else {"phase": "idle"}
                safe = self._interrupted_state(previous)
                notice = {
                    "handled": True, "phase": "failed", "interrupted": True,
                    "reply": (
                        "Esta operação foi interrompida e pode ter causado efeitos externos. "
                        "O sistema não vai repeti-la automaticamente. Confira os resultados "
                        "antes de pedir uma nova execução."
                    ),
                }
                for (turn,) in pending:
                    db.execute(
                        "UPDATE turns SET result=? WHERE session=? AND id=? AND result IS NULL",
                        (json.dumps(notice, ensure_ascii=False), session, turn),
                    )
                db.execute(
                    "UPDATE sessions SET state=? WHERE id=?",
                    (json.dumps(safe, ensure_ascii=False), session),
                )
                db.execute("DELETE FROM run_backups WHERE session=?", (session,))
                return {
                    "recovered": True, "interrupted_turns": len(pending),
                    "state": safe, "message": notice["reply"],
                }

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

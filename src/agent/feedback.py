"""Dataset local supervisionado: só exemplos aprovados explicitamente pelo dono.

Nenhuma conversa é enviada, coletada ou usada para treinamento automático.
Amostras ficam fora do repositório e têm proteção de permissões.
"""
import fcntl
import hashlib
import json
import os
import stat
from datetime import datetime, timezone

from src.memory.store import BrainStore
from src.tools.web import PRIVATE_QUERY

MAX_BYTES = 2 * 1024 * 1024
MAX_SAMPLES = 500


def _validate(value, name):
    if not isinstance(value, str) or not 8 <= len(value.strip()) <= 1200:
        raise ValueError(f"{name} deve ter entre 8 e 1200 caracteres.")
    if PRIVATE_QUERY.search(value) or "\x00" in value:
        raise ValueError("Exemplo parece incluir informação privada ou segredo.")
    return value.strip()


class FeedbackStore:
    def __init__(self, store=None):
        self.store = store or BrainStore()

    def _file(self):
        folder = self.store._directories(("treinamento",))
        path = folder / "aprovados.jsonl"
        if path.is_symlink() or (path.exists() and not stat.S_ISREG(path.lstat().st_mode)):
            raise ValueError("Dataset inválido.")
        return path

    def add(self, prompt, desired_reply, consent=False):
        if consent is not True:
            raise ValueError("É necessário autorizar explicitamente salvar este exemplo.")
        prompt = _validate(prompt, "Pedido")
        reply = _validate(desired_reply, "Resposta aprovada")
        key = hashlib.sha256((prompt + "\0" + reply).encode("utf-8")).hexdigest()[:24]
        path = self._file()
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "r+", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            os.fchmod(stream.fileno(), 0o600)
            if os.fstat(stream.fileno()).st_size > MAX_BYTES:
                raise ValueError("Dataset atingiu o limite de armazenamento.")
            records = stream.readlines()
            if len(records) >= MAX_SAMPLES:
                raise ValueError("Dataset já tem 500 exemplos; revise antes de continuar.")
            for raw in records:
                try:
                    if json.loads(raw).get("id") == key:
                        return {"status": "duplicate", "id": key}
                except (ValueError, TypeError, AttributeError):
                    raise ValueError("Dataset precisa de revisão.") from None
            event = {
                "id": key, "prompt": prompt, "response": reply, "approved": True,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            stream.seek(0, os.SEEK_END)
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            return {"status": "saved", "id": key}

    def stats(self):
        path = self._file()
        if not path.exists():
            return {"approved_examples": 0, "training_enabled": False}
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Dataset precisa de revisão.")
        with path.open(encoding="utf-8") as stream:
            return {
                "approved_examples": sum(bool(line.strip()) for line in stream),
                "training_enabled": False,
            }

    def samples(self, limit=100):
        """Acesso apenas local para futura exportação supervisionada de LoRA."""
        if not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("Limite inválido.")
        path = self._file()
        if not path.exists():
            return []
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Dataset precisa de revisão.")
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[:limit]]

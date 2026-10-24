"""Gerenciamento dinâmico de Core Memory (Memória Viva de Trabalho) do Menor v2.

Inspirado na arquitetura Letta / MemGPT: blocos de contexto sempre visíveis
no topo do prompt, editáveis e auditáveis com persistência em JSON atômico.
"""
import json
import logging
import os
import tempfile
import threading
from typing import Dict, Optional

from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)
_CORE_MEM_LOCK = threading.RLock()

DEFAULT_BLOCKS = {
    "user_profile": (
        "Nome: Isaac Werneck\n"
        "Papel: Fundador e Desenvolvedor Líder\n"
        "Hardware: PC Desktop (Ryzen 5 3500X, 16GB RAM, GTX 1650 4GB VRAM) e "
        "Notebook Servidor Ubuntu (Intel Core i7-1185G7, 32GB RAM, Iris Xe)\n"
        "Stack: Python, FastAPI, Node.js, SQLite, Ollama, Linux, Windows."
    ),
    "system_directives": (
        "1. Seja direto, técnico e aja como parceiro sênior de engenharia.\n"
        "2. Priorize respostas concisas e código pronto para produção.\n"
        "3. Utilize ferramentas do sistema (arquivos, terminal, busca) sempre que cabível.\n"
        "4. Mantenha 100% de privacidade local e zero custos de nuvem."
    ),
    "active_projects": (
        "Menor v2: Assistente de engenharia local distribuído (PC cliente + Servidor Notebook).\n"
        "Foco atual: Cérebro SOTA (Core Memory Letta, Busca Híbrida Mem0, Worker de Reflexão Stanford)."
    ),
    "study_anchors": (
        "1. Inteligência Artificial e Agentes (RAG, Agentes Autônomos, Embeddings, MoE, Fine-tuning)\n"
        "2. Engenharia de Software e Backend (Python assíncrono, FastAPI, Concorrência, SQLite, Arquitetura)\n"
        "3. Frontend e JavaScript (EventLoop, WebSockets, Web Workers, Web Audio API, DOM Performance)\n"
        "4. Design e UI/UX (Design Systems, Micro-interações, Teoria das Cores, Acessibilidade)"
    ),
}


class CoreMemoryManager:
    """Gerencia blocos atômicos de Core Memory no diretório de dados do Menor."""

    def __init__(self, store: Optional[BrainStore] = None):
        self.store = store if store is not None else BrainStore()
        self.file_path = self.store.brain_dir / "identidade" / "core_memory.json"

    def _ensure_file(self) -> Dict[str, str]:
        """Garante que a pasta identidade e o arquivo core_memory.json existam."""
        self.store.initialize()
        parent = self.file_path.parent
        parent.mkdir(parents=True, exist_ok=True)

        if not self.file_path.exists():
            with _CORE_MEM_LOCK:
                self._write_atomic(DEFAULT_BLOCKS)
            return dict(DEFAULT_BLOCKS)

        try:
            raw = self.file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                return dict(DEFAULT_BLOCKS)
            return data
        except Exception as exc:
            LOGGER.warning("Erro ao ler core_memory.json, restaurando padrões: %s", exc)
            return dict(DEFAULT_BLOCKS)

    def _write_atomic(self, data: Dict[str, str]):
        """Grava dados no disco de forma atômica com permissões restritas."""
        parent = self.file_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(data, ensure_ascii=False, indent=2)

        fd, temp_path = tempfile.mkstemp(prefix=".core_mem-", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                if hasattr(os, "fchmod"):
                    os.fchmod(handle.fileno(), 0o600)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.file_path)
            if hasattr(os, "chmod") and self.file_path.exists():
                os.chmod(self.file_path, 0o600)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def get_block(self, key: str) -> Optional[str]:
        """Obtém o conteúdo de um bloco específico da Core Memory."""
        blocks = self._ensure_file()
        return blocks.get(key)

    def set_block(self, key: str, content: str, mode: str = "replace") -> bool:
        """Define ou atualiza um bloco de memória (replace ou append)."""
        if not key or not isinstance(key, str):
            raise ValueError("Chave de bloco inválida.")
        if not isinstance(content, str):
            content = str(content)

        clean_key = key.strip().lower()
        clean_content = content.strip()

        with _CORE_MEM_LOCK:
            blocks = self._ensure_file()
            if mode == "append" and clean_key in blocks:
                existing = blocks[clean_key].strip()
                if clean_content not in existing:
                    merged = f"{existing}\n{clean_content}"
                    if len(merged) > 1600:
                        lines = merged.splitlines()
                        merged = "\n".join(lines[-15:])
                    blocks[clean_key] = merged
            else:
                blocks[clean_key] = clean_content

            self._write_atomic(blocks)
            return True

    def list_blocks(self) -> Dict[str, str]:
        """Retorna todos os blocos ativos da Core Memory."""
        return self._ensure_file()

    def format_system_context(self) -> str:
        """Formata os blocos para injeção limpa e prioritária no System Prompt."""
        blocks = self._ensure_file()
        if not blocks:
            return ""

        lines = [
            "=== CORE MEMORY (MEMÓRIA VIVA DO SISTEMA) ===",
            "Informações essenciais sempre residentes na atenção imediata:",
        ]
        for key, val in blocks.items():
            lines.append(f"\n[{key.upper()}]")
            lines.append(val.strip())
        lines.append("\n============================================")
        return "\n".join(lines)

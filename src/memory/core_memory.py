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
        "Papel: Fundador e Desenvolvedor Líder (Desenvolve sites modernos, jogos 2D, música no FL Studio, "
        "aplicativos mobile no Android Studio, automação de Excel/Word/PDF e sistemas de software)\n"
        "Hardware: PC Desktop (Ryzen 5 3500X, 16GB RAM, GTX 1650 4GB VRAM) e "
        "Notebook Servidor Ubuntu (Intel Core i7-1185G7, 32GB RAM, Iris Xe)\n"
        "Stack: Python, FastAPI, JavaScript (Raylib), GDScript (Godot 4), GML (GameMaker), FL Studio, Android Studio, openpyxl, SQLite, Tailwind, Linux, Windows."
    ),
    "system_directives": (
        "1. Seja direto, técnico e aja como parceiro sênior de engenharia.\n"
        "2. Priorize respostas concisas e código pronto para produção.\n"
        "3. Utilize ferramentas do sistema (arquivos, terminal, busca) sempre que cabível.\n"
        "4. Mantenha 100% de privacidade local e zero custos de nuvem."
    ),
    "active_projects": (
        "Menor v2: Assistente de engenharia local distribuído (PC cliente + Servidor Notebook).\n"
        "Foco atual: Cérebro SOTA (Core Memory Letta, Busca Híbrida Mem0, Laboratório de Avaliação Real)."
    ),
    "study_anchors": (
        "1. Jogos 2D e Game Development (JavaScript Raylib, Godot 4 GDScript, GameMaker 2 GML, Pixel Art, Shaders 2D, Level Design)\n"
        "2. Música, Produção de Áudio e Teoria Musical (FL Studio, Teoria Musical, Campo Harmônico, Acordes e Arranjos)\n"
        "3. Automação de Documentos e Office (Python openpyxl Excel, python-docx Word, Extração de texto de PDF)\n"
        "4. Desenvolvimento Mobile Android (Android Studio prático, Activities, Layouts XML, Ciclo de Vida)\n"
        "5. Engenharia de Software e Banco de Dados (Python FastAPI assíncrono, SQLite WAL FTS5, Descoberta de Linguagens como Rust e Go)\n"
        "6. Frontend Web Moderno (Tailwind CSS, WebSockets, Server-Sent Events, Web Workers, DOM Performance)\n"
        "7. Inteligência Artificial e LLMs (RAG Híbrido, Agentes Autônomos, Embeddings, Modelos Locais Ollama)"
    ),
    "environment": (
        "1. PC Interativo (Windows): AMD Ryzen 5 3500X, 16GB RAM, NVIDIA GTX 1650 (4GB VRAM). Roda voz e interface.\n"
        "2. Servidor Hub Central (Ubuntu): Intel Core i7-1185G7, 32GB RAM, Iris Xe. Roda API FastAPI (porta 8000), SQLite FTS5 e Ollama (127.0.0.1:11434).\n"
        "3. Conexão de Rede: Rede local 192.168.0.x e túnel Cloudflare para acesso remoto seguro."
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
            updated = False
            for k, v in DEFAULT_BLOCKS.items():
                if k not in data:
                    data[k] = v
                    updated = True
            current_anchors = data.get("study_anchors", "").lower()
            if "jogos" not in current_anchors or "android" not in current_anchors or "áudio" not in current_anchors or "raylib" not in current_anchors:
                data["study_anchors"] = DEFAULT_BLOCKS["study_anchors"]
                if "canvas" in data.get("user_profile", "").lower() or "dsp" in data.get("user_profile", "").lower():
                    data["user_profile"] = DEFAULT_BLOCKS["user_profile"]
                updated = True
            if updated:
                with _CORE_MEM_LOCK:
                    self._write_atomic(data)
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

"""Cerebro persistente do Menor: Markdown privado fora do repositorio Git.

Esta etapa nao expõe escrita de memoria pela API: a gravacao e feita localmente
pelo operador. O chat apenas le preferências explicitamente registradas.
"""

import argparse
import threading
from datetime import datetime, timezone
import os
import stat
import tempfile
from pathlib import Path, PurePosixPath


MAX_NOTE_BYTES = 64 * 1024
MAX_PREFERENCE_CHARS = 280
_write_lock = threading.RLock()

FOLDERS = (
    "identidade",
    "conhecimentos/design",
    "conhecimentos/programacao",
    "conhecimentos/engenharia_software",
    "conhecimentos/musica",
    "conhecimentos/game_design",
    "conhecimentos/game-design",
    "conhecimentos/comunicacao",
    "ferramentas/programacao",
    "ferramentas/imagens",
    "ferramentas/web",
    "projetos",
    "memoria",
    "propostas/melhorias",
)

SEED_FILES = {
    "identidade/perfil_usuario.md": "# Perfil do usuário\n\nInformações fornecidas ou confirmadas pelo usuário.\n",
    "identidade/preferencias.md": "# Preferências\n\nPreferências explícitas do usuário:\n",
    "conhecimentos/aprendizados_gerais.md": "# Aprendizados gerais\n\n",
    "conhecimentos/design/estilo_visual.md": (
        "# Estilo Visual e Design do Isaac\n\n"
        "## Diretrizes de Interface\n"
        "- Tema dark minimalista com alto contraste e elegância.\n"
        "- Tipografia moderna, legível e hierarquia clara.\n"
        "- Micro-interações táteis e responsivas sem animações pesadas.\n"
        "- Componentes modulares, cantos suavemente arredondados e bordas sutis.\n"
    ),
    "conhecimentos/programacao/estilo_isaac.md": (
        "# Estilo de Programação do Isaac\n\n"
        "## Convenções e Filosofia de Código\n"
        "- Código limpo, modular e direto ao ponto (princípio YAGNI).\n"
        "- Preferência por recursos nativos da linguagem/stdlib antes de instalar dependências.\n"
        "- Tipagem estrita com dataclasses / Pydantic e funções coesas de responsabilidade única.\n"
        "- Testes unitários para validar todo comportamento crítico antes do commit.\n"
    ),
    "conhecimentos/engenharia_software/arquitetura.md": (
        "# Engenharia de Software e Arquitetura do Menor\n\n"
        "## Padrões de Produção\n"
        "- FastAPI assíncrono com ciclo de vida (lifespan) estruturado.\n"
        "- Concorrência segura com locks (RLock) e isolamento temporal.\n"
        "- Armazenamento durável em SQLite FTS5 híbrido fora da árvore Git.\n"
        "- Preempção atômica em processos demorados para liberar a CPU do operador imediatamente.\n"
    ),
    "conhecimentos/musica/producao_e_sintese.md": (
        "# Conhecimentos Musicais e Produção de Áudio\n\n"
        "## Sound Design e Composição\n"
        "- Teoria musical moderna, escalas, harmonia funcional e progressões de acordes.\n"
        "- Síntese sonora subtrativa, aditiva, FM e modelagem física.\n"
        "- Processamento de áudio digital (DSP), envelopes ADSR, filtros e efeitos temporais.\n"
        "- Preferências sonoras do Isaac para beats, trilhas e texturas imersivas.\n"
    ),
    "conhecimentos/game_design/filosofia_jogos.md": (
        "# Game Design e Desenvolvimento de Jogos\n\n"
        "## Filosofia de Gameplay e Gráficos\n"
        "- Mecânicas de jogo responsivas, loop de gameplay viciante e curva de aprendizado justa.\n"
        "- Shaders GLSL / HLSL modernos (iluminação dinâmica, pós-processamento, partículas).\n"
        "- Desenvolvimento em C++ e Unreal Engine 5 com arquitetura ECS / UObject limpa.\n"
        "- Otimização de framerate, draw calls e profiling de GPU/CPU.\n"
    ),
    "menor_refletir.md": (
        "# Temas de Estudo e Pesquisa do Menor\n\n"
        "- [ ] Inteligência Artificial: Arquiteturas de agentes, RAG híbrido, MoE\n"
        "- [ ] Engenharia de Software: Padrões de concorrência em Python, FastAPI production\n"
        "- [ ] JavaScript: EventLoop, Web Workers, Web Audio API\n"
        "- [ ] Design e UI/UX: Design Systems modernos, micro-interações, teoria das cores\n"
    ),
    "ferramentas/catalogo.md": (
        "# Catálogo de ferramentas\n\nAs ferramentas executáveis serão registradas no código.\n"
    ),
    "projetos/exemplo-de-projeto/contexto.md": (
        "# Exemplo de projeto\n\nModelo de organização; não é um projeto ativo.\n"
    ),
    "projetos/exemplo-de-projeto/decisoes.md": "# Decisões\n\n",
    "projetos/exemplo-de-projeto/tarefas.md": "# Tarefas\n\n",
    "projetos/exemplo-de-projeto/diario.md": "# Diário\n\n",
}


class BrainStore:
    """Gerencia notas Markdown sob <MENOR_DATA_DIR>/cerebro/."""

    def __init__(self, data_dir=None):
        base = data_dir if data_dir is not None else os.environ.get("MENOR_DATA_DIR", "~/menor-data")
        self.data_dir = Path(base).expanduser().absolute()
        self.brain_dir = self.data_dir / "cerebro"

    @staticmethod
    def _require_directory(path):
        if path.is_symlink():
            raise ValueError(f"Diretório simbólico não permitido: {path}")
        if path.exists():
            if not path.is_dir():
                raise ValueError(f"O caminho não é um diretório: {path}")
        else:
            path.mkdir(mode=0o700)
        # Dados pessoais não devem ser acessíveis a outros usuários locais.
        path.chmod(0o700)

    def _directories(self, relative):
        current = self.data_dir
        self._require_directory(current)
        current = self.brain_dir
        self._require_directory(current)
        for part in relative:
            current = current / part
            self._require_directory(current)
        return current

    @staticmethod
    def _check_relative(relative):
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise ValueError("Caminho relativo inválido.")
        path = PurePosixPath(relative)
        if path.is_absolute() or any(part in (".", "..") for part in relative.split("/")):
            raise ValueError("Não é permitido sair do cérebro.")
        if any(not part or len(part) > 120 for part in relative.split("/")):
            raise ValueError("Componente de caminho inválido.")
        if path.suffix != ".md":
            raise ValueError("Somente notas Markdown são permitidas.")
        return path

    def _note_path(self, relative, create_parent=False):
        path = self._check_relative(relative)
        folder_parts = path.parts[:-1]
        if create_parent:
            parent = self._directories(folder_parts)
        else:
            parent = self.brain_dir
            for part in folder_parts:
                parent = parent / part
                if parent.is_symlink():
                    raise ValueError("Links simbólicos não são permitidos.")
        target = parent / path.name
        if target.is_symlink():
            raise ValueError("Links simbólicos não são permitidos.")
        return target

    def initialize(self):
        """Idempotente: cria diretórios e modelos sem substituir notas existentes."""
        self._directories(())
        for folder in FOLDERS:
            self._directories(folder.split("/"))
        self._directories(("projetos", "exemplo-de-projeto", "arquivos"))
        for relative, content in SEED_FILES.items():
            target = self._note_path(relative, create_parent=True)
            try:
                with target.open("x", encoding="utf-8") as handle:
                    os.chmod(target, 0o600)
                    handle.write(content)
            except FileExistsError:
                if target.is_symlink() or not target.is_file():
                    raise ValueError("Nota inicial existente não é arquivo regular.") from None
        return self.brain_dir

    def read_note(self, relative):
        target = self._note_path(relative)
        if not target.exists():
            return ""
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_NOTE_BYTES:
            raise ValueError("Arquivo inválido ou muito grande.")
        return target.read_text(encoding="utf-8")

    def write_note(self, relative, content):
        """Salva atomicamente uma nota Markdown e impede traversal/symlinks."""
        if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_NOTE_BYTES:
            raise ValueError("Nota excede o limite de 64 KiB.")
        target = self._note_path(relative, create_parent=True)
        if target.exists() and not target.is_file():
            raise ValueError("O destino não é arquivo regular.")
        fd, temporary = tempfile.mkstemp(prefix=".menor-", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                if hasattr(os, "fchmod"):
                    os.fchmod(handle.fileno(), 0o600)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if target.is_symlink():
                raise ValueError("Links simbólicos não são permitidos.")
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return target

    @staticmethod
    def _memory_text(text):
        if not isinstance(text, str):
            raise ValueError("A memória deve ser texto.")
        value = " ".join(text.split()).strip()
        if not value or len(value) > MAX_PREFERENCE_CHARS or any(ord(c) < 32 for c in value):
            raise ValueError("Memória inválida ou grande demais.")
        return value

    def remember_preference(self, preference):
        """Registra somente uma preferência explicitamente confirmada."""
        value = self._memory_text(preference)
        self.initialize()
        relative = "identidade/preferencias.md"
        line = "- " + value
        with _write_lock:
            current = self.read_note(relative)
            if not any(row.casefold().strip() == line.casefold() for row in current.splitlines()):
                self.write_note(relative, current.rstrip() + "\n" + line + "\n")
        return line

    def remember_knowledge(self, knowledge):
        """Guarda aprendizado explícito sem tratá-lo como preferência pessoal."""
        value = self._memory_text(knowledge)
        self.initialize()
        relative = "conhecimentos/aprendizados_gerais.md"
        line = "- " + datetime.now(timezone.utc).strftime("%Y-%m-%d") + " — " + value
        with _write_lock:
            current = self.read_note(relative)
            known = [
                row[2:].split(" — ", 1)[-1].casefold().strip()
                for row in current.splitlines() if row.startswith("- ")
            ]
            if value.casefold() not in known:
                self.write_note(relative, current.rstrip() + "\n" + line + "\n")
        return line

    def remember_idea(self, kind, idea):
        """Registra proposta; não instala ferramenta ou cria projeto automaticamente."""
        if kind not in ("project", "tool"):
            raise ValueError("Tipo de ideia desconhecido.")
        value = self._memory_text(idea)
        self.initialize()
        relative = "projetos/ideias.md" if kind == "project" else "ferramentas/ideias.md"
        heading = "# Ideias de projetos" if kind == "project" else "# Propostas de ferramentas"
        line = "- " + datetime.now(timezone.utc).strftime("%Y-%m-%d") + " — " + value
        with _write_lock:
            current = self.read_note(relative)
            if not current:
                current = heading + "\n"
            contents = current.rstrip() + "\n" + line + "\n"
            self.write_note(relative, contents)
        return line

    def list_notes(self, subfolder=""):
        """Lista todas as notas Markdown relativas ao cérebro."""
        base = self.brain_dir / subfolder if subfolder else self.brain_dir
        if not base.exists():
            return []
        notes = []
        for path in base.rglob("*.md"):
            if not path.is_symlink() and path.is_file():
                rel = path.relative_to(self.brain_dir).as_posix()
                notes.append(rel)
        return sorted(notes)

    def preference_context(self, max_chars=4000):
        """Retorna apenas preferências já gravadas; não varre dados de outros projetos."""
        if not self.brain_dir.exists():
            return ""
        content = self.read_note("identidade/preferencias.md")
        preferences = [line for line in content.splitlines() if line.startswith("- ")]
        if not preferences:
            return ""
        selected = []
        length = 0
        for line in preferences:
            if length + len(line) + 1 > max_chars:
                break
            selected.append(line)
            length += len(line) + 1
        return "\n".join(selected)

    def list_domains(self):
        """Lista os domínios de conhecimento padrão."""
        return ["design", "programacao", "engenharia_software", "musica", "game_design"]

    def list_domain_knowledge(self, domain):
        """Retorna todas as notas de um domínio específico."""
        domain_clean = str(domain).lower().strip().replace("-", "_")
        folder = f"conhecimentos/{domain_clean}"
        results = {}
        for note_rel in self.list_notes(folder):
            content = self.read_note(note_rel)
            results[note_rel] = content
        return results

    def improve_knowledge(self, domain, topic, content, mode="append"):
        """Atualiza ou expande uma nota de conhecimento em um domínio padrão."""
        domain_clean = str(domain).lower().strip().replace("-", "_")
        valid_domains = self.list_domains()
        if domain_clean not in valid_domains:
            domain_clean = "geral"

        safe_topic = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in topic.lower().strip())[:50]
        if not safe_topic:
            safe_topic = "nota"

        rel_path = f"conhecimentos/{domain_clean}/{safe_topic}.md"
        with _write_lock:
            existing = self.read_note(rel_path)
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            if mode == "append" and existing:
                updated = existing.rstrip() + f"\n\n### Atualização [{now_str}]\n{content.strip()}\n"
            else:
                updated = f"# {topic.title()}\n\n*Última melhoria em: {now_str}*\n\n{content.strip()}\n"
            self.write_note(rel_path, updated)
        return {"success": True, "path": rel_path, "domain": domain_clean, "mode": mode}


def main():
    parser = argparse.ArgumentParser(description="Gerenciar o cérebro local do Menor.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Criar pastas e notas iniciais.")
    remember = sub.add_parser("remember", help="Registrar preferência explicitamente informada.")
    remember.add_argument("text", help="Texto da preferência.")
    sub.add_parser("show", help="Mostrar preferências salvas.")
    args = parser.parse_args()
    store = BrainStore()
    if args.command == "init":
        print(f"Cérebro pronto em: {store.initialize()}")
    elif args.command == "remember":
        print(f"Registrado: {store.remember_preference(args.text)}")
    else:
        print(store.preference_context() or "(nenhuma preferência registrada)")


if __name__ == "__main__":
    main()

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
    "conhecimentos/android",
    "conhecimentos/design",
    "conhecimentos/programacao",
    "conhecimentos/engenharia_software",
    "conhecimentos/musica",
    "conhecimentos/game_design",
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
    "identidade/diretrizes_executivas.md": (
        "# Diretrizes Executivas e de Identidade do Menor v2\n\n"
        "## 1. Filosofia de Atuação e Zero Recusas\n"
        "- O Menor v2 é um assistente executivo e proativo, parceiro técnico do Isaac.\n"
        "- **Zero Recusas:** É estritamente proibido usar 'sou apenas voz' ou 'não posso criar'.\n"
        "- **Execução Real:** Se solicitado uma tela ou script, materializa o arquivo via `fs_write`.\n"
        "- **Comunicação Executiva:** Respostas objetivas, elegantes e diretas, sem preâmbulos.\n\n"
        "## 2. Padrões de Entrega de Demandas\n"
        "1. Para web: gera o HTML/CSS/JS e devolve o link clicável `/preview/<arquivo>.html`.\n"
        "2. Para mobile (Android Studio): entrega o modelo Kotlin/Clean Arch pronto para compilar.\n"
        "3. Em ambiguidades de negócio: faz 1 ou 2 perguntas de alinhamento antes de construir.\n"
    ),
    "conhecimentos/android/arquitetura_mobile.md": (
        "# Playbook Canônico: Engenharia Android Studio & Mobile\n\n"
        "## 1. Stack Tecnológico & Versões Canônicas\n"
        "- **Linguagem & SDK:** Kotlin 2.0+ (K2 compiler), Android Min SDK 26, Target SDK 35.\n"
        "- **UI & Toolkit:** Jetpack Compose (BOM moderno), Material 3 (`androidx.compose.material3`).\n"
        "- **Persistência Local:** Room Database (`androidx.room:room-ktx:2.6+`) com SQLite bundled.\n"
        "- **Fluxo Reativo & Assincronismo:** Kotlin Coroutines + `StateFlow` / `SharedFlow`.\n"
        "- **Injeção de Dependências:** Koin ou Hilt estruturado por módulos (feature-based).\n"
        "- **Rede & Serialização:** Ktor Client ou Retrofit 2.11 com `kotlinx.serialization.json`.\n\n"
        "## 2. Padrão Obrigatório de Arquitetura (Clean Architecture + MVI)\n"
        "```text\n"
        "com.empresa.app/\n"
        "├── data/         # Entities, Room DAOs, API Services, Repositories Impl\n"
        "├── domain/       # Modelos puros imutáveis, Interfaces de Repository, UseCases\n"
        "└── presentation/ # Compose Screens, ViewModels, UiState imutável, Tema\n"
        "```\n\n"
        "## 3. Snippets de Referência Canônica\n"
        "```kotlin\n"
        "sealed interface EstoqueUiState {\n"
        "    data object Loading : EstoqueUiState\n"
        "    data class Success(val itens: List<ItemEstoque>) : EstoqueUiState\n"
        "    data class Error(val mensagem: String) : EstoqueUiState\n"
        "}\n\n"
        "@HiltViewModel\n"
        "class EstoqueViewModel @Inject constructor(\n"
        "    private val getItensUseCase: GetItensEstoqueUseCase\n"
        ") : ViewModel() {\n"
        "    private val _uiState = MutableStateFlow<EstoqueUiState>(EstoqueUiState.Loading)\n"
        "    val uiState: StateFlow<EstoqueUiState> = _uiState.asStateFlow()\n"
        "}\n"
        "```\n\n"
        "## 4. Anti-Padrões Proibidos\n"
        "- NUNCA usar `LiveData` em código novo; use `StateFlow` com `collectAsStateWithLifecycle()`.\n"
        "- NUNCA rodar operações de banco ou rede na Main Dispatcher.\n"
        "- NUNCA criar Activities gigantes monolíticas.\n"
    ),
    "conhecimentos/design/estilo_visual.md": (
        "# Estilo Visual e Design System do Isaac\n\n"
        "## 1. Diretrizes de Interface & Paleta Dark Minimalist\n"
        "- **Background Root:** `#0c0b10` (Preto azulado profundo, sem cansar a vista).\n"
        "- **Surface / Card Background:** `#14131c` (Elevação primária elegante).\n"
        "- **Border / Divider:** `rgba(255, 255, 255, 0.08)` (Borda nítida e sutil).\n"
        "- **Accent Primário (Violeta):** `#8b5cf6` (Foco, botões de ação e status ativo).\n"
        "- **Accent Secundário (Cyan):** `#06b6d4` (Indicadores de estado, links e previews).\n"
        "- **Texto Principal:** `#f3f4f6` (Alto contraste e legibilidade perfeita).\n\n"
        "## 2. Tipografia & Componentes\n"
        "- **UI Geral:** Inter, Plus Jakarta Sans ou system sans-serif moderna.\n"
        "- **Código & Schemas:** Cascadia Code, JetBrains Mono ou Consolas.\n"
        "- **Border Radius:** 8px para botões/inputs; 12px a 14px para cards e modais.\n"
        "- **Micro-interações:** Transições táteis rápidas de 150ms a 200ms `ease-out`.\n\n"
        "## 3. Anti-Padrões Visuais Proibidos\n"
        "- NUNCA usar fundo branco puro (`#ffffff`) para interfaces do Isaac.\n"
        "- NUNCA usar sombras escuras opacas ou borradas que sujem o contraste.\n"
        "- NUNCA usar animações lentas (>300ms) que prejudiquem a agilidade.\n"
    ),
    "conhecimentos/programacao/estilo_isaac.md": (
        "# Estilo de Programação e Engenharia do Isaac\n\n"
        "## 1. Convenções & Filosofia de Código\n"
        "- **Princípio YAGNI & Código Limpo:** O menor código que resolve o problema completamente.\n"
        "- **Prioridade Nativa:** Usar biblioteca padrão antes de instalar pacotes de terceiros.\n"
        "- **Tipagem Estrita:** Pydantic v2 / Dataclasses com validação em tempo de compilação/execução.\n"
        "- **Funções Coesas:** Responsabilidade única, funções curtas e testabilidade direta.\n\n"
        "## 2. Qualidade e Ciclo de Vida\n"
        "- Testes unitários para validar todo comportamento crítico antes do commit.\n"
        "- Tratamento explícito de exceções sem `except: pass` silencioso em lógica de negócio.\n"
    ),
    "conhecimentos/engenharia_software/arquitetura.md": (
        "# Engenharia de Software e Arquitetura do Menor\n\n"
        "## 1. Padrões de Produção FastAPI\n"
        "- Ciclo de vida estruturado com `@asynccontextmanager async def lifespan(app: FastAPI)`.\n"
        "- Async / Await: operações I/O bloqueantes (disco, subprocessos) com `run_in_threadpool`.\n"
        "- Armazenamento híbrido durável em SQLite FTS5 fora da árvore Git (`~/menor-data/`).\n"
        "- Locks `threading.RLock()` para atomicidade e proteção de concorrência.\n\n"
        "## 2. Anti-Padrões de Backend Proibidos\n"
        "- NUNCA chamar `time.sleep()` em rotas assíncronas do FastAPI.\n"
        "- NUNCA concatenar strings em queries SQL cruas; use prepared statements.\n"
    ),
    "conhecimentos/musica/producao_e_sintese.md": (
        "# Conhecimentos Musicais e Produção de Áudio DSP\n\n"
        "## 1. Sound Design & Teoria Harmônica\n"
        "- Escalas Menor Natural, Harmônica e Dórica para progressões e texturas imersivas.\n"
        "- Síntese subtrativa: Osciladores -> Filtro VCF 24dB com Cutoff dinâmico -> ADSR -> LFO.\n"
        "- Síntese procedural de bateria: Kick (pitch drop 140Hz -> 38Hz), Snare (ruído branco + seno 180Hz).\n\n"
        "## 2. Processamento Digital de Sinais (DSP)\n"
        "- Taxa de amostragem padrão: 44.1 kHz / 48 kHz com float32 `[-1.0, 1.0]`.\n"
        "- Envelope anti-click: fade-in e fade-out de 3-5ms em bordas de buffer para evitar descontinuidade de fase.\n"
        "- Master bus sempre com limiter para impedir clipping digital (`> 0 dBFS`).\n"
    ),
    "conhecimentos/game_design/filosofia_jogos.md": (
        "# Game Design e Desenvolvimento de Jogos\n\n"
        "## 1. Arquitetura de Engine & Gráficos\n"
        "- Desenvolvimento em C++20 / Unreal Engine 5 com arquitetura ECS / UObject limpa.\n"
        "- Shaders GLSL / HLSL modernos: iluminação PBR (Cook-Torrance, albedo, metallic, roughness).\n"
        "- Game loop determinístico com física em passo fixo e interpolação de renderização.\n\n"
        "## 2. Anti-Padrões de Jogos\n"
        "- NUNCA alocar memória dinâmica (`new`/`malloc`) dentro do loop de renderização (tick).\n"
        "- NUNCA criar dependências circulares entre atores ou subsistemas.\n"
    ),
    "conhecimentos/aprendizados_gerais.md": "# Aprendizados gerais\n\n",
    "menor_refletir.md": (
        "# Temas de Estudo e Pesquisa do Menor\n\n"
        "- [ ] Android: Compose multiplatform, Room migrations e Ktor Client\n"
        "- [ ] Inteligência Artificial: Arquiteturas de agentes, RAG híbrido, MoE\n"
        "- [ ] Engenharia de Software: Padrões de concorrência em Python, FastAPI production\n"
        "- [ ] Design e UI/UX: Design Systems modernos, micro-interações, teoria das cores\n"
        "- [ ] Áudio DSP: Web Audio API, síntese procedural e processamento de som\n"
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

    def sync_playbooks(self, force: bool = False):
        """Sincroniza os playbooks normativos de engenharia com o cérebro permanente."""
        updated = []
        for rel_path, content in SEED_FILES.items():
            # Preserva integralmente dados pessoais de perfil e preferências
            if rel_path in ("identidade/perfil_usuario.md", "identidade/preferencias.md"):
                continue
            target = self._note_path(rel_path, create_parent=True)
            if force or not target.exists():
                self.write_note(rel_path, content)
                try:
                    self._update_fts_index(rel_path, content)
                except Exception:
                    pass
                updated.append(rel_path)
        return updated

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
        return ["design", "programacao", "engenharia_software", "musica", "game_design", "android"]

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

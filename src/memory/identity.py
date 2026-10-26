"""Identidade Canônica do Menor v2 (Pilar 1 - Desacoplamento Núcleo / Mente / Corpo).

O Núcleo detém a identidade durável e o estado permanente em disco; os modelos LLM na Mente
são processadores cognitivos descartáveis e plugáveis. Trocar o modelo do Ollama não altera
quem a IA é nem suas memórias.

Arquivos gerenciados em ~/menor-data/identidade/:
- SOUL.md: Identidade durável, essência, tom parceiro e princípios inegociáveis.
- SELF.md: Autopercepção viva em 1ª pessoa revisável pelo assistente.
- RELATION.md: Histórico de parceria e vínculo com o operador (Isaac Werneck).
"""
import os
from pathlib import Path
from typing import Optional

from src.memory.store import BrainStore

DEFAULT_SOUL = """# SOUL: Essência e Identidade Durável do Menor v2

Sou o Menor v2, assistente executivo, arquiteto de software e parceiro técnico do Isaac Werneck.
Minha atuação é pautada por excelência em engenharia, autonomia responsável, transparência e pragmatismo.

## Princípios Inegociáveis
1. **Ferramentas Reais, Zero Simulações:** Executo ações reais no sistema operacional através de ferramentas (arquivos, terminal, banco de dados). Nunca finjo saídas fictícias.
2. **Parceria Sênior e Proatividade:** Ajo como parceiro de desenvolvimento sênior: direto, colaborativo, resolutivo e sem condescendência.
3. **Privacidade e Soberania Local:** Todo processamento prioritário roda na nossa própria infraestrutura local (Hub Ubuntu + PC Interativo), garantindo total privacidade e soberania de dados.
4. **Tom de Voz:** Fluente, técnico, parceiro e natural em português brasileiro. Foco em soluções diretas sem rodeios corporativos.
"""

DEFAULT_SELF = """# SELF: Autopercepção e Capacidades do Menor v2

Operei como assistente distribuído em dois nós principais:
- **Hub Central (Notebook Servidor Ubuntu):** Onde resido permanentemente. Executo a API FastAPI, o SQLite FTS5 (cérebro permanente) e a orquestração pesada via Ollama.
- **PC Interativo (Windows / GPU GTX 1650):** Estação de trabalho do Isaac, de onde recebo comandos via voz de alta velocidade e interface web.

Tenho plena capacidade de criar e refatorar projetos de software completos, inspecionar cobertura de testes, gerenciar rotinas de estudo autônomo e apoiar na construção de sites, jogos 2D, processamento de áudio DSP e sistemas backend.
"""

DEFAULT_RELATION = """# RELATION: Parceria com Isaac Werneck

Isaac Werneck é o criador, operador e desenvolvedor líder com quem trabalho em estreita colaboração.
- **Perfil Técnico:** Desenvolvedor focado em sites modernos, jogos 2D, música/áudio DSP, aplicativos mobile Android e sistemas backend assíncronos.
- **Relação:** Parceria de trabalho contínua. Mantenho histórico factual de preferências, decisões técnicas e projetos em andamento, respeitando suas diretrizes de arquitetura limpa e pragmatismo técnico.
"""


class IdentityManager:
    """Gerencia a leitura e persistência da identidade canônica positiva."""

    def __init__(self, store: Optional[BrainStore] = None):
        self.store = store if store is not None else BrainStore()
        self.ident_dir = self.store.brain_dir / "identidade"

    def _ensure_files(self):
        """Garante a existência do diretório e dos arquivos canônicos."""
        self.store.initialize()
        self.ident_dir.mkdir(parents=True, exist_ok=True)

        files = {
            "SOUL.md": DEFAULT_SOUL,
            "SELF.md": DEFAULT_SELF,
            "RELATION.md": DEFAULT_RELATION,
        }
        for filename, default_text in files.items():
            path = self.ident_dir / filename
            if not path.exists():
                path.write_text(default_text.strip(), encoding="utf-8")

    def get_soul(self) -> str:
        self._ensure_files()
        path = self.ident_dir / "SOUL.md"
        return path.read_text(encoding="utf-8").strip()

    def get_self(self) -> str:
        self._ensure_files()
        path = self.ident_dir / "SELF.md"
        return path.read_text(encoding="utf-8").strip()

    def get_relation(self) -> str:
        self._ensure_files()
        path = self.ident_dir / "RELATION.md"
        return path.read_text(encoding="utf-8").strip()

    def update_self(self, text: str) -> None:
        self._ensure_files()
        path = self.ident_dir / "SELF.md"
        path.write_text(text.strip(), encoding="utf-8")

    def update_relation(self, text: str) -> None:
        self._ensure_files()
        path = self.ident_dir / "RELATION.md"
        path.write_text(text.strip(), encoding="utf-8")

    def format_canonical_identity(self, compact: bool = False) -> str:
        """Formata o bloco de identidade para injeção no prompt (< 280 tokens)."""
        soul = self.get_soul()
        if compact:
            # Resumo condensado para conversas casuais e ultrarrápidas (< 80 tokens)
            return (
                "Você é o Menor v2, parceiro de tecnologia e assistente de software de alto nível do Isaac Werneck.\n"
                "Tom: Direto, parceiro, inteligente e natural em pt-BR. Use ferramentas reais para ações no SO."
            )

        self_desc = self.get_self()
        relation = self.get_relation()
        return (
            f"[IDENTIDADE CANÔNICA - SOUL]\n{soul}\n\n"
            f"[AUTOPERCEPÇÃO - SELF]\n{self_desc}\n\n"
            f"[VÍNCULO COM OPERADOR - RELATION]\n{relation}"
        )

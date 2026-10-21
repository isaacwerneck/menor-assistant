"""Diretrizes locais Ponytail somente para trabalho supervisionado com código.

São contexto de qualidade, nunca permissões de escrita, rede ou execução.
"""
from pathlib import Path


_SKILL = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "ponytail" / "SKILL.md"


def coding_guidance():
    """Lê a parte aplicável da skill versionada; não executa conteúdo de terceiros."""
    content = _SKILL.read_text(encoding="utf-8")
    start = content.index("## Before you write")
    end = content.index("## Levels", start)
    return "Diretriz de qualidade, não é autorização de ferramenta:\n" + content[start:end].strip()

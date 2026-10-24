"""Otimizador algorítmico de prompts e guardrails offline (DSPy Pattern).

Compila falhas de auto-diagnóstico, anti-padrões e erros de ferramentas
em regras concisas e demonstrações few-shot sem adicionar latência ao chat em tempo real.
"""
import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)

DEFAULT_OPTIMIZED_RULES = [
    "Sempre use 'fs_patch' com 2 a 3 linhas de contexto acima e abaixo para evitar erros de bloco duplicado.",
    "Antes de navegar em múltiplos arquivos, use 'symbol_lookup' ou 'repo_map' para economizar contexto.",
    "Para testes de código, execute 'terminal_run' e analise stdout/stderr antes de confirmar a conclusão.",
]


class PromptOptimizer:
    def __init__(self, store: Optional[BrainStore] = None):
        self.store = store or BrainStore()
        self.store.initialize()
        self.prompts_file = self.store.brain_dir / "identidade" / "optimized_prompts.json"

    def _get_diagnostic_gaps(self, limit: int = 5) -> List[str]:
        """Lê os últimos gaps técnicos do auto-diagnóstico (scores < 7.0)."""
        gaps: List[str] = []
        db_path = self.store.brain_dir / "diagnosticos" / "historico_scores.sqlite"
        if not db_path.exists():
            return gaps

        try:
            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT topic, critique FROM scores WHERE total_score < 7.0 ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
                for topic, critique in cursor.fetchall():
                    if critique:
                        gaps.append(f"{topic}: {critique[:120]}")
        except Exception as exc:
            LOGGER.debug("Erro ao ler gaps de diagnóstico para otimização de prompts: %s", exc)

        return gaps

    def compile(self) -> Dict[str, Any]:
        """Compila regras refinadas a partir de anti-padrões, gaps de diagnóstico e diretrizes Ponytail."""
        rules: List[str] = list(DEFAULT_OPTIMIZED_RULES)

        # 1. Carrega gaps do auto-diagnóstico
        gaps = self._get_diagnostic_gaps()
        for g in gaps:
            rules.append(f"Atenção reforçada: Evitar falhas observadas em {g}")

        # 2. Carrega anti-padrões das notas de conhecimentos
        try:
            notes = self.store.list_notes()
            for note in notes:
                if "anti_padrao" in note.lower() or "erros" in note.lower():
                    content = self.store.read_note(note)
                    if content:
                        for line in content.splitlines():
                            clean = line.strip("-* ").strip()
                            if len(clean) > 10 and clean not in rules:
                                rules.append(clean[:150])
                                if len(rules) >= 8:
                                    break
        except Exception as exc:
            LOGGER.debug("Falha ao coletar notas de anti-padrões: %s", exc)

        data = {
            "version": "2.0-dspy",
            "active_rules": rules[:7],
            "total_compiled": len(rules),
        }

        try:
            self.prompts_file.parent.mkdir(parents=True, exist_ok=True)
            self.prompts_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            LOGGER.warning("Não foi possível salvar prompts otimizados: %s", exc)

        return data

    def load_rules(self) -> List[str]:
        """Carrega as regras ativas compiladas para injeção rápida no sistema."""
        if not self.prompts_file.exists():
            return DEFAULT_OPTIMIZED_RULES

        try:
            raw = self.prompts_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            rules = data.get("active_rules", [])
            return rules if rules else DEFAULT_OPTIMIZED_RULES
        except Exception:
            return DEFAULT_OPTIMIZED_RULES

    def format_system_injection(self) -> str:
        """Formata as regras otimizadas para injeção concisa no Orchestrator."""
        rules = self.load_rules()
        if not rules:
            return ""
        lines = [f"- {r}" for r in rules]
        return "[DIRETRIZES TÉCNICAS REFINADAS (DSPy COMPILER)]:\n" + "\n".join(lines)

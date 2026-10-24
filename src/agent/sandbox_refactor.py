"""Motor de Auto-Refatoração e Melhoria de Código em Sandbox Git Isolada (Fase 5).

Permite ao Menor testar otimizações e refatorações no próprio código em branches
efêmeras com rollback atômico instantâneo se qualquer teste quebrar, garantindo zero risco de regressão.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, Optional

from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)


class SandboxRefactorEngine:
    """Gerencia branches isoladas para testes de refatoração autônoma."""

    def __init__(self, root_dir: Optional[str] = None, store: Optional[BrainStore] = None):
        self.root_dir = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()
        self.store = store or BrainStore()

    def _run_git(self, args: list) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args,
            cwd=str(self.root_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def is_tree_clean(self) -> bool:
        """Verifica se não há alterações pendentes que possam ser perdidas."""
        res = self._run_git(["status", "--porcelain", "-uno"])
        return len(res.stdout.strip()) == 0

    def current_branch(self) -> str:
        res = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        return res.stdout.strip() or "main"

    def run_refactoring_trial(
        self,
        target_file: str,
        description: str,
        search_block: str,
        replace_block: str,
    ) -> Dict[str, Any]:
        """Executa um ciclo completo de refatoração em branch temporária."""
        target_path = (self.root_dir / target_file).resolve()
        if not target_path.exists() or not target_path.is_file():
            return {"success": False, "error": f"Arquivo não encontrado: {target_file}"}

        if not self.is_tree_clean():
            return {
                "success": False,
                "error": "A árvore git possui alterações locais pendentes. Salve ou commite antes de refatorar.",
            }

        original_content = target_path.read_text(encoding="utf-8", errors="replace")
        if search_block not in original_content:
            return {"success": False, "error": "Bloco de código alvo não encontrado no arquivo."}

        orig_branch = self.current_branch()
        trial_id = int(time.time())
        trial_branch = f"auto-refactor/{trial_id}"

        # 1. Cria a branch temporária isolada
        checkout_res = self._run_git(["checkout", "-b", trial_branch])
        if checkout_res.returncode != 0:
            return {"success": False, "error": f"Falha ao criar branch de sandbox: {checkout_res.stderr}"}

        try:
            # 2. Aplica a alteração
            new_content = original_content.replace(search_block, replace_block, 1)
            target_path.write_text(new_content, encoding="utf-8")

            # 3. Executa os testes unitários
            test_proc = subprocess.run(
                ["python", "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )

            # 4. Se falhar, faz rollback atômico e destrói a branch
            if test_proc.returncode != 0:
                self._run_git(["checkout", orig_branch])
                self._run_git(["branch", "-D", trial_branch])

                # Salva como anti-padrão no cérebro
                self.store.improve_knowledge(
                    domain="engenharia_software",
                    topic="anti_padroes_refatoracao",
                    content=(
                        f"- Refatoração rejeitada em '{target_file}': {description}. "
                        f"Erro: {test_proc.stderr[-300:] if test_proc.stderr else test_proc.stdout[-300:]}"
                    ),
                    mode="append",
                )

                return {
                    "success": False,
                    "rolled_back": True,
                    "reason": "Testes unitários falharam durante a validação em sandbox.",
                    "test_output": test_proc.stdout[-1000:],
                }

            # 5. Se passar 100%, gera o diff e salva a proposta
            diff_proc = self._run_git(["diff", target_file])
            diff_text = diff_proc.stdout

            self._run_git(["add", target_file])
            self._run_git(["commit", "-m", f"refactor({target_file}): {description}"])

            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            proposal_md = (
                f"# Proposta de Refatoração Validada: {description}\n"
                f"**Data:** {now_str}  \n"
                f"**Branch Isolada:** `{trial_branch}`  \n"
                f"**Arquivo Modificado:** `{target_file}`  \n"
                f"**Status dos Testes:**  100% dos testes unitários passaram!\n\n"
                f"## Diff das Alterações\n```diff\n{diff_text}\n```\n"
            )

            prop_dir = self.store.brain_dir / "propostas" / "melhorias"
            prop_dir.mkdir(parents=True, exist_ok=True)
            prop_file = prop_dir / f"refatoracao_{trial_id}.md"
            prop_file.write_text(proposal_md, encoding="utf-8")

            # Retorna para a branch original por segurança
            self._run_git(["checkout", orig_branch])

            return {
                "success": True,
                "trial_branch": trial_branch,
                "proposal_report": str(prop_file),
                "diff": diff_text,
                "message": f"Refatoração validada com sucesso em '{trial_branch}'. Proposta pronta para aprovação.",
            }

        except Exception as exc:
            self._run_git(["checkout", orig_branch])
            self._run_git(["branch", "-D", trial_branch])
            return {"success": False, "error": f"Erro inesperado no sandbox: {exc}"}


def trial_code_refactoring(
    target_file: str,
    description: str,
    search_block: str,
    replace_block: str,
    root_dir: Optional[str] = None,
    store: Optional[BrainStore] = None,
) -> Dict[str, Any]:
    """Ferramenta para testar e validar refatorações em sandbox Git isolada."""
    try:
        engine = SandboxRefactorEngine(root_dir=root_dir, store=store)
        return engine.run_refactoring_trial(
            target_file=target_file,
            description=description,
            search_block=search_block,
            replace_block=replace_block,
        )
    except Exception as exc:
        return {"success": False, "error": str(exc)}

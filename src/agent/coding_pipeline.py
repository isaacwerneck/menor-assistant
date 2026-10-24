"""Pipeline autônomo de programação e autocorreção cíclica (Aider & LangGraph Pattern).

Implementa uma Máquina de Estados Finitos (FSM) com Circuit Breaker rígido (max 2 tentativas):
[INSPECIONAR] -> [APLICAR PATCH] -> [RODAR TESTES] -> [SUCESSO / RETENTATIVA / ABORTO]
"""
from dataclasses import dataclass, field
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional
import requests

from src.tools.core import fs_patch, fs_read, terminal_run
from src.agent.ponytail import get_ponytail_system_prompt

LOGGER = logging.getLogger(__name__)


@dataclass
class CodingPipelineResult:
    success: bool
    status: str
    target_file: str
    attempts: int
    test_command: str
    patches_applied: List[Dict[str, Any]] = field(default_factory=list)
    initial_test_output: Optional[Dict[str, Any]] = None
    final_test_output: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "target_file": self.target_file,
            "attempts": self.attempts,
            "test_command": self.test_command,
            "patches_applied": self.patches_applied,
            "initial_test_output": self.initial_test_output,
            "final_test_output": self.final_test_output,
            "error_message": self.error_message,
            "events_count": len(self.events),
        }


class AutonomousCodingPipeline:
    def __init__(
        self,
        ollama_url: Optional[str] = None,
        model: Optional[str] = None,
        max_attempts: int = 2,
    ):
        self.ollama_url = (ollama_url or os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        from src.agent.study import get_optimal_model
        self.model = model or os.environ.get("OLLAMA_MODEL") or get_optimal_model(self.ollama_url)
        self.max_attempts = max_attempts

    def _query_model_for_patch(
        self,
        target_file: str,
        current_content: str,
        task_instruction: str,
        test_failure_stderr: str,
    ) -> Optional[Dict[str, str]]:
        """Solicita ao modelo local a menor substituição cirúrgica (search_block e replace_block)."""
        prompt = (
            f"{get_ponytail_system_prompt()}\n\n"
            f"Arquivo alvo: {target_file}\n"
            f"Instrução: {task_instruction}\n\n"
            f"Saída de erro nos testes:\n{test_failure_stderr[-3000:]}\n\n"
            f"Conteúdo atual do arquivo:\n```\n{current_content[:6000]}\n```\n\n"
            "Retorne EXCLUSIVAMENTE um objeto JSON válido com dois campos:\n"
            "{\n"
            '  "search_block": "trecho exato a ser substituído (incluindo 2-3 linhas de contexto)",\n'
            '  "replace_block": "novo trecho corrigido"\n'
            "}\n"
            "NÃO adicione explicações em markdown fora do JSON."
        )

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.2, "num_ctx": 4096},
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            raw_text = data.get("message", {}).get("content", "").strip()
            parsed = json.loads(raw_text)
            if "search_block" in parsed and "replace_block" in parsed:
                return {
                    "search_block": str(parsed["search_block"]),
                    "replace_block": str(parsed["replace_block"]),
                }
        except Exception as exc:
            LOGGER.warning("Falha ao consultar modelo para patch autônomo: %s", exc)
        return None

    def run_task(
        self,
        target_file: str,
        task_instruction: str,
        test_command: str,
        direct_patch: Optional[Dict[str, str]] = None,
        patch_generator: Optional[Callable[[str, str, str, str], Optional[Dict[str, str]]]] = None,
    ) -> CodingPipelineResult:
        """Executa o ciclo FSM completo com verificação e autocorreção defensiva."""
        events: List[Dict[str, Any]] = []
        patches_applied: List[Dict[str, Any]] = []

        events.append({"state": "INSPECT", "file": target_file, "command": test_command})

        # Estado 1: Inspeciona e lê arquivo
        read_res = fs_read(target_file)
        if not read_res.get("success"):
            return CodingPipelineResult(
                success=False,
                status="FILE_READ_FAILED",
                target_file=target_file,
                attempts=0,
                test_command=test_command,
                error_message=read_res.get("error"),
                events=events,
            )

        current_content = read_res["content"]

        # Estado 2: Executa testes de baseline se aplicável
        baseline_test = terminal_run(test_command)
        events.append({"state": "BASELINE_TEST", "exit_code": baseline_test.get("exit_code")})

        # Se os testes já passam e não há instrução de patch, encerra
        if baseline_test.get("success") and not direct_patch and not task_instruction:
            return CodingPipelineResult(
                success=True,
                status="ALREADY_PASSING",
                target_file=target_file,
                attempts=0,
                test_command=test_command,
                initial_test_output=baseline_test,
                final_test_output=baseline_test,
                events=events,
            )

        attempts = 0
        last_test_output = baseline_test

        while attempts < self.max_attempts:
            attempts += 1
            events.append({"state": "ATTEMPT_START", "attempt": attempts})

            # Determina o patch a aplicar
            if direct_patch and attempts == 1:
                patch_cand = direct_patch
            elif patch_generator:
                stderr = last_test_output.get("stderr") or last_test_output.get("stdout") or ""
                patch_cand = patch_generator(target_file, current_content, task_instruction, stderr)
            else:
                stderr = last_test_output.get("stderr") or last_test_output.get("stdout") or ""
                patch_cand = self._query_model_for_patch(
                    target_file=target_file,
                    current_content=current_content,
                    task_instruction=task_instruction,
                    test_failure_stderr=stderr,
                )

            if not patch_cand or not patch_cand.get("search_block"):
                events.append({"state": "PATCH_GENERATION_FAILED", "attempt": attempts})
                status = "CIRCUIT_BREAKER_EXCEEDED" if patches_applied else "PATCH_GENERATION_FAILED"
                err_msg = (
                    f"Testes continuaram falhando após {len(patches_applied)} patch(es) aplicado(s)."
                    if patches_applied
                    else "Não foi possível gerar um bloco de substituição válido."
                )
                return CodingPipelineResult(
                    success=False,
                    status=status,
                    target_file=target_file,
                    attempts=attempts,
                    test_command=test_command,
                    initial_test_output=baseline_test,
                    final_test_output=last_test_output,
                    patches_applied=patches_applied,
                    error_message=err_msg,
                    events=events,
                )

            # Aplica o patch cirúrgico
            patch_res = fs_patch(
                filepath=target_file,
                search_block=patch_cand["search_block"],
                replace_block=patch_cand["replace_block"],
            )

            if not patch_res.get("success"):
                events.append({"state": "PATCH_APPLY_FAILED", "error": patch_res.get("error")})
                # Se falhar a aplicação física do patch, tenta nova iteração se ainda houver tentativa
                continue

            patches_applied.append(patch_res)
            events.append({"state": "PATCH_APPLIED", "lines_added": patch_res.get("lines_added")})

            # Atualiza conteúdo em memória
            fresh_read = fs_read(target_file)
            if fresh_read.get("success"):
                current_content = fresh_read["content"]

            # Estado 3: Executa testes de verificação
            verify_res = terminal_run(test_command)
            last_test_output = verify_res
            events.append({"state": "TEST_VERIFICATION", "exit_code": verify_res.get("exit_code")})

            if verify_res.get("success"):
                events.append({"state": "SUCCESS", "attempts": attempts})
                return CodingPipelineResult(
                    success=True,
                    status="SUCCESS",
                    target_file=target_file,
                    attempts=attempts,
                    test_command=test_command,
                    patches_applied=patches_applied,
                    initial_test_output=baseline_test,
                    final_test_output=verify_res,
                    events=events,
                )

        # Circuit breaker acionado
        events.append({"state": "CIRCUIT_BREAKER_TRIGGERED", "max_attempts": self.max_attempts})
        return CodingPipelineResult(
            success=False,
            status="CIRCUIT_BREAKER_EXCEEDED",
            target_file=target_file,
            attempts=attempts,
            test_command=test_command,
            patches_applied=patches_applied,
            initial_test_output=baseline_test,
            final_test_output=last_test_output,
            error_message=f"Os testes continuaram falhando após {self.max_attempts} tentativas de patch.",
            events=events,
        )

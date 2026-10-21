"""Auditoria offline dos relatórios do Menor Lab sem revelar prompts nem respostas.

Uso: python3 -m ops.lab_batch_audit ~/menor-data/lab
Não acessa GitHub/rede e não modifica qualquer arquivo.
"""
import argparse
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path


_COMPLETE = {"answered", "decision_validated"}
_KNOWN_STATES = _COMPLETE | {"inference_failed", "busy", "no_valid_decision"}
_MAX_BYTES = 8 * 1024 * 1024
_RUN_ID = re.compile(r"\d{8}T\d{6}Z-[a-f0-9]{8}")


def _median(numbers):
    return round(statistics.median(numbers), 3) if numbers else None


def _p95(numbers):
    if not numbers:
        return None
    ordered = sorted(numbers)
    return round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)], 3)


def _seconds(performance, key):
    number = performance.get(key)
    if type(number) is int and 0 <= number <= 10 ** 15:
        return number / 1e9
    return None


def inspect(directory, limit=100):
    """Devolve somente estatísticas e IDs de bateria/execução, nunca conteúdo."""
    if not isinstance(directory, Path) or not directory.is_dir():
        raise ValueError("Pasta local de relatórios não encontrada.")
    if not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("Limite de relatórios inválido.")
    scanned, total, passes, failures, ungraded, technical = 0, 0, 0, 0, 0, 0
    timings, prefill, generation, token_rates = [], [], [], []
    statuses, by_suite, prompts = Counter(), {}, set()
    prompt_executions = 0
    ceiling_hits = 0
    technical_graded_failures = 0
    completed_graded_failures = 0
    validation_issues = Counter()
    known_validation_issues = {
        "move", "goal", "text_type", "reply_or_question", "steps_or_acceptance",
        "steps_required", "question_required", "relation", "resume_goal_id",
        "unknown_goal", "query", "tool_arguments_type", "tool", "tool_schema",
        "arguments", "tool_required",
    }
    for path in sorted(directory.glob("*.json"), reverse=True):
        if scanned >= limit:
            break
        if path.name.endswith(".summary.json") or path.is_symlink():
            continue
        if not _RUN_ID.fullmatch(path.stem):
            continue
        try:
            if path.stat().st_size > _MAX_BYTES:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("run_id") != path.stem:
                continue
            suite = data.get("suite_id")
            cases = data.get("cases")
            if not isinstance(suite, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", suite):
                continue
            if not isinstance(cases, list) or not 1 <= len(cases) <= 200:
                continue
        except (OSError, ValueError, TypeError, UnicodeError):
            continue
        scanned += 1
        item = by_suite.setdefault(suite, {
            "reports": 0, "cases_executed": 0, "graded_passes": 0,
            "graded_failures": 0, "ungraded": 0, "technical_failures": 0,
            "technical_graded_failures": 0, "completed_graded_failures": 0,
            "output_limits": 0, "statuses": Counter(), "validation_issues": Counter(),
            "_timings": [],
        })
        item["reports"] += 1
        for case in cases:
            if not isinstance(case, dict):
                continue
            total += 1
            item["cases_executed"] += 1
            outcome = case.get("automatic_pass")
            if outcome is True:
                passes += 1
                item["graded_passes"] += 1
            elif outcome is False:
                failures += 1
                item["graded_failures"] += 1
            else:
                ungraded += 1
                item["ungraded"] += 1
            result = case.get("result")
            result = result if isinstance(result, dict) else {}
            status = result.get("status", "unknown")
            if not isinstance(status, str):
                status = "unknown"
            status = status if status in _KNOWN_STATES else "unknown"
            statuses[status] += 1
            item["statuses"][status] += 1
            if outcome is False:
                if status not in _COMPLETE:
                    technical_graded_failures += 1
                    item["technical_graded_failures"] += 1
                else:
                    completed_graded_failures += 1
                    item["completed_graded_failures"] += 1
            if status == "no_valid_decision":
                diagnostic = result.get("diagnostics")
                if isinstance(diagnostic, dict):
                    issue = diagnostic.get("validation_issue")
                    if isinstance(issue, str) and issue in known_validation_issues:
                        validation_issues[issue] += 1
                        item["validation_issues"][issue] += 1
            if status not in _COMPLETE:
                technical += 1
                item["technical_failures"] += 1
            elapsed = case.get("elapsed_seconds")
            if type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed <= 3600:
                timings.append(elapsed)
                item["_timings"].append(elapsed)
            perf = result.get("performance")
            perf = perf if isinstance(perf, dict) else {}
            p = _seconds(perf, "prompt_eval_duration")
            g = _seconds(perf, "eval_duration")
            if p is not None:
                prefill.append(p)
            if g is not None:
                generation.append(g)
            speed = perf.get("generation_tokens_per_second")
            if type(speed) in (int, float) and math.isfinite(speed) and 0 < speed < 10000:
                token_rates.append(speed)
            if result.get("output_limited") is True:
                ceiling_hits += 1
                item["output_limits"] += 1
            question = case.get("question")
            history = case.get("history")
            if isinstance(question, str) and len(question) <= 10000:
                key = json.dumps([question, history], ensure_ascii=False, sort_keys=True)
                prompts.add(hashlib.sha256(key.encode()).digest())
                prompt_executions += 1
    for suite in by_suite.values():
        suite["latency_p50_seconds"] = _median(suite.pop("_timings"))
        suite["statuses"] = dict(sorted(suite["statuses"].items()))
        suite["validation_issues"] = dict(sorted(suite["validation_issues"].items()))
    attention = sorted(by_suite, key=lambda suite_id: (
        -by_suite[suite_id]["technical_failures"],
        -by_suite[suite_id]["completed_graded_failures"],
        -by_suite[suite_id]["output_limits"],
        suite_id,
    ))
    return {
        "reports": scanned, "cases_executed": total,
        "unique_prompt_history_pairs": len(prompts),
        "repeated_prompt_executions": prompt_executions - len(prompts),
        "graded_passes": passes, "graded_failures": failures, "ungraded": ungraded,
        "technical_graded_failures": technical_graded_failures,
        "completed_graded_failures": completed_graded_failures,
        "technical_failures": technical, "statuses": dict(sorted(statuses.items())),
        "validation_issues": dict(sorted(validation_issues.items())),
        "priority_suites": attention,
        "latency_p50_seconds": _median(timings), "latency_p95_seconds": _p95(timings),
        "prefill_p50_seconds": _median(prefill), "generation_p50_seconds": _median(generation),
        "tokens_per_second_p50": _median(token_rates),
        "reported_output_limits": ceiling_hits,
        "suites": dict(sorted(by_suite.items())),
        "caveats": [
            "Casos agregados e repetidos contam execuções, não perguntas independentes.",
            "Repetição é estimada pela igualdade exata de pergunta e histórico; perfis diferentes podem se repetir.",
            "Uma falha automática técnica não prova resposta semanticamente incorreta.",
            "Prioridade indica triagem operacional, não ranking de inteligência nem causalidade.",
            "Sem nota automática exige revisão humana; contrato válido não prova plano correto.",
            "Métricas de prefill e geração são as fornecidas pelo Ollama, quando presentes.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Auditoria de relatórios do Menor sem conteúdo privado.")
    parser.add_argument("directory", type=Path, help="Pasta local ~/menor-data/lab")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args(argv)
    print(json.dumps(inspect(args.directory.expanduser(), limit=args.limit),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

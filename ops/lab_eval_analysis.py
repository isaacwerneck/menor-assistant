"""Analisa relatórios do Menor Lab sem imprimir perguntas, respostas ou histórico.

Uso: python -m ops.lab_eval_analysis ~/menor-data/lab/<run_id>.json [...]
Gera resumo local JSON, sem rede e sem alterar arquivos.
"""
import argparse
import json
import math
import re
import unicodedata
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = ROOT / "lab" / "suites"
FAILING_STATES = {"inference_failed", "busy", "no_valid_decision"}
KNOWN_VALIDATION_ISSUES = {
    "move", "goal", "text_type", "reply_or_question", "steps_or_acceptance",
    "steps_required", "question_required", "relation", "resume_goal_id",
    "unknown_goal", "query", "tool_arguments_type", "tool", "tool_schema",
    "arguments", "tool_required",
}


def _duration_seconds(value):
    if type(value) is int and 0 <= value <= 10 ** 15:
        return round(value / 1_000_000_000, 3)
    return None


_SMALL_NUMBERS = {
    "0": "zero", "1": "um", "2": "dois", "3": "tres", "4": "quatro",
    "5": "cinco", "6": "seis", "7": "sete", "8": "oito", "9": "nove",
    "10": "dez",
}


def _fold_text(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def _possible_format_mismatch(spec, case):
    """Apenas recomenda revisão humana: nunca altera automatic_pass."""
    if case.get("automatic_pass") is not False or spec.get("grader") not in (None, "strict"):
        return False
    result = case.get("result", {})
    if not isinstance(result, dict) or result.get("status") != "answered":
        return False
    reply = result.get("reply", "")
    if not isinstance(reply, str) or len(reply) > 4000:
        return False
    folded = _fold_text(reply)
    parts = spec.get("expected_contains") or []
    expected = spec.get("expected_exact")
    if isinstance(expected, str) and expected.strip():
        parts = [expected]
    if not isinstance(parts, list) or not 1 <= len(parts) <= 3:
        return False
    for raw in parts:
        if not isinstance(raw, str) or not 1 <= len(raw) <= 80:
            return False
        target = _fold_text(raw.strip())
        if not target:
            return False
        pattern = r"(?<!\w)" + re.escape(target) + r"(?!\w)"
        if re.search(pattern, folded):
            continue
        word = _SMALL_NUMBERS.get(target)
        if not word or not re.search(r"(?<!\w)" + word + r"(?!\w)", folded):
            return False
    return True


def _load_suite(suite_id, suite_dir):
    if not isinstance(suite_id, str) or not suite_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("ID de bateria inválido.")
    path = suite_dir / (suite_id + ".json")
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(report, suite):
    """Classifica falhas observáveis; texto aberto continua exigindo revisão humana."""
    if report.get("suite_id") != suite.get("id"):
        raise ValueError("Relatório e bateria não correspondem.")
    reference = {case["id"]: case for case in suite["cases"]}
    records = []
    buckets = defaultdict(Counter)
    incidents = Counter()
    prefill_seconds = []
    generation_seconds = []
    for case in report.get("cases", []):
        cid = case.get("id")
        if cid not in reference:
            raise ValueError("Caso de relatório ausente da bateria: " + str(cid))
        spec = reference[cid]
        result = case.get("result", {})
        if not isinstance(result, dict):
            result = {}
        status = result.get("status", "unknown")
        mode = case.get("mode", spec["mode"])
        elapsed = case.get("elapsed_seconds")
        elapsed = (elapsed if type(elapsed) in (int, float)
                   and math.isfinite(elapsed) and elapsed >= 0 else None)
        auto = case.get("automatic_pass")
        if auto is True:
            grade = "passed"
        elif auto is False:
            grade = "failed"
        else:
            grade = "needs_human_review"
        flags = []
        if status in FAILING_STATES:
            flags.append(status)
        if auto is False:
            flags.append("objective_mismatch")
            if _possible_format_mismatch(spec, case):
                flags.append("possible_format_mismatch")
        if auto is True and case.get("format_compliant") is False:
            flags.append("numeric_format_mismatch")
        if elapsed is not None and elapsed > (45 if mode == "planner" else 25):
            flags.append("slow_execution")
        if grade == "needs_human_review":
            flags.append("qualitative_review")
        if result.get("output_limited") is True:
            flags.append("output_limited")
        if result.get("reply_truncated") is True:
            flags.append("reply_truncated")
        if isinstance(result.get("plan_warnings"), list) and result["plan_warnings"]:
            flags.append("plan_constraints")
        diagnostics = result.get("diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = {}
        issue = diagnostics.get("validation_issue")
        if status == "no_valid_decision" and isinstance(issue, str) and issue in KNOWN_VALIDATION_ISSUES:
            flags.append("schema_validation")
        performance = result.get("performance")
        if not isinstance(performance, dict):
            performance = {}
        prefill = _duration_seconds(performance.get("prompt_eval_duration"))
        generation = _duration_seconds(performance.get("eval_duration"))
        if prefill is not None:
            prefill_seconds.append(prefill)
        if generation is not None:
            generation_seconds.append(generation)
        if prefill is not None and prefill > 8:
            flags.append("slow_prefill")
        if generation is not None and generation > 20:
            flags.append("slow_generation")
        for flag in set(flags):
            incidents[flag] += 1
        category = spec.get("category", suite["id"])
        split = spec.get("split", "unspecified")
        buckets[category][grade] += 1
        buckets[split][grade] += 1
        records.append({
            "id": cid, "mode": mode, "split": split, "category": category,
            "status": status, "grade": grade, "elapsed_seconds": elapsed,
            "flags": flags, "human_review_required": bool(spec.get("review_criteria")),
            "validation_issue": issue if isinstance(issue, str) and issue in KNOWN_VALIDATION_ISSUES else None,
            "prefill_seconds": prefill, "generation_seconds": generation,
        })
    graded = sum(item["grade"] in ("passed", "failed") for item in records)
    passed = sum(item["grade"] == "passed" for item in records)
    latencies = [item["elapsed_seconds"] for item in records if item["elapsed_seconds"] is not None]
    suggestions = []
    if incidents["inference_failed"] or incidents["busy"]:
        suggestions.append(
            "Investigar timeout, fila e recursos do Ollama; separar infraestrutura de lógica.")
    if incidents["no_valid_decision"]:
        suggestions.append(
            "Reproduzir falhas do planner; inspecionar contrato JSON, validação e limites.")
    if incidents["objective_mismatch"]:
        suggestions.append(
            "Revisar respostas contra critérios; isolar problemas de prompt, contexto ou parser.")
    if incidents["qualitative_review"]:
        suggestions.append("Avaliar rubricas manualmente antes de afirmar sucesso; não tratar sem nota como falha.")
    if incidents["slow_execution"]:
        suggestions.append("Medir latência por modo e carga do Ubuntu; investigar desempenho sem sacrificar acurácia.")
    if incidents["plan_constraints"]:
        suggestions.append("Revisar planos que violam restrições ou omitem etapas; nunca inferir aprovação.")
    if incidents["possible_format_mismatch"]:
        suggestions.append("Revisar possíveis equivalências de escrita; nunca alterar nota automaticamente.")
    if incidents["numeric_format_mismatch"]:
        suggestions.append("Valor numérico correto, mas formato descumprido; não é erro matemático.")
    if incidents["schema_validation"]:
        suggestions.append("Usar categoria do contrato rejeitado para corrigir schema/prompt, sem expor o JSON bruto.")
    if incidents["output_limited"] or incidents["reply_truncated"]:
        suggestions.append("Examinar saídas cortadas e orçamento de geração, sem aumentar tokens sem medição.")
    if incidents["slow_prefill"]:
        suggestions.append("Perfilar prompt e ferramentas: prefill caro pode dominar antes do primeiro token.")
    if incidents["slow_generation"]:
        suggestions.append("Medir tokens/s e comprimento da resposta antes de trocar modelo ou hardware.")
    return {
        "run_id": report.get("run_id"), "suite_id": suite["id"],
        "total": len(records), "graded_count": graded, "graded_passes": passed,
        "graded_failures": graded - passed, "ungraded_count": len(records) - graded,
        "accuracy_on_graded": round(passed / graded, 4) if graded else None,
        "median_seconds": round(statistics.median(latencies), 3) if latencies else None,
        "median_prefill_seconds": (round(statistics.median(prefill_seconds), 3)
                                   if prefill_seconds else None),
        "median_generation_seconds": (round(statistics.median(generation_seconds), 3)
                                      if generation_seconds else None),
        "incidents": dict(incidents),
        "group_counts": {key: dict(value) for key, value in sorted(buckets.items())},
        "cases": records, "recommendations": suggestions,
        "caveat": "Passes por substrings nao provam correção semântica; revise os casos abertos.",
    }


def compare(previous, current):
    """Compara execuções da mesma bateria, sem incluir respostas privadas."""
    if previous["suite_id"] != current["suite_id"]:
        raise ValueError("Compare apenas a mesma bateria.")
    old = {case["id"]: case for case in previous["cases"]}
    new = {case["id"]: case for case in current["cases"]}
    shared = old.keys() & new.keys()
    regressions = sorted(cid for cid in shared if old[cid]["grade"] == "passed"
                         and new[cid]["grade"] != "passed")
    improvements = sorted(cid for cid in shared if old[cid]["grade"] == "failed"
                          and new[cid]["grade"] == "passed")
    return {
        "suite_id": current["suite_id"],
        "previous_run": previous["run_id"], "current_run": current["run_id"],
        "comparable_cases": len(shared), "regressions": regressions,
        "improvements": improvements,
        "previous_accuracy": previous["accuracy_on_graded"],
        "current_accuracy": current["accuracy_on_graded"],
        "warning": "Sem nota nao indica erro nem sucesso; reveja amostras humanas e variancia de repeticoes.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Analisar relatórios locais do Menor Lab sem expor respostas.")
    parser.add_argument("reports", nargs="+", type=Path, help="Arquivos JSON completos gerados pelo Menor Lab")
    parser.add_argument("--suite-dir", type=Path, default=SUITES)
    args = parser.parse_args(argv)
    analyses = []
    for path in args.reports:
        data = json.loads(path.read_text(encoding="utf-8"))
        analyses.append(summarize(data, _load_suite(data["suite_id"], args.suite_dir)))
    by_suite = defaultdict(list)
    for item in analyses:
        by_suite[item["suite_id"]].append(item)
    comparisons = []
    for items in by_suite.values():
        for before, after in zip(items, items[1:]):
            comparisons.append(compare(before, after))
    print(json.dumps({"reports": analyses, "comparisons": comparisons},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

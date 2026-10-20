"""Compara relatórios completos do Menor Lab sem expor perguntas e respostas.

Uso: python -m ops.eval_compare baseline.json candidato.json
     python -m ops.eval_compare relatorio.json
"""
import argparse
import json
import math
from collections import Counter
from pathlib import Path


COMPLETE = ("answered", "decision_validated")


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)], 3)


def summarize(report):
    cases = report["cases"]
    statuses = Counter(case.get("result", {}).get("status", "unknown") for case in cases)
    errors = Counter(
        case.get("result", {}).get("error_type", case.get("result", {}).get("status", "unknown"))
        for case in cases if case.get("result", {}).get("status") not in COMPLETE
    )
    passes = sum(case.get("automatic_pass") is True for case in cases)
    failures = sum(case.get("automatic_pass") is False for case in cases)
    reviews = sum(case.get("automatic_pass") is None for case in cases)
    elapsed = [case["elapsed_seconds"] for case in cases
               if isinstance(case.get("elapsed_seconds"), (int, float))
               and not isinstance(case.get("elapsed_seconds"), bool)
               and case["elapsed_seconds"] >= 0]
    by_split = {}
    for split in ("development", "validation"):
        group = [case for case in cases if case.get("split", "development") == split]
        passed = sum(case.get("automatic_pass") is True for case in group)
        failed = sum(case.get("automatic_pass") is False for case in group)
        by_split[split] = {"cases": len(group), "graded": passed + failed,
                           "graded_pass_rate": round(passed / (passed + failed), 4) if passed + failed else None}
    return {
        "suite_id": report.get("suite_id"), "run_id": report.get("run_id"), "total": len(cases),
        "graded": passes + failures, "graded_passes": passes, "graded_failures": failures,
        "ungraded": reviews,
        "graded_pass_rate": round(passes / (passes + failures), 4) if passes + failures else None,
        "completion_rate": round(sum(n for status, n in statuses.items() if status in COMPLETE) / len(cases), 4)
        if cases else None,
        "statuses": dict(sorted(statuses.items())),
        "execution_errors": dict(sorted(errors.items())),
        "latency_p50_seconds": percentile(elapsed, 0.50),
        "latency_p95_seconds": percentile(elapsed, 0.95),
        "by_split": by_split,
        "profiles": dict(sorted(Counter(case.get("profile", "baseline") for case in cases).items())),
    }


def compare(baseline, candidate):
    same_suite = baseline.get("suite_id") == candidate.get("suite_id")
    group = baseline.get("comparison_group")
    same_group = (isinstance(group, str) and bool(group)
                  and group == candidate.get("comparison_group"))
    if not same_suite and not same_group:
        raise ValueError("Relatórios devem ser da mesma bateria ou do mesmo grupo A/B.")
    old = {item["id"]: item for item in baseline["cases"]}
    new = {item["id"]: item for item in candidate["cases"]}
    if old.keys() != new.keys() or len(old) != len(baseline["cases"]) or len(new) != len(candidate["cases"]):
        raise ValueError("Casos de teste diferentes: comparação não é equivalente.")
    for case_id in old:
        for key in ("question", "history", "mode", "expected_exact", "expected_contains", "grader"):
            if old[case_id].get(key) != new[case_id].get(key):
                raise ValueError("Conteúdo ou critérios dos casos mudaram; comparação inválida.")
    regressions = [key for key in sorted(old) if old[key].get("automatic_pass") is True
                   and new[key].get("automatic_pass") is False]
    improvements = [key for key in sorted(old) if old[key].get("automatic_pass") is False
                    and new[key].get("automatic_pass") is True]
    baseline_summary = summarize(baseline)
    candidate_summary = summarize(candidate)
    completion_delta = _difference(baseline_summary["completion_rate"], candidate_summary["completion_rate"])
    pass_delta = _difference(baseline_summary["graded_pass_rate"], candidate_summary["graded_pass_rate"])
    return {"baseline": baseline_summary, "candidate": candidate_summary,
            "new_regressions": regressions, "resolved_failures": improvements,
            "completion_delta": completion_delta, "graded_pass_delta": pass_delta,
            "note": "Notas automáticas medem apenas critérios determinísticos; rubricas abertas exigem revisão."}


def _difference(before, after):
    return round(after - before, 4) if before is not None and after is not None else None


def recommendations(report):
    summary = summarize(report)
    suggestions = []
    if summary["execution_errors"]:
        suggestions.append("Investigar infraestrutura e timeouts antes de ajustar prompts ou modelo.")
    if summary["statuses"].get("no_valid_decision", 0):
        suggestions.append("Revisar saída estruturada, parse e tentativas do raciocinador.")
    if summary["graded_failures"]:
        suggestions.append("Inspecionar falhas por ID e comparar instruções, contexto e modelo.")
    if summary["ungraded"]:
        suggestions.append("Revisar manualmente casos abertos com a rubrica salva em cada resultado.")
    if not suggestions:
        suggestions.append("Repetir a bateria e validar em casos inéditos para medir consistência.")
    return suggestions


def main(argv=None):
    parser = argparse.ArgumentParser(description="Resumo privado de relatórios do Menor Lab.")
    parser.add_argument("baseline", help="JSON da execução original")
    parser.add_argument("candidate", nargs="?", help="JSON da nova versão, para comparação opcional")
    args = parser.parse_args(argv)
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    result = {"summary": summarize(baseline), "recommendations": recommendations(baseline)}
    if args.candidate:
        candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
        result = compare(baseline, candidate)
        result["recommendations"] = recommendations(candidate)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

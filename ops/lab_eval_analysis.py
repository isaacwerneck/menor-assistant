"""Analisa relatórios do Menor Lab sem imprimir perguntas, respostas ou histórico.

Uso: python -m ops.lab_eval_analysis ~/menor-data/lab/<run_id>.json [...]
Gera resumo local JSON, sem rede e sem alterar arquivos.
"""
import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = ROOT / "lab" / "suites"
FAILING_STATES = {"inference_failed", "busy", "no_valid_decision"}


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
    for case in report.get("cases", []):
        cid = case.get("id")
        if cid not in reference:
            raise ValueError("Caso de relatório ausente da bateria: " + str(cid))
        spec = reference[cid]
        status = case.get("result", {}).get("status", "unknown")
        mode = case.get("mode", spec["mode"])
        elapsed = case.get("elapsed_seconds")
        elapsed = elapsed if type(elapsed) in (int, float) and elapsed >= 0 else None
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
        if elapsed is not None and elapsed > (45 if mode == "planner" else 25):
            flags.append("slow_execution")
        if grade == "needs_human_review":
            flags.append("qualitative_review")
        for flag in flags:
            incidents[flag] += 1
        category = spec.get("category", suite["id"])
        split = spec.get("split", "unspecified")
        buckets[category][grade] += 1
        buckets[split][grade] += 1
        records.append({
            "id": cid, "mode": mode, "split": split, "category": category,
            "status": status, "grade": grade, "elapsed_seconds": elapsed,
            "flags": flags, "human_review_required": bool(spec.get("review_criteria")),
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
    return {
        "run_id": report.get("run_id"), "suite_id": suite["id"],
        "total": len(records), "graded_count": graded, "graded_passes": passed,
        "graded_failures": graded - passed, "ungraded_count": len(records) - graded,
        "accuracy_on_graded": round(passed / graded, 4) if graded else None,
        "median_seconds": round(statistics.median(latencies), 3) if latencies else None,
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

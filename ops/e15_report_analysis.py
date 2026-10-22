"""Agrega E15 sem expor mensagens privadas: somente métricas e estados técnicos."""
import argparse
from collections import Counter, defaultdict
import json
import math
import os
from pathlib import Path
import statistics
import sys

ALLOWED_SUITES = frozenset({
    "e15-conversas-descoberta", "e15-conversas-memoria",
    "e15-intencao-sem-antigos-gatilhos", "e15-seguranca-e-autorizacao",
})
SUCCESS = frozenset(("answered", "decision_validated"))
MAX_REPORT_BYTES = 25 * 1024 * 1024


def _median(values):
    values = [v for v in values if type(v) in (float, int)
              and math.isfinite(v) and 0 <= v < 10 ** 10]
    return round(statistics.median(values), 3) if values else None


def _p95(values):
    values = sorted(v for v in values if type(v) in (float, int)
                    and math.isfinite(v) and 0 <= v < 10 ** 10)
    return round(values[math.ceil(len(values) * 0.95) - 1], 3) if values else None


def _read_report(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_REPORT_BYTES:
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    if (not isinstance(report, dict)
            or report.get("suite_id") not in ALLOWED_SUITES
            or not isinstance(report.get("evaluation_model"), str)
            or not isinstance(report.get("cases"), list)
            or len(report["cases"]) > 300):
        return None
    if any(not isinstance(item, dict) or item.get("mode") != "dialogue"
           or not isinstance(item.get("conversation_id"), str)
           or type(item.get("turn_index")) is not int
           or not isinstance(item.get("result"), dict) for item in report["cases"]):
        return None
    return report


def latest_reports(folder):
    """Último relatório completo por (bateria, modelo), sem ler summaries."""
    folder = Path(folder).expanduser()
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError("Diretório local de relatórios inválido.")
    chosen = {}
    for path in sorted(folder.glob("*.json"))[-1000:]:
        if path.name.endswith(".summary.json") or not path.name.startswith("202"):
            continue
        report = _read_report(path)
        if report is None:
            continue
        key = (report["suite_id"], report["evaluation_model"])
        timestamp = str(report.get("finished_at", ""))
        if key not in chosen or timestamp >= chosen[key][0]:
            chosen[key] = (timestamp, report)
    return [item[1] for item in chosen.values()]


def summarize(report):
    rows = report["cases"]
    status = Counter(item["result"].get("status", "unknown") for item in rows)
    checks = Counter("pass" if item.get("automatic_pass") is True else
                     "fail" if item.get("automatic_pass") is False else
                     "human" for item in rows)
    scenarios = defaultdict(list)
    for row in rows:
        scenarios[row["conversation_id"]].append(row)
    completed = sum(
        all(row["result"].get("status") in SUCCESS for row in turns)
        for turns in scenarios.values()
    )
    valid = [r for r in rows if r["result"].get("status") in SUCCESS]
    elapsed = [r.get("elapsed_seconds") for r in valid]
    rates = [r["result"].get("performance", {}).get("generation_tokens_per_second")
             for r in valid if isinstance(r["result"].get("performance"), dict)]
    prefill = [r["result"].get("performance", {}).get("prompt_processing_ms")
               for r in valid if isinstance(r["result"].get("performance"), dict)]
    generation = [r["result"].get("performance", {}).get("token_generation_ms")
                  for r in valid if isinstance(r["result"].get("performance"), dict)]
    tracked = report.get("code_provenance", {})
    return {
        "suite_id": report["suite_id"], "model": report["evaluation_model"],
        "scenarios": len(scenarios), "scenarios_completed_structurally": completed,
        "turns": len(rows), "statuses": dict(status), "automatic_checks": dict(checks),
        "median_wall_seconds": _median(elapsed), "p95_wall_seconds": _p95(elapsed),
        "median_generation_tokens_per_second": _median(rates),
        "median_prefill_ms": _median(prefill), "median_generation_ms": _median(generation),
        "revision_changed": tracked.get("revision_changed") if isinstance(tracked, dict) else None,
        "human_review_required": checks["human"],
        "quality_claim": "not_automatically_assessed",
    }


def paired(reports):
    """Compara turnos equivalentes sem inferir qualidade semântica de um JSON."""
    groups = defaultdict(list)
    for report in reports:
        groups[report["suite_id"]].append(report)
    output = []
    for suite, candidates in sorted(groups.items()):
        if len(candidates) != 2:
            continue
        a, b = sorted(candidates, key=lambda item: item["evaluation_model"])
        turns = [
            {(case["conversation_id"], case["turn_index"]): case for case in item["cases"]}
            for item in (a, b)
        ]
        common = set(turns[0]).intersection(turns[1])

        def status_a(row):
            return row["result"].get("status") in SUCCESS
        both = sum(status_a(turns[0][key]) and status_a(turns[1][key]) for key in common)
        only_a = sum(status_a(turns[0][key]) and not status_a(turns[1][key]) for key in common)
        only_b = sum(status_a(turns[1][key]) and not status_a(turns[0][key]) for key in common)
        output.append({
            "suite_id": suite, "models": [a["evaluation_model"], b["evaluation_model"]],
            "paired_turns": len(common),
            "both_structurally_valid": both, "first_only": only_a,
            "second_only": only_b,
            "both_failed": len(common) - both - only_a - only_b,
            "meaningfulness": "requires_human_review",
        })
    return output


def analyze(folder):
    records = latest_reports(folder)
    rows = sorted((summarize(report) for report in records),
                  key=lambda item: (item["suite_id"], item["model"]))
    return {
        "status": "available" if rows else "no_e15_reports",
        "latest_reports_by_suite_model": len(rows),
        "models": sorted({item["model"] for item in rows}),
        "summary": rows,
        "paired_model_checks": paired(records),
        "warning": "Resposta válida e decisão segura não comprovam qualidade, "
                   "memória correta, criação de arquivos ou uso real de ferramentas. "
                   "O relatório NÃO contém o texto privado dos testes.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Comparar resultados E15 sem expor prompts.")
    parser.add_argument("--lab-dir", default=os.environ.get(
        "MENOR_LAB_DATA_DIR", str(Path.home() / "menor-data" / "lab")))
    args = parser.parse_args(argv)
    try:
        result = analyze(args.lab_dir)
    except (OSError, ValueError) as error:
        # Não incluir paths/segredos do erro em stdout.
        print(json.dumps({"status": "unavailable", "error_type": type(error).__name__}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

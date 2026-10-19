"""Diagnóstico de execuções locais com dados mínimos e sem conteúdo pessoal."""
import json
import stat
import sqlite3
from collections import Counter

from src.memory.store import BrainStore
from src.agent.quality_metrics import DecisionMetrics

MAX_RECENT = 200


def _attach_decisions(report, store):
    try:
        report["decision_quality"] = DecisionMetrics(store).report()
    except (OSError, ValueError, sqlite3.Error):
        report["decision_quality"] = {"status": "unavailable"}
    return report


def analyze(store=None):
    store = store or BrainStore()
    path = store.brain_dir / "memoria" / "execucoes.jsonl"
    if path.is_symlink():
        raise ValueError("Auditoria não confiável.")
    if not path.exists():
        return _attach_decisions({"events": 0, "failures": 0, "issues": [], "status": "no-data"}, store)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("Auditoria inválida.")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Arquivo de auditoria fora do limite.")
    events = []
    for line in path.read_text(encoding="utf-8").splitlines()[-MAX_RECENT:]:
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        if event.get("status") not in ("executed", "planned", "failed"):
            continue
        name = event.get("action")
        if not isinstance(name, str) or len(name) > 100:
            continue
        events.append({"action": name, "status": event["status"]})
    failures = Counter(e["action"] for e in events if e["status"] == "failed")
    issues = [
        {
            "tool": name, "failures": count,
            "next_step": "Verificar permissões e argumentos; reproduzir em teste antes de corrigir.",
        }
        for name, count in failures.most_common(10)
    ]
    return _attach_decisions({
        "events": len(events),
        "failures": sum(failures.values()),
        "issues": issues,
        "status": "needs-review" if issues else "ok",
    }, store)

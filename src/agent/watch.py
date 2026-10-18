"""Revisão automática periódica de falhas, sem auto-merge ou execução de código.

É inofensiva sem opt-in. Falhas de provedores externos nunca geram patch
de código automaticamente. Guarda carimbo de revisão para evitar PR repetido.
"""
import hashlib
from datetime import datetime, timezone

from src.agent.diagnostics import analyze
from src.agent.self_edit import ImprovementUnavailable, propose, status
from src.memory.store import BrainStore, _write_lock

STATE_PATH = "memoria/revisoes.md"
MIN_FAILURES = 3
REVIEWABLE = {
    "agent.route": "O roteador do Menor apresenta erros recorrentes de intenção",
    "agent.resolve": "O resolvedor do Menor falha com respostas curtas",
}


def review(store=None):
    store = store if store is not None else BrainStore()
    report = analyze(store)
    issues = [
        row for row in report["issues"]
        if row["failures"] >= MIN_FAILURES and row["tool"] in REVIEWABLE
    ]
    if not issues:
        return {"status": "no-action", "reason": "Sem falhas corrigíveis acima do limite."}
    issue = issues[0]
    token = hashlib.sha256(issue["tool"].encode()).hexdigest()[:16]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stamp = f"- {today}: {token}"
    with _write_lock:
        store.initialize()
        history = store.read_note(STATE_PATH)
        if stamp in history.splitlines():
            return {"status": "already-reviewed", "tool": issue["tool"]}
        store.write_note(STATE_PATH, history.rstrip() + "\n" + stamp + "\n")
    available = status()
    if not available["enabled"] or not available["github_connected"]:
        return {"status": "pending-configuration", "tool": issue["tool"],
                "reason": "Configure opt-in e integração GitHub para abrir PR."}
    try:
        result = propose(REVIEWABLE[issue["tool"]], dry_run=False)
        return {"status": "review-opened", "tool": issue["tool"], "result": result}
    except (ImprovementUnavailable, ValueError, OSError):
        return {"status": "failed", "tool": issue["tool"],
                "reason": "Não foi possível produzir uma proposta validada."}


def main():
    result = review()
    print(f"Menor revisão: {result['status']}")


if __name__ == "__main__":
    main()

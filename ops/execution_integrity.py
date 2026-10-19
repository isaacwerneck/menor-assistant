"""Auditoria agregada de trilhas de execução, sem I/O ou efeitos colaterais.

Não substitui transações atômicas, evidência persistida ou autorização do executor.
"""
from ops.execution_transitions import audit_sequence
from ops.recovery_decision import recovery_decision

_MAX_RUNS = 128
_MAX_EVENTS = 64
_FIELDS = ("mission_id", "action_id", "idempotency_key")
_TERMINAL = frozenset(("executed", "verified"))
_RANK = {"ok": 0, "unknown": 1, "warning": 2, "critical": 3}


def _valid_identity(record):
    return (isinstance(record, dict)
            and all(type(record.get(key)) is str and 1 <= len(record[key]) <= 128
                    for key in _FIELDS))


def _band(number):
    if number == 0:
        return "0"
    if number < 10:
        return "1-9"
    if number < 50:
        return "10-49"
    return "50+"


def audit_runs(runs):
    """Aceita no máximo 128 trilhas, cada uma com 1 a 64 eventos.

    O relatório não inclui IDs, payloads, prompts, caminhos ou exceções.
    """
    if not isinstance(runs, (tuple, list)) or len(runs) > _MAX_RUNS:
        return {"status": "unknown", "reason": "invalid_batch",
                "read_only": True, "runs": "unknown", "findings": {}}
    findings = {}
    worst = "ok"
    seen = {}

    def add(code, severity):
        nonlocal worst
        findings[code] = findings.get(code, 0) + 1
        if _RANK[severity] > _RANK[worst]:
            worst = severity

    for events in runs:
        if not isinstance(events, (tuple, list)) or not 1 <= len(events) <= _MAX_EVENTS:
            add("invalid_trace", "critical")
            continue
        first, last = events[0], events[-1]
        if not _valid_identity(first) or not _valid_identity(last):
            add("invalid_identity", "critical")
            continue
        identity = tuple(first[field] for field in _FIELDS)
        key = identity[2]
        # Uma chave de idempotência não pode ser reutilizada para outra ação.
        if key in seen and seen[key] != identity[:2]:
            add("idempotency_collision", "critical")
        else:
            seen[key] = identity[:2]
        if len(events) == 1:
            decision = recovery_decision(last)
            if decision["reason"] == "invalid_evidence":
                add("invalid_trace", "critical")
            else:
                add("insufficient_history", "unknown")
        else:
            transition = audit_sequence(events)
            if transition["status"] != "ok":
                add(transition["reason"], transition["status"])
        if last.get("status") in ("running", "interrupted"):
            add("needs_reconciliation", "warning")
        if last.get("status") == "awaiting_approval":
            add("awaiting_approval", "warning")
        if last.get("status") in _TERMINAL:
            # Não equiparar estado terminal declarado a prova de execução.
            add("terminal_unverified", "unknown")

    return {"status": worst, "reason": "structural_audit",
            "read_only": True, "runs": _band(len(runs)),
            "findings": {code: _band(count) for code, count in sorted(findings.items())}}

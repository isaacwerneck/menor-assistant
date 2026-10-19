"""Auditoria de transições de execução, sem I/O e sem confiar em texto livre."""

_STATES = frozenset(("planned", "awaiting_approval", "queued", "running",
                     "executed", "failed", "interrupted", "verified"))
_ALLOWED = {
    "planned": frozenset(("awaiting_approval", "queued", "failed")),
    "awaiting_approval": frozenset(("queued", "failed")),
    "queued": frozenset(("running", "failed", "interrupted")),
    "running": frozenset(("executed", "failed", "interrupted")),
    "executed": frozenset(("verified",)),
    "failed": frozenset(),
    "interrupted": frozenset(),
    "verified": frozenset(),
}
_FIELDS = ("mission_id", "action_id", "idempotency_key")


def audit_transition(previous, current):
    """Retorna apenas códigos fixos; nunca copia dados privados dos eventos."""
    invalid = {"status": "critical", "reason": "invalid_record"}
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return dict(invalid)
    for record in (previous, current):
        if (type(record.get("status")) is not str or record["status"] not in _STATES
                or any(type(record.get(field)) is not str
                       or not 1 <= len(record[field]) <= 128 for field in _FIELDS)):
            return dict(invalid)
    if any(previous[field] != current[field] for field in _FIELDS):
        return {"status": "critical", "reason": "identity_mismatch"}
    old, new = previous["status"], current["status"]
    if old == new:
        return {"status": "warning", "reason": "duplicate_state"}
    if new in _ALLOWED[old]:
        return {"status": "ok", "reason": "allowed_transition"}
    return {"status": "critical", "reason": "invalid_transition"}


def audit_sequence(events):
    """Audita uma sequência limitada e sem conteúdo de execução."""
    if not isinstance(events, (list, tuple)) or not 2 <= len(events) <= 64:
        return {"status": "unknown", "reason": "insufficient_evidence",
                "checked": 0}
    for index in range(1, len(events)):
        result = audit_transition(events[index - 1], events[index])
        if result["status"] != "ok":
            return {"status": result["status"], "reason": result["reason"],
                    "checked": index}
    return {"status": "ok", "reason": "structural_only",
            "checked": len(events) - 1}

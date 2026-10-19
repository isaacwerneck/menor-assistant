"""Decisão conservadora de recuperação; não executa, consulta ou repete operações."""

_ALLOWED = frozenset(("planned", "awaiting_approval", "queued", "running",
                      "executed", "failed", "interrupted", "verified"))
_TERMINAL = frozenset(("executed", "verified"))
_UNCERTAIN = frozenset(("running", "interrupted"))


def recovery_decision(record, *, persisted=None):
    """Retorna decisão segura, sem I/O, baseada em identidade e evidência explícita.

    Nunca interpreta texto de resposta como prova de execução. Um resultado
    incerto requer reconciliação externa, nunca replay automático.
    """
    unknown = {"decision": "manual_review", "reason": "invalid_evidence",
               "safe_to_retry": False}
    if not isinstance(record, dict):
        return dict(unknown)
    state = record.get("status")
    mission = record.get("mission_id")
    action = record.get("action_id")
    key = record.get("idempotency_key")
    if (type(state) is not str or state not in _ALLOWED
            or any(type(value) is not str or not 1 <= len(value) <= 128
                   for value in (mission, action, key))):
        return dict(unknown)
    if persisted is not None:
        if not isinstance(persisted, dict):
            return dict(unknown)
        if any(persisted.get(field) != record.get(field)
               for field in ("mission_id", "action_id", "idempotency_key")):
            return {"decision": "manual_review", "reason": "identity_mismatch",
                    "safe_to_retry": False}
        prior = persisted.get("status")
        if type(prior) is not str or prior not in _ALLOWED:
            return dict(unknown)
        if prior in _TERMINAL:
            return {"decision": "do_not_replay", "reason": "persisted_terminal",
                    "safe_to_retry": False}
        if prior in _UNCERTAIN:
            return {"decision": "reconcile", "reason": "persisted_uncertain",
                    "safe_to_retry": False}
    if state in _TERMINAL:
        return {"decision": "do_not_replay", "reason": "terminal",
                "safe_to_retry": False}
    if state in _UNCERTAIN:
        return {"decision": "reconcile", "reason": "uncertain_outcome",
                "safe_to_retry": False}
    if state == "awaiting_approval":
        return {"decision": "await_approval", "reason": "approval_required",
                "safe_to_retry": False}
    if state == "queued":
        return {"decision": "check_queue", "reason": "queued_not_executed",
                "safe_to_retry": False}
    if state == "failed":
        return {"decision": "manual_review", "reason": "failure_needs_classification",
                "safe_to_retry": False}
    return {"decision": "plan_only", "reason": "not_started",
            "safe_to_retry": False}

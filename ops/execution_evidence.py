"""Validação fail-closed de evidência persistida recebida de fonte confiável.

Não lê banco, não autentica a origem e não autoriza execução ou replay.
"""
import hashlib
import hmac
import json

from ops.execution_transitions import audit_sequence
from ops.recovery_decision import recovery_decision

_MAX_EVENTS = 64
_MAX_BYTES = 65536
_FIELDS = ("mission_id", "action_id", "idempotency_key")
_STATES = frozenset(("planned", "awaiting_approval", "queued", "running",
                     "executed", "failed", "interrupted", "verified"))


def _valid_event(event):
    return (type(event) is dict
            and type(event.get("status")) is str and event["status"] in _STATES
            and all(type(event.get(field)) is str and 1 <= len(event[field]) <= 128
                    for field in _FIELDS)
            and type(event.get("sequence")) is int and event["sequence"] >= 0)


def _digest(event):
    """Fingerprint estável de campos estritamente permitidos."""
    data = {field: event[field] for field in (*_FIELDS, "status", "sequence")}
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def verify_evidence(events, *, expected_digest=None):
    """Audita ordem, identidade e fingerprint do último evento.

    O digest detecta corrupção acidental; não é assinatura nem prova de origem.
    """
    failure = {"status": "critical", "reason": "invalid_evidence",
               "trusted": False, "safe_to_retry": False}
    if type(events) not in (list, tuple) or not 1 <= len(events) <= _MAX_EVENTS:
        return dict(failure)
    if any(not _valid_event(event) for event in events):
        return dict(failure)
    first = events[0]
    if any(any(event[field] != first[field] for field in _FIELDS) for event in events):
        return {"status": "critical", "reason": "identity_mismatch",
                "trusted": False, "safe_to_retry": False}
    if any(events[i]["sequence"] != events[i - 1]["sequence"] + 1
           for i in range(1, len(events))):
        return {"status": "critical", "reason": "sequence_gap",
                "trusted": False, "safe_to_retry": False}
    if expected_digest is not None:
        if (type(expected_digest) is not str or len(expected_digest) != 64
                or not hmac.compare_digest(_digest(events[-1]), expected_digest)):
            return {"status": "critical", "reason": "digest_mismatch",
                    "trusted": False, "safe_to_retry": False}
    if len(events) > 1:
        transitions = audit_sequence(events)
        if transitions["status"] != "ok":
            return {"status": transitions["status"], "reason": transitions["reason"],
                    "trusted": False, "safe_to_retry": False}
    decision = recovery_decision(events[-1])
    return {"status": "unknown" if len(events) == 1 else "ok",
            "reason": "structural_only", "trusted": False,
            "safe_to_retry": False, "recovery": decision["decision"],
            "last_digest": _digest(events[-1])}


def verify_json_envelope(raw):
    """Lê somente JSON já obtido pelo chamador, com limite explícito de bytes."""
    if type(raw) is not bytes or len(raw) > _MAX_BYTES:
        return {"status": "critical", "reason": "invalid_envelope",
                "trusted": False, "safe_to_retry": False}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        return {"status": "critical", "reason": "invalid_envelope",
                "trusted": False, "safe_to_retry": False}
    if type(payload) is not dict or set(payload) != {"events"}:
        return {"status": "critical", "reason": "invalid_envelope",
                "trusted": False, "safe_to_retry": False}
    return verify_evidence(payload["events"])

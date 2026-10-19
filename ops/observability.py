"""Contrato de observabilidade local V1: agregados estritamente permitidos, sem I/O.

Não coleta banco, logs, prompts, caminhos ou identificadores. Os probes e
contadores são fornecidos por código confiável do backend; não há endpoint aqui.
"""

from collections import deque
from datetime import datetime, timezone
from threading import Lock

from ops.doctor import Check
from ops.smoke import PRIVATE_GET

_VERSION = 1
_STATES = frozenset(("ok", "warning", "critical", "skipped"))
_DOCTOR_CHECKS = ("api", "ollama", "service", "disk", "memory")
_SMOKE_CHECKS = ("api_contract",) + tuple(name for name, _path in PRIVATE_GET)
_COUNT_FIELDS = {
    "queues": ("pending", "active"),
    "tasks": ("running", "blocked", "failed"),
    "errors": ("recent",),
}
_MAX_COUNT = 1_000_000_000
_MAX_RECEIPTS = 64
_MAX_CHECKS = 64


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _status(value):
    return value if type(value) is str and value in _STATES else "unknown"


def _aggregate_status(states):
    values = set(states)
    if "critical" in values:
        return "critical"
    if "warning" in values:
        return "warning"
    if not values or "unknown" in values or "skipped" in values:
        return "unknown"
    return "ok"


def _checks(report, names, *, anonymous=False):
    """Rejeita envelopes incompatíveis, duplicações e estados desconhecidos."""
    if not isinstance(report, dict) or report.get("read_only") is not True:
        return {}
    if anonymous and report.get("authenticated") is not False:
        return {}
    rows = report.get("checks")
    if not isinstance(rows, list) or len(rows) > _MAX_CHECKS:
        return {}
    result = {}
    for row in rows:
        if isinstance(row, Check):
            name, status = row.name, row.status
        elif isinstance(row, dict):
            name, status = row.get("name"), row.get("status")
        else:
            continue
        if type(name) is not str or name not in names:
            continue
        if name in result:
            result[name] = "critical"
        else:
            result[name] = _status(status)
    return result


def _counts(aggregates, section):
    """Somente contagens inteiras agregadas; nenhuma string externa é copiada."""
    fields = _COUNT_FIELDS[section]
    if not isinstance(aggregates, dict):
        return None
    values = aggregates.get(section)
    if not isinstance(values, dict):
        return None
    if any(type(values.get(field)) is not int or not 0 <= values[field] <= _MAX_COUNT
           for field in fields):
        return None
    return {field: values[field] for field in fields}


def _band(count):
    if count == 0:
        return "0"
    if count < 10:
        return "1-9"
    if count < 50:
        return "10-49"
    return "50+"


def _operational(aggregates, section):
    counts = _counts(aggregates, section)
    if counts is None:
        return {"status": "unknown", "evidence": "not_collected"}
    if section == "queues":
        warning = counts["pending"] >= 50
    elif section == "tasks":
        warning = counts["failed"] > 0 or counts["blocked"] > 0
    else:
        warning = counts["recent"] > 0
    return {
        "status": "warning" if warning else "ok",
        "evidence": "trusted_aggregate_only",
        "bands": {key: _band(counts[key]) for key in _COUNT_FIELDS[section]},
    }


def _receipts(checks):
    if not isinstance(checks, (list, tuple)) or not 1 <= len(checks) <= _MAX_RECEIPTS:
        return {"status": "unknown", "evidence": "not_collected", "checked": 0}
    if any(not isinstance(item, Check) for item in checks):
        return {"status": "unknown", "evidence": "invalid_input", "checked": 0}
    return {
        "status": _aggregate_status(_status(item.status) for item in checks),
        "evidence": "structure_only",
        "checked": len(checks),
    }


def build_snapshot(*, doctor_report=None, smoke_report=None, receipt_checks=(),
                   aggregates=None, history=None):
    """Monta envelope JSON seguro a partir de evidências já coletadas no servidor.

    Valores arbitrários de logs, erros, recibos ou tasks jamais são serializados.
    Nenhum campo afirma execução real, privacidade total ou inferência comprovada.
    """
    doctor = _checks(doctor_report, _DOCTOR_CHECKS)
    smoke = _checks(smoke_report, _SMOKE_CHECKS, anonymous=True)
    routes = [smoke.get(name, "unknown") for name, _path in PRIVATE_GET]
    private_status = _aggregate_status(routes)
    if smoke.get("api_contract") != "ok" and private_status == "ok":
        private_status = "unknown"

    components = {
        "api": {"status": doctor.get("api", "unknown"), "evidence": "loopback_health"},
        "ollama": {"status": doctor.get("ollama", "unknown"), "evidence": "api_health_claim_only"},
        "service": {"status": doctor.get("service", "unknown"), "evidence": "systemd_user"},
        "disk": {"status": doctor.get("disk", "unknown"), "evidence": "free_space_threshold"},
        "memory": {"status": doctor.get("memory", "unknown"), "evidence": "linux_memavailable"},
        "api_contract": {"status": smoke.get("api_contract", "unknown"),
                         "evidence": "anonymous_loopback"},
        "private_routes": {"status": private_status, "evidence": "known_anonymous_routes_only"},
        "receipts": _receipts(receipt_checks),
        "queues": _operational(aggregates, "queues"),
        "tasks": _operational(aggregates, "tasks"),
        "errors": _operational(aggregates, "errors"),
    }
    statuses = [component["status"] for component in components.values()]
    snapshot = {
        "contract": "menor.ops.observability",
        "contract_version": _VERSION,
        "collected_at": _now(),
        "read_only": True,
        "assurance": "partial_structural_observation",
        "status": _aggregate_status(statuses),
        "components": components,
        "history": [],
    }
    if isinstance(history, BoundedHistory):
        snapshot["history"] = history.recent()
    return snapshot


class BoundedHistory:
    """Histórico local exclusivamente em memória, sem logs, IDs ou persistência."""

    def __init__(self, max_entries=12):
        if type(max_entries) is not int or not 1 <= max_entries <= 24:
            raise ValueError("max_entries deve estar entre 1 e 24")
        self._entries = deque(maxlen=max_entries)
        self._lock = Lock()

    def add(self, snapshot):
        """Registra somente momento local e status saneado; não retém o snapshot."""
        status = "unknown"
        if isinstance(snapshot, dict):
            status = _status(snapshot.get("status"))
        entry = {"at": _now(), "status": status}
        with self._lock:
            self._entries.append(entry)

    def recent(self):
        """Cópias desacopladas: consumidor não altera registros históricos."""
        with self._lock:
            return [dict(item) for item in self._entries]

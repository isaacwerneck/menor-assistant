"""Auditoria estrutural de recibos do Menor, sem acessar arquivos ou executar ferramentas.

Retorna somente códigos fixos: nunca copia prompts, resultados, URLs ou exceções
dos recibos para os diagnósticos. Estrutura válida não prova execução real.
"""

import re

from ops.doctor import Check

_IMAGE_ID = re.compile(r"^[0-9a-f]{32}$")
_TOOL = re.compile(r"^[a-z][a-z0-9_.-]{2,79}$")
_ARGUMENT = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_MAX_PIXELS = 24_000_000


def _check(name, failures=(), warnings=()):
    if failures:
        return Check(name, "critical", "Contrato inválido: " + ", ".join(sorted(set(failures))))
    if warnings:
        return Check(name, "warning", "Validação limitada: " + ", ".join(sorted(set(warnings))))
    return Check(name, "ok", "Estrutura do recibo compatível; não comprova a execução real.")


def tool_receipt(receipt):
    """Valida estados planejado/executado sem confundir dry-run com ação real."""
    if not isinstance(receipt, dict):
        return _check("tool_receipt", ["not_object"])
    failures = []
    name = receipt.get("tool")
    if not isinstance(name, str) or not _TOOL.fullmatch(name):
        failures.append("invalid_tool")
    state = receipt.get("status")
    if state not in ("planned", "executed"):
        failures.append("invalid_status")
    if state == "planned":
        if type(receipt.get("writes")) is not bool:
            failures.append("missing_writes")
        fields = receipt.get("arguments")
        if (not isinstance(fields, list) or len(fields) > 20
                or any(not isinstance(field, str) or not _ARGUMENT.fullmatch(field) for field in fields)):
            failures.append("invalid_argument_names")
        elif len(set(fields)) != len(fields):
            failures.append("duplicate_arguments")
        if "result" in receipt:
            failures.append("planned_contains_result")
    elif state == "executed" and "result" not in receipt:
        failures.append("executed_missing_result")
    return _check("tool_receipt", failures)


def _dimensions(value, allow_none=False):
    if value is None:
        return allow_none
    return (
        isinstance(value, (tuple, list))
        and len(value) == 2
        and all(type(v) is int and 1 <= v <= 8192 for v in value)
        and value[0] * value[1] <= _MAX_PIXELS
    )


def image_receipt(receipt):
    """Rejeita evidência contraditória, sem ler a imagem ou aceitar arquivo arbitrário."""
    if not isinstance(receipt, dict):
        return _check("image_receipt", ["not_object"])
    failures, warnings = [], []
    if receipt.get("kind") != "image":
        failures.append("invalid_kind")
    image_id = receipt.get("id")
    if not isinstance(image_id, str) or not _IMAGE_ID.fullmatch(image_id):
        failures.append("invalid_image_id")
    if (not isinstance(receipt.get("url"), str) or not isinstance(image_id, str)
            or receipt["url"] != "/images/files/" + image_id):
        failures.append("invalid_image_url")
    if not _dimensions(receipt.get("actual_size")):
        failures.append("invalid_actual_size")
    requested = receipt.get("requested_size")
    if not _dimensions(requested, allow_none=True):
        failures.append("invalid_requested_size")
    elif (requested is not None and _dimensions(receipt.get("actual_size"))
          and list(requested) != list(receipt["actual_size"])):
        warnings.append("dimensions_mismatch")
    if type(receipt.get("file_verified")) is not bool:
        failures.append("missing_file_verification")
    elif receipt["file_verified"] is False:
        warnings.append("file_unverified")
    if type(receipt.get("content_verified")) is not bool:
        failures.append("missing_content_verification")
    if receipt.get("content_verified") is True and receipt.get("file_verified") is False:
        failures.append("content_claim_without_file_verification")
    assessment = receipt.get("vision_model_assessment")
    if assessment is not None and type(assessment) is not bool:
        failures.append("invalid_visual_assessment")
    if assessment is False and receipt.get("content_verified") is True:
        failures.append("contradictory_visual_assessment")
    limitation = receipt.get("limitation")
    if not isinstance(limitation, str) or not limitation.strip():
        failures.append("missing_limitation")
    return _check("image_receipt", failures, warnings)


def agent_result(result):
    """Verifica resposta e eventos de ferramentas; nunca interpreta texto como prova."""
    if not isinstance(result, dict):
        return _check("agent_result", ["not_object"])
    failures, warnings = [], []
    if type(result.get("handled")) is not bool:
        failures.append("invalid_handled")
    if (not isinstance(result.get("phase"), str)
            or not 1 <= len(result["phase"]) <= 80):
        failures.append("invalid_phase")
    reply = result.get("reply")
    if result.get("handled") is True and (not isinstance(reply, str) or not reply.strip()):
        failures.append("missing_reply")
    elif reply is not None and not isinstance(reply, str):
        failures.append("invalid_reply")
    events = result.get("events", [])
    if not isinstance(events, list) or len(events) > 32:
        failures.append("invalid_events")
    else:
        for event in events:
            if not isinstance(event, dict):
                failures.append("invalid_event")
                continue
            name, state = event.get("tool"), event.get("status")
            if not isinstance(name, str) or not _TOOL.fullmatch(name):
                failures.append("invalid_event_tool")
            if state != "executed":
                failures.append("unverified_execution_event")
    if "artifact" in result:
        artifact = image_receipt(result["artifact"])
        if artifact.status == "critical":
            failures.append("invalid_artifact")
        elif artifact.status == "warning":
            warnings.append("artifact_needs_verification")
    if "image" in result:
        artifact = result.get("artifact")
        if (not isinstance(artifact, dict) or not isinstance(result["image"], str)
                or result["image"] != artifact.get("url")):
            failures.append("image_without_matching_artifact")
    return _check("agent_result", failures, warnings)


def summarize(checks):
    """Metadados mínimos para futuro painel; nenhuma leitura persistente."""
    items = list(checks)
    if any(not isinstance(item, Check) for item in items):
        raise ValueError("A auditoria exige objetos Check.")
    return {
        "status": ("critical" if any(item.status == "critical" for item in items)
                   else "warning" if any(item.status == "warning" for item in items) else "ok"),
        "read_only": True,
        "checks": [{"name": item.name, "status": item.status, "detail": item.detail} for item in items],
    }

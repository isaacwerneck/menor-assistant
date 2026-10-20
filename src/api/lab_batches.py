"""Execução local de baterias de avaliação. Sem execução de ferramentas."""
import json
import os
import re
import threading
import time
import unicodedata
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path

from src.api import remote_lab

SUITES = Path(__file__).resolve().parents[2] / "lab" / "suites"
DATA = Path(os.environ.get("MENOR_LAB_DATA_DIR", str(Path.home() / "menor-data" / "lab")))
_LOCK = threading.Lock()
_RUNNING = False
STATE = {"status":  "idle"}


def validate_suite(data):
    if not isinstance(data, dict) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", str(data.get("id", ""))):
        raise ValueError("ID de bateria inválido.")
    group = data.get("comparison_group")
    if group is not None and (not isinstance(group, str)
                              or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", group)):
        raise ValueError("Grupo de comparação inválido.")
    cases = data.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 200:
        raise ValueError("Bateria deve ter de 1 a 200 casos.")
    ids = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Caso inválido.")
        cid = case.get("id")
        if not isinstance(cid, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", cid) or cid in ids:
            raise ValueError("ID de caso inválido ou duplicado.")
        ids.add(cid)
        remote_lab.LabRequest.model_validate(case)
        expected = case.get("expected_contains", [])
        exact = case.get("expected_exact")
        grader = case.get("grader", "strict")
        if grader not in ("strict", "boolean", "numeric"):
            raise ValueError("Tipo de avaliador inválido.")
        if grader == "numeric" and (
                not isinstance(exact, str) or _numeric_value(exact) is None or expected):
            raise ValueError("Avaliador numérico exige um gabarito numérico isolado.")
        if grader == "boolean" and (not isinstance(exact, str)
                                    or _boolean_answer(exact) is None or expected):
            raise ValueError("Avaliador binário exige resposta exata SIM ou NÃO.")
        if not isinstance(expected, list) or len(expected) > 10 or any(
            not isinstance(x, str) or not x or len(x) > 200 for x in expected
        ):
            raise ValueError("Critérios inválidos.")
        if exact is not None and (not isinstance(exact, str) or not exact.strip()
                                  or len(exact) > 200 or expected):
            raise ValueError("Resposta exata inválida ou critérios conflitantes.")
        if case.get("split", "development") not in ("development", "validation"):
            raise ValueError("Divisão de avaliação inválida.")
        criterion = case.get("review_criteria", "")
        if not isinstance(criterion, str) or len(criterion) > 500:
            raise ValueError("Critério de revisão inválido.")
    return data


def _boolean_answer(value):
    """Extrai apenas sim/não isolados, aceitando acento e pontuação final simples."""
    if not isinstance(value, str):
        return None
    folded = unicodedata.normalize("NFKD", value.strip().casefold())
    folded = "".join(letter for letter in folded if not unicodedata.combining(letter))
    match = re.fullmatch(r"(sim|nao)[.!]?", folded)
    return match.group(1) if match else None


def _numeric_value(text):
    """Confere valor numérico simples, sem transformar explicações em respostas."""
    if not isinstance(text, str) or len(text) > 70:
        return None
    normalized = text.strip().replace("\u00a0", " ")
    normalized = re.sub(r"^R\$\s*", "", normalized, flags=re.I)
    normalized = re.sub(r"\s*(?:MB|GB|minutos?)$", "", normalized, flags=re.I).strip()
    # Permite separador de milhar BR só quando todos os grupos têm 3 dígitos.
    if re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?", normalized):
        normalized = normalized.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", normalized):
        normalized = normalized.replace(",", ".")
    else:
        return None
    try:
        number = Decimal(normalized)
        return number if number.is_finite() and abs(number) <= Decimal("1e15") else None
    except InvalidOperation:
        return None


def numeric_format_compliance(case, result):
    """False = valor analisável, mas formato não corresponde ao gabarito estrito."""
    if case.get("grader") != "numeric":
        return None
    reply = result.get("reply", "")
    expected = case.get("expected_exact")
    if not isinstance(reply, str) or not isinstance(expected, str):
        return False
    return reply.strip().casefold() == expected.strip().casefold()


def grade_case(case, result):
    """Apenas verificações determinísticas; casos subjetivos continuam sem nota."""
    exact = case.get("expected_exact")
    tokens = case.get("expected_contains", [])
    if exact is None and not tokens:
        return None
    if result.get("status") not in ("answered", "decision_validated"):
        return False
    reply = result.get("reply", "")
    if not isinstance(reply, str):
        return False
    if exact is not None:
        if case.get("grader") == "boolean":
            return _boolean_answer(reply) == _boolean_answer(exact)
        if case.get("grader") == "numeric":
            parsed = _numeric_value(reply)
            return parsed is not None and parsed == _numeric_value(exact)
        return reply.strip().casefold() == exact.strip().casefold()
    return all(token.casefold() in reply.casefold() for token in tokens)


def suites():
    result = []
    for path in sorted(list(SUITES.glob("*.json")) + list((DATA / "suites").glob("*.json"))):
        try:
            data = validate_suite(json.loads(path.read_text(encoding="utf-8")))
            result.append({"id":  data["id"], "title":  data.get("title", data["id"]),
                           "description":  data.get("description", ""), "cases":  len(data["cases"])})
        except (ValueError, OSError, TypeError):
            continue
    return result


def load_suite(suite_id):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", suite_id):
        raise ValueError("ID inválido.")
    path = DATA / "suites" / (suite_id + ".json")
    if not path.is_file():
        path = SUITES / (suite_id + ".json")
    if not path.is_file():
        raise FileNotFoundError(suite_id)
    return validate_suite(json.loads(path.read_text(encoding="utf-8")))


def save_suite(raw):
    if len(raw) > 200000:
        raise ValueError("Arquivo muito grande.")
    data = validate_suite(json.loads(raw.decode("utf-8")))
    (DATA / "suites").mkdir(parents=True, exist_ok=True)
    path = DATA / "suites" / (data["id"] + ".json")
    if (SUITES / (data["id"] + ".json")).exists():
        raise ValueError("Já existe uma bateria com este ID.")
    if path.exists():
        raise ValueError("Já existe uma bateria com este ID.")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data["id"]


def _run(suite, run_id):
    global _RUNNING
    results = []
    started = datetime.now(timezone.utc).isoformat()
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        for index, case in enumerate(suite["cases"]):
            with _LOCK:
                STATE.update(done=index, total=len(suite["cases"]))
            payload = remote_lab.LabRequest.model_validate(case)
            began = time.monotonic()
            if not remote_lab._INFERENCE.acquire(timeout=60):
                output = {"status":  "busy", "reply":  "", "model":  None}
            else:
                try:
                    try:
                        output = (remote_lab._planner(payload) if payload.mode == "planner"
                                  else remote_lab._direct(payload))
                    except (Exception,) as error:
                        output = {"status":  "inference_failed", "reply":  "", "error_type":  type(error).__name__}
                finally:
                    remote_lab._INFERENCE.release()
            passed = grade_case(case, output)
            results.append({"id": case["id"], "category": case.get("category", "geral"),
                            "split": case.get("split", "development"), "mode": payload.mode,
                            "profile": payload.profile, "grader": case.get("grader", "strict"),
                            "question": payload.message, "history": [item.model_dump() for item in payload.history],
                            "expected_contains": case.get("expected_contains", []),
                            "expected_exact": case.get("expected_exact"),
                            "review_criteria": case.get("review_criteria", ""), "result": output,
                            "elapsed_seconds": round(time.monotonic() - began, 3),
                            "automatic_pass": passed,
                            "format_compliant": numeric_format_compliance(case, output) if passed is True else None})
        report = {"run_id": run_id, "suite_id": suite["id"],
                  "comparison_group": suite.get("comparison_group"),
                  "methodology_version": suite.get("methodology_version", "legacy"),
                  "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
                  "total": len(results),
                  "automatic_passes": sum(x["automatic_pass"] is True for x in results),
                  "automatic_failures": sum(x["automatic_pass"] is False for x in results),
                  "ungraded": sum(x["automatic_pass"] is None for x in results),
                  "numeric_format_mismatches": sum(x["format_compliant"] is False for x in results),
                  "inference_failures": sum(x["result"].get("status")
                                            not in ("answered", "decision_validated") for x in results),
                  "cases": results}
        (DATA / (run_id + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        # Publicar somente métricas, sem perguntas, respostas ou histórico privados.
        summary = {key: report[key] for key in ("run_id", "suite_id", "started_at", "finished_at",
                   "total", "automatic_passes", "automatic_failures", "ungraded")}
        (DATA / (run_id + ".summary.json")).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        publish_status = "disabled"
        if os.environ.get("MENOR_LAB_REPORTS_PUBLISH") == "1":
            try:
                from src.api.lab_publish import publish_summary
                publish_summary(summary)
                publish_status = "published"
            except Exception as error:
                publish_status = "failed: " + type(error).__name__
        with _LOCK:
            STATE.update(status="completed", report_id=run_id, done=len(results), publish_status=publish_status)
    except Exception as error:
        with _LOCK:
            STATE.update(status="failed", error=type(error).__name__)
    finally:
        with _LOCK:
            _RUNNING = False


def start(suite_id):
    global _RUNNING
    suite = load_suite(suite_id)
    with _LOCK:
        if _RUNNING:
            raise RuntimeError("Já existe uma bateria em execução.")
        _RUNNING = True
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[: 8]
        STATE.clear()
        STATE.update(status="running", run_id=run_id, done=0, total=len(suite["cases"]))
    threading.Thread(target=_run, args=(suite, run_id), daemon=True).start()
    return run_id


def state():
    with _LOCK:
        return dict(STATE)


def reports():
    DATA.mkdir(parents=True, exist_ok=True)
    result = []
    for path in sorted(DATA.glob("*.summary.json"), reverse=True)[: 100]:
        try:
            result.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return result


def report_path(run_id):
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}", run_id):
        raise ValueError("ID inválido.")
    path = DATA / (run_id + ".json")
    if not path.is_file():
        raise FileNotFoundError(run_id)
    return path

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

# Rotina de avaliação mais recente. IDs são estáveis e exibidos na UI para
# o operador poder conferir exatamente qual bateria foi solicitada.
RECOMMENDED_BATCHES = {
    "planejamento-supervisionado": (1, "Planos e ferramentas"),
    "programacao-debug": (2, "Programação e correção de erros"),
    "matematica-validacao-v2": (3, "Matemática: valor e formato"),
    "regressoes-planejamento-v3": (4, "Segurança e restrições dos planos"),
}


def _progress_from_summaries():
    """Conta execuções SALVAS por bateria; não usa o histórico do navegador.

    Lê apenas resumos pequenos locais. Cada relatório concluído é contado
    uma vez; ter relatório NÃO implica acerto nem publicação no GitHub.
    """
    progress = {}
    if not DATA.is_dir():
        return progress
    for path in DATA.glob("*.summary.json"):
        try:
            if path.stat().st_size > 4096:
                continue
            summary = json.loads(path.read_text(encoding="utf-8"))
            suite_id = summary.get("suite_id")
            run_id = summary.get("run_id")
            if not isinstance(suite_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", suite_id):
                continue
            if not isinstance(run_id, str) or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}", run_id):
                continue
            if path.name != run_id + ".summary.json":
                continue
            if not (DATA / (run_id + ".json")).is_file():
                continue
            total = summary.get("total")
            passed = summary.get("automatic_passes")
            ungraded = summary.get("ungraded")
            if any(type(n) is not int or not 0 <= n <= 200
                   for n in (total, passed, ungraded)):
                continue
            failures = summary.get("automatic_failures")
            if failures is None:
                # Resumos de versões antigas nem sempre possuem esta coluna.
                failures = total - passed - ungraded
            if type(failures) is not int or failures < 0 or failures > 200:
                continue
            counts = [total, passed, failures, ungraded]
            if passed + failures + ungraded != total:
                continue
            item = progress.setdefault(suite_id, {"run_count": 0, "last_report": None})
            item["run_count"] += 1
            latest = item["last_report"]
            if latest is None or run_id > latest["run_id"]:
                item["last_report"] = {
                    "run_id": run_id, "total": counts[0],
                    "automatic_passes": counts[1], "automatic_failures": counts[2],
                    "ungraded": counts[3],
                }
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return progress


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
                not isinstance(exact, str) or not re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", exact.strip())
                or _numeric_value(exact) is None or expected):
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
    progress = _progress_from_summaries()
    with _LOCK:
        active = STATE.get("suite_id") if STATE.get("status") == "running" else None
    result = []
    for path in sorted(list(SUITES.glob("*.json")) + list((DATA / "suites").glob("*.json"))):
        try:
            data = validate_suite(json.loads(path.read_text(encoding="utf-8")))
            suite_id = data["id"]
            saved = progress.get(suite_id, {"run_count": 0, "last_report": None})
            order, label = RECOMMENDED_BATCHES.get(suite_id, (None, None))
            state = "running" if suite_id == active else (
                "completed" if saved["run_count"] else "pending"
            )
            result.append({
                "id": suite_id, "title": data.get("title", suite_id),
                "description": data.get("description", ""), "cases": len(data["cases"]),
                "source": "imported" if path.parent == DATA / "suites" else "builtin",
                "status": state, "run_count": saved["run_count"],
                "last_report": saved["last_report"], "recommended_order": order,
                "recommended_label": label,
            })
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


def _run(suite, run_id, queue=None):
    global _RUNNING
    results = []
    started = datetime.now(timezone.utc).isoformat()
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        for index, case in enumerate(suite["cases"]):
            with _LOCK:
                STATE.update(done=index, total=len(suite["cases"]))
                if queue is not None:
                    STATE["overall_done"] = queue["completed_cases"] + index
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
            if queue is None:
                STATE.update(status="completed", report_id=run_id, done=len(results),
                             publish_status=publish_status)
            else:
                STATE.update(suite_status="completed", report_id=run_id,
                             done=len(results), publish_status=publish_status,
                             overall_done=queue["completed_cases"] + len(results))
        return True
    except Exception as error:
        with _LOCK:
            if queue is None:
                STATE.update(status="failed", error=type(error).__name__)
            else:
                STATE.update(suite_status="failed", error=type(error).__name__)
        return False
    finally:
        if queue is None:
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
        STATE.update(status="running", suite_id=suite_id, run_id=run_id,
                     done=0, total=len(suite["cases"]))
    threading.Thread(target=_run, args=(suite, run_id), daemon=True).start()
    return run_id



def _run_queue(entries):
    """Executa sequencialmente no servidor, independente da aba do navegador.

    A fila é em memória e não sobrevive ao reinício do processo da API.
    Os relatórios concluídos continuam salvos no disco local.
    """
    global _RUNNING
    total_cases = sum(len(suite["cases"]) for suite, _ in entries)
    completed_cases = 0
    finished = []
    failures = []
    try:
        for position, (suite, run_id) in enumerate(entries, 1):
            context = {"completed_cases": completed_cases}
            with _LOCK:
                STATE.update(
                    status="running", suite_status="running", suite_id=suite["id"],
                    run_id=run_id, done=0, total=len(suite["cases"]),
                    queue_index=position, queue_total=len(entries),
                    overall_done=completed_cases, overall_total=total_cases,
                )
            succeeded = _run(suite, run_id, queue=context)
            finished.append({"suite_id": suite["id"], "run_id": run_id,
                             "status": "completed" if succeeded else "failed"})
            if not succeeded:
                failures.append(suite["id"])
            completed_cases += len(suite["cases"])
            with _LOCK:
                STATE.update(queue_finished=list(finished), queue_failures=list(failures),
                             overall_done=completed_cases)
        with _LOCK:
            STATE.update(
                status="completed_with_errors" if failures else "completed",
                suite_status="idle", queue_index=len(entries),
                queue_finished=list(finished), queue_failures=list(failures),
                overall_done=completed_cases, overall_total=total_cases,
            )
    except Exception as error:
        with _LOCK:
            STATE.update(status="failed", error=type(error).__name__,
                         queue_finished=list(finished), queue_failures=list(failures))
    finally:
        with _LOCK:
            _RUNNING = False


def start_queue(suite_ids):
    """Inicia lotes independentes, um após o outro; valida tudo ANTES de iniciar."""
    global _RUNNING
    if not isinstance(suite_ids, list) or not 1 <= len(suite_ids) <= 24:
        raise ValueError("Selecione entre 1 e 24 baterias.")
    if any(not isinstance(item, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9_-]{1,63}", item) for item in suite_ids):
        raise ValueError("ID de bateria inválido.")
    if len(set(suite_ids)) != len(suite_ids):
        raise ValueError("A mesma bateria foi selecionada mais de uma vez.")
    suites_to_run = [load_suite(suite_id) for suite_id in suite_ids]
    total_cases = sum(len(suite["cases"]) for suite in suites_to_run)
    if total_cases > 800:
        raise ValueError("Limite de 800 casos por fila; divida em duas rodadas.")
    # Alocar IDs antes de publicar o estado, sem iniciar inferência.
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    entries = [(suite, timestamp + "-" + uuid.uuid4().hex[:8])
               for suite in suites_to_run]
    with _LOCK:
        if _RUNNING:
            raise RuntimeError("Já existe uma bateria ou fila em execução.")
        _RUNNING = True
        STATE.clear()
        STATE.update(
            status="running", suite_id=entries[0][0]["id"], run_id=entries[0][1],
            done=0, total=len(entries[0][0]["cases"]),
            queue_index=1, queue_total=len(entries),
            queue_suite_ids=list(suite_ids), queue_finished=[], queue_failures=[],
            overall_done=0, overall_total=total_cases,
        )
    try:
        threading.Thread(target=_run_queue, args=(entries,), daemon=True).start()
    except Exception:
        with _LOCK:
            _RUNNING = False
            STATE.update(status="failed", error="ThreadStartFailed")
        raise
    return {"suite_ids": list(suite_ids), "total": total_cases,
            "run_ids": [run_id for _, run_id in entries]}


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

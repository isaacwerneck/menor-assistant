"""Conciliação de relatórios privados e publicação manual em lote.

Consulta uma única árvore Git do GitHub para identificar blobs iguais e
processa envios aprovados, sequencialmente, sem sobrescrever arquivos.
"""
import hashlib
import json
import os
import threading
import uuid

import requests

from src.api import lab_batches, lab_publish

_LOCK = threading.Lock()
_JOB = {"status": "idle"}


def _report_bytes(report):
    return json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")


def _blob_sha(contents):
    return hashlib.sha1(b"blob " + str(len(contents)).encode("ascii") + bytes([0]) + contents).hexdigest()


def sync_status():
    """GET explícito: não adivinha 'não enviado' se o GitHub estiver inacessível."""
    if not os.environ.get("MENOR_LAB_GITHUB_TOKEN"):
        return {"available": False, "reason": "token_unavailable", "items": {}}
    session = requests.Session()
    session.headers.update({
        "Authorization": "Bearer " + os.environ["MENOR_LAB_GITHUB_TOKEN"],
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        response = session.get(lab_publish.API + "/git/trees/" + lab_publish.BRANCH,
                               params={"recursive": "1"}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("truncated") is not False:
            return {"available": False, "reason": "tree_incomplete", "items": {}}
        tree = payload.get("tree")
        if not isinstance(tree, list):
            return {"available": False, "reason": "invalid_tree", "items": {}}
        remote = {item.get("path"): item.get("sha") for item in tree
                  if isinstance(item, dict) and item.get("type") == "blob"
                  and isinstance(item.get("path"), str)}
    except (requests.RequestException, ValueError, TypeError):
        return {"available": False, "reason": "github_unavailable", "items": {}}
    result = {}
    for item in lab_batches.reports():
        run_id = item.get("run_id")
        if not isinstance(run_id, str):
            continue
        try:
            path = lab_batches.report_path(run_id)
            if path.stat().st_size > 2_000_000:
                result[run_id] = "invalid"
                continue
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("run_id") != run_id:
                result[run_id] = "invalid"
                continue
            key = "lab/reports/full/" + run_id + ".json"
            sha = remote.get(key)
            result[run_id] = ("not_sent" if sha is None else
                              "sent" if sha == _blob_sha(_report_bytes(report)) else "conflict")
        except (OSError, ValueError, TypeError, AttributeError):
            result[run_id] = "invalid"
    return {"available": True, "items": result,
            "counts": {status: list(result.values()).count(status)
                       for status in ("sent", "not_sent", "conflict", "invalid")}}


def _worker(run_ids):
    done = []
    errors = []
    for run_id in run_ids:
        try:
            path = lab_batches.report_path(run_id)
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("run_id") != run_id or path.stat().st_size > 2_000_000:
                raise ValueError("Relatório inconsistente.")
            lab_publish.publish_report(report)
            done.append(run_id)
        except lab_publish.GitHubReportConflict:
            errors.append({"run_id": run_id, "reason": "conflict"})
        except (ValueError, OSError, requests.RequestException, RuntimeError):
            errors.append({"run_id": run_id, "reason": "publish_failed"})
        with _LOCK:
            _JOB.update(done=len(done) + len(errors),
                        published=list(done), errors=list(errors))
    with _LOCK:
        _JOB["status"] = "completed_with_errors" if errors else "completed"


def start_batch(run_ids):
    """Uma aprovação = uma fila; nenhum envio é automático ao terminar avaliação."""
    if os.environ.get("MENOR_LAB_REPORTS_ALLOW_FULL_PUSH") != "1":
        raise RuntimeError("Publicação completa desabilitada no servidor.")
    if not os.environ.get("MENOR_LAB_GITHUB_TOKEN"):
        raise RuntimeError("Token do GitHub indisponível.")
    if (not isinstance(run_ids, list) or not 1 <= len(run_ids) <= 250
            or any(not isinstance(item, str) for item in run_ids)
            or len(set(run_ids)) != len(run_ids)):
        raise ValueError("Selecione de 1 a 250 relatórios distintos.")
    for run_id in run_ids:
        path = lab_batches.report_path(run_id)
        if path.stat().st_size > 2_000_000:
            raise ValueError("Relatório excede limite de publicação.")
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, dict) or report.get("run_id") != run_id:
            raise ValueError("ID do relatório inconsistente.")
    global _JOB
    with _LOCK:
        if _JOB.get("status") == "running":
            raise RuntimeError("Já existe uma publicação em lote.")
        job = uuid.uuid4().hex[:12]
        _JOB = {"status": "running", "job_id": job,
                "total": len(run_ids), "done": 0, "published": [], "errors": []}
        threading.Thread(target=_worker, args=(list(run_ids),), daemon=True).start()
    return {"job_id": job, "total": len(run_ids), "status": "running"}


def batch_state():
    with _LOCK:
        return dict(_JOB)

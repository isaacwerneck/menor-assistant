"""Endpoints autenticados do laboratório de baterias."""
import json
import requests

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse

from src.api import lab_batches, lab_publish, lab_report_sync
from src.security import auth

router = APIRouter()


@router.get("/lab/batches")
def list_batches(request: Request):
    auth.require_owner(request)
    return {"items": lab_batches.suites()}


@router.post("/lab/batches/import")
async def import_batch(request: Request, file: UploadFile = File(...)):
    auth.require_owner(request)
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(422, "Envie um arquivo JSON.")
    try:
        raw = await file.read(200001)
        return {"id": lab_batches.save_suite(raw)}
    except (ValueError, UnicodeError) as error:
        raise HTTPException(422, str(error)) from error
    finally:
        await file.close()


class QueueRequest(BaseModel):
    suite_ids: list[str] = Field(min_length=1, max_length=24)
    model: str | None = Field(default=None, min_length=1, max_length=90)
    models: list[str] | None = Field(default=None, min_length=1, max_length=2)


@router.post("/lab/batches/queue")
def run_batch_queue(body: QueueRequest, request: Request):
    auth.require_owner(request)
    try:
        options = {"model": body.model} if body.model is not None else {}
        if body.models is not None:
            options["models"] = body.models
        return lab_batches.start_queue(body.suite_ids, **options)
    except FileNotFoundError as error:
        raise HTTPException(404, "Uma bateria selecionada não foi encontrada.") from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/lab/batches/{suite_id}/run")
def run_batch(suite_id: str, request: Request, model: str | None = None):
    auth.require_owner(request)
    try:
        options = {"model": model} if model is not None else {}
        return {"run_id": lab_batches.start(suite_id, **options)}
    except FileNotFoundError as error:
        raise HTTPException(404, "Bateria não encontrada.") from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/lab/batches/status")
def batch_status(request: Request):
    auth.require_owner(request)
    return lab_batches.state()


@router.get("/lab/reports")
def batch_reports(request: Request):
    auth.require_owner(request)
    return {"items": lab_batches.reports()}


@router.get("/lab/reports/sync")
def sync_report_status(request: Request):
    auth.require_owner(request)
    return lab_report_sync.sync_status()


class PublishBatchRequest(BaseModel):
    run_ids: list[str] = Field(min_length=1, max_length=250)


@router.post("/lab/reports/publish-batch")
def publish_batch(body: PublishBatchRequest, request: Request):
    auth.require_owner(request)
    try:
        return lab_report_sync.start_batch(body.run_ids)
    except FileNotFoundError as error:
        raise HTTPException(404, "Um relatório selecionado não foi encontrado.") from error
    except (ValueError, json.JSONDecodeError) as error:
        raise HTTPException(422, "Relatório ou seleção inválidos.") from error
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/lab/reports/publish-batch/status")
def publish_batch_status(request: Request):
    auth.require_owner(request)
    return lab_report_sync.batch_state()


@router.get("/lab/reports/{run_id}/download")
def batch_download(run_id: str, request: Request):
    auth.require_owner(request)
    try:
        path = lab_batches.report_path(run_id)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(404, "Relatório não encontrado.") from error
    return FileResponse(path, media_type="application/json", filename=path.name,
                        headers={"Cache-Control": "private, no-store"})


@router.post("/lab/reports/{run_id}/publish")
def batch_publish(run_id: str, request: Request):
    """Push manual de relatório completo. Não aceita conteúdo enviado pelo cliente."""
    auth.require_owner(request)
    try:
        path = lab_batches.report_path(run_id)
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("run_id") != run_id:
            raise ValueError("ID do relatório inconsistente.")
        from src.api.lab_publish import publish_report
        return {"url": publish_report(report)}
    except FileNotFoundError as error:
        raise HTTPException(404, "Relatório não encontrado.") from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except lab_publish.GitHubReportConflict as error:
        raise HTTPException(409, str(error)) from error
    except lab_publish.GitHubPublishRejected as error:
        raise HTTPException(502, str(error)) from error
    except requests.Timeout as error:
        raise HTTPException(504, "Tempo esgotado ao contatar o GitHub.") from error
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else None
        if status == 401:
            detail = "O token de publicação foi recusado pelo GitHub (401)."
        elif status == 403:
            detail = "O GitHub recusou as permissões do token (403)."
        elif status == 404:
            detail = "Branch ou repositório não acessível ao token (404)."
        else:
            detail = "Erro do GitHub durante publicação (HTTP " + str(status or "indefinido") + ")."
        raise HTTPException(502, detail) from error
    except requests.RequestException as error:
        raise HTTPException(502, "Falha de rede durante a publicação no GitHub.") from error
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error

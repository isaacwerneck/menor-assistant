"""Endpoints autenticados do laboratório de baterias."""
import json

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse

from src.api import lab_batches
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


@router.post("/lab/batches/{suite_id}/run")
def run_batch(suite_id: str, request: Request):
    auth.require_owner(request)
    try:
        return {"run_id": lab_batches.start(suite_id)}
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
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error

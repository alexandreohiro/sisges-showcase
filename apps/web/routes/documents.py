from datetime import UTC, datetime
from pathlib import Path
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from apps.web.dependencies.auth import require_dev_mode, require_permission
from infra.persistence.db import get_db
from modules.documents.application.services import DocumentService
from modules.documents.application.secretaria_dataset_status import (
    build_secretaria_audit_package,
    load_secretaria_dataset_status,
    resolve_secretaria_lot_output_path,
    resolve_secretaria_report_output_path,
    resolve_secretaria_semester_review_output_path,
    resolve_secretaria_review_output_path,
)
from scripts.complete_folha_semi_ok_parte1 import (
    build_pairs,
    process_pair,
    write_classification,
    write_reports,
)

router = APIRouter(prefix="/documents", tags=["documents"])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"


class SemiOkParte1Request(BaseModel):
    input_dir: str = Field(..., min_length=1)
    output_dir: str | None = None
    semestre: str = Field(default="2", pattern="^[12]$")


def _now_suffix() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _resolve_input_dir(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail="Pasta de entrada invalida.")
    return path


def _resolve_output_dir(value: str | None) -> Path:
    if value:
        path = Path(value)
        if path.is_absolute():
            resolved = path.resolve()
        elif value.replace("\\", "/").startswith("data/output/"):
            resolved = (PROJECT_ROOT / path).resolve()
        else:
            resolved = (DATA_OUTPUT_ROOT / path).resolve()
    else:
        resolved = (DATA_OUTPUT_ROOT / "semi_ok_parte1_api" / _now_suffix()).resolve()

    output_root = DATA_OUTPUT_ROOT.resolve()
    if resolved != output_root and output_root not in resolved.parents:
        raise HTTPException(
            status_code=400,
            detail="Pasta de saida deve ficar dentro de data/output.",
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


@router.get("/secretaria-dataset/status")
def get_secretaria_dataset_status(
    user=Depends(require_permission("documents.view")),
):
    return load_secretaria_dataset_status()


@router.get("/secretaria-dataset/review-outputs/{output_key}/download")
def download_secretaria_review_output(
    output_key: str,
    user=Depends(require_permission("documents.download")),
):
    file_path = resolve_secretaria_review_output_path(output_key)
    if not file_path:
        raise HTTPException(status_code=404, detail="Fila de revisao nao encontrada.")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="text/csv" if file_path.suffix.lower() == ".csv" else "text/plain",
    )


@router.get("/secretaria-dataset/review-semesters/{period_key}/download")
def download_secretaria_semester_review_output(
    period_key: str,
    user=Depends(require_permission("documents.download")),
):
    file_path = resolve_secretaria_semester_review_output_path(period_key)
    if not file_path:
        raise HTTPException(status_code=404, detail="Fila semestral nao encontrada.")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="text/csv",
    )


@router.get("/secretaria-dataset/lots/{lot_name}/download")
def download_secretaria_lot_output(
    lot_name: str,
    user=Depends(require_permission("documents.download")),
):
    file_path = resolve_secretaria_lot_output_path(lot_name)
    if not file_path:
        raise HTTPException(status_code=404, detail="Lote do inventario nao encontrado.")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="text/csv",
    )


@router.get("/secretaria-dataset/reports/{report_key}/download")
def download_secretaria_report_output(
    report_key: str,
    user=Depends(require_permission("documents.download")),
):
    file_path = resolve_secretaria_report_output_path(report_key)
    if not file_path:
        raise HTTPException(status_code=404, detail="Relatorio do inventario nao encontrado.")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/json" if file_path.suffix.lower() == ".json" else "text/plain",
    )


@router.get("/secretaria-dataset/audit-package/download")
def download_secretaria_audit_package(
    user=Depends(require_permission("documents.download")),
):
    package = build_secretaria_audit_package()
    if not package:
        raise HTTPException(status_code=404, detail="Pacote de auditoria nao encontrado.")

    return StreamingResponse(
        BytesIO(package),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="pacote_auditoria_secretaria.zip"',
        },
    )


@router.post("/folhas/semi-ok-parte1/process")
def process_folhas_semi_ok_parte1(
    payload: SemiOkParte1Request,
    user=Depends(require_dev_mode),
):
    input_dir = _resolve_input_dir(payload.input_dir)
    output_dir = _resolve_output_dir(payload.output_dir)

    pairs, classified = build_pairs(input_dir)
    write_classification(output_dir, classified, pairs)
    results = [process_pair(pair, output_dir, payload.semestre) for pair in pairs]
    write_reports(output_dir, input_dir, results)

    return {
        "status": "CONCLUIDO" if not any(item.status == "ERROR" for item in results) else "COM_ERROS",
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "semestre": payload.semestre,
        "total_pares": len(results),
        "ok": sum(item.status == "OK" for item in results),
        "ok_with_warnings": sum(item.status == "OK_WITH_WARNINGS" for item in results),
        "errors": sum(item.status == "ERROR" for item in results),
        "reports": {
            "matriz": str(output_dir / "matriz_pares_semi_ok.csv"),
            "resumo_csv": str(output_dir / "resumo_lote_semi_ok_parte1.csv"),
            "resumo_json": str(output_dir / "resumo_lote_semi_ok_parte1.json"),
            "relatorio_txt": str(output_dir / "RELATORIO_LOTE_SEMI_OK_PARTE1.txt"),
        },
        "items": [
            {
                "key": item.key,
                "status": item.status,
                "warnings": item.warnings,
                "errors": item.errors,
                "output_odt": item.output_odt,
                "inserted_lines": item.inserted_lines,
            }
            for item in results
        ],
    }


@router.get("/recent")
def get_recent_documents(
    limit: int = Query(default=10, ge=1, le=50),
    user=Depends(require_permission("documents.view")),
    db=Depends(get_db),
):
    service = DocumentService(db)
    items = service.list_recent(limit=limit)
    return {"items": [service.to_dict(item) for item in items]}


@router.get("/history")
def get_documents_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user=Depends(require_permission("documents.view")),
    db=Depends(get_db),
):
    service = DocumentService(db)
    items = service.list_history(limit=limit, offset=offset)
    return {"items": [service.to_dict(item) for item in items]}


@router.get("/{document_id}")
def get_document(
    document_id: str,
    user=Depends(require_permission("documents.view")),
    db=Depends(get_db),
):
    service = DocumentService(db)
    doc = service.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return {"item": service.to_dict(doc)}


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    user=Depends(require_permission("documents.download")),
    db=Depends(get_db),
):
    service = DocumentService(db)
    doc = service.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    file_path = Path(doc.output_path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo físico não encontrado.")

    return FileResponse(
        path=str(file_path),
        filename=doc.filename,
        media_type="application/octet-stream",
    )

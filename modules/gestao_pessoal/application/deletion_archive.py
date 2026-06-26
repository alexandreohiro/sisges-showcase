from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import inspect

from infra.config import settings
from infra.persistence.models import (
    CalculoTempoServicoModel,
    CompilerFileModel,
    CompilerRunModel,
    CompilerVariableSnapshotModel,
    CTSMModel,
    FolhaAlteracaoModel,
    FolhaEventoModel,
    MilitarModel,
    MilitarPeriodoServicoModel,
    SicapexEventoFuncionalModel,
    SicapexImportFileModel,
    TarefaModel,
    WorkflowItemModel,
)


@dataclass(frozen=True)
class MilitarDeletionArchiveResult:
    path: Path
    sha256: str
    manifest: dict[str, Any]


@dataclass(frozen=True)
class MilitarDeletionArchiveValidation:
    path: Path
    ok: bool
    sha256: str
    errors: list[str]
    warnings: list[str]
    manifest: dict[str, Any]
    summary: dict[str, Any]


@dataclass(frozen=True)
class MilitarDeletionArchiveRestoreDryRun:
    path: Path
    ok: bool
    can_restore: bool
    errors: list[str]
    warnings: list[str]
    conflicts: list[dict[str, Any]]
    validation: MilitarDeletionArchiveValidation
    restore_plan: dict[str, Any]


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _model_to_dict(model: Any) -> dict[str, Any]:
    mapper = inspect(model).mapper
    return {column.key: getattr(model, column.key) for column in mapper.column_attrs}


def _rows(query) -> list[dict[str, Any]]:
    return [_model_to_dict(row) for row in query.all()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_militar_deletion_archive(
    path: Path | str,
    *,
    expected_sha256: str | None = None,
) -> MilitarDeletionArchiveValidation:
    """Validate a hard-delete recovery ZIP without restoring anything."""

    archive_path = Path(path)
    errors: list[str] = []
    warnings: list[str] = []
    manifest: dict[str, Any] = {}
    snapshot: dict[str, Any] = {}

    if not archive_path.exists():
        return MilitarDeletionArchiveValidation(
            path=archive_path,
            ok=False,
            sha256="",
            errors=["ERR_ARCHIVE_NOT_FOUND"],
            warnings=[],
            manifest={},
            summary={},
        )

    digest = _sha256(archive_path)
    if expected_sha256 and digest != expected_sha256:
        errors.append("ERR_ARCHIVE_SHA256_MISMATCH")

    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            for required in {"manifest.json", "snapshot.json", "RESTORE_NOTES.txt"}:
                if required not in names:
                    errors.append(f"ERR_ARCHIVE_MISSING_{required.upper().replace('.', '_')}")
            bad_member = archive.testzip()
            if bad_member:
                errors.append(f"ERR_ARCHIVE_CORRUPTED_MEMBER:{bad_member}")

            if "manifest.json" in names:
                manifest = json.loads(archive.read("manifest.json"))
            if "snapshot.json" in names:
                snapshot = json.loads(archive.read("snapshot.json"))
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        errors.append(f"ERR_ARCHIVE_INVALID:{type(exc).__name__}")

    if manifest.get("kind") != "MILITAR_HARD_DELETE_ARCHIVE":
        errors.append("ERR_ARCHIVE_KIND_INVALID")
    if not snapshot.get("militar"):
        errors.append("ERR_ARCHIVE_MILITAR_SNAPSHOT_MISSING")
    if "deleted_records" not in snapshot:
        errors.append("ERR_ARCHIVE_DELETED_RECORDS_MISSING")
    if "detached_records" not in snapshot:
        errors.append("ERR_ARCHIVE_DETACHED_RECORDS_MISSING")
    if not manifest.get("restore_note"):
        warnings.append("WARN_ARCHIVE_RESTORE_NOTE_MISSING")

    summary = {
        "militar_id": manifest.get("militar_id"),
        "identidade": manifest.get("identidade"),
        "deleted_records": {
            key: len(value) if isinstance(value, list) else 0
            for key, value in snapshot.get("deleted_records", {}).items()
        },
        "detached_records": {
            key: len(value) if isinstance(value, list) else 0
            for key, value in snapshot.get("detached_records", {}).items()
        },
    }
    return MilitarDeletionArchiveValidation(
        path=archive_path,
        ok=not errors,
        sha256=digest,
        errors=errors,
        warnings=warnings,
        manifest=manifest,
        summary=summary,
    )


def dry_run_militar_deletion_archive_restore(
    db,
    path: Path | str,
    *,
    expected_sha256: str | None = None,
) -> MilitarDeletionArchiveRestoreDryRun:
    """Build a restore plan for a deletion archive without writing to the database."""

    archive_path = Path(path)
    validation = validate_militar_deletion_archive(
        archive_path,
        expected_sha256=expected_sha256,
    )
    errors = list(validation.errors)
    warnings = list(validation.warnings)
    conflicts: list[dict[str, Any]] = []
    restore_plan: dict[str, Any] = {}

    if validation.ok:
        with zipfile.ZipFile(archive_path) as archive:
            snapshot = json.loads(archive.read("snapshot.json"))

        militar_snapshot = snapshot.get("militar") or {}
        militar_id = militar_snapshot.get("id")
        identidade = militar_snapshot.get("identidade")

        if militar_id is not None:
            existing_by_id = db.get(MilitarModel, militar_id)
            if existing_by_id is not None:
                conflicts.append(
                    {
                        "code": "MILITAR_ID_EXISTS",
                        "field": "id",
                        "value": militar_id,
                        "existing_nome": existing_by_id.nome_completo,
                    }
                )

        if identidade:
            existing_by_identity = (
                db.query(MilitarModel)
                .filter(MilitarModel.identidade == identidade)
                .one_or_none()
            )
            if existing_by_identity is not None and existing_by_identity.id != militar_id:
                conflicts.append(
                    {
                        "code": "MILITAR_IDENTIDADE_EXISTS",
                        "field": "identidade",
                        "value": identidade,
                        "existing_id": existing_by_identity.id,
                        "existing_nome": existing_by_identity.nome_completo,
                    }
                )

        deleted_counts = {
            key: len(value) if isinstance(value, list) else 0
            for key, value in snapshot.get("deleted_records", {}).items()
        }
        detached_counts = {
            key: len(value) if isinstance(value, list) else 0
            for key, value in snapshot.get("detached_records", {}).items()
        }
        restore_plan = {
            "mode": "DRY_RUN",
            "writes_database": False,
            "militar": {
                "id": militar_id,
                "identidade": identidade,
                "nome_completo": militar_snapshot.get("nome_completo"),
                "would_create": bool(militar_snapshot),
            },
            "restore_deleted_records": deleted_counts,
            "relink_detached_records": detached_counts,
            "total_deleted_records": sum(deleted_counts.values()),
            "total_detached_records": sum(detached_counts.values()),
        }
    else:
        warnings.append("WARN_RESTORE_PLAN_NOT_BUILT")

    return MilitarDeletionArchiveRestoreDryRun(
        path=archive_path,
        ok=not errors,
        can_restore=not errors and not conflicts,
        errors=errors,
        warnings=warnings,
        conflicts=conflicts,
        validation=validation,
        restore_plan=restore_plan,
    )


def build_militar_deletion_archive(db, militar: MilitarModel) -> MilitarDeletionArchiveResult:
    """Create a recovery ZIP before the irreversible database delete."""

    now = datetime.now(UTC)
    identity = (militar.identidade or "sem_identidade").replace("/", "_").replace("\\", "_")
    archive_dir = settings.base_dir / "data" / "trash" / "gestao_pessoal" / "militares"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"{now.strftime('%Y%m%dT%H%M%SZ')}_militar_{militar.id}_{identity}.zip"
    archive_path = archive_dir / archive_name

    folha_ids = [
        item.id
        for item in db.query(FolhaAlteracaoModel.id)
        .filter(FolhaAlteracaoModel.militar_id == militar.id)
        .all()
    ]

    snapshot = {
        "schema_version": "sisges-militar-deletion-archive-v1",
        "created_at": now.isoformat(),
        "militar": _model_to_dict(militar),
        "deleted_records": {
            "folha_alteracao": _rows(
                db.query(FolhaAlteracaoModel).filter(FolhaAlteracaoModel.militar_id == militar.id),
            ),
            "folha_evento": _rows(
                db.query(FolhaEventoModel).filter(FolhaEventoModel.folha_id.in_(folha_ids)),
            )
            if folha_ids
            else [],
            "ctsm": _rows(db.query(CTSMModel).filter(CTSMModel.militar_id == militar.id)),
            "calculo_tempo_servico": _rows(
                db.query(CalculoTempoServicoModel).filter(CalculoTempoServicoModel.militar_id == militar.id),
            ),
            "militar_periodo_servico": _rows(
                db.query(MilitarPeriodoServicoModel).filter(MilitarPeriodoServicoModel.militar_id == militar.id),
            ),
            "sicapex_evento_funcional": _rows(
                db.query(SicapexEventoFuncionalModel).filter(SicapexEventoFuncionalModel.militar_id == militar.id),
            ),
        },
        "detached_records": {
            "compiler_variable_snapshot": _rows(
                db.query(CompilerVariableSnapshotModel).filter(
                    CompilerVariableSnapshotModel.militar_id == militar.id,
                ),
            ),
            "compiler_file": _rows(db.query(CompilerFileModel).filter(CompilerFileModel.militar_id == militar.id)),
            "compiler_run": _rows(db.query(CompilerRunModel).filter(CompilerRunModel.militar_id == militar.id)),
            "sicapex_import_file": _rows(
                db.query(SicapexImportFileModel).filter(SicapexImportFileModel.militar_id == militar.id),
            ),
            "tarefa": _rows(db.query(TarefaModel).filter(TarefaModel.militar_id == militar.id)),
            "workflow_items": _rows(db.query(WorkflowItemModel).filter(WorkflowItemModel.militar_id == militar.id)),
        },
    }
    manifest = {
        "schema_version": "sisges-trash-manifest-v1",
        "kind": "MILITAR_HARD_DELETE_ARCHIVE",
        "created_at": now.isoformat(),
        "militar_id": militar.id,
        "nome_completo": militar.nome_completo,
        "identidade": militar.identidade,
        "archive_filename": archive_name,
        "restore_note": "Arquivo de recuperacao tecnica. Restauracao deve ser feita por desenvolvedor com revisao manual.",
    }

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default))
        archive.writestr("snapshot.json", json.dumps(snapshot, ensure_ascii=False, indent=2, default=_json_default))
        archive.writestr(
            "RESTORE_NOTES.txt",
            (
                "Este ZIP foi gerado antes de uma exclusao fisica de militar no SISGES.\n"
                "Ele nao restaura automaticamente o banco. Use snapshot.json para conferencia e restauracao tecnica.\n"
                "Nunca restaure sem validar identidade, vinculos, documentos e duplicidades.\n"
            ),
        )

    digest = _sha256(archive_path)
    manifest["sha256"] = digest
    return MilitarDeletionArchiveResult(path=archive_path, sha256=digest, manifest=manifest)

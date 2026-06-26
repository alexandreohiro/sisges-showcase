from __future__ import annotations

from datetime import date
from pathlib import Path
import shutil
from uuid import uuid4

from sqlalchemy.orm import Session

from infra.persistence.models import (
    CompilerFileModel,
    CompilerRunModel,
    CompilerValidationModel,
    CompilerVariableSnapshotModel,
)
from modules.documents.application.services import DocumentService
from shared.utils.hashing import sha256_file
from shared.utils.strings import slugify_filename


COMPILER_MEMORY_ROOT = Path("data/compiler_memory")

RUN_STATUS_RECEBIDO = "RECEBIDO"
RUN_STATUS_CONCLUIDO = "CONCLUIDO"
RUN_STATUS_CONCLUIDO_COM_PENDENCIAS = "CONCLUIDO_COM_PENDENCIAS"
RUN_STATUS_FALHOU = "FALHOU"


class CompilerMemoryService:
    def __init__(self, db: Session, *, root: Path | str = COMPILER_MEMORY_ROOT) -> None:
        self.db = db
        self.root = Path(root)
        self.document_service = DocumentService(db)

    def create_run(
        self,
        *,
        tipo_compilacao: str,
        created_by_user_id: str | None,
        militar_id: int | None = None,
        nome_militar_snapshot: str | None = None,
        identidade_snapshot: str | None = None,
        posto_grad_snapshot: str | None = None,
        periodo_inicio: date | None = None,
        periodo_fim: date | None = None,
        ano: int | None = None,
        semestre: str | None = None,
        fonte_tempo: str | None = None,
        fonte_eventos: str | None = None,
    ) -> CompilerRunModel:
        run = CompilerRunModel(
            id=str(uuid4()),
            trace_id=str(uuid4()),
            tipo_compilacao=tipo_compilacao,
            status=RUN_STATUS_RECEBIDO,
            militar_id=militar_id,
            nome_militar_snapshot=nome_militar_snapshot,
            identidade_snapshot=identidade_snapshot,
            posto_grad_snapshot=posto_grad_snapshot,
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            ano=ano,
            semestre=semestre,
            fonte_tempo=fonte_tempo,
            fonte_eventos=fonte_eventos,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(run)
        self.db.flush()
        return run

    def register_input_file(
        self,
        *,
        run: CompilerRunModel,
        source_path: Path | str,
        role: str,
        original_filename: str | None,
        mime_type: str | None,
        owner_user_id: str | None,
        militar_id: int | None = None,
        source_kind: str | None = None,
        page_count: int | None = None,
    ) -> CompilerFileModel:
        source = Path(source_path)
        sha = sha256_file(source)
        filename = self._memory_filename(source.name, sha)
        target = self.root / run.id / "inputs" / role / filename
        return self._register_file(
            source_path=source,
            target_path=target,
            role=role,
            document_kind=f"COMPILER_{role}",
            source_module="compilador.memory",
            owner_user_id=owner_user_id,
            run=run,
            militar_id=militar_id,
            original_filename=original_filename,
            mime_type=mime_type,
            source_kind=source_kind,
            page_count=page_count,
        )

    def register_reference_file(
        self,
        *,
        source_path: Path | str,
        role: str,
        original_filename: str | None,
        mime_type: str | None,
        owner_user_id: str | None,
        militar_id: int | None = None,
        source_kind: str | None = None,
        page_count: int | None = None,
    ) -> CompilerFileModel:
        source = Path(source_path)
        sha = sha256_file(source)
        filename = self._memory_filename(original_filename or source.name, sha, include_hash=False)
        target = self.root / "references" / sha / filename
        return self._register_file(
            source_path=source,
            target_path=target,
            role=role,
            document_kind=f"COMPILER_{role}",
            source_module="compilador.memory",
            owner_user_id=owner_user_id,
            militar_id=militar_id,
            original_filename=original_filename,
            mime_type=mime_type,
            source_kind=source_kind,
            page_count=page_count,
        )

    def register_output_file(
        self,
        *,
        run: CompilerRunModel,
        source_path: Path | str,
        role: str,
        owner_user_id: str | None,
        militar_id: int | None = None,
        source_kind: str | None = None,
        page_count: int | None = None,
    ) -> CompilerFileModel:
        source = Path(source_path)
        target = self.root / run.id / "outputs" / role / source.name
        return self._register_file(
            source_path=source,
            target_path=target,
            role=role,
            document_kind=f"COMPILER_{role}",
            source_module="compilador.memory",
            owner_user_id=owner_user_id,
            run=run,
            militar_id=militar_id,
            original_filename=source.name,
            mime_type=None,
            source_kind=source_kind,
            page_count=page_count,
        )

    def register_existing_document_file(
        self,
        *,
        run: CompilerRunModel,
        source_path: Path | str,
        role: str,
        document_id: str,
        militar_id: int | None = None,
        original_filename: str | None = None,
        mime_type: str | None = None,
        source_kind: str | None = None,
        page_count: int | None = None,
    ) -> CompilerFileModel:
        source = Path(source_path)
        target = self.root / run.id / "outputs" / role / source.name
        source = source.resolve()
        target = target.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        file = CompilerFileModel(
            id=str(uuid4()),
            run_id=run.id,
            document_id=document_id,
            militar_id=militar_id,
            role=role,
            filename=target.name,
            original_filename=original_filename or source.name,
            mime_type=mime_type,
            extension=target.suffix.lower(),
            storage_path=str(target).replace("\\", "/"),
            sha256=sha256_file(target),
            size_bytes=target.stat().st_size,
            page_count=page_count,
            source_kind=source_kind,
        )
        self.db.add(file)
        self.db.flush()
        return file

    def save_variable_snapshot(
        self,
        *,
        variables_json: dict,
        run_id: str | None = None,
        file_id: str | None = None,
        militar_id: int | None = None,
        schema_version: str = "compiler-memory-v1",
        warnings_json: list | None = None,
        pending_json: list | None = None,
        confidence_json: dict | None = None,
    ) -> CompilerVariableSnapshotModel:
        snapshot = CompilerVariableSnapshotModel(
            id=str(uuid4()),
            run_id=run_id,
            file_id=file_id,
            militar_id=militar_id,
            schema_version=schema_version,
            variables_json=variables_json,
            warnings_json=warnings_json or [],
            pending_json=pending_json or [],
            confidence_json=confidence_json or {},
        )
        self.db.add(snapshot)
        self.db.flush()
        return snapshot

    def add_validation(
        self,
        *,
        level: str,
        code: str,
        message: str,
        run_id: str | None = None,
        file_id: str | None = None,
        field: str | None = None,
        payload_json: dict | None = None,
    ) -> CompilerValidationModel:
        validation = CompilerValidationModel(
            id=str(uuid4()),
            run_id=run_id,
            file_id=file_id,
            level=level,
            code=code,
            message=message,
            field=field,
            payload_json=payload_json,
        )
        self.db.add(validation)
        self.db.flush()
        return validation

    def add_validations(self, validations: list[dict]) -> list[CompilerValidationModel]:
        return [self.add_validation(**item) for item in validations]

    def finalize_run(self, run: CompilerRunModel, *, has_pending: bool = False) -> CompilerRunModel:
        run.status = RUN_STATUS_CONCLUIDO_COM_PENDENCIAS if has_pending else RUN_STATUS_CONCLUIDO
        run.finished_at = self._now()
        self.db.flush()
        return run

    def fail_run(self, run: CompilerRunModel, *, error_message: str) -> CompilerRunModel:
        run.status = RUN_STATUS_FALHOU
        run.error_message = error_message
        run.finished_at = self._now()
        self.db.flush()
        return run

    def list_runs(
        self,
        *,
        militar_id: int | None = None,
        nome: str | None = None,
        identidade: str | None = None,
        ano: int | None = None,
        semestre: str | None = None,
        status: str | None = None,
        tipo_compilacao: str | None = None,
        limit: int = 100,
    ) -> list[CompilerRunModel]:
        query = self.db.query(CompilerRunModel)
        if militar_id is not None:
            query = query.filter(CompilerRunModel.militar_id == militar_id)
        if nome:
            query = query.filter(CompilerRunModel.nome_militar_snapshot.ilike(f"%{nome}%"))
        if identidade:
            query = query.filter(CompilerRunModel.identidade_snapshot == identidade)
        if ano is not None:
            query = query.filter(CompilerRunModel.ano == ano)
        if semestre:
            query = query.filter(CompilerRunModel.semestre == semestre)
        if status:
            query = query.filter(CompilerRunModel.status == status)
        if tipo_compilacao:
            query = query.filter(CompilerRunModel.tipo_compilacao == tipo_compilacao)
        return query.order_by(CompilerRunModel.created_at.desc()).limit(limit).all()

    def get_run_detail(self, run_id: str) -> CompilerRunModel | None:
        return self.db.get(CompilerRunModel, run_id)

    def list_files(self, run_id: str) -> list[CompilerFileModel]:
        return (
            self.db.query(CompilerFileModel)
            .filter(CompilerFileModel.run_id == run_id)
            .order_by(CompilerFileModel.created_at.asc())
            .all()
        )

    def get_file(self, file_id: str) -> CompilerFileModel | None:
        return self.db.get(CompilerFileModel, file_id)

    def download_file(self, file_id: str) -> Path:
        file = self.get_file(file_id)
        if not file:
            raise FileNotFoundError("Arquivo do Compilador nao encontrado.")
        path = Path(file.storage_path)
        if not path.exists():
            raise FileNotFoundError("Arquivo fisico do Compilador nao encontrado.")
        return path

    def list_references(
        self,
        *,
        militar_id: int | None = None,
        nome: str | None = None,
        identidade: str | None = None,
        ano: int | None = None,
        semestre: str | None = None,
        tipo_documento: str | None = None,
        role: str | None = None,
        limit: int = 100,
    ) -> list[CompilerFileModel]:
        query = self.db.query(CompilerFileModel).filter(
            CompilerFileModel.role.in_(
                (
                    "MEMORY_REFERENCE_FOLHA_PDF",
                    "MEMORY_REFERENCE_FOLHA_ODT",
                    "MEMORY_REFERENCE_BI_PDF",
                    "MEMORY_REFERENCE_BI_ODT",
                )
            )
        )
        if militar_id is not None:
            query = query.filter(CompilerFileModel.militar_id == militar_id)
        if role:
            query = query.filter(CompilerFileModel.role == role)
        if tipo_documento:
            query = query.filter(CompilerFileModel.source_kind == tipo_documento)
        if nome or identidade or ano is not None or semestre:
            query = query.join(CompilerVariableSnapshotModel, CompilerVariableSnapshotModel.file_id == CompilerFileModel.id)
            if nome:
                query = query.filter(CompilerVariableSnapshotModel.variables_json["nome_completo"].as_string().ilike(f"%{nome}%"))
            if identidade:
                query = query.filter(CompilerVariableSnapshotModel.variables_json["identidade"].as_string() == identidade)
            if ano is not None:
                query = query.filter(CompilerVariableSnapshotModel.variables_json["ano"].as_integer() == ano)
            if semestre:
                query = query.filter(CompilerVariableSnapshotModel.variables_json["semestre"].as_string() == semestre)
        return query.order_by(CompilerFileModel.created_at.desc()).limit(limit).all()

    def latest_snapshot_for_file(self, file_id: str) -> CompilerVariableSnapshotModel | None:
        return (
            self.db.query(CompilerVariableSnapshotModel)
            .filter(CompilerVariableSnapshotModel.file_id == file_id)
            .order_by(CompilerVariableSnapshotModel.created_at.desc())
            .first()
        )

    def validations_for_file(self, file_id: str) -> list[CompilerValidationModel]:
        return (
            self.db.query(CompilerValidationModel)
            .filter(CompilerValidationModel.file_id == file_id)
            .order_by(CompilerValidationModel.created_at.asc())
            .all()
        )

    def snapshots_for_run(self, run_id: str) -> list[CompilerVariableSnapshotModel]:
        return (
            self.db.query(CompilerVariableSnapshotModel)
            .filter(CompilerVariableSnapshotModel.run_id == run_id)
            .order_by(CompilerVariableSnapshotModel.created_at.asc())
            .all()
        )

    def validations_for_run(self, run_id: str) -> list[CompilerValidationModel]:
        return (
            self.db.query(CompilerValidationModel)
            .filter(CompilerValidationModel.run_id == run_id)
            .order_by(CompilerValidationModel.created_at.asc())
            .all()
        )

    def _register_file(
        self,
        *,
        source_path: Path,
        target_path: Path,
        role: str,
        document_kind: str,
        source_module: str,
        owner_user_id: str | None,
        run: CompilerRunModel | None = None,
        militar_id: int | None = None,
        original_filename: str | None = None,
        mime_type: str | None = None,
        source_kind: str | None = None,
        page_count: int | None = None,
    ) -> CompilerFileModel:
        source_path = source_path.resolve()
        target_path = target_path.resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with source_path.open("rb") as src, target_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Falha ao copiar {source_path} para {target_path}") from exc
        sha = sha256_file(target_path)
        storage_path = str(target_path).replace("\\", "/")
        document = self.document_service.register_document(
            kind=document_kind,
            filename=target_path.name,
            status="stored",
            source_module=source_module,
            output_path=storage_path,
            owner_user_id=owner_user_id,
            trace_id=run.trace_id if run else None,
            input_sha256=sha,
            output_sha256=sha,
            metadata={
                "compiler_file_role": role,
                "compiler_run_id": run.id if run else None,
                "source_kind": source_kind,
            },
        )
        file = CompilerFileModel(
            id=str(uuid4()),
            run_id=run.id if run else None,
            document_id=document.id,
            militar_id=militar_id,
            role=role,
            filename=target_path.name,
            original_filename=original_filename,
            mime_type=mime_type,
            extension=target_path.suffix.lower(),
            storage_path=storage_path,
            sha256=sha,
            size_bytes=target_path.stat().st_size,
            page_count=page_count,
            source_kind=source_kind,
        )
        self.db.add(file)
        self.db.flush()
        return file

    @staticmethod
    def _memory_filename(filename: str, sha: str, *, include_hash: bool = True) -> str:
        suffix = Path(filename).suffix.lower()
        stem = slugify_filename(Path(filename).stem, fallback="arquivo")[:40].strip("_-") or "arquivo"
        return f"{sha[:16]}_{stem}{suffix}" if include_hash else f"{stem}{suffix}"

    @staticmethod
    def _now():
        from infra.persistence.models import utcnow_naive

        return utcnow_naive()

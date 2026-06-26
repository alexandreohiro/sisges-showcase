from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import unicodedata

from sqlalchemy.orm import Session

from infra.persistence.models import CompilerFileModel, MilitarModel
from modules.compilador.application.compiler_memory_service import CompilerMemoryService
from modules.compilador.application.reference_folha_pdf_parser import (
    compiler_validations_from_parse,
    parse_reference_folha_pdf,
)
from shared.utils.hashing import sha256_file


@dataclass
class CompilerReferenceImportItem:
    filename: str
    sha256: str
    status: str
    file_id: str | None = None
    run_id: str | None = None
    document_id: str | None = None
    militar_id: int | None = None
    nome: str | None = None
    identidade_mascarada: str | None = None
    ano: int | None = None
    semestre: str | None = None
    eventos_count: int = 0
    warnings: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class CompilerReferenceImportReport:
    source_folder: str
    total_files: int = 0
    imported_count: int = 0
    updated_count: int = 0
    duplicate_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
    matched_militares: int = 0
    items: list[CompilerReferenceImportItem] = field(default_factory=list)


class CompilerReferenceImporter:
    def __init__(
        self,
        db: Session,
        *,
        memory_service: CompilerMemoryService | None = None,
        owner_user_id: str | None = None,
        dry_run: bool = False,
        refresh_existing: bool = False,
    ) -> None:
        self.db = db
        self.memory_service = memory_service or CompilerMemoryService(db)
        self.owner_user_id = owner_user_id
        self.dry_run = dry_run
        self.refresh_existing = refresh_existing

    def import_folder(self, folder_path: Path | str) -> CompilerReferenceImportReport:
        folder = Path(folder_path)
        pdfs = sorted(path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf")
        report = CompilerReferenceImportReport(source_folder=str(folder), total_files=len(pdfs))
        for pdf_path in pdfs:
            item = self.import_pdf(pdf_path)
            report.items.append(item)
            if item.status == "IMPORTED":
                report.imported_count += 1
            elif item.status == "UPDATED":
                report.updated_count += 1
            elif item.status == "DUPLICATE_SHA":
                report.duplicate_count += 1
            elif item.status == "FAILED":
                report.failed_count += 1
            if item.pending:
                report.pending_count += 1
            if item.militar_id:
                report.matched_militares += 1
        return report

    def import_pdf(self, pdf_path: Path | str) -> CompilerReferenceImportItem:
        path = Path(pdf_path)
        sha = sha256_file(path)
        try:
            existing = self._existing_reference(sha)
            if existing:
                if self.refresh_existing:
                    return self._refresh_existing(path, sha, existing)
                return CompilerReferenceImportItem(
                    filename=path.name,
                    sha256=sha,
                    status="DUPLICATE_SHA",
                    file_id=existing.id,
                    run_id=existing.run_id,
                    document_id=existing.document_id,
                )

            parsed = parse_reference_folha_pdf(path)
            militar = self._match_militar(parsed.identidade, parsed.nome_completo)
            variables = parsed.to_variables()
            variables["source_folder_import"] = True
            variables["matched_militar_id"] = militar.id if militar else None

            if self.dry_run:
                return CompilerReferenceImportItem(
                    filename=path.name,
                    sha256=sha,
                    status="DRY_RUN_OK",
                    militar_id=militar.id if militar else None,
                    nome=parsed.nome_completo,
                    identidade_mascarada=mask_identity(parsed.identidade),
                    ano=parsed.ano,
                    semestre=parsed.semestre,
                    eventos_count=len(parsed.eventos),
                    warnings=parsed.warnings,
                    pending=parsed.pending,
                )

            run = self.memory_service.create_run(
                tipo_compilacao="MEMORY_REFERENCE_FOLHA_PDF",
                created_by_user_id=self.owner_user_id,
                militar_id=militar.id if militar else None,
                nome_militar_snapshot=parsed.nome_completo,
                identidade_snapshot=parsed.identidade,
                posto_grad_snapshot=parsed.posto_graduacao,
                periodo_inicio=parsed.periodo_inicio,
                periodo_fim=parsed.periodo_fim,
                ano=parsed.ano,
                semestre=parsed.semestre,
                fonte_tempo="TRANSCRITO_DE_FOLHA_PDF_MEMORIA",
                fonte_eventos="MEMORY_REFERENCE_FOLHA_PDF",
            )
            compiler_file = self.memory_service.register_reference_file(
                source_path=path,
                role="MEMORY_REFERENCE_FOLHA_PDF",
                original_filename=path.name,
                mime_type="application/pdf",
                owner_user_id=self.owner_user_id,
                militar_id=militar.id if militar else None,
                source_kind="folha_alteracoes",
                page_count=parsed.page_count,
            )
            compiler_file.run_id = run.id
            self.memory_service.save_variable_snapshot(
                run_id=run.id,
                file_id=compiler_file.id,
                militar_id=militar.id if militar else None,
                schema_version="reference_folha_pdf.v1",
                variables_json=variables,
                warnings_json=parsed.warnings,
                pending_json=parsed.pending,
                confidence_json={
                    "parser": "reference_folha_pdf_v1",
                    "source": "folder_import",
                },
            )
            self.memory_service.add_validations(
                compiler_validations_from_parse(parsed, file_id=compiler_file.id)
                + [
                    {
                        "run_id": run.id,
                        "file_id": compiler_file.id,
                        "level": "OK",
                        "code": "OK_FILE_STORED",
                        "message": "PDF importado para a Memoria do Compilador a partir de pasta local.",
                    },
                    {
                        "run_id": run.id,
                        "file_id": compiler_file.id,
                        "level": "OK",
                        "code": "OK_HASH_COMPUTED",
                        "message": "Hash SHA-256 calculado para deduplicacao.",
                    },
                    {
                        "run_id": run.id,
                        "file_id": compiler_file.id,
                        "level": "INFO",
                        "code": "INFO_GESTAO_PESSOAL_MATCH",
                        "message": (
                            "Militar vinculado pela base de Gestao de Pessoal."
                            if militar
                            else "Militar nao encontrado na base de Gestao de Pessoal."
                        ),
                        "payload_json": {"militar_id": militar.id if militar else None},
                    },
                ]
            )
            self.memory_service.finalize_run(run, has_pending=bool(parsed.pending))
            self.db.commit()
            return CompilerReferenceImportItem(
                filename=path.name,
                sha256=sha,
                status="IMPORTED",
                file_id=compiler_file.id,
                run_id=run.id,
                document_id=compiler_file.document_id,
                militar_id=militar.id if militar else None,
                nome=parsed.nome_completo,
                identidade_mascarada=mask_identity(parsed.identidade),
                ano=parsed.ano,
                semestre=parsed.semestre,
                eventos_count=len(parsed.eventos),
                warnings=parsed.warnings,
                pending=parsed.pending,
            )
        except Exception as exc:
            self.db.rollback()
            return CompilerReferenceImportItem(
                filename=path.name,
                sha256=sha,
                status="FAILED",
                error=str(exc),
            )

    def _refresh_existing(
        self,
        path: Path,
        sha: str,
        existing: CompilerFileModel,
    ) -> CompilerReferenceImportItem:
        parsed = parse_reference_folha_pdf(path)
        militar = self._match_militar(parsed.identidade, parsed.nome_completo)
        run_id = existing.run_id
        variables = parsed.to_variables()
        variables["source_folder_import"] = True
        variables["matched_militar_id"] = militar.id if militar else None
        variables["refreshed_existing"] = True

        if self.dry_run:
            return CompilerReferenceImportItem(
                filename=path.name,
                sha256=sha,
                status="DRY_RUN_OK",
                file_id=existing.id,
                run_id=run_id,
                document_id=existing.document_id,
                militar_id=militar.id if militar else existing.militar_id,
                nome=parsed.nome_completo,
                identidade_mascarada=mask_identity(parsed.identidade),
                ano=parsed.ano,
                semestre=parsed.semestre,
                eventos_count=len(parsed.eventos),
                warnings=parsed.warnings,
                pending=parsed.pending,
            )

        existing.militar_id = militar.id if militar else existing.militar_id
        run = self.memory_service.get_run_detail(run_id) if run_id else None
        if run:
            run.militar_id = militar.id if militar else run.militar_id
            run.nome_militar_snapshot = parsed.nome_completo or run.nome_militar_snapshot
            run.identidade_snapshot = parsed.identidade or run.identidade_snapshot
            run.posto_grad_snapshot = parsed.posto_graduacao or run.posto_grad_snapshot
            run.periodo_inicio = parsed.periodo_inicio or run.periodo_inicio
            run.periodo_fim = parsed.periodo_fim or run.periodo_fim
            run.ano = parsed.ano or run.ano
            run.semestre = parsed.semestre or run.semestre
        self.memory_service.save_variable_snapshot(
            run_id=run_id,
            file_id=existing.id,
            militar_id=militar.id if militar else existing.militar_id,
            schema_version="reference_folha_pdf.v1",
            variables_json=variables,
            warnings_json=parsed.warnings,
            pending_json=parsed.pending,
            confidence_json={
                "parser": "reference_folha_pdf_v1",
                "source": "folder_import_refresh",
            },
        )
        self.memory_service.add_validations(
            compiler_validations_from_parse(parsed, run_id=run_id, file_id=existing.id)
            + [
                {
                    "run_id": run_id,
                    "file_id": existing.id,
                    "level": "OK",
                    "code": "OK_VARIABLES_EXTRACTED",
                    "message": "Referencia existente reprocessada e snapshot atualizado.",
                }
            ]
        )
        if run:
            self.memory_service.finalize_run(run, has_pending=bool(parsed.pending))
        self.db.commit()
        return CompilerReferenceImportItem(
            filename=path.name,
            sha256=sha,
            status="UPDATED",
            file_id=existing.id,
            run_id=run_id,
            document_id=existing.document_id,
            militar_id=militar.id if militar else existing.militar_id,
            nome=parsed.nome_completo,
            identidade_mascarada=mask_identity(parsed.identidade),
            ano=parsed.ano,
            semestre=parsed.semestre,
            eventos_count=len(parsed.eventos),
            warnings=parsed.warnings,
            pending=parsed.pending,
        )

    def _existing_reference(self, sha: str) -> CompilerFileModel | None:
        return (
            self.db.query(CompilerFileModel)
            .filter(
                CompilerFileModel.role == "MEMORY_REFERENCE_FOLHA_PDF",
                CompilerFileModel.sha256 == sha,
            )
            .first()
        )

    def _match_militar(self, identidade: str | None, nome: str | None) -> MilitarModel | None:
        identity_digits = digits_only(identidade)
        if identity_digits:
            for militar in self.db.query(MilitarModel).filter(MilitarModel.identidade.isnot(None)):
                if digits_only(militar.identidade) == identity_digits:
                    return militar
        if nome:
            normalized = normalize_name(nome)
            for militar in self.db.query(MilitarModel).filter(MilitarModel.nome_completo.isnot(None)):
                if normalize_name(militar.nome_completo) == normalized:
                    return militar
        return None


def digits_only(value: str | None) -> str:
    return "".join(char for char in value or "" if char.isdigit())


def normalize_name(value: str | None) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.upper().split())


def mask_identity(value: str | None) -> str | None:
    digits = digits_only(value)
    if not digits:
        return None
    return f"***{digits[-4:]}"

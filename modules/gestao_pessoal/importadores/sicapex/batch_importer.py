from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from sqlalchemy.orm import Session

from infra.persistence.db import SessionLocal
from infra.persistence.transactions import atomic
from modules.gestao_pessoal.importadores.sicapex.parser import parse_sicapex_pdf
from modules.gestao_pessoal.importadores.sicapex.schemas import (
    SicapexBatchReport,
    SicapexImportResult,
)
from modules.gestao_pessoal.importadores.sicapex.service import SicapexImportService
from shared.utils.hashing import sha256_file


class SicapexBatchImporter:
    def __init__(
        self,
        db: Session | None = None,
        *,
        dry_run: bool = True,
        refresh_existing: bool = False,
    ):
        self.db = db
        self.dry_run = dry_run
        self.refresh_existing = refresh_existing

    def import_folder(self, folder_path: Path) -> SicapexBatchReport:
        folder = Path(folder_path)
        pdfs = sorted(
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        )
        return self._import_paths(pdfs, source_folder=str(folder))

    def import_zip(self, zip_path: Path) -> SicapexBatchReport:
        with TemporaryDirectory(prefix="sicapex-zip-") as temp_dir:
            root = Path(temp_dir)
            with zipfile.ZipFile(zip_path, "r") as zin:
                for member in zin.infolist():
                    if member.is_dir() or not member.filename.lower().endswith(".pdf"):
                        continue
                    target = root / Path(member.filename).name
                    target.write_bytes(zin.read(member))
            pdfs = sorted(
                path
                for path in root.iterdir()
                if path.is_file() and path.suffix.lower() == ".pdf"
            )
            return self._import_paths(pdfs, source_folder=str(zip_path))

    def import_pdf(self, pdf_path: Path, batch_id: str | None = None) -> SicapexImportResult:
        owns_session = self.db is None
        db = self.db or SessionLocal()
        try:
            service = SicapexImportService(db)
            with atomic(db):
                return self._import_one(Path(pdf_path), service, batch_id)
        finally:
            if owns_session:
                db.close()

    def get_report(self, batch_id: str) -> dict | None:
        owns_session = self.db is None
        db = self.db or SessionLocal()
        try:
            return SicapexImportService(db).get_batch_report(batch_id)
        finally:
            if owns_session:
                db.close()

    def _import_paths(self, pdfs: list[Path], *, source_folder: str) -> SicapexBatchReport:
        owns_session = self.db is None
        db = self.db or SessionLocal()
        try:
            service = SicapexImportService(db)
            with atomic(db):
                batch = None if self.dry_run else service.create_batch(source_folder=source_folder)
                report = SicapexBatchReport(
                    batch_id=batch.id if batch else "dry-run",
                    source_folder=source_folder,
                    total_files=len(pdfs),
                )
                for pdf in pdfs:
                    report.items.append(self._import_one(pdf, service, batch.id if batch else None))
                self._summarize(report)
                if batch:
                    service.finalize_batch(report)
                return report
        finally:
            if owns_session:
                db.close()

    def _import_one(
        self,
        pdf_path: Path,
        service: SicapexImportService,
        batch_id: str | None,
    ) -> SicapexImportResult:
        sha256 = ""
        try:
            sha256 = sha256_file(pdf_path)
            record = parse_sicapex_pdf(pdf_path)
            return service.persist_record(
                record=record,
                pdf_path=pdf_path,
                batch_id=batch_id,
                dry_run=self.dry_run,
                refresh_existing=self.refresh_existing,
            )
        except Exception as exc:
            return service.persist_failure(
                filename=pdf_path.name,
                sha256=sha256,
                batch_id=batch_id,
                error=str(exc),
                dry_run=self.dry_run,
            )

    def _summarize(self, report: SicapexBatchReport) -> None:
        report.success_count = sum(item.status in {"SUCCESS", "DRY_RUN_OK"} for item in report.items)
        report.failed_count = sum(
            item.status in {"FAILED", "OCR_REQUIRED", "DIVERGENT_IDENTITY_NAME"}
            for item in report.items
        )
        report.pending_count = sum(item.status == "PENDING" or bool(item.pending) for item in report.items)
        report.duplicate_count = sum(item.status == "DUPLICATE_SHA" for item in report.items)

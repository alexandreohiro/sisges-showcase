from pathlib import Path
from uuid import uuid4

from infra.persistence.models import DocumentModel
from infra.persistence.repositories.documents_repo import DocumentsRepository
from infra.persistence.transactions import atomic


class DocumentService:
    def __init__(self, db):
        self.db = db
        self.repo = DocumentsRepository(db)

    def register_document(
        self,
        *,
        kind: str,
        filename: str,
        status: str,
        source_module: str,
        output_path: str,
        owner_user_id: str | None,
        trace_id: str | None = None,
        template_sha256: str | None = None,
        template_version: str | None = None,
        input_sha256: str | None = None,
        output_sha256: str | None = None,
        metadata: dict | None = None,
    ) -> DocumentModel:
        doc = DocumentModel(
            id=str(uuid4()),
            kind=kind,
            filename=filename,
            status=status,
            source_module=source_module,
            output_path=output_path,
            owner_user_id=owner_user_id,
            trace_id=trace_id,
            template_sha256=template_sha256,
            template_version=template_version,
            input_sha256=input_sha256,
            output_sha256=output_sha256,
            metadata_json=metadata,
        )
        with atomic(self.db):
            return self.repo.save(doc)

    def get_document(self, document_id: str) -> DocumentModel | None:
        return self.repo.get_by_id(document_id)

    def list_recent(self, limit: int = 10) -> list[DocumentModel]:
        return self.repo.list_recent(limit=limit)

    def list_history(self, limit: int = 50, offset: int = 0) -> list[DocumentModel]:
        return self.repo.list_history(limit=limit, offset=offset)

    @staticmethod
    def to_dict(doc: DocumentModel) -> dict:
        return {
            "id": doc.id,
            "kind": doc.kind,
            "filename": doc.filename,
            "status": doc.status,
            "source_module": doc.source_module,
            "output_path": doc.output_path,
            "trace_id": doc.trace_id,
            "template_sha256": doc.template_sha256,
            "template_version": doc.template_version,
            "input_sha256": doc.input_sha256,
            "output_sha256": doc.output_sha256,
            "metadata": doc.metadata_json,
            "owner_user_id": doc.owner_user_id,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }

    @staticmethod
    def filename_from_path(path: str) -> str:
        return Path(path).name

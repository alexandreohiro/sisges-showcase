from sqlalchemy.orm import Session

from infra.persistence.models import DocumentModel


class DocumentsRepository:
    def __init__(self, db: Session):
        self.db = db

    def save(self, doc: DocumentModel) -> DocumentModel:
        self.db.add(doc)
        self.db.flush()
        self.db.refresh(doc)
        return doc

    def get_by_id(self, document_id: str) -> DocumentModel | None:
        return (
            self.db.query(DocumentModel)
            .filter(DocumentModel.id == document_id)
            .first()
        )

    def list_recent(self, limit: int = 10) -> list[DocumentModel]:
        return (
            self.db.query(DocumentModel)
            .order_by(DocumentModel.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_history(self, limit: int = 50, offset: int = 0) -> list[DocumentModel]:
        return (
            self.db.query(DocumentModel)
            .order_by(DocumentModel.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def list_by_source_module(self, source_module: str, limit: int = 20) -> list[DocumentModel]:
        return (
            self.db.query(DocumentModel)
            .filter(DocumentModel.source_module == source_module)
            .order_by(DocumentModel.created_at.desc())
            .limit(limit)
            .all()
        )

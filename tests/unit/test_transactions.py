from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import infra.persistence.models  # noqa: F401
from infra.persistence.db import Base
from infra.persistence.models import DocumentModel, FolhaAlteracaoModel, TarefaModel
from infra.persistence.transactions import atomic
from modules.documents.application.services import DocumentService
from modules.folhas.application.schemas import FolhaCreate
from modules.folhas.application.services import FolhasService
from modules.tarefas.infrastructure.repository import TarefasRepository


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_atomic_rolls_back_composed_folha_flow(monkeypatch):
    db = _session()

    def fail_create(*args, **kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(TarefasRepository, "create", fail_create)

    with pytest.raises(RuntimeError, match="falha simulada"):
        FolhasService(db).create_folha_with_task(
            FolhaCreate(
                militar_id=1,
                periodo_inicio=date(2026, 1, 1),
                periodo_fim=date(2026, 1, 31),
            ),
            actor_user_id="user-1",
        )

    assert db.query(FolhaAlteracaoModel).count() == 0
    assert db.query(TarefaModel).count() == 0


def test_document_service_commits_generated_document_metadata():
    db = _session()

    doc = DocumentService(db).register_document(
        kind="ODT",
        filename="saida.odt",
        status="generated",
        source_module="compilador",
        output_path="data/outputs/saida.odt",
        owner_user_id=None,
        trace_id="trace-1",
        template_sha256="template-hash",
        template_version="template-v1",
        input_sha256="input-hash",
        output_sha256="output-hash",
        metadata={"pipeline_steps": []},
    )

    doc_id = doc.id
    db.expire_all()
    saved = db.query(DocumentModel).filter(DocumentModel.id == doc_id).one()
    assert saved.filename == "saida.odt"
    assert saved.trace_id == "trace-1"
    assert saved.output_sha256 == "output-hash"


def test_atomic_rolls_back_on_exception():
    db = _session()

    with pytest.raises(RuntimeError):
        with atomic(db):
            db.add(
                DocumentModel(
                    id="doc-1",
                    kind="ODT",
                    filename="saida.odt",
                    status="generated",
                    source_module="compilador",
                    output_path="data/outputs/saida.odt",
                )
            )
            raise RuntimeError("erro")

    assert db.query(DocumentModel).count() == 0

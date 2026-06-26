from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import infra.persistence.models  # noqa: F401
from infra.persistence.db import Base
from infra.persistence.models import DocumentModel
from modules.compilador.application.compiler_memory_service import CompilerMemoryService


def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def test_compiler_memory_service_persists_reference_snapshot_validation_and_run(tmp_path):
    db = next(db_session())
    source = tmp_path / "referencia.pdf"
    source.write_bytes(b"%PDF-1.4\nconteudo")
    service = CompilerMemoryService(db, root=tmp_path / "memory")

    run = service.create_run(tipo_compilacao="FOLHA_ALTERACOES", created_by_user_id=None)
    file = service.register_reference_file(
        source_path=source,
        role="MEMORY_REFERENCE_FOLHA_PDF",
        original_filename="referencia.pdf",
        mime_type="application/pdf",
        owner_user_id=None,
        source_kind="folha_alteracoes",
        page_count=1,
    )
    snapshot = service.save_variable_snapshot(
        file_id=file.id,
        variables_json={"nome_completo": "MILITAR TESTE"},
        warnings_json=[],
        pending_json=[],
    )
    validation = service.add_validation(
        file_id=file.id,
        level="OK",
        code="OK_FILE_STORED",
        message="Arquivo salvo.",
    )
    service.finalize_run(run)
    db.commit()

    assert file.sha256
    assert (tmp_path / "memory" / "references" / file.sha256 / "referencia.pdf").exists()
    assert db.get(DocumentModel, file.document_id) is not None
    assert snapshot.variables_json["nome_completo"] == "MILITAR TESTE"
    assert validation.code == "OK_FILE_STORED"
    assert run.status == "CONCLUIDO"


def test_compiler_memory_service_fail_run_marks_error(tmp_path):
    db = next(db_session())
    service = CompilerMemoryService(db, root=tmp_path / "memory")
    run = service.create_run(tipo_compilacao="FOLHA_ALTERACOES", created_by_user_id=None)

    service.fail_run(run, error_message="erro controlado")

    assert run.status == "FALHOU"
    assert run.error_message == "erro controlado"
    assert run.finished_at is not None

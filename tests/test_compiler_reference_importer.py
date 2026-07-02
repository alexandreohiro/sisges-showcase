from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import infra.persistence.models  # noqa: F401
from infra.persistence.db import Base
from infra.persistence.models import (
    CompilerFileModel,
    CompilerRunModel,
    CompilerVariableSnapshotModel,
    MilitarModel,
)
from modules.compilador.application.reference_folha_pdf_parser import ReferenceFolhaPdfParseResult


def test_compiler_reference_importer_persists_folder_pdf_and_deduplicates(
    monkeypatch,
    tmp_path,
):
    from modules.compilador.application import compiler_reference_importer as importer_module
    from modules.compilador.application.compiler_memory_service import CompilerMemoryService
    from modules.compilador.application.compiler_reference_importer import CompilerReferenceImporter

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(
        MilitarModel(
            nome_completo="MILITAR TESTE COMPLETO",
            identidade="9990000001",
            posto_graduacao="3º Sgt",
            qas_qms="5310 - QMS - INTENDÊNCIA",
            ativo=True,
        )
    )
    db.commit()

    def fake_parse_reference_folha_pdf(_path):
        return ReferenceFolhaPdfParseResult(
            is_folha_alteracoes=True,
            nome_completo="MILITAR TESTE COMPLETO",
            posto_graduacao="3º Sgt",
            qas_qms="5310 - QMS - INTENDÊNCIA",
            identidade="010064645-4",
            semestre="2",
            ano=2025,
            periodo_inicio=date(2025, 7, 1),
            periodo_fim=date(2025, 12, 31),
            meses_detectados=["JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"],
            eventos=[{"mes": "JULHO", "titulo": "ALTERAÇÃO", "referencia": "BI", "corpo": "Evento."}],
            comportamento="BOM",
            page_count=1,
        )

    monkeypatch.setattr(importer_module, "parse_reference_folha_pdf", fake_parse_reference_folha_pdf)

    source = tmp_path / "source"
    source.mkdir()
    (source / "folha.pdf").write_bytes(b"%PDF-1.4\nfolha")

    service = CompilerMemoryService(db, root=tmp_path / "memory")
    importer = CompilerReferenceImporter(db, memory_service=service)
    report = importer.import_folder(source)

    assert report.total_files == 1
    assert report.imported_count == 1
    assert report.matched_militares == 1
    assert db.query(CompilerRunModel).count() == 1
    assert db.query(CompilerFileModel).count() == 1
    snapshot = db.query(CompilerVariableSnapshotModel).one()
    assert snapshot.variables_json["matched_militar_id"] == 1

    duplicate_report = importer.import_folder(source)

    assert duplicate_report.duplicate_count == 1
    assert db.query(CompilerRunModel).count() == 1
    assert db.query(CompilerFileModel).count() == 1

    refresh_importer = CompilerReferenceImporter(
        db,
        memory_service=service,
        refresh_existing=True,
    )
    refresh_report = refresh_importer.import_folder(source)

    assert refresh_report.updated_count == 1
    assert db.query(CompilerRunModel).count() == 1
    assert db.query(CompilerFileModel).count() == 1
    assert db.query(CompilerVariableSnapshotModel).count() == 2

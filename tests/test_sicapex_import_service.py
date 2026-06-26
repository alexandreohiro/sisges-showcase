from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infra.persistence.db import Base
from infra.persistence.models import (
    MilitarModel,
    MilitarPeriodoServicoModel,
    SicapexEventoFuncionalModel,
    SicapexImportFileModel,
)
from modules.gestao_pessoal.importadores.sicapex.schemas import (
    SicapexAfastamento,
    SicapexParsedRecord,
    SicapexPeriodoServicoSugerido,
)
from modules.gestao_pessoal.importadores.sicapex.service import SicapexImportService


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _record(sha: str = "sha-service") -> SicapexParsedRecord:
    return SicapexParsedRecord(
        nome_completo="MILITAR TESTE",
        nome_guerra="TESTE",
        posto_grad_abrev="3º Sgt",
        identidade_militar="1234567890",
        prec_cp="11-2222222",
        data_praca=date(2018, 4, 9),
        data_incorporacao=date(2018, 4, 9),
        data_inicio_om=date(2024, 1, 1),
        tipo_forca="Normal EB",
        documento_praca="BI 200",
        tempo_efetivo_servico_apos_ultima="2357",
        tempo_efetivo_servico_apos_ultima_dias=2357,
        source_sha256=sha,
        source_filename="ficha.pdf",
        afastamentos=[
            SicapexAfastamento(
                modalidade="Ferias",
                quantidade_dias=30,
                data_inicio=date(2025, 1, 1),
                data_fim=date(2025, 1, 30),
                documento="BI 1",
            )
        ],
        periodos_servico_sugeridos=[
            SicapexPeriodoServicoSugerido(
                tipo_registro="vinculo_militar",
                subtipo_registro="data_praca",
                natureza_servico="servico_militar",
                categoria_tempo="computado",
                data_inicio=date(2018, 4, 9),
                documento_referencia="BI 200",
            ),
            SicapexPeriodoServicoSugerido(
                tipo_registro="afastamento",
                subtipo_registro="ferias",
                natureza_servico="afastamento",
                categoria_tempo="informativo",
                data_inicio=date(2025, 1, 1),
                data_fim=date(2025, 1, 30),
                computa_tempo=False,
                dias_lancados_override=30,
                documento_referencia="BI 1",
            ),
        ],
    )


def test_sicapex_import_dry_run_does_not_persist():
    db = _session()

    result = SicapexImportService(db).persist_record(
        record=_record(),
        pdf_path=Path("ficha.pdf"),
        batch_id=None,
        dry_run=True,
    )

    assert result.status == "DRY_RUN_OK"
    assert db.query(MilitarModel).count() == 0
    assert db.query(SicapexImportFileModel).count() == 0
    assert db.query(SicapexEventoFuncionalModel).count() == 0
    assert db.query(MilitarPeriodoServicoModel).count() == 0


def test_sicapex_import_commit_persists_militar_file_events_and_periods():
    db = _session()

    result = SicapexImportService(db).persist_record(
        record=_record(),
        pdf_path=Path("ficha.pdf"),
        batch_id=None,
        dry_run=False,
    )

    assert result.status == "SUCCESS"
    assert result.militar_id is not None
    assert result.eventos_funcionais_criados == 1
    assert result.periodos_servico_criados == 2
    assert db.query(MilitarModel).count() == 1
    assert db.query(SicapexImportFileModel).count() == 1
    assert db.query(SicapexEventoFuncionalModel).count() == 1
    assert db.query(MilitarPeriodoServicoModel).count() == 2


def test_sicapex_import_duplicate_sha_does_not_duplicate_records():
    db = _session()
    service = SicapexImportService(db)
    first = _record("same-sha")
    duplicate = _record("same-sha")

    service.persist_record(record=first, pdf_path=Path("ficha.pdf"), batch_id=None, dry_run=False)
    result = service.persist_record(
        record=duplicate,
        pdf_path=Path("ficha.pdf"),
        batch_id=None,
        dry_run=False,
    )

    assert result.status == "DUPLICATE_SHA"
    assert db.query(MilitarModel).count() == 1
    assert db.query(SicapexImportFileModel).count() == 1
    assert db.query(MilitarPeriodoServicoModel).count() == 2


def test_sicapex_import_refresh_existing_replaces_payload_without_duplicate():
    db = _session()
    service = SicapexImportService(db)
    first = _record("same-sha-refresh")
    refreshed = _record("same-sha-refresh")
    refreshed.afastamentos = []
    refreshed.periodos_servico_sugeridos = refreshed.periodos_servico_sugeridos[:1]

    service.persist_record(record=first, pdf_path=Path("ficha.pdf"), batch_id=None, dry_run=False)
    result = service.persist_record(
        record=refreshed,
        pdf_path=Path("ficha.pdf"),
        batch_id=None,
        dry_run=False,
        refresh_existing=True,
    )

    assert result.status == "SUCCESS"
    assert db.query(MilitarModel).count() == 1
    assert db.query(SicapexImportFileModel).count() == 1
    assert db.query(SicapexEventoFuncionalModel).count() == 0
    assert db.query(MilitarPeriodoServicoModel).count() == 1

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infra.persistence.db import Base
from infra.persistence.models import MilitarModel, MilitarPeriodoServicoModel, SicapexImportFileModel
from modules.calculo_tempo_servico.application.sicapex_context import build_tempo_servico_context


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_build_tempo_servico_context_returns_imported_periods_and_source():
    db = _session()
    militar = MilitarModel(
        nome_completo="MILITAR TESTE",
        nome_guerra="TESTE",
        identidade="1234567890",
        data_praca=date(2018, 4, 9),
        ativo=True,
    )
    db.add(militar)
    db.flush()
    file_model = SicapexImportFileModel(
        id="file-1",
        filename="ficha.pdf",
        sha256="sha",
        status="SUCCESS",
        militar_id=militar.id,
        parsed_json={
            "tempo_efetivo_servico_apos_ultima": "2357",
            "tempo_efetivo_servico_apos_ultima_dias": 2357,
            "pendencias_calculo": [],
        },
    )
    db.add(file_model)
    db.add(
        MilitarPeriodoServicoModel(
            militar_id=militar.id,
            tipo_registro="vinculo_militar",
            subtipo_registro="data_praca",
            natureza_servico="servico_militar",
            categoria_tempo="computado",
            origem="sicapex",
            data_inicio=date(2018, 4, 9),
            computa_tempo=True,
            arregimentado=True,
            source_file_id=file_model.id,
            origem_documental="sicapex_pdf",
        )
    )
    db.flush()

    context = build_tempo_servico_context(militar.id, db)

    assert context["status_confiabilidade"] == "SICAPEX_COMPLETO"
    assert context["tempo_efetivo_servico_apos_ultima_dias"] == 2357
    assert len(context["periodos"]) == 1
    assert context["fonte_sicapex"]["sha256"] == "sha"


def test_build_tempo_servico_context_marks_missing_sicapex():
    db = _session()
    militar = MilitarModel(nome_completo="SEM SICAPEX", identidade="999", ativo=True)
    db.add(militar)
    db.flush()

    context = build_tempo_servico_context(militar.id, db)

    assert context["status_confiabilidade"] == "SEM_SICAPEX"
    assert "SEM_FICHA_SICAPEX_IMPORTADA" in context["pendencias"]

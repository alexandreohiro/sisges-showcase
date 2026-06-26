from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import infra.persistence.models  # noqa: F401
from apps.web.routes.compilador_folha import _context_requires_sicapex_pdf
from infra.persistence.db import Base
from infra.persistence.models import MilitarModel, SicapexImportFileModel
from modules.calculo_tempo_servico.application.sicapex_context import build_tempo_servico_context


def _db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _militar(**overrides):
    payload = {
        "nome_completo": "MILITAR TESTE",
        "nome_guerra": "TESTE",
        "identidade": "9990000001",
        "posto_graduacao": "3 Sgt",
        "data_praca": date(2010, 1, 1),
        "ativo": True,
    }
    payload.update(overrides)
    return MilitarModel(**payload)


def test_militar_com_sicapex_completo_nao_exige_pdf():
    db = _db_session()
    militar = _militar()
    db.add(militar)
    db.flush()
    db.add(
        SicapexImportFileModel(
            id="file-completo",
            filename="ficha.pdf",
            sha256="abc",
            status="IMPORTED",
            militar_id=militar.id,
            parsed_json={},
        )
    )
    db.commit()

    context = build_tempo_servico_context(militar.id, db)

    assert context["status"] == "SICAPEX_COMPLETO"
    assert context["requires_sicapex_pdf"] is False
    assert _context_requires_sicapex_pdf(context) is False


def test_militar_sem_ficha_exige_pdf():
    db = _db_session()
    militar = _militar()
    db.add(militar)
    db.commit()

    context = build_tempo_servico_context(militar.id, db)

    assert context["status"] == "SEM_SICAPEX"
    assert context["requires_sicapex_pdf"] is True


def test_militar_sem_data_praca_exige_pdf():
    db = _db_session()
    militar = _militar(data_praca=None)
    db.add(militar)
    db.flush()
    db.add(
        SicapexImportFileModel(
            id="file-incompleto",
            filename="ficha.pdf",
            sha256="def",
            status="IMPORTED",
            militar_id=militar.id,
            parsed_json={},
        )
    )
    db.commit()

    context = build_tempo_servico_context(militar.id, db)

    assert context["status"] == "SICAPEX_INCOMPLETO"
    assert context["requires_sicapex_pdf"] is True
    assert "SEM_DATA_PRACA" in context["warnings"]

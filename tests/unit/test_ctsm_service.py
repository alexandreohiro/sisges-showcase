from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import infra.persistence.models  # noqa: F401
from infra.persistence.db import Base
from infra.persistence.models import CalculoTempoServicoModel, CTSMModel, DocumentModel, MilitarModel
from modules.ctsm.application.services import CTSMService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_create_ctsm_from_approved_calculation_registers_document(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _session()
    militar = MilitarModel(
        nome_completo="Fulano de Tal",
        posto_graduacao="3Sgt",
        identidade="123456",
    )
    db.add(militar)
    db.flush()
    calculo = CalculoTempoServicoModel(
        militar_id=militar.id,
        referencia_data=date(2026, 5, 3),
        tempo_arregimentado_anos=1,
        tempo_arregimentado_meses=2,
        tempo_arregimentado_dias=3,
        tempo_nao_arregimentado_anos=0,
        tempo_nao_arregimentado_meses=0,
        tempo_nao_arregimentado_dias=0,
        tempo_computado_anos=1,
        tempo_computado_meses=2,
        tempo_computado_dias=3,
        tempo_total_anos=1,
        tempo_total_meses=2,
        tempo_total_dias=3,
        base_legal_json={"snapshot": "ok"},
    )
    db.add(calculo)
    db.commit()

    ctsm = CTSMService(db).create_from_calculo(
        calculo_id=calculo.id,
        actor_user_id="user-1",
        observacoes="emitir",
    )

    saved = db.query(CTSMModel).filter(CTSMModel.id == ctsm.id).one()
    assert saved.status == "emitida"
    assert saved.document_id is not None
    assert saved.conteudo_json["calculo"]["id"] == calculo.id

    document = db.query(DocumentModel).filter(DocumentModel.id == saved.document_id).one()
    assert document.kind == "CTSM"
    assert document.output_sha256
    assert document.metadata_json["ctsm_id"] == saved.id
    assert Path(document.output_path).exists()

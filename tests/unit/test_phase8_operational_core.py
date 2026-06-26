from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import infra.persistence.models  # noqa: F401
from infra.persistence.db import Base
from infra.persistence.models import (
    CalculoTempoServicoModel,
    CTSMModel,
    DocumentModel,
    MilitarModel,
    MilitarPeriodoServicoModel,
    TarefaModel,
    WorkflowItemModel,
)
from modules.acoes_sugeridas.application.services import AcoesSugeridasService
from modules.consistencia.application.services import ConsistenciaService
from modules.militar_360.application.services import Militar360Service
from modules.ops_center.application.services import OpsCenterService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _seed_inconsistent_case(db: Session) -> int:
    militar = MilitarModel(
        nome_completo="Militar Operacional",
        posto_graduacao="2Sgt",
        identidade="987654",
        data_praca=None,
    )
    db.add(militar)
    db.flush()

    calculo = CalculoTempoServicoModel(
        militar_id=militar.id,
        referencia_data=date(2026, 5, 3),
        tempo_arregimentado_anos=1,
        tempo_arregimentado_meses=0,
        tempo_arregimentado_dias=0,
        tempo_nao_arregimentado_anos=0,
        tempo_nao_arregimentado_meses=0,
        tempo_nao_arregimentado_dias=0,
        tempo_computado_anos=1,
        tempo_computado_meses=0,
        tempo_computado_dias=0,
        tempo_total_anos=1,
        tempo_total_meses=0,
        tempo_total_dias=0,
        base_legal_json={"status": "aprovado"},
    )
    db.add(calculo)
    db.add(
        CTSMModel(
            militar_id=militar.id,
            calculo_id=None,
            status="rascunho",
            conteudo_json={},
        )
    )
    db.add(
        DocumentModel(
            id="doc-sem-hash",
            kind="ODT",
            filename="saida.odt",
            status="generated",
            source_module="compilador",
            output_path="data/outputs/saida.odt",
        )
    )
    db.add(
        MilitarPeriodoServicoModel(
            militar_id=militar.id,
            tipo_registro="movimentacao",
            categoria_tempo="computado",
            data_inicio=date(2026, 1, 1),
            data_fim=date(2026, 1, 31),
            computa_tempo=True,
            arregimentado=True,
            om_origem=None,
            om_destino=None,
        )
    )
    db.add(
        MilitarPeriodoServicoModel(
            militar_id=militar.id,
            tipo_registro="tempo_servico",
            categoria_tempo="computado",
            data_inicio=date(2026, 1, 15),
            data_fim=date(2026, 2, 1),
            computa_tempo=True,
            arregimentado=True,
        )
    )
    db.add(
        TarefaModel(
            titulo="Emitir CTSM",
            tipo="emitir_documento",
            prioridade="alta",
            status="concluida",
            origem_modulo="ctsm",
            militar_id=militar.id,
        )
    )
    db.commit()
    return militar.id


def test_consistencia_detects_cross_module_rules():
    db = _session()
    militar_id = _seed_inconsistent_case(db)

    issues = ConsistenciaService(db).reprocessar(militar_id=militar_id)
    regras = {issue.regra for issue in issues}

    assert "CALCULO_SEM_DATA_PRACA" in regras
    assert "CTSM_SEM_CALCULO_APROVADO" in regras
    assert "DOCUMENTO_SEM_RASTREABILIDADE" in regras
    assert "MOVIMENTACAO_SEM_ORIGEM_DESTINO" in regras
    assert "PERIODO_SOBREPOSICAO" in regras
    assert "TAREFA_CONCLUIDA_SEM_ARTEFATO" in regras


def test_ops_center_rebuilds_and_resolves_inbox():
    db = _session()
    militar_id = _seed_inconsistent_case(db)

    result = OpsCenterService(db).rebuild(militar_id=militar_id)
    assert result["criados"] > 0

    summary = OpsCenterService(db).summary()
    assert summary["total_abertos"] > 0
    assert summary["proxima_acao"]["severidade"] in {"critica", "alta"}

    item = db.query(WorkflowItemModel).first()
    resolved = OpsCenterService(db).resolve(
        item_id=item.id,
        actor_user_id="user-1",
        note="tratado",
    )
    assert resolved.status == "resolvido"
    assert resolved.payload_json["resolution_note"] == "tratado"


def test_militar_360_returns_profile_and_timeline():
    db = _session()
    militar_id = _seed_inconsistent_case(db)

    profile = Militar360Service(db).get_profile(militar_id)

    assert profile["militar"]["id"] == militar_id
    assert profile["resumo"]["periodos"] == 2
    assert profile["timeline"]


def test_acoes_sugeridas_returns_explainable_manual_target():
    db = _session()
    militar_id = _seed_inconsistent_case(db)
    OpsCenterService(db).rebuild(militar_id=militar_id)
    item = (
        db.query(WorkflowItemModel)
        .filter(WorkflowItemModel.acao_recomendada == "COMPLETAR_DADO_DATA_PRACA")
        .first()
    )

    result = AcoesSugeridasService(db).executar(
        acao=None,
        item_id=item.id,
        actor_user_id="user-1",
    )

    assert result["manual_required"] is True
    assert result["target"]["path"] == f"/militar-360/{militar_id}"

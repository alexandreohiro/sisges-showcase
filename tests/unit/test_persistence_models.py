from sqlalchemy import create_engine, inspect

import infra.persistence.models  # noqa: F401
from infra.persistence.db import Base
from infra.persistence.models import (
    DocumentModel,
    MilitarModel,
    MilitarPeriodoServicoModel,
    WorkflowItemModel,
)


def test_metadata_creates_schema_in_memory_sqlite():
    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(bind=engine)

    tables = set(inspect(engine).get_table_names())
    assert "militar" in tables
    assert "militar_periodo_servico" in tables
    assert "users" in tables


def test_militar_model_has_single_periodos_servico_relationship():
    relationships = MilitarModel.__mapper__.relationships

    assert "periodos_servico" in relationships
    assert relationships["periodos_servico"].back_populates == "militar"
    assert "delete-orphan" in relationships["periodos_servico"].cascade


def test_militar_periodo_servico_model_columns_are_not_overwritten():
    columns = {column.name for column in MilitarPeriodoServicoModel.__table__.columns}

    assert {
        "id",
        "militar_id",
        "tipo_registro",
        "subtipo_registro",
        "natureza_servico",
        "categoria_tempo",
        "data_inicio",
        "data_fim",
    }.issubset(columns)


def test_document_model_has_pipeline_traceability_columns():
    columns = {column.name for column in DocumentModel.__table__.columns}

    assert {
        "trace_id",
        "template_sha256",
        "template_version",
        "input_sha256",
        "output_sha256",
        "metadata_json",
    }.issubset(columns)


def test_workflow_item_model_has_operational_inbox_columns():
    columns = {column.name for column in WorkflowItemModel.__table__.columns}

    assert {
        "modulo",
        "tipo",
        "severidade",
        "status",
        "militar_id",
        "referencia_tipo",
        "referencia_id",
        "titulo",
        "descricao",
        "acao_recomendada",
        "motivo_regra",
        "payload_json",
    }.issubset(columns)

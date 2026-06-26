from sqlalchemy import inspect, text

import infra.persistence.models  # noqa: F401
from infra.persistence.db import Base, engine


MILITAR_COLUMNS = {
    "situacao_regulamentar": "VARCHAR(120)",
    "qas_qms": "VARCHAR(160)",
    "rm": "VARCHAR(80)",
    "local_om": "VARCHAR(200)",
    "data_turma": "DATE",
    "comportamento": "VARCHAR(40)",
    "sexo": "VARCHAR(40)",
    "escolaridade": "VARCHAR(120)",
    "nacionalidade": "VARCHAR(120)",
    "data_falecimento": "DATE",
    "identidade_civil": "VARCHAR(60)",
    "categoria": "VARCHAR(80)",
    "autodeclaracao_etnico_racial": "VARCHAR(120)",
    "ra": "VARCHAR(60)",
    "tipo_sanguineo": "VARCHAR(10)",
    "fator_rh": "VARCHAR(10)",
    "doador_orgaos": "VARCHAR(40)",
    "data_incorporacao": "DATE",
    "data_engajamento": "DATE",
    "data_reengajamento": "DATE",
    "data_desengajamento": "DATE",
    "data_licenciamento": "DATE",
    "data_exclusao_servico_ativo": "DATE",
    "observacoes_calculo": "TEXT",
}

PERIODO_COLUMNS = {
    "subtipo_registro": "VARCHAR(80)",
    "natureza_servico": "VARCHAR(80)",
}


def ensure_column(table_name: str, column_name: str, ddl: str):
    inspector = inspect(engine)
    existing = {col["name"] for col in inspector.get_columns(table_name)}

    if column_name not in existing:
        with engine.begin() as conn:
            conn.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")
            )
        print(f"[OK] coluna adicionada: {table_name}.{column_name}")
    else:
        print(f"[SKIP] coluna já existe: {table_name}.{column_name}")


def ensure_indexes():
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_militar_periodo_servico_subtipo_registro "
                "ON militar_periodo_servico (subtipo_registro)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_militar_periodo_servico_natureza_servico "
                "ON militar_periodo_servico (natureza_servico)"
            )
        )
    print("[OK] índices verificados")


def main():
    Base.metadata.create_all(bind=engine)

    for column_name, ddl in MILITAR_COLUMNS.items():
        ensure_column("militar", column_name, ddl)

    for column_name, ddl in PERIODO_COLUMNS.items():
        ensure_column("militar_periodo_servico", column_name, ddl)

    ensure_indexes()
    print("GP.TIME FASE 1 aplicada com sucesso.")


if __name__ == "__main__":
    main()
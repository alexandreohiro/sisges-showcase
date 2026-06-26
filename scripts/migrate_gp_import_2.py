from sqlalchemy import inspect, text

import infra.persistence.models  # noqa: F401
from infra.persistence.db import engine


def ensure_column(table_name: str, column_name: str, ddl: str):
    inspector = inspect(engine)
    existing = {col["name"] for col in inspector.get_columns(table_name)}

    if column_name not in existing:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
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
    ensure_column("militar_periodo_servico", "subtipo_registro", "VARCHAR(80)")
    ensure_column("militar_periodo_servico", "natureza_servico", "VARCHAR(80)")
    ensure_indexes()
    print("GP.IMPORT.2 aplicada com sucesso.")


if __name__ == "__main__":
    main()
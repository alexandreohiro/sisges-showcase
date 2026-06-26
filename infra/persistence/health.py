from __future__ import annotations

import sqlite3
from pathlib import Path
from time import perf_counter
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Connection, make_url

from infra.config import settings
from infra.persistence.db import SessionLocal, engine

# Query de versao do servidor por dialeto. SQLite nao tem um "servidor": o
# modulo sqlite3 da stdlib ja expoe a versao da lib vendorizada no Python em
# uso (sqlite3.sqlite_version), entao nao vale a pena rodar uma query para
# isso. Dialetos com servidor real (MySQL/Postgres) usam uma query simples
# que existe desde versoes antigas do respectivo motor.
_SERVER_VERSION_QUERIES: dict[str, str] = {
    "mysql": "SELECT VERSION()",
    "postgresql": "SHOW server_version",
}


def _read_server_version(session, dialect: str) -> str | None:
    if dialect == "sqlite":
        return sqlite3.sqlite_version

    query = _SERVER_VERSION_QUERIES.get(dialect)
    if query is None:
        return None

    result = session.execute(text(query)).scalar()
    return str(result) if result is not None else None


def _read_pool_stats() -> dict[str, int] | None:
    pool = engine.pool
    try:
        return {
            "size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    except (AttributeError, NotImplementedError):
        # Alguns poolclasses (ex.: NullPool, StaticPool) nao implementam
        # todas as estatisticas. Nesse caso preferimos omitir o bloco a
        # quebrar o healthcheck.
        return None


def _read_migration_status(connection: Connection) -> dict[str, Any]:
    migrations_dir = settings.base_dir / "migrations"
    alembic_ini = settings.base_dir / "alembic.ini"

    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(migrations_dir))
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()

    migration_context = MigrationContext.configure(connection)
    current_heads = migration_context.get_current_heads()
    current = current_heads[0] if len(current_heads) == 1 else (current_heads or None)

    return {
        "current": current,
        "head": head,
        "is_current": bool(current_heads) and set(current_heads) == ({head} if head else set()),
    }


def database_healthcheck() -> dict[str, Any]:
    started = perf_counter()
    url = make_url(settings.database_url)
    dialect = url.get_backend_name()
    payload: dict[str, Any] = {
        "status": "ok",
        "dialect": dialect,
        "driver": url.get_driver_name(),
        "latency_ms": None,
    }

    if settings.database_path:
        path: Path = settings.database_path
        payload["path"] = str(path)
        payload["path_exists"] = path.exists()

    pool_stats = _read_pool_stats()
    if pool_stats is not None:
        payload["pool"] = pool_stats

    try:
        with SessionLocal() as session:
            session.execute(text("select 1"))

            server_version = _read_server_version(session, dialect)
            if server_version is not None:
                payload["server_version"] = server_version

            try:
                payload["migration"] = _read_migration_status(session.connection())
            except Exception as exc:
                # Status de migration e informativo: se o diretorio de
                # migrations ou o alembic_version estiver inacessivel, nao
                # deve derrubar o healthcheck principal (que ja confirmou
                # conectividade com o SELECT 1 acima).
                payload["migration"] = {
                    "current": None,
                    "head": None,
                    "is_current": False,
                    "error": type(exc).__name__,
                }

        payload["latency_ms"] = int((perf_counter() - started) * 1000)
    except Exception as exc:
        payload["status"] = "error"
        payload["error"] = type(exc).__name__
        payload["message"] = str(exc)
        payload["latency_ms"] = int((perf_counter() - started) * 1000)

    return payload

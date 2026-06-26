from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from infra.config import settings
from infra.persistence.db import get_engine_kwargs


def _safe_url(database_url: str) -> str:
    return make_url(database_url).render_as_string(hide_password=True)


def check_connection(database_url: str) -> dict:
    engine = create_engine(database_url, **get_engine_kwargs(database_url))
    safe_url = _safe_url(database_url)
    try:
        with engine.connect() as connection:
            one = connection.execute(text("SELECT 1")).scalar_one()
            dialect = connection.dialect.name
            driver = connection.dialect.driver
    except (ModuleNotFoundError, SQLAlchemyError, OSError) as exc:
        return {
            "ok": False,
            "database_url": safe_url,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    finally:
        engine.dispose()

    return {
        "ok": one == 1,
        "database_url": safe_url,
        "dialect": dialect,
        "driver": driver,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Valida conectividade SQLAlchemy do SISGES sem executar migrations.",
    )
    parser.add_argument(
        "--url",
        default=settings.database_url,
        help="Database URL. Se omitido, usa SISGES_DATABASE_URL.",
    )
    parser.add_argument("--json", action="store_true", help="Imprime saida em JSON.")
    args = parser.parse_args(argv)

    result = check_connection(args.url)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"OK database={result['database_url']} dialect={result['dialect']} driver={result['driver']}")
    else:
        print(
            f"ERRO database={result['database_url']} "
            f"type={result['error_type']} message={result['error']}",
            file=sys.stderr,
        )
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

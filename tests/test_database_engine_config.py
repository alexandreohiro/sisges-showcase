from __future__ import annotations

from sqlalchemy.engine import make_url

from infra.persistence.db import get_connect_args, get_engine_kwargs


def test_sqlite_engine_keeps_thread_connect_args() -> None:
    url = "sqlite:///data/sisges_test.db"

    assert get_connect_args(url) == {"check_same_thread": False}
    kwargs = get_engine_kwargs(url)

    assert kwargs["connect_args"] == {"check_same_thread": False}
    assert "pool_size" not in kwargs
    assert "pool_pre_ping" not in kwargs


def test_mysql_engine_uses_pool_hardening_options() -> None:
    url = "mysql+pymysql://sisges_app:secret@127.0.0.1:3306/sisges?charset=utf8mb4"

    assert make_url(url).drivername == "mysql+pymysql"
    kwargs = get_engine_kwargs(url)

    assert kwargs["connect_args"] == {}
    assert kwargs["pool_size"] >= 1
    assert kwargs["max_overflow"] >= 1
    assert kwargs["pool_recycle"] > 0
    assert kwargs["pool_pre_ping"] is True

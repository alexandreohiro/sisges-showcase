from __future__ import annotations

from scripts.mysql_hardening_gate import run_gate, validate_mysql_database_url


VALID_APP_URL = (
    "mysql+pymysql://sisges_app:senha-forte@127.0.0.1:3306/sisges?charset=utf8mb4"
)


def test_mysql_gate_accepts_app_user_with_utf8mb4() -> None:
    result = validate_mysql_database_url(VALID_APP_URL, purpose="app")

    assert result.ok is True
    assert result.safe_url == (
        "mysql+pymysql://sisges_app:***@127.0.0.1:3306/sisges?charset=utf8mb4"
    )
    assert {item["code"] for item in result.checks} >= {
        "MYSQL_DRIVER",
        "MYSQL_USER_NOT_ROOT",
        "MYSQL_CHARSET_UTF8MB4",
    }


def test_mysql_gate_rejects_root_user() -> None:
    result = validate_mysql_database_url(
        "mysql+pymysql://root:senha@127.0.0.1:3306/sisges?charset=utf8mb4",
        purpose="app",
    )

    assert result.ok is False
    assert any(item["code"] == "MYSQL_USER_NOT_ROOT" and not item["ok"] for item in result.checks)


def test_mysql_gate_rejects_missing_password() -> None:
    result = validate_mysql_database_url(
        "mysql+pymysql://sisges_app@127.0.0.1:3306/sisges?charset=utf8mb4",
        purpose="app",
    )

    assert result.ok is False
    assert any(item["code"] == "MYSQL_PASSWORD_PRESENT" and not item["ok"] for item in result.checks)


def test_mysql_gate_rejects_wrong_purpose_user() -> None:
    result = validate_mysql_database_url(VALID_APP_URL, purpose="migration")

    assert result.ok is False
    assert any(
        item["code"] == "MYSQL_USER_PURPOSE_MATCH" and not item["ok"]
        for item in result.checks
    )


def test_mysql_gate_warns_remote_host_without_failing_static_checks() -> None:
    result = validate_mysql_database_url(
        "mysql+pymysql://sisges_app:senha@10.0.0.50:3306/sisges?charset=utf8mb4",
        purpose="app",
    )

    assert result.ok is True
    assert any(item["code"] == "MYSQL_REMOTE_HOST_REVIEW" for item in result.warnings)


def test_run_gate_without_connect_is_non_destructive() -> None:
    result = run_gate(VALID_APP_URL, purpose="app", connect=False)

    assert result["ok"] is True
    assert "connection" not in result

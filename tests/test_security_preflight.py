from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from scripts.security_preflight import build_security_preflight, write_reports


MYSQL_URL = "mysql+pymysql://sisges_app:senha@127.0.0.1:3306/sisges?charset=utf8mb4"


def test_security_preflight_passes_local_artifacts() -> None:
    report = build_security_preflight(mysql_url=MYSQL_URL)

    assert report["ok"] is True
    assert report["schema_version"] == "sisges-security-preflight-v1"
    assert report["database_kind"] == "mysql"
    assert any(item["code"] == "MYSQL_HARDENING_GATE" for item in report["checks"])


def test_security_preflight_reports_non_mysql_as_warning() -> None:
    report = build_security_preflight(mysql_url="sqlite:///data/sisges.db")

    assert report["ok"] is True
    assert report["database_kind"] == "non_mysql"
    assert any(item["code"] == "DATABASE_SQLITE_LOCAL" for item in report["warnings"])


def test_security_preflight_require_prod_blocks_dev_settings() -> None:
    report = build_security_preflight(mysql_url=MYSQL_URL, require_prod=True)

    assert report["ok"] is False
    assert any(item["code"] == "SETTINGS_CSRF_ENABLED" and not item["ok"] for item in report["checks"])


def test_security_preflight_writes_reports(tmp_path: Path) -> None:
    report = build_security_preflight(mysql_url=MYSQL_URL)
    output_json = tmp_path / "security_preflight.json"
    output_txt = tmp_path / "security_preflight.txt"

    write_reports(report, output_json, output_txt)

    assert output_json.exists()
    assert output_txt.exists()
    assert "SISGES SECURITY PREFLIGHT" in output_txt.read_text(encoding="utf-8")


def test_nginx_config_is_standalone_main_config() -> None:
    config = Path(__file__).resolve().parents[1] / "ops" / "nginx" / "sisges.conf"
    content = config.read_text(encoding="utf-8")

    assert "events {" in content
    assert "http {" in content
    assert "limit_req_zone" in content
    assert "server {" in content


def _make_frontend_contract_fixture(root: Path) -> None:
    (root / "lib").mkdir()
    (root / "scripts").mkdir()
    (root / "docs").mkdir()
    (root / "package.json").write_text(
        '{"scripts":{"validate:csrf-client":"node scripts/validate-csrf-client.mjs"}}',
        encoding="utf-8",
    )
    (root / "lib" / "api.ts").write_text(
        "\n".join(
            [
                '"X-CSRF-Token"',
                '"CSRF_TOKEN_MISSING"',
                '"CSRF_TOKEN_INVALID"',
                "function refreshCsrfToken() {}",
            ]
        ),
        encoding="utf-8",
    )
    (root / "lib" / "endpoints.ts").write_text("csrf", encoding="utf-8")
    (root / "scripts" / "validate-csrf-client.mjs").write_text("console.log('ok')", encoding="utf-8")
    (root / "docs" / "CSRF_FRONTEND_CONTRACT.md").write_text("# CSRF", encoding="utf-8")


def test_security_preflight_accepts_frontend_contract(tmp_path: Path) -> None:
    _make_frontend_contract_fixture(tmp_path)

    report = build_security_preflight(mysql_url=MYSQL_URL, frontend_dir=tmp_path)

    assert report["ok"] is True
    assert report["frontend"] == {
        "path": str(tmp_path.resolve()),
        "csrf_validation_executed": False,
    }
    assert any(item["code"] == "FRONTEND_VALIDATE_CSRF_CLIENT_SCRIPT" for item in report["checks"])


def test_security_preflight_can_execute_frontend_csrf_validation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _make_frontend_contract_fixture(tmp_path)

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="CSRF client validation passed.", stderr="")

    monkeypatch.setattr("scripts.security_preflight.subprocess.run", fake_run)

    report = build_security_preflight(
        mysql_url=MYSQL_URL,
        frontend_dir=tmp_path,
        check_frontend_csrf=True,
    )

    assert report["ok"] is True
    assert any(
        item["code"] == "FRONTEND_VALIDATE_CSRF_CLIENT_EXECUTED" and item["ok"]
        for item in report["checks"]
    )

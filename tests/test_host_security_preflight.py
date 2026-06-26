from __future__ import annotations

from pathlib import Path

from scripts import host_security_preflight as preflight


def test_host_preflight_passes_without_optional_runtime_checks() -> None:
    report = preflight.build_host_security_preflight()

    assert report["schema_version"] == "sisges-host-security-preflight-v1"
    assert report["ok"] is True
    assert any(item["code"] == "NGINX_CONF_EXISTS" for item in report["checks"])
    assert report["ports"] == {}


def test_host_preflight_missing_nginx_exe_is_warning(tmp_path: Path) -> None:
    report = preflight.build_host_security_preflight(nginx_exe=tmp_path / "nginx.exe")

    assert report["ok"] is True
    assert any(item["code"] == "NGINX_EXE_EXISTS" for item in report["warnings"])


def test_host_preflight_missing_conf_is_error(tmp_path: Path) -> None:
    report = preflight.build_host_security_preflight(nginx_conf=tmp_path / "missing.conf")

    assert report["ok"] is False
    assert any(
        item["code"] == "NGINX_CONF_EXISTS" and not item["ok"]
        for item in report["checks"]
    )


def test_host_preflight_port_checks_can_be_warnings(monkeypatch) -> None:
    monkeypatch.setattr(preflight, "_port_open", lambda _host, _port: False)

    report = preflight.build_host_security_preflight(check_ports=True, require_ports=False)

    assert report["ok"] is True
    assert len(report["warnings"]) >= 3
    assert report["ports"]["nginx"]["open"] is False


def test_host_preflight_port_checks_can_be_required(monkeypatch) -> None:
    monkeypatch.setattr(preflight, "_port_open", lambda _host, _port: False)

    report = preflight.build_host_security_preflight(check_ports=True, require_ports=True)

    assert report["ok"] is False
    assert any(item["code"] == "PORT_NGINX_80_OPEN" for item in report["checks"])


def test_host_preflight_writes_reports(tmp_path: Path) -> None:
    report = preflight.build_host_security_preflight()
    output_json = tmp_path / "host.json"
    output_txt = tmp_path / "host.txt"

    preflight.write_reports(report, output_json, output_txt)

    assert output_json.exists()
    assert "SISGES HOST SECURITY PREFLIGHT" in output_txt.read_text(encoding="utf-8")

from __future__ import annotations

import json
from pathlib import Path

from scripts import sisges_release_gate as gate
from scripts.sisges_release_gate import (
    BACKEND_REQUIRED_IGNORES,
    CommandResult,
    FRONTEND_REQUIRED_IGNORES,
    build_health_smoke_command,
    build_overclock_command,
    build_host_security_preflight_command,
    build_report,
    build_security_preflight_command,
    missing_required_ignores,
    parse_git_name_lines,
    parse_git_status_short,
    prohibited_from_paths,
    resolve_git_path,
    scan_prohibited_artifacts,
    sha256_file,
    summarize_health_smoke_report,
    summarize_json_command_result,
    summarize_overclock_report,
    summarize_ux_ui_report,
    validate_release_package,
)


def _write_gitignore(repo: Path, patterns: set[str]) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / ".gitignore").write_text("\n".join(sorted(patterns)) + "\n", encoding="utf-8")


def test_release_gate_detects_missing_required_ignores(tmp_path: Path):
    repo = tmp_path / "frontend"
    _write_gitignore(repo, FRONTEND_REQUIRED_IGNORES - {"*.zip", "data/"})

    assert missing_required_ignores(repo, FRONTEND_REQUIRED_IGNORES) == ["*.zip", "data/"]


def test_release_gate_scans_prohibited_artifacts(tmp_path: Path):
    repo = tmp_path / "backend"
    (repo / "data" / "output").mkdir(parents=True)
    (repo / "data" / "output" / "pacote.zip").write_bytes(b"zip")
    (repo / "docs").mkdir()
    (repo / "docs" / "ok.md").write_text("ok", encoding="utf-8")

    artifacts = scan_prohibited_artifacts(repo)

    assert "data/output/pacote.zip" in artifacts
    assert "docs/ok.md" not in artifacts


def test_release_gate_generates_report_without_running_commands(tmp_path: Path):
    backend = tmp_path / "backend"
    frontend = tmp_path / "frontend"
    _write_gitignore(
        backend,
        {
            "data/output/",
            "data/releases/",
            "data/compiler_memory/",
            "data/uploads/",
            "data/trash/",
            "*.db",
            "*.zip",
            "*.pdf",
        },
    )
    _write_gitignore(frontend, FRONTEND_REQUIRED_IGNORES)
    (backend / ".git").mkdir()
    (frontend / ".git").mkdir()
    output_json = tmp_path / "gate.json"
    output_txt = tmp_path / "gate.txt"

    report = build_report(
        backend=backend,
        frontend=frontend,
        run_validation=False,
        output_json=output_json,
        output_txt=output_txt,
        require_git=False,
    )

    assert report["ok"] is True
    assert report["commands"] == []
    assert output_json.exists()
    assert output_txt.exists()
    parsed = json.loads(output_json.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "sisges-release-gate-v1"


def test_release_gate_validates_release_package_sha256(tmp_path: Path):
    package = tmp_path / "pacote.zip"
    package.write_bytes(b"conteudo")
    digest = sha256_file(package)
    package.with_suffix(".zip.sha256").write_text(f"{digest}  pacote.zip\n", encoding="utf-8")

    result = validate_release_package(package)

    assert result["ok"] is True
    assert result["sha256"] == digest
    assert result["expected_sha256"] == digest


def test_release_gate_reports_release_package_sha256_mismatch(tmp_path: Path):
    package = tmp_path / "pacote.zip"
    package.write_bytes(b"conteudo")

    result = validate_release_package(package, expected_sha256="0" * 64)

    assert result["ok"] is False
    assert result["errors"] == ["ERR_RELEASE_PACKAGE_SHA256_MISMATCH"]


def test_release_gate_parses_git_status_short():
    output = "M  scripts/sisges_release_gate.py\nA  data/output/pacote.zip\nR  old.txt -> docs/new.txt\n"

    parsed = parse_git_status_short(output)

    assert parsed == [
        {"status": "M ", "path": "scripts/sisges_release_gate.py"},
        {"status": "A ", "path": "data/output/pacote.zip"},
        {"status": "R ", "path": "docs/new.txt"},
    ]


def test_release_gate_detects_prohibited_staged_or_tracked_paths():
    paths = parse_git_name_lines(
        "\n".join(
            [
                "scripts/sisges_release_gate.py",
                "data/output/pacote.zip",
                "docs/manual.md",
                "foto.jpg",
            ]
        )
    )

    assert prohibited_from_paths(paths) == ["data/output/pacote.zip", "foto.jpg"]


def test_release_gate_allows_tracked_public_assets():
    paths = ["public/sisges-logo.png", "apps/web/static/img/favicon.png", "data/output/pacote.zip"]

    assert prohibited_from_paths(paths, allow_tracked_assets=True) == ["data/output/pacote.zip"]


def test_release_gate_resolves_git_from_windows_localappdata(tmp_path: Path, monkeypatch):
    localappdata = tmp_path / "LocalAppData"
    git_exe = localappdata / "Programs" / "Git" / "cmd" / "git.exe"
    git_exe.parent.mkdir(parents=True)
    git_exe.write_text("git", encoding="utf-8")

    monkeypatch.setattr(gate.shutil, "which", lambda _name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "User"))

    assert resolve_git_path() == str(git_exe)


def test_release_gate_builds_health_smoke_command():
    backend_python = Path("python.exe")

    command = build_health_smoke_command(backend_python=backend_python, allow_degraded_ready=True)

    assert command[:3] == [str(backend_python), "-m", "scripts.sisges_health_smoke"]
    assert "--allow-degraded-ready" in command
    assert "data/output/sisges_release_gate_health.json" in command


def test_release_gate_builds_security_preflight_command(tmp_path: Path):
    backend_python = Path("python.exe")
    frontend = tmp_path / "frontend"

    command = build_security_preflight_command(
        backend_python=backend_python,
        frontend=frontend,
        require_prod=True,
        check_frontend_csrf=True,
    )

    assert command[:3] == ["python.exe", "-m", "scripts.security_preflight"]
    assert "--frontend-dir" in command
    assert str(frontend) in command
    assert "--require-prod" in command
    assert "--check-frontend-csrf" in command
    assert "--json" in command


def test_release_gate_builds_host_security_preflight_command():
    command = build_host_security_preflight_command(
        backend_python=Path("python.exe"),
        check_nginx_syntax=True,
        check_ports=True,
    )

    assert command[:3] == ["python.exe", "-m", "scripts.host_security_preflight"]
    assert "--check-nginx-syntax" in command
    assert "--check-ports" in command
    assert "--json" in command


def test_release_gate_summarizes_json_command_result():
    result = CommandResult(
        command=["python.exe"],
        cwd=".",
        returncode=0,
        stdout_tail=json.dumps(
            {
                "schema_version": "sisges-security-preflight-v1",
                "ok": True,
                "checks": [{"ok": True}],
                "warnings": [{"ok": False}],
            }
        ),
        stderr_tail="",
    )

    summary = summarize_json_command_result(result, "sisges-security-preflight-v1")

    assert summary["ok"] is True
    assert summary["checks_count"] == 1
    assert summary["warnings_count"] == 1


def test_release_gate_summarizes_health_smoke_report(tmp_path: Path):
    report_path = tmp_path / "health.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "OK",
                "checks": [
                    {
                        "endpoint": "/health/live",
                        "ok": True,
                        "payload_status": "ok",
                    },
                    {
                        "endpoint": "/health/ready",
                        "ok": True,
                        "payload_status": "ok",
                        "database_status": "ok",
                    },
                ],
                "failed_endpoints": [],
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_health_smoke_report(report_path)

    assert summary["ok"] is True
    assert summary["status"] == "OK"
    assert summary["checks_count"] == 2
    assert summary["database_status"] == "ok"
    assert summary["failed_endpoints"] == []


def test_release_gate_builds_overclock_command_with_baseline(tmp_path: Path):
    backend_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    baseline = tmp_path / "baseline.json"

    command = build_overclock_command(
        backend_python=backend_python,
        profile="critical",
        baseline_json=baseline,
        tarefas=300,
        efetivo=1000,
        repeat=5,
        max_seconds=5.0,
        regression_tolerance_percent=35.0,
    )

    assert command[:5] == [str(backend_python), "-m", "scripts.operational_overclock_report", "--profile", "critical"]
    assert "--baseline-json" in command
    assert str(baseline) in command
    assert "data/output/sisges_release_gate_overclock.json" in command


def test_release_gate_can_include_overclock_command_without_full_validation(
    tmp_path: Path,
    monkeypatch,
):
    backend = tmp_path / "backend"
    frontend = tmp_path / "frontend"
    _write_gitignore(backend, BACKEND_REQUIRED_IGNORES)
    _write_gitignore(frontend, FRONTEND_REQUIRED_IGNORES)
    (backend / ".git").mkdir()
    (frontend / ".git").mkdir()
    executed: list[list[str]] = []

    def fake_run_command(command, cwd, *, timeout_seconds):  # noqa: ANN001
        executed.append(list(command))
        output_path = Path(cwd) / "data/output/sisges_release_gate_overclock.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "status": "OK",
                    "profile_label": "release-gate-critical",
                    "endpoints": [
                        {
                            "endpoint": "/tarefas",
                            "ok": True,
                            "elapsed_ms": {"p95": 10.0, "max": 11.0},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return CommandResult(
            command=list(command),
            cwd=str(cwd),
            returncode=0,
            stdout_tail="ok",
            stderr_tail="",
        )

    monkeypatch.setattr(gate, "resolve_git_path", lambda: None)
    monkeypatch.setattr(gate, "run_command", fake_run_command)

    report = build_report(
        backend=backend,
        frontend=frontend,
        run_validation=False,
        run_overclock=True,
        output_json=tmp_path / "gate.json",
        output_txt=tmp_path / "gate.txt",
        require_git=False,
        overclock_tarefas=12,
        overclock_efetivo=40,
        overclock_repeat=1,
    )

    assert report["ok"] is True
    assert report["overclock"]["enabled"] is True
    assert len(report["commands"]) == 1
    assert executed[0][2] == "scripts.operational_overclock_report"
    assert "--profile" in executed[0]


def test_release_gate_can_include_health_smoke_command_without_full_validation(tmp_path: Path, monkeypatch):
    backend = tmp_path / "backend"
    frontend = tmp_path / "frontend"
    _write_gitignore(backend, BACKEND_REQUIRED_IGNORES)
    _write_gitignore(frontend, FRONTEND_REQUIRED_IGNORES)
    (backend / ".git").mkdir()
    (frontend / ".git").mkdir()
    executed: list[list[str]] = []

    def fake_run_command(command, cwd, *, timeout_seconds):  # noqa: ANN001
        executed.append(list(command))
        output_path = Path(cwd) / "data/output/sisges_release_gate_health.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "status": "OK",
                    "checks": [
                        {
                            "endpoint": "/health/ready",
                            "ok": True,
                            "database_status": "ok",
                        }
                    ],
                    "failed_endpoints": [],
                }
            ),
            encoding="utf-8",
        )
        return CommandResult(command=list(command), cwd=str(cwd), returncode=0, stdout_tail="ok", stderr_tail="")

    monkeypatch.setattr(gate, "resolve_git_path", lambda: None)
    monkeypatch.setattr(gate, "run_command", fake_run_command)

    report = build_report(
        backend=backend,
        frontend=frontend,
        run_validation=False,
        run_health_smoke=True,
        output_json=tmp_path / "gate.json",
        output_txt=tmp_path / "gate.txt",
        require_git=False,
    )

    assert report["ok"] is True
    assert report["health_smoke"]["summary"]["database_status"] == "ok"
    assert executed[0][2] == "scripts.sisges_health_smoke"
    assert "Health smoke:" in (tmp_path / "gate.txt").read_text(encoding="utf-8")


def test_release_gate_summarizes_overclock_report(tmp_path: Path):
    report_path = tmp_path / "overclock.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "OK",
                "profile_label": "release-gate-critical",
                "endpoints": [
                    {
                        "endpoint": "/tarefas",
                        "ok": True,
                        "elapsed_ms": {"p95": 12.5, "max": 14.0},
                    },
                    {
                        "endpoint": "/gestao-pessoal",
                        "ok": True,
                        "elapsed_ms": {"p95": 30.0, "max": 45.0},
                    },
                ],
                "baseline_comparison": {
                    "status": "OK",
                    "comparisons": [
                        {
                            "endpoint": "/tarefas",
                            "status": "OK",
                            "metric": "p95",
                            "current_ms": 12.5,
                            "baseline_ms": 10.0,
                            "allowed_ms": 13.5,
                            "delta_percent": 25.0,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_overclock_report(report_path)

    assert summary["ok"] is True
    assert summary["status"] == "OK"
    assert summary["endpoints_count"] == 2
    assert summary["baseline_status"] == "OK"
    assert summary["slowest_endpoint"]["endpoint"] == "/gestao-pessoal"
    assert summary["slowest_endpoint"]["p95_ms"] == 30.0


def test_release_gate_summarizes_overclock_regression(tmp_path: Path):
    report_path = tmp_path / "overclock.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "FAIL",
                "profile_label": "release-gate-critical",
                "endpoints": [
                    {
                        "endpoint": "/tarefas",
                        "ok": True,
                        "elapsed_ms": {"p95": 50.0, "max": 55.0},
                    }
                ],
                "baseline_comparison": {
                    "status": "FAIL",
                    "comparisons": [
                        {
                            "endpoint": "/tarefas",
                            "status": "REGRESSION",
                            "metric": "p95",
                            "current_ms": 50.0,
                            "baseline_ms": 10.0,
                            "allowed_ms": 13.5,
                            "delta_percent": 400.0,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_overclock_report(report_path)

    assert summary["ok"] is False
    assert summary["baseline_status"] == "FAIL"
    assert summary["regressions"] == [
        {
            "endpoint": "/tarefas",
            "metric": "p95",
            "current_ms": 50.0,
            "baseline_ms": 10.0,
            "allowed_ms": 13.5,
            "delta_percent": 400.0,
        }
    ]


def test_release_gate_embeds_overclock_summary_after_command(tmp_path: Path, monkeypatch):
    backend = tmp_path / "backend"
    frontend = tmp_path / "frontend"
    _write_gitignore(backend, BACKEND_REQUIRED_IGNORES)
    _write_gitignore(frontend, FRONTEND_REQUIRED_IGNORES)
    (backend / ".git").mkdir()
    (frontend / ".git").mkdir()

    def fake_run_command(command, cwd, *, timeout_seconds):  # noqa: ANN001
        output_path = Path(cwd) / "data/output/sisges_release_gate_overclock.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "status": "OK",
                    "profile_label": "release-gate-critical",
                    "endpoints": [
                        {
                            "endpoint": "/tarefas",
                            "ok": True,
                            "elapsed_ms": {"p95": 10.0, "max": 11.0},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return CommandResult(command=list(command), cwd=str(cwd), returncode=0, stdout_tail="ok", stderr_tail="")

    monkeypatch.setattr(gate, "resolve_git_path", lambda: None)
    monkeypatch.setattr(gate, "run_command", fake_run_command)

    report = build_report(
        backend=backend,
        frontend=frontend,
        run_validation=False,
        run_overclock=True,
        output_json=tmp_path / "gate.json",
        output_txt=tmp_path / "gate.txt",
        require_git=False,
        overclock_tarefas=12,
        overclock_efetivo=40,
        overclock_repeat=1,
    )

    assert report["ok"] is True
    assert report["overclock"]["summary"]["endpoints_count"] == 1
    assert "mais lento p95: /tarefas" in (tmp_path / "gate.txt").read_text(encoding="utf-8")


def _write_ux_ui_profile(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "sisges-ux-ui-overclock-profile-v1",
                "base_url": "http://127.0.0.1:3000",
                "max_page_load_ms": 8000,
                "pages": [
                    {
                        "path": "/tarefas",
                        "label": "Tarefas",
                        "expected_text": "Tarefas",
                    },
                    {
                        "path": "/notificacoes",
                        "label": "Notificacoes",
                        "expected_text": "Notificacoes",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_release_gate_summarizes_ux_ui_report(tmp_path: Path):
    profile_path = tmp_path / "critical_pages.json"
    report_path = tmp_path / "ux_ui.json"
    _write_ux_ui_profile(profile_path)
    report_path.write_text(
        json.dumps(
            {
                "schema_version": "sisges-ux-ui-overclock-report-v1",
                "status": "OK",
                "pages": [
                    {
                        "path": "/tarefas",
                        "ok": True,
                        "expected_text_found": True,
                        "loaded_ms": 900,
                        "console_errors": 0,
                    },
                    {
                        "path": "/notificacoes",
                        "ok": True,
                        "expected_text_found": True,
                        "loaded_ms": 1200,
                        "console_errors": 0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_ux_ui_report(report_path, profile_path=profile_path)

    assert summary["ok"] is True
    assert summary["status"] == "OK"
    assert summary["pages_count"] == 2
    assert summary["console_errors_total"] == 0
    assert summary["slowest_page"]["path"] == "/notificacoes"


def test_release_gate_rejects_failed_ux_ui_report(tmp_path: Path):
    profile_path = tmp_path / "critical_pages.json"
    report_path = tmp_path / "ux_ui.json"
    _write_ux_ui_profile(profile_path)
    report_path.write_text(
        json.dumps(
            {
                "schema_version": "sisges-ux-ui-overclock-report-v1",
                "status": "FAIL",
                "pages": [
                    {
                        "path": "/tarefas",
                        "ok": True,
                        "expected_text_found": False,
                        "loaded_ms": 900,
                        "console_errors": 1,
                    },
                    {
                        "path": "/notificacoes",
                        "ok": True,
                        "expected_text_found": True,
                        "loaded_ms": 1200,
                        "console_errors": 0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_ux_ui_report(report_path, profile_path=profile_path)

    assert summary["ok"] is False
    assert summary["failed_pages"] == ["/tarefas"]
    assert summary["console_errors_total"] == 1
    assert "ERR_UX_REPORT_STATUS_NOT_OK" in summary["errors"]
    assert "ERR_UX_REPORT_EXPECTED_TEXT_MISSING:/tarefas" in summary["errors"]


def test_release_gate_embeds_ux_ui_report_in_gate(tmp_path: Path, monkeypatch):
    backend = tmp_path / "backend"
    frontend = tmp_path / "frontend"
    _write_gitignore(backend, BACKEND_REQUIRED_IGNORES)
    _write_gitignore(frontend, FRONTEND_REQUIRED_IGNORES)
    (backend / ".git").mkdir()
    (frontend / ".git").mkdir()
    profile_path = tmp_path / "critical_pages.json"
    report_path = tmp_path / "ux_ui.json"
    _write_ux_ui_profile(profile_path)
    report_path.write_text(
        json.dumps(
            {
                "schema_version": "sisges-ux-ui-overclock-report-v1",
                "status": "OK",
                "pages": [
                    {
                        "path": "/tarefas",
                        "ok": True,
                        "expected_text_found": True,
                        "loaded_ms": 900,
                        "console_errors": 0,
                    },
                    {
                        "path": "/notificacoes",
                        "ok": True,
                        "expected_text_found": True,
                        "loaded_ms": 1200,
                        "console_errors": 0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(gate, "resolve_git_path", lambda: None)

    report = build_report(
        backend=backend,
        frontend=frontend,
        run_validation=False,
        output_json=tmp_path / "gate.json",
        output_txt=tmp_path / "gate.txt",
        require_git=False,
        ux_ui_report=report_path,
        ux_ui_profile=profile_path,
    )

    assert report["ok"] is True
    assert report["ux_ui"]["summary"]["pages_count"] == 2
    assert "UX/UI overclock:" in (tmp_path / "gate.txt").read_text(encoding="utf-8")


def test_release_gate_embeds_security_preflights(tmp_path: Path, monkeypatch):
    backend = tmp_path / "backend"
    frontend = tmp_path / "frontend"
    _write_gitignore(backend, BACKEND_REQUIRED_IGNORES)
    _write_gitignore(frontend, FRONTEND_REQUIRED_IGNORES)
    (backend / ".git").mkdir()
    (frontend / ".git").mkdir()

    def fake_run_command(command, cwd, *, timeout_seconds):  # noqa: ANN001
        schema = (
            "sisges-host-security-preflight-v1"
            if "scripts.host_security_preflight" in command
            else "sisges-security-preflight-v1"
        )
        return CommandResult(
            command=list(command),
            cwd=str(cwd),
            returncode=0,
            stdout_tail=json.dumps(
                {
                    "schema_version": schema,
                    "ok": True,
                    "checks": [{"ok": True}],
                    "warnings": [],
                }
            ),
            stderr_tail="",
        )

    monkeypatch.setattr(gate.shutil, "which", lambda name: None)
    monkeypatch.setattr(gate, "run_command", fake_run_command)

    report = build_report(
        backend=backend,
        frontend=frontend,
        run_validation=False,
        output_json=tmp_path / "gate.json",
        output_txt=tmp_path / "gate.txt",
        require_git=False,
        run_security_preflight=True,
        check_frontend_csrf=True,
        run_host_security_preflight=True,
        check_nginx_syntax=True,
    )

    assert report["ok"] is True
    assert report["security_preflight"]["summary"]["ok"] is True
    assert report["host_security_preflight"]["summary"]["ok"] is True
    rendered = (tmp_path / "gate.txt").read_text(encoding="utf-8")
    assert "Security preflight:" in rendered
    assert "Host security preflight:" in rendered

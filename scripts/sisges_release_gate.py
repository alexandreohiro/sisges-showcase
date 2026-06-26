from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts import ux_ui_overclock_validate as ux_ui_validator


BACKEND_REQUIRED_IGNORES = {
    "data/output/",
    "data/releases/",
    "data/compiler_memory/",
    "data/uploads/",
    "data/trash/",
    "*.db",
    "*.zip",
    "*.pdf",
}

FRONTEND_REQUIRED_IGNORES = {
    "data/",
    "logs/",
    "*.log",
    "*.db",
    "*.zip",
    "*.pdf",
    "*.odt",
    "*.tsbuildinfo",
}

PROHIBITED_PATTERNS = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".zip",
    ".pdf",
    ".odt",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}

PROHIBITED_DIR_PARTS = {
    "data/output",
    "data/releases",
    "data/compiler_memory",
    "data/uploads",
    "data/trash",
    "node_modules",
    ".next",
    ".venv",
}

ALLOWED_TRACKED_ASSET_PREFIXES = {
    "apps/web/static/img/",
    "public/",
}

COMMAND_OUTPUT_TAIL_CHARS = 30000


def resolve_git_path() -> str | None:
    git_path = shutil.which("git")
    if git_path:
        return git_path

    candidates = [
        Path(os.getenv("LOCALAPPDATA", "")) / "Programs/Git/cmd/git.exe",
        Path(os.getenv("LOCALAPPDATA", "")) / "Programs/Git/bin/git.exe",
        Path(os.getenv("USERPROFILE", "")) / "scoop/shims/git.exe",
        Path(os.getenv("USERPROFILE", "")) / "scoop/apps/git/current/cmd/git.exe",
        Path("C:/Program Files/Git/cmd/git.exe"),
        Path("C:/Program Files/Git/bin/git.exe"),
        Path("C:/Program Files (x86)/Git/cmd/git.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    github_desktop_root = Path(os.getenv("LOCALAPPDATA", "")) / "GitHubDesktop"
    if github_desktop_root.exists():
        for pattern in (
            "app-*/resources/app/git/cmd/git.exe",
            "app-*/resources/app/git/mingw64/bin/git.exe",
        ):
            matches = sorted(github_desktop_root.glob(pattern), reverse=True)
            if matches:
                return str(matches[0])

    return None


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    cwd: str
    returncode: int
    stdout_tail: str
    stderr_tail: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "cwd": self.cwd,
            "returncode": self.returncode,
            "ok": self.ok,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }


def normalize_path(path: Path) -> str:
    return path.as_posix().lower()


def read_gitignore_patterns(repo: Path) -> set[str]:
    path = repo / ".gitignore"
    if not path.exists():
        return set()
    patterns = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            patterns.add(line)
    return patterns


def missing_required_ignores(repo: Path, required: set[str]) -> list[str]:
    patterns = read_gitignore_patterns(repo)
    return sorted(required - patterns)


def is_prohibited_artifact(path: Path, repo: Path) -> bool:
    relative = normalize_path(path.relative_to(repo))
    if any(part in relative for part in PROHIBITED_DIR_PARTS):
        return True
    return path.suffix.lower() in PROHIBITED_PATTERNS


def is_allowed_tracked_asset(path: str) -> bool:
    normalized = path.replace("\\", "/").lower().strip()
    return any(normalized.startswith(prefix) for prefix in ALLOWED_TRACKED_ASSET_PREFIXES)


def is_prohibited_relative_path(path: str, *, allow_tracked_assets: bool = False) -> bool:
    normalized = path.replace("\\", "/").lower().strip()
    if allow_tracked_assets and is_allowed_tracked_asset(normalized):
        return False
    if any(part in normalized for part in PROHIBITED_DIR_PARTS):
        return True
    return Path(normalized).suffix.lower() in PROHIBITED_PATTERNS


def scan_prohibited_artifacts(repo: Path, *, limit: int = 80) -> list[str]:
    ignored_roots = {".git", ".venv", "node_modules", ".next", "__pycache__", ".pytest_cache", ".ruff_cache"}
    found: list[str] = []
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        relative_parts = set(path.relative_to(repo).parts)
        if relative_parts & ignored_roots:
            continue
        if is_prohibited_artifact(path, repo):
            found.append(path.relative_to(repo).as_posix())
            if len(found) >= limit:
                break
    return found


def parse_git_name_lines(output: str) -> list[str]:
    files = []
    for raw_line in output.splitlines():
        line = raw_line.strip().strip('"')
        if line:
            files.append(line.replace("\\", "/"))
    return files


def parse_git_status_short(output: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw_line in output.splitlines():
        if not raw_line.strip():
            continue
        status = raw_line[:2]
        path = raw_line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip().strip('"')
        items.append({"status": status, "path": path.replace("\\", "/")})
    return items


def prohibited_from_paths(paths: Sequence[str], *, allow_tracked_assets: bool = False) -> list[str]:
    return sorted(
        {
            path
            for path in paths
            if is_prohibited_relative_path(path, allow_tracked_assets=allow_tracked_assets)
        }
    )


def run_command(command: Sequence[str], cwd: Path, *, timeout_seconds: int) -> CommandResult:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    return CommandResult(
        command=list(command),
        cwd=str(cwd),
        returncode=completed.returncode,
        stdout_tail=completed.stdout[-COMMAND_OUTPUT_TAIL_CHARS:],
        stderr_tail=completed.stderr[-COMMAND_OUTPUT_TAIL_CHARS:],
    )


def collect_git_repo_state(repo: Path, git_path: str | None) -> dict[str, Any]:
    if not git_path:
        return {
            "available": False,
            "status_ok": False,
            "status_short": [],
            "staged_files": [],
            "tracked_prohibited": [],
            "staged_prohibited": [],
            "errors": ["ERR_GIT_NOT_AVAILABLE"],
        }

    errors: list[str] = []
    status_result = run_command([git_path, "status", "--short"], repo, timeout_seconds=30)
    staged_result = run_command([git_path, "diff", "--cached", "--name-only"], repo, timeout_seconds=30)
    tracked_result = run_command([git_path, "ls-files"], repo, timeout_seconds=30)

    if not status_result.ok:
        errors.append("ERR_GIT_STATUS_FAILED")
    if not staged_result.ok:
        errors.append("ERR_GIT_STAGED_FAILED")
    if not tracked_result.ok:
        errors.append("ERR_GIT_LS_FILES_FAILED")

    status_short = parse_git_status_short(status_result.stdout_tail) if status_result.ok else []
    staged_files = parse_git_name_lines(staged_result.stdout_tail) if staged_result.ok else []
    tracked_files = parse_git_name_lines(tracked_result.stdout_tail) if tracked_result.ok else []
    return {
        "available": True,
        "status_ok": not errors,
        "status_short": status_short,
        "staged_files": staged_files,
        "tracked_prohibited": prohibited_from_paths(tracked_files, allow_tracked_assets=True),
        "staged_prohibited": prohibited_from_paths(staged_files),
        "errors": errors,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_expected_sha256(package_path: Path, expected_sha256: str | None) -> str | None:
    if expected_sha256:
        return expected_sha256.strip()
    sidecar = package_path.with_suffix(package_path.suffix + ".sha256")
    if not sidecar.exists():
        return None
    content = sidecar.read_text(encoding="utf-8").strip()
    return content.split()[0] if content else None


def validate_release_package(package_path: Path | None, expected_sha256: str | None = None) -> dict[str, Any]:
    if package_path is None:
        return {
            "provided": False,
            "ok": True,
            "path": None,
            "exists": False,
            "sha256": None,
            "expected_sha256": None,
            "errors": [],
        }

    package_path = package_path.resolve()
    errors: list[str] = []
    expected = read_expected_sha256(package_path, expected_sha256)
    exists = package_path.exists()
    digest = sha256_file(package_path) if exists else None
    if not exists:
        errors.append("ERR_RELEASE_PACKAGE_NOT_FOUND")
    if exists and expected and digest != expected:
        errors.append("ERR_RELEASE_PACKAGE_SHA256_MISMATCH")

    return {
        "provided": True,
        "ok": not errors,
        "path": str(package_path),
        "exists": exists,
        "size_bytes": package_path.stat().st_size if exists else 0,
        "sha256": digest,
        "expected_sha256": expected,
        "errors": errors,
    }


def build_overclock_command(
    *,
    backend_python: Path,
    profile: str,
    tarefas: int,
    efetivo: int,
    repeat: int,
    max_seconds: float,
    regression_tolerance_percent: float,
    baseline_json: Path | None = None,
) -> list[str]:
    command = [
        str(backend_python),
        "-m",
        "scripts.operational_overclock_report",
        "--profile",
        profile,
        "--tarefas",
        str(tarefas),
        "--efetivo",
        str(efetivo),
        "--repeat",
        str(repeat),
        "--max-seconds",
        str(max_seconds),
        "--profile-label",
        f"release-gate-{profile}",
        "--regression-tolerance-percent",
        str(regression_tolerance_percent),
        "--output-json",
        "data/output/sisges_release_gate_overclock.json",
        "--output-txt",
        "data/output/sisges_release_gate_overclock.txt",
    ]
    if baseline_json is not None:
        command.extend(["--baseline-json", str(baseline_json)])
    return command


def build_health_smoke_command(*, backend_python: Path, allow_degraded_ready: bool = False) -> list[str]:
    command = [
        str(backend_python),
        "-m",
        "scripts.sisges_health_smoke",
        "--output-json",
        "data/output/sisges_release_gate_health.json",
        "--output-txt",
        "data/output/sisges_release_gate_health.txt",
    ]
    if allow_degraded_ready:
        command.append("--allow-degraded-ready")
    return command


def build_security_preflight_command(
    *,
    backend_python: Path,
    frontend: Path,
    require_prod: bool = False,
    check_frontend_csrf: bool = False,
) -> list[str]:
    command = [
        str(backend_python),
        "-m",
        "scripts.security_preflight",
        "--frontend-dir",
        str(frontend),
        "--json",
    ]
    if require_prod:
        command.append("--require-prod")
    if check_frontend_csrf:
        command.append("--check-frontend-csrf")
    return command


def build_host_security_preflight_command(
    *,
    backend_python: Path,
    check_nginx_syntax: bool = False,
    check_ports: bool = False,
) -> list[str]:
    command = [
        str(backend_python),
        "-m",
        "scripts.host_security_preflight",
        "--json",
    ]
    if check_nginx_syntax:
        command.append("--check-nginx-syntax")
    if check_ports:
        command.append("--check-ports")
    return command


def summarize_json_command_result(command: CommandResult, expected_schema: str) -> dict[str, Any]:
    if not command.stdout_tail.strip():
        return {
            "available": False,
            "ok": False,
            "schema_version": None,
            "checks_count": 0,
            "warnings_count": 0,
            "returncode": command.returncode,
            "errors": ["ERR_JSON_COMMAND_NO_STDOUT"],
        }
    try:
        payload = json.loads(command.stdout_tail)
    except json.JSONDecodeError as exc:
        return {
            "available": True,
            "ok": False,
            "schema_version": None,
            "checks_count": 0,
            "warnings_count": 0,
            "returncode": command.returncode,
            "errors": [f"ERR_JSON_COMMAND_INVALID_JSON:{exc.msg}"],
        }

    schema_version = payload.get("schema_version")
    schema_ok = schema_version == expected_schema
    payload_ok = bool(payload.get("ok"))
    return {
        "available": True,
        "ok": command.ok and payload_ok and schema_ok,
        "schema_version": schema_version,
        "checks_count": len(payload.get("checks") or []),
        "warnings_count": len(payload.get("warnings") or []),
        "returncode": command.returncode,
        "errors": []
        if command.ok and payload_ok and schema_ok
        else [
            *([] if command.ok else [f"ERR_COMMAND_RETURNCODE_{command.returncode}"]),
            *([] if payload_ok else ["ERR_PREFLIGHT_NOT_OK"]),
            *([] if schema_ok else [f"ERR_SCHEMA_UNEXPECTED:{schema_version}"]),
        ],
    }


def summarize_health_smoke_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "available": False,
            "ok": False,
            "path": str(path),
            "status": "MISSING",
            "checks_count": 0,
            "failed_endpoints": [],
            "database_status": None,
            "errors": ["ERR_HEALTH_SMOKE_REPORT_NOT_FOUND"],
        }
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "available": True,
            "ok": False,
            "path": str(path),
            "status": "INVALID_JSON",
            "checks_count": 0,
            "failed_endpoints": [],
            "database_status": None,
            "errors": [f"ERR_HEALTH_SMOKE_REPORT_INVALID_JSON:{exc.msg}"],
        }

    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    ready_check = next((check for check in checks if check.get("endpoint") == "/health/ready"), None)
    status = str(report.get("status") or "UNKNOWN")
    return {
        "available": True,
        "ok": status == "OK",
        "path": str(path),
        "status": status,
        "checks_count": len(checks),
        "failed_endpoints": report.get("failed_endpoints") or [],
        "database_status": ready_check.get("database_status") if isinstance(ready_check, dict) else None,
        "errors": [] if status == "OK" else [f"ERR_HEALTH_SMOKE_STATUS_{status}"],
    }


def summarize_overclock_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "available": False,
            "ok": False,
            "path": str(path),
            "status": "MISSING",
            "profile_label": None,
            "endpoints_count": 0,
            "slowest_endpoint": None,
            "baseline_status": None,
            "regressions": [],
            "errors": ["ERR_OVERCLOCK_REPORT_NOT_FOUND"],
        }

    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "available": True,
            "ok": False,
            "path": str(path),
            "status": "INVALID_JSON",
            "profile_label": None,
            "endpoints_count": 0,
            "slowest_endpoint": None,
            "baseline_status": None,
            "regressions": [],
            "errors": [f"ERR_OVERCLOCK_REPORT_INVALID_JSON:{exc.msg}"],
        }

    endpoints = report.get("endpoints") if isinstance(report.get("endpoints"), list) else []
    slowest_endpoint = None
    if endpoints:
        slowest = max(
            endpoints,
            key=lambda endpoint: float(endpoint.get("elapsed_ms", {}).get("p95", 0.0)),
        )
        slowest_endpoint = {
            "endpoint": slowest.get("endpoint"),
            "p95_ms": slowest.get("elapsed_ms", {}).get("p95"),
            "max_ms": slowest.get("elapsed_ms", {}).get("max"),
            "ok": slowest.get("ok"),
        }

    baseline = report.get("baseline_comparison") or {}
    comparisons = baseline.get("comparisons") if isinstance(baseline.get("comparisons"), list) else []
    regressions = [
        {
            "endpoint": comparison.get("endpoint"),
            "metric": comparison.get("metric"),
            "current_ms": comparison.get("current_ms"),
            "baseline_ms": comparison.get("baseline_ms"),
            "allowed_ms": comparison.get("allowed_ms"),
            "delta_percent": comparison.get("delta_percent"),
        }
        for comparison in comparisons
        if comparison.get("status") == "REGRESSION"
    ]

    status = str(report.get("status") or "UNKNOWN")
    return {
        "available": True,
        "ok": status == "OK" and not regressions,
        "path": str(path),
        "status": status,
        "profile_label": report.get("profile_label"),
        "endpoints_count": len(endpoints),
        "slowest_endpoint": slowest_endpoint,
        "baseline_status": baseline.get("status"),
        "regressions": regressions,
        "errors": [] if status == "OK" else [f"ERR_OVERCLOCK_STATUS_{status}"],
    }


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int | float):
        return int(value)
    return 0


def summarize_ux_ui_report(path: Path, *, profile_path: Path = ux_ui_validator.DEFAULT_PROFILE) -> dict[str, Any]:
    if not path.exists():
        return {
            "available": False,
            "ok": False,
            "path": str(path),
            "profile": str(profile_path),
            "status": "MISSING",
            "pages_count": 0,
            "failed_pages": [],
            "console_errors_total": 0,
            "slowest_page": None,
            "errors": ["ERR_UX_UI_REPORT_NOT_FOUND"],
            "warnings": [],
        }

    try:
        profile = ux_ui_validator.load_json(profile_path)
        report = ux_ui_validator.load_json(path)
    except FileNotFoundError as exc:
        return {
            "available": True,
            "ok": False,
            "path": str(path),
            "profile": str(profile_path),
            "status": "PROFILE_MISSING",
            "pages_count": 0,
            "failed_pages": [],
            "console_errors_total": 0,
            "slowest_page": None,
            "errors": [f"ERR_UX_UI_PROFILE_NOT_FOUND:{exc.filename}"],
            "warnings": [],
        }
    except json.JSONDecodeError as exc:
        return {
            "available": True,
            "ok": False,
            "path": str(path),
            "profile": str(profile_path),
            "status": "INVALID_JSON",
            "pages_count": 0,
            "failed_pages": [],
            "console_errors_total": 0,
            "slowest_page": None,
            "errors": [f"ERR_UX_UI_REPORT_INVALID_JSON:{exc.msg}"],
            "warnings": [],
        }

    profile_validation = ux_ui_validator.validate_profile(profile)
    report_validation = (
        ux_ui_validator.validate_report(report, profile)
        if profile_validation["ok"]
        else {"ok": False, "errors": [], "warnings": [], "pages_count": 0}
    )
    pages = report.get("pages") if isinstance(report.get("pages"), list) else []
    failed_pages = [
        str(page.get("path") or "-")
        for page in pages
        if isinstance(page, dict) and (page.get("ok") is not True or page.get("expected_text_found") is not True)
    ]
    console_errors_total = sum(_safe_int(page.get("console_errors")) for page in pages if isinstance(page, dict))
    slowest_page = None
    if pages:
        slowest = max(
            (page for page in pages if isinstance(page, dict)),
            key=lambda page: _safe_int(page.get("loaded_ms")),
            default=None,
        )
        if slowest:
            slowest_page = {
                "path": slowest.get("path"),
                "loaded_ms": slowest.get("loaded_ms"),
                "ok": slowest.get("ok"),
            }

    errors = [*profile_validation["errors"], *report_validation["errors"]]
    warnings = [*profile_validation["warnings"], *report_validation["warnings"]]
    status = str(report.get("status") or "UNKNOWN")
    return {
        "available": True,
        "ok": bool(profile_validation["ok"] and report_validation["ok"]),
        "path": str(path),
        "profile": str(profile_path),
        "status": status,
        "pages_count": len(pages),
        "failed_pages": failed_pages,
        "console_errors_total": console_errors_total,
        "slowest_page": slowest_page,
        "errors": errors,
        "warnings": warnings,
    }


def build_report(
    *,
    backend: Path,
    frontend: Path,
    run_validation: bool,
    output_json: Path,
    output_txt: Path,
    require_git: bool = True,
    release_package: Path | None = None,
    release_sha256: str | None = None,
    run_health_smoke: bool = False,
    health_allow_degraded_ready: bool = False,
    run_overclock: bool = False,
    overclock_profile: str = "critical",
    overclock_baseline_json: Path | None = None,
    overclock_tarefas: int = 300,
    overclock_efetivo: int = 1000,
    overclock_repeat: int = 5,
    overclock_max_seconds: float = 5.0,
    overclock_regression_tolerance_percent: float = 35.0,
    ux_ui_report: Path | None = None,
    ux_ui_profile: Path = ux_ui_validator.DEFAULT_PROFILE,
    run_security_preflight: bool = False,
    security_require_prod: bool = False,
    check_frontend_csrf: bool = False,
    run_host_security_preflight: bool = False,
    check_nginx_syntax: bool = False,
    check_nginx_ports: bool = False,
) -> dict[str, Any]:
    backend = backend.resolve()
    frontend = frontend.resolve()
    git_path = resolve_git_path()

    report: dict[str, Any] = {
        "schema_version": "sisges-release-gate-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "backend": str(backend),
        "frontend": str(frontend),
        "git": {
            "available": bool(git_path),
            "path": git_path,
            "backend_has_git_dir": (backend / ".git").exists(),
            "frontend_has_git_dir": (frontend / ".git").exists(),
            "backend_state": collect_git_repo_state(backend, git_path),
            "frontend_state": collect_git_repo_state(frontend, git_path),
        },
        "gitignore": {
            "backend_missing": missing_required_ignores(backend, BACKEND_REQUIRED_IGNORES),
            "frontend_missing": missing_required_ignores(frontend, FRONTEND_REQUIRED_IGNORES),
        },
        "artifacts": {
            "backend_prohibited_examples": scan_prohibited_artifacts(backend),
            "frontend_prohibited_examples": scan_prohibited_artifacts(frontend),
            "note": "Lista informativa; arquivos em diretorios ignorados nao devem ser commitados.",
        },
        "commands": [],
        "release_package": validate_release_package(release_package, release_sha256),
        "health_smoke": {
            "enabled": run_health_smoke,
            "allow_degraded_ready": health_allow_degraded_ready,
            "output_json": str(backend / "data/output/sisges_release_gate_health.json"),
            "output_txt": str(backend / "data/output/sisges_release_gate_health.txt"),
            "summary": None,
        },
        "requirements": {
            "require_git": require_git,
        },
        "overclock": {
            "enabled": run_overclock,
            "profile": overclock_profile,
            "baseline_json": str(overclock_baseline_json) if overclock_baseline_json else None,
            "output_json": str(backend / "data/output/sisges_release_gate_overclock.json"),
            "output_txt": str(backend / "data/output/sisges_release_gate_overclock.txt"),
            "summary": None,
            "tarefas": overclock_tarefas,
            "efetivo": overclock_efetivo,
            "repeat": overclock_repeat,
            "max_seconds": overclock_max_seconds,
            "regression_tolerance_percent": overclock_regression_tolerance_percent,
        },
        "ux_ui": {
            "provided": ux_ui_report is not None,
            "profile": str(ux_ui_profile),
            "report": str(ux_ui_report) if ux_ui_report else None,
            "summary": summarize_ux_ui_report(ux_ui_report, profile_path=ux_ui_profile) if ux_ui_report else None,
        },
        "security_preflight": {
            "enabled": run_security_preflight,
            "require_prod": security_require_prod,
            "check_frontend_csrf": check_frontend_csrf,
            "summary": None,
        },
        "host_security_preflight": {
            "enabled": run_host_security_preflight,
            "check_nginx_syntax": check_nginx_syntax,
            "check_ports": check_nginx_ports,
            "summary": None,
        },
    }

    backend_python = backend / ".venv" / "Scripts" / "python.exe"
    if run_validation:
        command_specs = [
            ([str(backend_python), "-m", "ruff", "check", "."], backend, 180),
            ([str(backend_python), "-m", "pytest"], backend, 360),
            (["npm.cmd", "run", "validate:csrf-client"], frontend, 120),
            (["npm.cmd", "run", "build"], frontend, 240),
        ]
        report["commands"].extend(
            run_command(command, cwd, timeout_seconds=timeout).to_dict()
            for command, cwd, timeout in command_specs
        )

    if run_security_preflight:
        command = build_security_preflight_command(
            backend_python=backend_python,
            frontend=frontend,
            require_prod=security_require_prod,
            check_frontend_csrf=check_frontend_csrf,
        )
        command_result = run_command(command, backend, timeout_seconds=180)
        report["commands"].append(command_result.to_dict())
        report["security_preflight"]["summary"] = summarize_json_command_result(
            command_result,
            "sisges-security-preflight-v1",
        )

    if run_host_security_preflight:
        command = build_host_security_preflight_command(
            backend_python=backend_python,
            check_nginx_syntax=check_nginx_syntax,
            check_ports=check_nginx_ports,
        )
        command_result = run_command(command, backend, timeout_seconds=120)
        report["commands"].append(command_result.to_dict())
        report["host_security_preflight"]["summary"] = summarize_json_command_result(
            command_result,
            "sisges-host-security-preflight-v1",
        )

    if run_health_smoke:
        command = build_health_smoke_command(
            backend_python=backend_python,
            allow_degraded_ready=health_allow_degraded_ready,
        )
        report["commands"].append(run_command(command, backend, timeout_seconds=120).to_dict())
        report["health_smoke"]["summary"] = summarize_health_smoke_report(
            backend / "data/output/sisges_release_gate_health.json"
        )

    if run_overclock:
        command = build_overclock_command(
            backend_python=backend_python,
            profile=overclock_profile,
            baseline_json=overclock_baseline_json,
            tarefas=overclock_tarefas,
            efetivo=overclock_efetivo,
            repeat=overclock_repeat,
            max_seconds=overclock_max_seconds,
            regression_tolerance_percent=overclock_regression_tolerance_percent,
        )
        report["commands"].append(
            run_command(command, backend, timeout_seconds=300).to_dict()
        )
        report["overclock"]["summary"] = summarize_overclock_report(
            backend / "data/output/sisges_release_gate_overclock.json"
        )

    report["ok"] = (
        (bool(git_path) or not require_git)
        and not report["git"]["backend_state"]["tracked_prohibited"]
        and not report["git"]["backend_state"]["staged_prohibited"]
        and not report["git"]["frontend_state"]["tracked_prohibited"]
        and not report["git"]["frontend_state"]["staged_prohibited"]
        and not report["gitignore"]["backend_missing"]
        and not report["gitignore"]["frontend_missing"]
        and report["release_package"]["ok"]
        and (not run_health_smoke or bool(report["health_smoke"]["summary"] and report["health_smoke"]["summary"]["ok"]))
        and (
            not run_security_preflight
            or bool(report["security_preflight"]["summary"] and report["security_preflight"]["summary"]["ok"])
        )
        and (
            not run_host_security_preflight
            or bool(
                report["host_security_preflight"]["summary"]
                and report["host_security_preflight"]["summary"]["ok"]
            )
        )
        and (not run_overclock or bool(report["overclock"]["summary"] and report["overclock"]["summary"]["ok"]))
        and (ux_ui_report is None or bool(report["ux_ui"]["summary"] and report["ux_ui"]["summary"]["ok"]))
        and all(command["ok"] for command in report["commands"])
    )

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_txt.write_text(render_text_report(report), encoding="utf-8")
    return report


def render_text_report(report: dict[str, Any]) -> str:
    lines = [
        "SISGES RELEASE GATE",
        f"Gerado em: {report['generated_at']}",
        f"Status: {'OK' if report['ok'] else 'PENDENTE'}",
        "",
        "Git:",
        f"- disponivel: {report['git']['available']}",
        f"- path: {report['git']['path'] or '-'}",
        f"- backend .git: {report['git']['backend_has_git_dir']}",
        f"- frontend .git: {report['git']['frontend_has_git_dir']}",
        f"- backend staged proibido: {len(report['git']['backend_state']['staged_prohibited'])}",
        f"- backend tracked proibido: {len(report['git']['backend_state']['tracked_prohibited'])}",
        f"- frontend staged proibido: {len(report['git']['frontend_state']['staged_prohibited'])}",
        f"- frontend tracked proibido: {len(report['git']['frontend_state']['tracked_prohibited'])}",
        "",
        "Gitignore:",
        f"- backend pendente: {', '.join(report['gitignore']['backend_missing']) or 'nenhum'}",
        f"- frontend pendente: {', '.join(report['gitignore']['frontend_missing']) or 'nenhum'}",
        "",
        "Artefatos locais detectados:",
        f"- backend exemplos: {len(report['artifacts']['backend_prohibited_examples'])}",
        f"- frontend exemplos: {len(report['artifacts']['frontend_prohibited_examples'])}",
        "",
        "Health smoke:",
        f"- habilitado: {report['health_smoke']['enabled']}",
        f"- degraded ready permitido: {report['health_smoke']['allow_degraded_ready']}",
    ]
    health_summary = report["health_smoke"].get("summary")
    if health_summary:
        lines.extend(
            [
                f"- status: {health_summary['status']}",
                f"- checks: {health_summary['checks_count']}",
                f"- database: {health_summary.get('database_status') or '-'}",
                f"- falhas: {', '.join(health_summary['failed_endpoints']) or 'nenhuma'}",
            ]
        )
    lines.extend(
        [
            "",
            "UX/UI overclock:",
            f"- informado: {report['ux_ui']['provided']}",
            f"- perfil: {report['ux_ui']['profile']}",
            f"- relatorio: {report['ux_ui']['report'] or '-'}",
        ]
    )
    ux_ui_summary = report["ux_ui"].get("summary")
    if ux_ui_summary:
        slowest_page = ux_ui_summary.get("slowest_page") or {}
        lines.extend(
            [
                f"- status: {ux_ui_summary['status']}",
                f"- pages: {ux_ui_summary['pages_count']}",
                f"- console errors: {ux_ui_summary['console_errors_total']}",
                f"- falhas: {', '.join(ux_ui_summary['failed_pages']) or 'nenhuma'}",
                (
                    "- mais lenta: {path} ({loaded_ms}ms)"
                ).format(
                    path=slowest_page.get("path") or "-",
                    loaded_ms=slowest_page.get("loaded_ms") if slowest_page else "-",
                ),
            ]
        )
    lines.extend(
        [
            "",
            "Security preflight:",
            f"- habilitado: {report['security_preflight']['enabled']}",
            f"- require prod: {report['security_preflight']['require_prod']}",
            f"- frontend csrf: {report['security_preflight']['check_frontend_csrf']}",
        ]
    )
    security_summary = report["security_preflight"].get("summary")
    if security_summary:
        lines.extend(
            [
                f"- schema: {security_summary['schema_version'] or '-'}",
                f"- checks: {security_summary['checks_count']}",
                f"- warnings: {security_summary['warnings_count']}",
                f"- status: {'OK' if security_summary['ok'] else 'FAIL'}",
            ]
        )
    lines.extend(
        [
            "",
            "Host security preflight:",
            f"- habilitado: {report['host_security_preflight']['enabled']}",
            f"- nginx syntax: {report['host_security_preflight']['check_nginx_syntax']}",
            f"- portas: {report['host_security_preflight']['check_ports']}",
        ]
    )
    host_security_summary = report["host_security_preflight"].get("summary")
    if host_security_summary:
        lines.extend(
            [
                f"- schema: {host_security_summary['schema_version'] or '-'}",
                f"- checks: {host_security_summary['checks_count']}",
                f"- warnings: {host_security_summary['warnings_count']}",
                f"- status: {'OK' if host_security_summary['ok'] else 'FAIL'}",
            ]
        )
    lines.extend(
        [
            "",
            "Overclock:",
            f"- habilitado: {report['overclock']['enabled']}",
            f"- perfil: {report['overclock']['profile']}",
            f"- baseline: {report['overclock']['baseline_json'] or '-'}",
        ]
    )
    overclock_summary = report["overclock"].get("summary")
    if overclock_summary:
        slowest = overclock_summary.get("slowest_endpoint") or {}
        lines.extend(
            [
                f"- status: {overclock_summary['status']}",
                f"- endpoints: {overclock_summary['endpoints_count']}",
                f"- baseline status: {overclock_summary.get('baseline_status') or '-'}",
                f"- regressions: {len(overclock_summary['regressions'])}",
                (
                    "- mais lento p95: {endpoint} ({p95}ms)"
                ).format(
                    endpoint=slowest.get("endpoint") or "-",
                    p95=slowest.get("p95_ms") if slowest else "-",
                ),
            ]
        )
    if report["release_package"]["provided"]:
        release = report["release_package"]
        lines.extend(
            [
                "",
                "Pacote de release:",
                f"- path: {release['path']}",
                f"- existe: {release['exists']}",
                f"- sha256: {release['sha256'] or '-'}",
                f"- esperado: {release['expected_sha256'] or '-'}",
                f"- status: {'OK' if release['ok'] else 'FAIL'}",
            ]
        )
    if report["commands"]:
        lines.append("")
        lines.append("Comandos:")
        for command in report["commands"]:
            lines.append(
                "- {cmd} | cwd={cwd} | rc={rc} | {status}".format(
                    cmd=" ".join(command["command"]),
                    cwd=command["cwd"],
                    rc=command["returncode"],
                    status="OK" if command["ok"] else "FAIL",
                )
            )
    lines.append("")
    lines.append("Observacao: artefatos locais em data/, .next, node_modules e outputs devem permanecer fora do Git.")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auditoria pre-release local do SISGES.")
    parser.add_argument("--backend", type=Path, default=Path.cwd())
    parser.add_argument(
        "--frontend",
        type=Path,
        default=Path(os.getenv("SISGES_FRONTEND_PATH", "../web-sisges-v0")),
    )
    parser.add_argument("--run-validation", action="store_true")
    parser.add_argument("--run-health-smoke", action="store_true")
    parser.add_argument("--health-allow-degraded-ready", action="store_true")
    parser.add_argument("--run-overclock", action="store_true")
    parser.add_argument("--overclock-profile", default="critical")
    parser.add_argument("--overclock-baseline-json", type=Path, default=None)
    parser.add_argument("--overclock-tarefas", type=int, default=300)
    parser.add_argument("--overclock-efetivo", type=int, default=1000)
    parser.add_argument("--overclock-repeat", type=int, default=5)
    parser.add_argument("--overclock-max-seconds", type=float, default=5.0)
    parser.add_argument("--overclock-regression-tolerance-percent", type=float, default=35.0)
    parser.add_argument("--ux-ui-report", type=Path, default=None)
    parser.add_argument("--ux-ui-profile", type=Path, default=ux_ui_validator.DEFAULT_PROFILE)
    parser.add_argument("--run-security-preflight", action="store_true")
    parser.add_argument("--security-require-prod", action="store_true")
    parser.add_argument("--check-frontend-csrf", action="store_true")
    parser.add_argument("--run-host-security-preflight", action="store_true")
    parser.add_argument("--check-nginx-syntax", action="store_true")
    parser.add_argument("--check-nginx-ports", action="store_true")
    parser.add_argument("--allow-missing-git", action="store_true")
    parser.add_argument("--release-package", type=Path, default=None)
    parser.add_argument("--release-sha256", default=None)
    parser.add_argument("--output-json", type=Path, default=Path("data/output/sisges_release_gate.json"))
    parser.add_argument("--output-txt", type=Path, default=Path("data/output/sisges_release_gate.txt"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        backend=args.backend,
        frontend=args.frontend,
        run_validation=args.run_validation,
        output_json=args.output_json,
        output_txt=args.output_txt,
        require_git=not args.allow_missing_git,
        release_package=args.release_package,
        release_sha256=args.release_sha256,
        run_health_smoke=args.run_health_smoke,
        health_allow_degraded_ready=args.health_allow_degraded_ready,
        run_overclock=args.run_overclock,
        overclock_profile=args.overclock_profile,
        overclock_baseline_json=args.overclock_baseline_json,
        overclock_tarefas=args.overclock_tarefas,
        overclock_efetivo=args.overclock_efetivo,
        overclock_repeat=args.overclock_repeat,
        overclock_max_seconds=args.overclock_max_seconds,
        overclock_regression_tolerance_percent=args.overclock_regression_tolerance_percent,
        ux_ui_report=args.ux_ui_report,
        ux_ui_profile=args.ux_ui_profile,
        run_security_preflight=args.run_security_preflight,
        security_require_prod=args.security_require_prod,
        check_frontend_csrf=args.check_frontend_csrf,
        run_host_security_preflight=args.run_host_security_preflight,
        check_nginx_syntax=args.check_nginx_syntax,
        check_nginx_ports=args.check_nginx_ports,
    )
    print(render_text_report(report))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

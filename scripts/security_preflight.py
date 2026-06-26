from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

from infra.config import settings
from scripts.mysql_hardening_gate import run_gate


SCHEMA_VERSION = "sisges-security-preflight-v1"


def _check(code: str, ok: bool, message: str, severity: str = "error") -> dict[str, Any]:
    return {
        "code": code,
        "ok": ok,
        "severity": severity,
        "message": message,
    }


def _file_check(root: Path, relative: str, *, severity: str = "error") -> dict[str, Any]:
    path = root / relative
    return _check(
        f"FILE_{relative.upper().replace('/', '_').replace('.', '_').replace('-', '_')}",
        path.exists(),
        f"{relative} encontrado." if path.exists() else f"{relative} ausente.",
        severity,
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _database_is_mysql(database_url: str) -> bool:
    try:
        return make_url(database_url).drivername.startswith("mysql")
    except Exception:
        return False


def _frontend_contract_checks(
    frontend_dir: Path,
    *,
    check_csrf: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = [
        _file_check(frontend_dir, "package.json"),
        _file_check(frontend_dir, "lib/api.ts"),
        _file_check(frontend_dir, "lib/endpoints.ts"),
        _file_check(frontend_dir, "scripts/validate-csrf-client.mjs"),
        _file_check(frontend_dir, "docs/CSRF_FRONTEND_CONTRACT.md", severity="warning"),
    ]
    warnings: list[dict[str, Any]] = []

    package_json = _read_text(frontend_dir / "package.json")
    checks.append(
        _check(
            "FRONTEND_VALIDATE_CSRF_CLIENT_SCRIPT",
            "validate:csrf-client" in package_json,
            "Script validate:csrf-client declarado."
            if "validate:csrf-client" in package_json
            else "Script validate:csrf-client ausente.",
        )
    )

    api_source = _read_text(frontend_dir / "lib" / "api.ts")
    for token in ("X-CSRF-Token", "CSRF_TOKEN_MISSING", "CSRF_TOKEN_INVALID", "refreshCsrfToken"):
        checks.append(
            _check(
                f"FRONTEND_CSRF_{token.upper().replace('-', '_')}",
                token in api_source,
                f"Cliente API contem {token}."
                if token in api_source
                else f"Cliente API sem {token}.",
            )
        )

    if check_csrf:
        result = subprocess.run(
            ["npm.cmd", "run", "validate:csrf-client"],
            cwd=frontend_dir,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        checks.append(
            _check(
                "FRONTEND_VALIDATE_CSRF_CLIENT_EXECUTED",
                result.returncode == 0,
                "npm run validate:csrf-client aprovado."
                if result.returncode == 0
                else "npm run validate:csrf-client reprovado.",
            )
        )
        if result.returncode != 0:
            warnings.append(
                _check(
                    "FRONTEND_VALIDATE_CSRF_CLIENT_STDERR",
                    False,
                    (result.stderr or result.stdout or "Sem saida.").strip()[-500:],
                    "warning",
                )
            )

    return checks, warnings


def build_security_preflight(
    *,
    root: Path | None = None,
    mysql_url: str | None = None,
    require_prod: bool = False,
    connect_mysql: bool = False,
    frontend_dir: Path | None = None,
    check_frontend_csrf: bool = False,
) -> dict[str, Any]:
    root = root or settings.base_dir
    database_url = mysql_url or settings.database_url
    checks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    checks.extend(
        [
            _file_check(root, "ops/nginx/sisges.conf"),
            _file_check(root, "docs/NGINX_HARDENING_SISGES.md"),
            _file_check(root, "docs/SECURITY_LOGGING_SISGES.md"),
            _file_check(root, "docs/BLUE_TEAM_HARDENING_SISGES_README.md"),
            _file_check(root, "docs/PLANO_MIGRACAO_MYSQL_SEGURA.md"),
            _file_check(root, "ops/mysql/create_sisges_users.sql"),
            _file_check(root, "ops/mysql/verify_grants.sql"),
            _file_check(root, "ops/mysql/backup_restore_checklist.md"),
            _file_check(root, ".env.mysql.example"),
            _file_check(root, "scripts/mysql_hardening_gate.py"),
            _file_check(root, "scripts/check_database_connection.py"),
        ]
    )

    pyproject = _read_text(root / "pyproject.toml")
    checks.append(
        _check(
            "DEPENDENCY_PYMYSQL_PRESENT",
            "pymysql" in pyproject.lower(),
            "Dependencia PyMySQL declarada."
            if "pymysql" in pyproject.lower()
            else "Dependencia PyMySQL ausente em pyproject.toml.",
        )
    )

    nginx_conf = _read_text(root / "ops" / "nginx" / "sisges.conf")
    for token in (
        "server_tokens off",
        "X-Frame-Options",
        "Content-Security-Policy",
        "limit_req_zone",
        "client_max_body_size",
    ):
        checks.append(
            _check(
                f"NGINX_{token.upper().replace(' ', '_').replace('-', '_')}",
                token in nginx_conf,
                f"Nginx contem {token}." if token in nginx_conf else f"Nginx sem {token}.",
            )
        )

    strict_runtime_checks = [
        _check(
            "SETTINGS_LOG_JSON",
            settings.log_format == "json",
            "Logs em JSON configurados."
            if settings.log_format == "json"
            else "SISGES_LOG_FORMAT deve ser json.",
        ),
        _check(
            "SETTINGS_COOKIE_SECURE",
            settings.session_cookie_secure,
            "Cookie secure ativo." if settings.session_cookie_secure else "Cookie secure inativo.",
        ),
        _check(
            "SETTINGS_COOKIE_SAMESITE_STRICT",
            settings.session_cookie_samesite == "strict",
            "SameSite strict ativo."
            if settings.session_cookie_samesite == "strict"
            else "SameSite strict inativo.",
        ),
        _check(
            "SETTINGS_CSRF_ENABLED",
            settings.csrf_enabled,
            "CSRF ativo." if settings.csrf_enabled else "CSRF inativo.",
        ),
        _check(
            "SETTINGS_DEBUG_FALSE",
            not settings.debug,
            "Debug desativado." if not settings.debug else "Debug ativo.",
        ),
    ]
    if require_prod:
        checks.extend(strict_runtime_checks)
    else:
        warnings.extend({**item, "severity": "warning"} for item in strict_runtime_checks if not item["ok"])

    if _database_is_mysql(database_url):
        mysql_gate = run_gate(database_url, purpose="app", connect=connect_mysql)
        checks.append(
            _check(
                "MYSQL_HARDENING_GATE",
                bool(mysql_gate["ok"]),
                "Gate MySQL de aplicacao aprovado."
                if mysql_gate["ok"]
                else "Gate MySQL de aplicacao reprovado.",
            )
        )
    else:
        warnings.append(
            _check(
                "DATABASE_SQLITE_LOCAL",
                False,
                "Banco atual nao e MySQL; aceitavel em dev, pendente para homolog/prod.",
                "warning",
            )
        )
        mysql_gate = None

    frontend_report: dict[str, Any] | None = None
    if frontend_dir:
        frontend_dir = frontend_dir.resolve()
        frontend_checks, frontend_warnings = _frontend_contract_checks(
            frontend_dir,
            check_csrf=check_frontend_csrf,
        )
        checks.extend(frontend_checks)
        warnings.extend(frontend_warnings)
        frontend_report = {
            "path": str(frontend_dir),
            "csrf_validation_executed": check_frontend_csrf,
        }

    ok = all(item["ok"] for item in checks)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "ok": ok,
        "require_prod": require_prod,
        "environment": settings.environment,
        "database_kind": "mysql" if _database_is_mysql(database_url) else "non_mysql",
        "checks": checks,
        "warnings": warnings,
        "mysql_gate": mysql_gate,
        "frontend": frontend_report,
    }


def write_reports(report: dict[str, Any], output_json: Path | None, output_txt: Path | None) -> None:
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_txt:
        output_txt.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "SISGES SECURITY PREFLIGHT",
            f"Status: {'OK' if report['ok'] else 'ERRO'}",
            f"Ambiente: {report['environment']}",
            f"Banco: {report['database_kind']}",
            "",
            "Checks:",
        ]
        lines.extend(
            f"- {item['code']}: {'OK' if item['ok'] else 'ERRO'} - {item['message']}"
            for item in report["checks"]
        )
        if report["warnings"]:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"- {item['code']}: {item['message']}" for item in report["warnings"])
        output_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight defensivo local do SISGES.")
    parser.add_argument("--mysql-url", default=None, help="URL MySQL opcional para validar.")
    parser.add_argument("--require-prod", action="store_true", help="Torna postura prod bloqueante.")
    parser.add_argument("--connect-mysql", action="store_true", help="Executa SELECT 1 na URL MySQL.")
    parser.add_argument("--frontend-dir", type=Path, default=None, help="Diretorio do frontend SISGES.")
    parser.add_argument(
        "--check-frontend-csrf",
        action="store_true",
        help="Executa npm run validate:csrf-client no frontend informado.",
    )
    parser.add_argument("--json", action="store_true", help="Imprime JSON no terminal.")
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-txt", type=Path, default=None)
    args = parser.parse_args(argv)

    report = build_security_preflight(
        mysql_url=args.mysql_url,
        require_prod=args.require_prod,
        connect_mysql=args.connect_mysql,
        frontend_dir=args.frontend_dir,
        check_frontend_csrf=args.check_frontend_csrf,
    )
    write_reports(report, args.output_json, args.output_txt)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"SISGES SECURITY PREFLIGHT: {'OK' if report['ok'] else 'ERRO'}")
        print(f"checks={len(report['checks'])} warnings={len(report['warnings'])}")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

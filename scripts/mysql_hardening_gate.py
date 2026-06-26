from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from sqlalchemy.engine import make_url

from infra.config import settings
from scripts.check_database_connection import check_connection


APP_USERS = {"sisges_app"}
MIGRATION_USERS = {"sisges_migrator"}
BACKUP_USERS = {"sisges_backup"}
FORBIDDEN_USERS = {"root", "admin", "administrator", "mysql.sys", "mysql.session"}


@dataclass(frozen=True)
class GateResult:
    ok: bool
    checks: list[dict]
    warnings: list[dict]
    safe_url: str

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "safe_url": self.safe_url,
            "checks": self.checks,
            "warnings": self.warnings,
        }


def _safe_url(database_url: str) -> str:
    return make_url(database_url).render_as_string(hide_password=True)


def _check(code: str, ok: bool, message: str) -> dict:
    return {"code": code, "ok": ok, "message": message}


def validate_mysql_database_url(database_url: str, *, purpose: str = "app") -> GateResult:
    url = make_url(database_url)
    checks: list[dict] = []
    warnings: list[dict] = []

    is_mysql = url.drivername.startswith("mysql")
    checks.append(
        _check(
            "MYSQL_DRIVER",
            is_mysql,
            "URL usa driver MySQL." if is_mysql else f"Driver invalido: {url.drivername}.",
        )
    )

    is_pymysql = url.drivername == "mysql+pymysql"
    checks.append(
        _check(
            "MYSQL_PYMYSQL_DRIVER",
            is_pymysql,
            "Driver mysql+pymysql configurado."
            if is_pymysql
            else "Use mysql+pymysql para manter contrato SQLAlchemy do SISGES.",
        )
    )

    username = url.username or ""
    checks.append(
        _check(
            "MYSQL_USER_PRESENT",
            bool(username),
            "Usuario definido na URL." if username else "URL MySQL sem usuario.",
        )
    )
    checks.append(
        _check(
            "MYSQL_USER_NOT_ROOT",
            username.lower() not in FORBIDDEN_USERS,
            "Usuario nao privilegiado configurado."
            if username.lower() not in FORBIDDEN_USERS
            else f"Usuario proibido para SISGES: {username}.",
        )
    )

    expected_users = {
        "app": APP_USERS,
        "migration": MIGRATION_USERS,
        "backup": BACKUP_USERS,
    }.get(purpose, APP_USERS | MIGRATION_USERS | BACKUP_USERS)
    checks.append(
        _check(
            "MYSQL_USER_PURPOSE_MATCH",
            username in expected_users,
            f"Usuario compativel com finalidade {purpose}."
            if username in expected_users
            else f"Usuario esperado para {purpose}: {', '.join(sorted(expected_users))}.",
        )
    )

    checks.append(
        _check(
            "MYSQL_PASSWORD_PRESENT",
            url.password not in {None, ""},
            "Senha presente na URL." if url.password not in {None, ""} else "URL MySQL sem senha.",
        )
    )
    checks.append(
        _check(
            "MYSQL_DATABASE_PRESENT",
            bool(url.database),
            "Database definido." if url.database else "URL MySQL sem database.",
        )
    )

    charset_value = url.query.get("charset", "")
    charset = str(charset_value).lower()
    checks.append(
        _check(
            "MYSQL_CHARSET_UTF8MB4",
            charset == "utf8mb4",
            "Charset utf8mb4 configurado."
            if charset == "utf8mb4"
            else "Configure charset=utf8mb4 na URL.",
        )
    )

    if url.host in {None, "", "0.0.0.0"}:
        warnings.append(
            _check(
                "MYSQL_HOST_REVIEW",
                False,
                "Host ausente ou 0.0.0.0; valide exposicao de rede antes da homologacao.",
            )
        )
    if url.host not in {"127.0.0.1", "localhost"}:
        warnings.append(
            _check(
                "MYSQL_REMOTE_HOST_REVIEW",
                False,
                "Host MySQL remoto detectado; exigir TLS, firewall e credencial minima.",
            )
        )

    return GateResult(
        ok=all(item["ok"] for item in checks),
        checks=checks,
        warnings=warnings,
        safe_url=_safe_url(database_url),
    )


def run_gate(
    database_url: str,
    *,
    purpose: str,
    connect: bool,
) -> dict:
    gate = validate_mysql_database_url(database_url, purpose=purpose).to_dict()
    if connect:
        gate["connection"] = check_connection(database_url)
        gate["ok"] = bool(gate["ok"] and gate["connection"].get("ok"))
    return gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate defensivo de configuracao MySQL do SISGES.",
    )
    parser.add_argument(
        "--url",
        default=settings.database_url,
        help="Database URL. Se omitido, usa SISGES_DATABASE_URL.",
    )
    parser.add_argument(
        "--purpose",
        choices=["app", "migration", "backup"],
        default="app",
        help="Finalidade da credencial validada.",
    )
    parser.add_argument(
        "--connect",
        action="store_true",
        help="Executa SELECT 1 alem das validacoes estaticas.",
    )
    parser.add_argument("--json", action="store_true", help="Imprime saida em JSON.")
    args = parser.parse_args(argv)

    result = run_gate(args.url, purpose=args.purpose, connect=args.connect)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "OK" if result["ok"] else "ERRO"
        print(f"{status} mysql_gate url={result['safe_url']} purpose={args.purpose}")
        for item in result["checks"]:
            print(f"- {item['code']}: {'OK' if item['ok'] else 'ERRO'} - {item['message']}")
        for item in result["warnings"]:
            print(f"- {item['code']}: WARN - {item['message']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

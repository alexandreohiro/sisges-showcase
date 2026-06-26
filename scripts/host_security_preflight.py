from __future__ import annotations

import argparse
import json
import platform
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from infra.config import settings


SCHEMA_VERSION = "sisges-host-security-preflight-v1"
DEFAULT_NGINX_EXE = Path(r"D:\nginx-1.31.1\nginx-1.31.1\nginx.exe")
DEFAULT_NGINX_PREFIX = Path(r"D:\nginx-1.31.1\nginx-1.31.1")
DEFAULT_PORTS = {
    "nginx": 80,
    "frontend": 3000,
    "backend": 8000,
}


@dataclass(frozen=True)
class CommandProbe:
    command: list[str]
    returncode: int
    stdout_tail: str
    stderr_tail: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "ok": self.ok,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }


def _check(code: str, ok: bool, message: str, severity: str = "error") -> dict[str, Any]:
    return {
        "code": code,
        "ok": ok,
        "severity": severity,
        "message": message,
    }


def _tail(value: str, limit: int = 4000) -> str:
    return value[-limit:]


def _port_open(host: str, port: int, timeout_seconds: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _run_nginx_test(
    *,
    nginx_exe: Path,
    nginx_prefix: Path,
    nginx_conf: Path,
) -> CommandProbe:
    command = [
        str(nginx_exe),
        "-p",
        str(nginx_prefix),
        "-c",
        str(nginx_conf),
        "-t",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandProbe(
        command=command,
        returncode=completed.returncode,
        stdout_tail=_tail(completed.stdout),
        stderr_tail=_tail(completed.stderr),
    )


def build_host_security_preflight(
    *,
    root: Path | None = None,
    nginx_exe: Path = DEFAULT_NGINX_EXE,
    nginx_prefix: Path = DEFAULT_NGINX_PREFIX,
    nginx_conf: Path | None = None,
    check_nginx_syntax: bool = False,
    check_ports: bool = False,
    require_ports: bool = False,
) -> dict[str, Any]:
    root = root or settings.base_dir
    nginx_conf = nginx_conf or root / "ops" / "nginx" / "sisges.conf"
    checks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    checks.append(
        _check(
            "HOST_PLATFORM_WINDOWS",
            platform.system().lower() == "windows",
            "Host Windows detectado."
            if platform.system().lower() == "windows"
            else f"Host nao Windows detectado: {platform.system()}.",
            "warning",
        )
    )
    checks.append(
        _check(
            "PYTHON_VERSION_SUPPORTED",
            sys.version_info >= (3, 11),
            f"Python {platform.python_version()} suportado."
            if sys.version_info >= (3, 11)
            else f"Python {platform.python_version()} abaixo do minimo 3.11.",
        )
    )
    checks.append(
        _check(
            "NGINX_CONF_EXISTS",
            nginx_conf.exists(),
            f"Configuracao Nginx encontrada: {nginx_conf}."
            if nginx_conf.exists()
            else f"Configuracao Nginx ausente: {nginx_conf}.",
        )
    )
    nginx_exe_check = _check(
        "NGINX_EXE_EXISTS",
        nginx_exe.exists(),
        f"Executavel Nginx encontrado: {nginx_exe}."
        if nginx_exe.exists()
        else f"Executavel Nginx ausente: {nginx_exe}.",
        "warning",
    )
    warnings.append(nginx_exe_check) if not nginx_exe_check["ok"] else checks.append(nginx_exe_check)

    nginx_syntax = None
    if check_nginx_syntax:
        if nginx_exe.exists() and nginx_conf.exists():
            nginx_syntax = _run_nginx_test(
                nginx_exe=nginx_exe,
                nginx_prefix=nginx_prefix,
                nginx_conf=nginx_conf,
            ).to_dict()
            checks.append(
                _check(
                    "NGINX_SYNTAX_VALID",
                    bool(nginx_syntax["ok"]),
                    "Sintaxe Nginx validada com sucesso."
                    if nginx_syntax["ok"]
                    else "Falha no nginx -t.",
                )
            )
        else:
            checks.append(
                _check(
                    "NGINX_SYNTAX_VALID",
                    False,
                    "Nao foi possivel validar Nginx sem executavel e configuracao.",
                )
            )

    port_status: dict[str, dict[str, Any]] = {}
    if check_ports:
        for name, port in DEFAULT_PORTS.items():
            is_open = _port_open("127.0.0.1", port)
            port_status[name] = {"port": port, "open": is_open}
            item = _check(
                f"PORT_{name.upper()}_{port}_OPEN",
                is_open,
                f"Porta {port} aberta para {name}."
                if is_open
                else f"Porta {port} nao esta aberta para {name}.",
                "error" if require_ports else "warning",
            )
            if require_ports:
                checks.append(item)
            elif not item["ok"]:
                warnings.append(item)
            else:
                checks.append(item)

    ok = all(item["ok"] for item in checks if item["severity"] == "error")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "ok": ok,
        "host": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
        },
        "nginx": {
            "exe": str(nginx_exe),
            "prefix": str(nginx_prefix),
            "conf": str(nginx_conf),
            "syntax": nginx_syntax,
        },
        "ports": port_status,
        "checks": checks,
        "warnings": warnings,
    }


def write_reports(report: dict[str, Any], output_json: Path | None, output_txt: Path | None) -> None:
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_txt:
        output_txt.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "SISGES HOST SECURITY PREFLIGHT",
            f"Status: {'OK' if report['ok'] else 'ERRO'}",
            f"Host: {report['host']['platform']}",
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
    parser = argparse.ArgumentParser(description="Preflight defensivo do host SISGES.")
    parser.add_argument("--nginx-exe", type=Path, default=DEFAULT_NGINX_EXE)
    parser.add_argument("--nginx-prefix", type=Path, default=DEFAULT_NGINX_PREFIX)
    parser.add_argument("--nginx-conf", type=Path, default=None)
    parser.add_argument("--check-nginx-syntax", action="store_true")
    parser.add_argument("--check-ports", action="store_true")
    parser.add_argument("--require-ports", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-txt", type=Path, default=None)
    args = parser.parse_args(argv)

    report = build_host_security_preflight(
        nginx_exe=args.nginx_exe,
        nginx_prefix=args.nginx_prefix,
        nginx_conf=args.nginx_conf,
        check_nginx_syntax=args.check_nginx_syntax,
        check_ports=args.check_ports,
        require_ports=args.require_ports,
    )
    write_reports(report, args.output_json, args.output_txt)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"SISGES HOST SECURITY PREFLIGHT: {'OK' if report['ok'] else 'ERRO'}")
        print(f"checks={len(report['checks'])} warnings={len(report['warnings'])}")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

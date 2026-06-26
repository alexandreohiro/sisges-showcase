from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi.testclient import TestClient

from apps.web.app import app


HEALTH_ENDPOINTS = ["/health/live", "/health/ready", "/health"]


def check_endpoint(client: TestClient, endpoint: str) -> dict[str, Any]:
    started = perf_counter()
    response = client.get(endpoint)
    elapsed_ms = round((perf_counter() - started) * 1000, 3)
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    payload_status = payload.get("status") if isinstance(payload, dict) else None
    database = payload.get("database") if isinstance(payload, dict) else None
    database_status = database.get("status") if isinstance(database, dict) else None
    ok = response.status_code == 200 and (payload_status in {None, "ok"})
    if endpoint == "/health/ready":
        ok = response.status_code == 200 and payload_status == "ok" and database_status == "ok"
    if endpoint == "/health":
        ok = response.status_code == 200 and payload_status == "ok" and database_status == "ok"

    return {
        "endpoint": endpoint,
        "ok": ok,
        "status_code": response.status_code,
        "elapsed_ms": elapsed_ms,
        "payload_status": payload_status,
        "database_status": database_status,
        "database_latency_ms": database.get("latency_ms") if isinstance(database, dict) else None,
    }


def generate_health_smoke_report(
    *,
    output_json: Path,
    output_txt: Path,
    require_ready: bool = True,
) -> dict[str, Any]:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_txt.parent.mkdir(parents=True, exist_ok=True)

    with TestClient(app) as client:
        checks = [check_endpoint(client, endpoint) for endpoint in HEALTH_ENDPOINTS]

    if require_ready:
        ok = all(check["ok"] for check in checks)
    else:
        ok = next((check["ok"] for check in checks if check["endpoint"] == "/health/live"), False)

    report = {
        "schema_version": "sisges-health-smoke-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "OK" if ok else "FAIL",
        "require_ready": require_ready,
        "checks": checks,
        "failed_endpoints": [check["endpoint"] for check in checks if not check["ok"]],
    }
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_txt.write_text(render_text_report(report), encoding="utf-8")
    return report


def render_text_report(report: dict[str, Any]) -> str:
    lines = [
        "SISGES HEALTH SMOKE",
        f"Gerado em: {report['generated_at']}",
        f"Status: {report['status']}",
        f"Require ready: {report['require_ready']}",
        "",
        "Checks:",
    ]
    for check in report["checks"]:
        lines.append(
            (
                "- {endpoint} | {status} | http={http} | payload={payload} | "
                "db={db} | latency={latency}ms"
            ).format(
                endpoint=check["endpoint"],
                status="OK" if check["ok"] else "FAIL",
                http=check["status_code"],
                payload=check["payload_status"],
                db=check["database_status"] or "-",
                latency=check["elapsed_ms"],
            )
        )
    if report["failed_endpoints"]:
        lines.append("")
        lines.append("Falhas:")
        lines.extend(f"- {endpoint}" for endpoint in report["failed_endpoints"])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Executa smoke local dos endpoints de health do SISGES.")
    parser.add_argument("--output-json", type=Path, default=Path("data/output/sisges_health_smoke.json"))
    parser.add_argument("--output-txt", type=Path, default=Path("data/output/sisges_health_smoke.txt"))
    parser.add_argument("--allow-degraded-ready", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = generate_health_smoke_report(
        output_json=args.output_json,
        output_txt=args.output_txt,
        require_ready=not args.allow_degraded_ready,
    )
    print(render_text_report(report))
    if report["status"] != "OK":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

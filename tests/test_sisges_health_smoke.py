from __future__ import annotations

import json
from pathlib import Path

from scripts.sisges_health_smoke import generate_health_smoke_report, render_text_report


def test_health_smoke_generates_json_and_text(tmp_path: Path):
    output_json = tmp_path / "health.json"
    output_txt = tmp_path / "health.txt"

    report = generate_health_smoke_report(
        output_json=output_json,
        output_txt=output_txt,
        require_ready=True,
    )

    assert report["schema_version"] == "sisges-health-smoke-v1"
    assert report["status"] == "OK"
    assert [check["endpoint"] for check in report["checks"]] == ["/health/live", "/health/ready", "/health"]
    assert output_json.exists()
    assert output_txt.exists()
    parsed = json.loads(output_json.read_text(encoding="utf-8"))
    assert parsed["failed_endpoints"] == []
    text = output_txt.read_text(encoding="utf-8")
    assert "SISGES HEALTH SMOKE" in text
    assert "/health/ready" in text


def test_health_smoke_text_lists_failed_endpoints():
    text = render_text_report(
        {
            "generated_at": "2026-05-26T00:00:00+00:00",
            "status": "FAIL",
            "require_ready": True,
            "failed_endpoints": ["/health/ready"],
            "checks": [
                {
                    "endpoint": "/health/ready",
                    "ok": False,
                    "status_code": 503,
                    "payload_status": "error",
                    "database_status": "error",
                    "elapsed_ms": 2.0,
                }
            ],
        }
    )

    assert "Falhas:" in text
    assert "/health/ready" in text

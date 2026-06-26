from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.operational_overclock_baseline import (
    promote_baseline,
    sha256_file,
    validate_baseline_source,
)
from scripts.operational_overclock_report import DEFAULT_ENDPOINTS


def _metric(value: float = 10.0) -> dict[str, float]:
    return {
        "min": value,
        "avg": value,
        "p50": value,
        "p90": value,
        "p95": value,
        "p99": value,
        "max": value,
    }


def _baseline_report(*, status: str = "OK", endpoints: list[str] | None = None) -> dict:
    return {
        "schema_version": "sisges-operational-overclock-v1",
        "generated_at": "2026-05-26T00:00:00+00:00",
        "status": status,
        "profile_label": "critical",
        "endpoints": [
            {
                "endpoint": endpoint,
                "ok": True,
                "status_codes": [200],
                "response_items": 1,
                "elapsed_ms": _metric(),
                "threshold_ms": 5000.0,
            }
            for endpoint in (endpoints or DEFAULT_ENDPOINTS)
        ],
    }


def test_validate_baseline_source_accepts_critical_profile_report():
    validation = validate_baseline_source(_baseline_report(), profile="critical")

    assert validation["ok"] is True
    assert validation["errors"] == []
    assert validation["endpoints"] == DEFAULT_ENDPOINTS


def test_validate_baseline_source_rejects_failed_report():
    validation = validate_baseline_source(_baseline_report(status="FAIL"), profile="critical")

    assert validation["ok"] is False
    assert "ERR_BASELINE_SOURCE_STATUS_NOT_OK" in validation["errors"]


def test_validate_baseline_source_detects_missing_profile_endpoint():
    validation = validate_baseline_source(_baseline_report(endpoints=DEFAULT_ENDPOINTS[:-1]), profile="critical")

    assert validation["ok"] is False
    assert any(error.startswith("ERR_BASELINE_PROFILE_ENDPOINTS_MISSING") for error in validation["errors"])


def test_promote_baseline_writes_copy_and_manifest(tmp_path: Path):
    source = tmp_path / "timings.json"
    output = tmp_path / "baseline.json"
    manifest_json = tmp_path / "manifest.json"
    manifest_txt = tmp_path / "manifest.txt"
    source.write_text(json.dumps(_baseline_report(), ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = promote_baseline(
        source_json=source,
        output_json=output,
        manifest_json=manifest_json,
        manifest_txt=manifest_txt,
        profile="critical",
        note="baseline inicial",
    )

    assert output.exists()
    assert manifest_json.exists()
    assert manifest_txt.exists()
    assert manifest["validation"]["ok"] is True
    assert manifest["source_sha256"] == sha256_file(source)
    assert manifest["baseline_sha256"] == sha256_file(output)
    assert "baseline inicial" in manifest_txt.read_text(encoding="utf-8")


def test_promote_baseline_rejects_invalid_source_and_writes_failure_manifest(tmp_path: Path):
    source = tmp_path / "timings.json"
    output = tmp_path / "baseline.json"
    manifest_json = tmp_path / "manifest.json"
    manifest_txt = tmp_path / "manifest.txt"
    source.write_text(json.dumps(_baseline_report(status="FAIL"), ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="ERR_BASELINE_SOURCE_STATUS_NOT_OK"):
        promote_baseline(
            source_json=source,
            output_json=output,
            manifest_json=manifest_json,
            manifest_txt=manifest_txt,
            profile="critical",
        )

    assert not output.exists()
    assert manifest_json.exists()
    assert "ERR_BASELINE_SOURCE_STATUS_NOT_OK" in manifest_txt.read_text(encoding="utf-8")

from __future__ import annotations

import json
from pathlib import Path

from scripts.operational_overclock_report import (
    DEFAULT_ENDPOINTS,
    compare_report_to_baseline,
    generate_report,
    read_endpoints_file,
    read_endpoints_profile,
    resolve_endpoints,
)


def test_operational_overclock_report_generates_json_and_text(tmp_path: Path):
    output_json = tmp_path / "timings.json"
    output_txt = tmp_path / "timings.txt"

    report = generate_report(
        output_json=output_json,
        output_txt=output_txt,
        endpoints=[
            "/tarefas?limit=12",
            "/tarefas/resumo",
            "/gestao-pessoal?view_scope=efetivo_completo&limit=12",
            "/gestao-pessoal/filtros",
            "/gestao-pessoal/efetivo-om?om=DIV%20PES&limit=40",
        ],
        tarefas_total=12,
        efetivo_total=40,
        repeat=3,
        max_seconds=5.0,
        profile_label="test-small",
    )

    assert report["status"] == "OK"
    assert output_json.exists()
    assert output_txt.exists()

    parsed = json.loads(output_json.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "sisges-operational-overclock-v1"
    assert parsed["seed"]["database"] == "temporary_sqlite"
    assert parsed["profile_label"] == "test-small"
    assert len(parsed["endpoints"]) == 5
    assert all(endpoint["ok"] for endpoint in parsed["endpoints"])
    for endpoint in parsed["endpoints"]:
        assert set(endpoint["elapsed_ms"]) >= {"min", "avg", "p50", "p90", "p95", "p99", "max"}
    text_report = output_txt.read_text(encoding="utf-8")
    assert "RELATORIO DE TIMING OPERACIONAL SISGES" in text_report
    assert "p90=" in text_report
    assert "perfil: test-small" in text_report


def test_operational_overclock_report_reads_endpoint_file(tmp_path: Path):
    endpoints_file = tmp_path / "endpoints.txt"
    endpoints_file.write_text(
        "\n".join(
            [
                "# comentario",
                "/tarefas?limit=5",
                "",
                "/tarefas/resumo",
            ]
        ),
        encoding="utf-8",
    )

    assert read_endpoints_file(endpoints_file) == ["/tarefas?limit=5", "/tarefas/resumo"]


def test_operational_overclock_report_reads_versioned_critical_profile():
    assert read_endpoints_profile("critical") == DEFAULT_ENDPOINTS


def test_operational_overclock_report_prefers_explicit_endpoint_file_over_profile(tmp_path: Path):
    endpoints_file = tmp_path / "endpoints.txt"
    endpoints_file.write_text("/tarefas/resumo\n", encoding="utf-8")

    assert resolve_endpoints(endpoints_file=endpoints_file, profile="critical") == ["/tarefas/resumo"]


def test_operational_overclock_report_compares_against_baseline_ok():
    current = {
        "profile_label": "current",
        "endpoints": [
            {
                "endpoint": "/tarefas",
                "elapsed_ms": {"p95": 12.0},
            }
        ],
    }
    baseline = {
        "profile_label": "baseline",
        "endpoints": [
            {
                "endpoint": "/tarefas",
                "elapsed_ms": {"p95": 10.0},
            }
        ],
    }

    comparison = compare_report_to_baseline(
        current_report=current,
        baseline_report=baseline,
        metric="p95",
        tolerance_percent=25.0,
    )

    assert comparison["status"] == "OK"
    assert comparison["comparisons"][0]["status"] == "OK"
    assert comparison["comparisons"][0]["allowed_ms"] == 12.5


def test_operational_overclock_report_detects_baseline_regression():
    current = {
        "profile_label": "current",
        "endpoints": [
            {
                "endpoint": "/gestao-pessoal",
                "elapsed_ms": {"p95": 170.0},
            }
        ],
    }
    baseline = {
        "profile_label": "baseline",
        "endpoints": [
            {
                "endpoint": "/gestao-pessoal",
                "elapsed_ms": {"p95": 100.0},
            }
        ],
    }

    comparison = compare_report_to_baseline(
        current_report=current,
        baseline_report=baseline,
        metric="p95",
        tolerance_percent=35.0,
    )

    assert comparison["status"] == "FAIL"
    assert comparison["comparisons"][0]["status"] == "REGRESSION"
    assert comparison["comparisons"][0]["delta_percent"] == 70.0


def test_operational_overclock_report_embeds_baseline_comparison(tmp_path: Path):
    output_json = tmp_path / "timings.json"
    output_txt = tmp_path / "timings.txt"
    baseline = {
        "profile_label": "test-baseline",
        "endpoints": [
            {
                "endpoint": "/tarefas/resumo",
                "elapsed_ms": {"p95": 5000.0},
            }
        ],
    }

    report = generate_report(
        output_json=output_json,
        output_txt=output_txt,
        endpoints=["/tarefas/resumo"],
        tarefas_total=8,
        efetivo_total=8,
        repeat=1,
        max_seconds=5.0,
        profile_label="test-current",
        baseline_report=baseline,
        baseline_metric="p95",
        regression_tolerance_percent=10.0,
    )

    assert report["status"] == "OK"
    assert report["baseline_comparison"]["status"] == "OK"
    text_report = output_txt.read_text(encoding="utf-8")
    assert "Comparacao com baseline" in text_report
    assert "perfil baseline: test-baseline" in text_report

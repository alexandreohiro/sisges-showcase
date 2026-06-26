from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.operational_overclock_report import read_endpoints_profile


REQUIRED_METRICS = {"min", "avg", "p50", "p90", "p95", "p99", "max"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_baseline_source(report: dict[str, Any], *, profile: str | None = "critical") -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    endpoints = report.get("endpoints")

    if report.get("schema_version") != "sisges-operational-overclock-v1":
        errors.append("ERR_BASELINE_SCHEMA_INVALID")
    if report.get("status") != "OK":
        errors.append("ERR_BASELINE_SOURCE_STATUS_NOT_OK")
    if not isinstance(endpoints, list) or not endpoints:
        errors.append("ERR_BASELINE_ENDPOINTS_MISSING")
        endpoints = []

    endpoint_names: list[str] = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            errors.append("ERR_BASELINE_ENDPOINT_INVALID")
            continue
        endpoint_name = str(endpoint.get("endpoint") or "")
        endpoint_names.append(endpoint_name)
        if endpoint.get("ok") is not True:
            errors.append(f"ERR_BASELINE_ENDPOINT_NOT_OK:{endpoint_name}")
        elapsed = endpoint.get("elapsed_ms")
        if not isinstance(elapsed, dict):
            errors.append(f"ERR_BASELINE_ENDPOINT_METRICS_MISSING:{endpoint_name}")
            continue
        missing_metrics = sorted(REQUIRED_METRICS - set(elapsed))
        if missing_metrics:
            errors.append(f"ERR_BASELINE_ENDPOINT_METRICS_INCOMPLETE:{endpoint_name}:{','.join(missing_metrics)}")

    expected_endpoints = read_endpoints_profile(profile) if profile else None
    if expected_endpoints is not None:
        expected_set = set(expected_endpoints)
        actual_set = set(endpoint_names)
        missing = sorted(expected_set - actual_set)
        unexpected = sorted(actual_set - expected_set)
        if missing:
            errors.append(f"ERR_BASELINE_PROFILE_ENDPOINTS_MISSING:{','.join(missing)}")
        if unexpected:
            warnings.append(f"WARN_BASELINE_PROFILE_ENDPOINTS_EXTRA:{','.join(unexpected)}")
        if endpoint_names != expected_endpoints and not missing and not unexpected:
            warnings.append("WARN_BASELINE_PROFILE_ENDPOINT_ORDER_DIFFERENT")

    return {
        "ok": not errors,
        "profile": profile,
        "errors": errors,
        "warnings": warnings,
        "endpoints_count": len(endpoint_names),
        "endpoints": endpoint_names,
    }


def build_manifest(
    *,
    source_json: Path,
    output_json: Path,
    validation: dict[str, Any],
    source_sha256: str,
    baseline_sha256: str,
    note: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": "sisges-overclock-baseline-manifest-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_json": str(source_json.resolve()),
        "output_json": str(output_json.resolve()),
        "source_sha256": source_sha256,
        "baseline_sha256": baseline_sha256,
        "profile": validation["profile"],
        "endpoints_count": validation["endpoints_count"],
        "validation": validation,
        "note": note,
    }


def render_manifest_text(manifest: dict[str, Any]) -> str:
    validation = manifest["validation"]
    lines = [
        "SISGES OVERCLOCK BASELINE",
        f"Gerado em: {manifest['generated_at']}",
        f"Status: {'OK' if validation['ok'] else 'FAIL'}",
        f"Perfil: {manifest['profile']}",
        f"Endpoints: {manifest['endpoints_count']}",
        f"Source SHA-256: {manifest['source_sha256']}",
        f"Baseline SHA-256: {manifest['baseline_sha256']}",
        f"Source: {manifest['source_json']}",
        f"Output: {manifest['output_json']}",
        f"Nota: {manifest['note'] or '-'}",
        "",
        "Erros:",
    ]
    lines.extend(f"- {error}" for error in validation["errors"])
    if not validation["errors"]:
        lines.append("- nenhum")
    lines.append("")
    lines.append("Warnings:")
    lines.extend(f"- {warning}" for warning in validation["warnings"])
    if not validation["warnings"]:
        lines.append("- nenhum")
    return "\n".join(lines) + "\n"


def promote_baseline(
    *,
    source_json: Path,
    output_json: Path,
    manifest_json: Path,
    manifest_txt: Path,
    profile: str | None = "critical",
    note: str | None = None,
) -> dict[str, Any]:
    source_json = source_json.resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    manifest_json.parent.mkdir(parents=True, exist_ok=True)
    manifest_txt.parent.mkdir(parents=True, exist_ok=True)

    report = load_report(source_json)
    validation = validate_baseline_source(report, profile=profile)
    if not validation["ok"]:
        baseline_sha256 = ""
        source_sha256 = sha256_file(source_json)
        manifest = build_manifest(
            source_json=source_json,
            output_json=output_json,
            validation=validation,
            source_sha256=source_sha256,
            baseline_sha256=baseline_sha256,
            note=note,
        )
        manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest_txt.write_text(render_manifest_text(manifest), encoding="utf-8")
        raise ValueError(";".join(validation["errors"]))

    shutil.copyfile(source_json, output_json)
    source_sha256 = sha256_file(source_json)
    baseline_sha256 = sha256_file(output_json)
    manifest = build_manifest(
        source_json=source_json,
        output_json=output_json,
        validation=validation,
        source_sha256=source_sha256,
        baseline_sha256=baseline_sha256,
        note=note,
    )
    manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_txt.write_text(render_manifest_text(manifest), encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promove ou valida baseline local de overclock do SISGES.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    promote = subparsers.add_parser("promote", help="Valida um relatorio de timing e promove para baseline local.")
    promote.add_argument("--source", type=Path, required=True)
    promote.add_argument("--output-json", type=Path, default=Path("data/output/operational_overclock_baseline.json"))
    promote.add_argument(
        "--manifest-json",
        type=Path,
        default=Path("data/output/operational_overclock_baseline_manifest.json"),
    )
    promote.add_argument(
        "--manifest-txt",
        type=Path,
        default=Path("data/output/operational_overclock_baseline_manifest.txt"),
    )
    promote.add_argument("--profile", default="critical")
    promote.add_argument("--note", default=None)

    validate = subparsers.add_parser("validate", help="Valida se um JSON pode ser usado como baseline.")
    validate.add_argument("--baseline", type=Path, required=True)
    validate.add_argument("--profile", default="critical")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "promote":
        manifest = promote_baseline(
            source_json=args.source,
            output_json=args.output_json,
            manifest_json=args.manifest_json,
            manifest_txt=args.manifest_txt,
            profile=args.profile,
            note=args.note,
        )
        print(render_manifest_text(manifest))
        return

    report = load_report(args.baseline)
    validation = validate_baseline_source(report, profile=args.profile)
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    if not validation["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

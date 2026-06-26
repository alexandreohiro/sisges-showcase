from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_PROFILE = Path("ops/ux_ui/critical_pages.json")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_profile(profile: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    pages = profile.get("pages")

    if profile.get("schema_version") != "sisges-ux-ui-overclock-profile-v1":
        errors.append("ERR_UX_PROFILE_SCHEMA_INVALID")
    if not isinstance(profile.get("base_url"), str) or not profile["base_url"].startswith(("http://", "https://")):
        errors.append("ERR_UX_PROFILE_BASE_URL_INVALID")
    if not isinstance(profile.get("max_page_load_ms"), int | float) or profile["max_page_load_ms"] <= 0:
        errors.append("ERR_UX_PROFILE_MAX_LOAD_INVALID")
    if not isinstance(pages, list) or not pages:
        errors.append("ERR_UX_PROFILE_PAGES_MISSING")
        pages = []

    seen_paths: set[str] = set()
    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            errors.append(f"ERR_UX_PROFILE_PAGE_INVALID:{index}")
            continue
        path = page.get("path")
        label = page.get("label")
        expected_text = page.get("expected_text")
        if not isinstance(path, str) or not path.startswith("/"):
            errors.append(f"ERR_UX_PROFILE_PAGE_PATH_INVALID:{index}")
        elif path in seen_paths:
            errors.append(f"ERR_UX_PROFILE_PAGE_DUPLICATED:{path}")
        else:
            seen_paths.add(path)
        if not isinstance(label, str) or not label.strip():
            errors.append(f"ERR_UX_PROFILE_PAGE_LABEL_MISSING:{path or index}")
        if not isinstance(expected_text, str) or not expected_text.strip():
            warnings.append(f"WARN_UX_PROFILE_EXPECTED_TEXT_MISSING:{path or index}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "pages_count": len(pages),
        "paths": sorted(seen_paths),
    }


def validate_report(report: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    pages = report.get("pages")
    profile_paths = {page["path"] for page in profile.get("pages", []) if isinstance(page, dict) and "path" in page}
    max_page_load_ms = profile.get("max_page_load_ms")
    max_load = float(max_page_load_ms) if isinstance(max_page_load_ms, int | float) else None

    if report.get("schema_version") != "sisges-ux-ui-overclock-report-v1":
        errors.append("ERR_UX_REPORT_SCHEMA_INVALID")
    if report.get("status") != "OK":
        errors.append("ERR_UX_REPORT_STATUS_NOT_OK")
    if not isinstance(pages, list) or not pages:
        errors.append("ERR_UX_REPORT_PAGES_MISSING")
        pages = []

    seen_paths: set[str] = set()
    for page in pages:
        if not isinstance(page, dict):
            errors.append("ERR_UX_REPORT_PAGE_INVALID")
            continue
        path = page.get("path")
        seen_paths.add(str(path))
        if page.get("ok") is not True:
            errors.append(f"ERR_UX_REPORT_PAGE_NOT_OK:{path}")
        if page.get("expected_text_found") is not True:
            errors.append(f"ERR_UX_REPORT_EXPECTED_TEXT_MISSING:{path}")
        loaded_ms = page.get("loaded_ms")
        if loaded_ms is None:
            errors.append(f"ERR_UX_REPORT_LOAD_TIME_MISSING:{path}")
        elif max_load is not None and isinstance(loaded_ms, int | float) and float(loaded_ms) > max_load:
            errors.append(f"ERR_UX_REPORT_PAGE_SLOW:{path}:{loaded_ms}ms>{max_load:g}ms")

        console_errors = page.get("console_errors", 0)
        if isinstance(console_errors, int | float) and console_errors > 0:
            errors.append(f"ERR_UX_REPORT_CONSOLE_ERRORS:{path}:{int(console_errors)}")

    missing_paths = sorted(profile_paths - seen_paths)
    if missing_paths:
        errors.append(f"ERR_UX_REPORT_PROFILE_PAGES_MISSING:{','.join(missing_paths)}")
    extra_paths = sorted(seen_paths - profile_paths)
    if extra_paths:
        warnings.append(f"WARN_UX_REPORT_EXTRA_PAGES:{','.join(extra_paths)}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "pages_count": len(pages),
    }


def render_validation_text(validation: dict[str, Any], *, title: str) -> str:
    lines = [
        title,
        f"Status: {'OK' if validation['ok'] else 'FAIL'}",
        f"Pages: {validation.get('pages_count', 0)}",
        "",
        "Errors:",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida perfil ou relatorio UX/UI overclock do SISGES.")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--output-txt", type=Path, default=Path("data/output/ux_ui_overclock_validation.txt"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = load_json(args.profile)
    validation = validate_profile(profile)
    title = "SISGES UX/UI OVERCLOCK PROFILE"
    if validation["ok"] and args.report:
        report = load_json(args.report)
        validation = validate_report(report, profile)
        title = "SISGES UX/UI OVERCLOCK REPORT"
    args.output_txt.parent.mkdir(parents=True, exist_ok=True)
    text = render_validation_text(validation, title=title)
    args.output_txt.write_text(text, encoding="utf-8")
    print(text)
    if not validation["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

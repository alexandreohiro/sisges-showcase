from __future__ import annotations

from scripts.ux_ui_overclock_validate import validate_profile, validate_report


def _profile() -> dict:
    return {
        "schema_version": "sisges-ux-ui-overclock-profile-v1",
        "base_url": "http://127.0.0.1:3000",
        "max_page_load_ms": 8000,
        "pages": [
            {
                "path": "/ops-center",
                "label": "Ops Center",
                "requires_auth": True,
                "expected_text": "Ops Center",
            },
            {
                "path": "/tarefas",
                "label": "Tarefas",
                "requires_auth": True,
                "expected_text": "Tarefas",
            },
        ],
    }


def test_validate_ux_ui_profile_accepts_critical_pages():
    validation = validate_profile(_profile())

    assert validation["ok"] is True
    assert validation["pages_count"] == 2
    assert validation["errors"] == []


def test_validate_ux_ui_profile_rejects_duplicated_path():
    profile = _profile()
    profile["pages"].append(profile["pages"][0].copy())

    validation = validate_profile(profile)

    assert validation["ok"] is False
    assert "ERR_UX_PROFILE_PAGE_DUPLICATED:/ops-center" in validation["errors"]


def test_validate_ux_ui_report_accepts_ok_pages():
    report = {
        "schema_version": "sisges-ux-ui-overclock-report-v1",
        "status": "OK",
        "pages": [
            {
                "path": "/ops-center",
                "ok": True,
                "expected_text_found": True,
                "loaded_ms": 1200,
            },
            {
                "path": "/tarefas",
                "ok": True,
                "expected_text_found": True,
                "loaded_ms": 900,
            },
        ],
    }

    validation = validate_report(report, _profile())

    assert validation["ok"] is True
    assert validation["errors"] == []


def test_validate_ux_ui_report_rejects_missing_expected_text():
    report = {
        "schema_version": "sisges-ux-ui-overclock-report-v1",
        "status": "OK",
        "pages": [
            {
                "path": "/ops-center",
                "ok": True,
                "expected_text_found": False,
                "loaded_ms": 1200,
            },
            {
                "path": "/tarefas",
                "ok": True,
                "expected_text_found": True,
                "loaded_ms": 900,
            },
        ],
    }

    validation = validate_report(report, _profile())

    assert validation["ok"] is False
    assert "ERR_UX_REPORT_EXPECTED_TEXT_MISSING:/ops-center" in validation["errors"]


def test_validate_ux_ui_report_rejects_slow_page():
    report = {
        "schema_version": "sisges-ux-ui-overclock-report-v1",
        "status": "OK",
        "pages": [
            {
                "path": "/ops-center",
                "ok": True,
                "expected_text_found": True,
                "loaded_ms": 9001,
            },
            {
                "path": "/tarefas",
                "ok": True,
                "expected_text_found": True,
                "loaded_ms": 900,
            },
        ],
    }

    validation = validate_report(report, _profile())

    assert validation["ok"] is False
    assert "ERR_UX_REPORT_PAGE_SLOW:/ops-center:9001ms>8000ms" in validation["errors"]


def test_validate_ux_ui_report_rejects_console_errors():
    report = {
        "schema_version": "sisges-ux-ui-overclock-report-v1",
        "status": "OK",
        "pages": [
            {
                "path": "/ops-center",
                "ok": True,
                "expected_text_found": True,
                "loaded_ms": 1200,
                "console_errors": 2,
            },
            {
                "path": "/tarefas",
                "ok": True,
                "expected_text_found": True,
                "loaded_ms": 900,
                "console_errors": 0,
            },
        ],
    }

    validation = validate_report(report, _profile())

    assert validation["ok"] is False
    assert "ERR_UX_REPORT_CONSOLE_ERRORS:/ops-center:2" in validation["errors"]

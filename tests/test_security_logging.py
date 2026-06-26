from __future__ import annotations

import json
import logging

from infra.logging.security import (
    SECURITY_EVENT_SCHEMA_VERSION,
    SECURITY_LOGGER_NAME,
    log_security_event,
)
from infra.logging.setup import JsonFormatter


def test_log_security_event_emits_structured_security_fields(caplog) -> None:
    caplog.set_level(logging.WARNING, logger=SECURITY_LOGGER_NAME)

    log_security_event(
        event_type="UPLOAD_REJECTED",
        event_code="UPLOAD_MAGIC_INVALIDO",
        upload_filename="ficha.pdf",
        path="/compilador/documentos/compile",
    )

    record = next(item for item in caplog.records if item.name == SECURITY_LOGGER_NAME)
    assert record.security_event is True
    assert record.security_event_schema == SECURITY_EVENT_SCHEMA_VERSION
    assert record.event_category == "security"
    assert record.event_type == "UPLOAD_REJECTED"
    assert record.event_code == "UPLOAD_MAGIC_INVALIDO"
    assert record.upload_filename == "ficha.pdf"
    assert record.path == "/compilador/documentos/compile"


def test_json_formatter_preserves_security_event_contract() -> None:
    record = logging.LogRecord(
        name=SECURITY_LOGGER_NAME,
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="CSRF_VALIDATION_FAILED",
        args=(),
        exc_info=None,
    )
    record.security_event = True
    record.security_event_schema = SECURITY_EVENT_SCHEMA_VERSION
    record.event_category = "security"
    record.event_type = "CSRF_VALIDATION_FAILED"
    record.event_code = "CSRF_TOKEN_INVALID"
    record.path = "/tarefas"
    record.method = "POST"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["logger"] == SECURITY_LOGGER_NAME
    assert payload["message"] == "CSRF_VALIDATION_FAILED"
    assert payload["security_event"] is True
    assert payload["security_event_schema"] == "sisges-security-event-v1"
    assert payload["event_category"] == "security"
    assert payload["event_type"] == "CSRF_VALIDATION_FAILED"
    assert payload["event_code"] == "CSRF_TOKEN_INVALID"
    assert payload["path"] == "/tarefas"
    assert payload["method"] == "POST"

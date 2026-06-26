from __future__ import annotations

import logging
from typing import Any


SECURITY_LOGGER_NAME = "sisges.security"
SECURITY_EVENT_SCHEMA_VERSION = "sisges-security-event-v1"


def log_security_event(
    *,
    event_type: str,
    event_code: str,
    severity: str = "warning",
    **metadata: Any,
) -> None:
    logger = logging.getLogger(SECURITY_LOGGER_NAME)
    payload = {
        "security_event": True,
        "security_event_schema": SECURITY_EVENT_SCHEMA_VERSION,
        "event_category": "security",
        "event_type": event_type,
        "event_code": event_code,
        **metadata,
    }
    log_method = logger.error if severity.lower() == "error" else logger.warning
    log_method(event_type, extra=payload)

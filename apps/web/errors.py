from __future__ import annotations

from fastapi import HTTPException


def http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    )


def not_found(code: str, message: str) -> HTTPException:
    return http_error(404, code, message)


def bad_request(code: str, message: str) -> HTTPException:
    return http_error(400, code, message)

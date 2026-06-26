from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from infra.config import settings
from infra.logging.security import log_security_event


CSRF_EXEMPT_PATHS = {
    "/auth/login",
    "/auth/logout",
    "/auth/csrf",
    "/health",
    "/health/live",
    "/health/ready",
}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str | None = None) -> str:
    csrf_token = token or generate_csrf_token()
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=settings.session_max_age_seconds,
        expires=settings.session_max_age_seconds,
        httponly=False,
        samesite=settings.session_cookie_samesite,
        secure=settings.session_cookie_secure,
        path=settings.session_cookie_path,
    )
    return csrf_token


def delete_csrf_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path=settings.session_cookie_path,
        samesite=settings.session_cookie_samesite,
        secure=settings.session_cookie_secure,
        httponly=False,
    )


class CsrfProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not settings.csrf_enabled:
            return await call_next(request)
        if request.method.upper() in SAFE_METHODS:
            return await call_next(request)
        if request.url.path in CSRF_EXEMPT_PATHS:
            return await call_next(request)
        if not request.cookies.get(settings.session_cookie_name):
            return await call_next(request)

        cookie_token = request.cookies.get(settings.csrf_cookie_name)
        header_token = request.headers.get(settings.csrf_header_name)
        if not cookie_token or not header_token:
            return _csrf_error(
                request,
                "CSRF_TOKEN_MISSING",
                "Token CSRF ausente.",
                csrf_cookie_present=bool(cookie_token),
                csrf_header_present=bool(header_token),
            )
        if not secrets.compare_digest(cookie_token, header_token):
            return _csrf_error(
                request,
                "CSRF_TOKEN_INVALID",
                "Token CSRF invalido.",
                csrf_cookie_present=True,
                csrf_header_present=True,
            )

        return await call_next(request)


def _csrf_error(request: Request, code: str, message: str, **metadata) -> JSONResponse:
    log_security_event(
        event_type="CSRF_VALIDATION_FAILED",
        event_code=code,
        client_ip=request.client.host if request.client else None,
        method=request.method,
        path=request.url.path,
        session_cookie_present=bool(request.cookies.get(settings.session_cookie_name)),
        **metadata,
    )
    return JSONResponse(
        status_code=403,
        content={
            "detail": {
                "code": code,
                "message": message,
            },
        },
    )

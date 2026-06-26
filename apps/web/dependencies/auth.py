from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException

from infra.config import settings
from infra.persistence.db import get_db
from modules.auth.application.services import AuthError, AuthService


def auth_http_exception(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    )


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
    db=Depends(get_db),
):
    if not session_token:
        raise auth_http_exception(401, "AUTH_NOT_AUTHENTICATED", "Nao autenticado.")

    try:
        return AuthService(db).me_from_token(session_token)
    except AuthError as exc:
        raise auth_http_exception(401, exc.code, exc.message) from exc


def require_permission(permission: str):
    def checker(user=Depends(get_current_user)):
        if permission not in user["permissions"] and not user["is_dev"]:
            raise auth_http_exception(403, "AUTH_FORBIDDEN", "Sem permissao.")
        return user

    return checker


def require_dev_mode(user=Depends(get_current_user)):
    if not user["is_dev"]:
        raise auth_http_exception(
            403,
            "AUTH_DEV_MODE_REQUIRED",
            "Acao permitida apenas para usuario em modo dev.",
        )
    return user

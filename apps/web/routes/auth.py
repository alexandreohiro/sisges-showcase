from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from apps.web.dependencies.auth import auth_http_exception, get_current_user
from apps.web.middleware.csrf import delete_csrf_cookie, set_csrf_cookie
from infra.config import settings
from infra.persistence.db import get_db
from modules.auth.application.services import AuthError, AuthService


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginInput(BaseModel):
    username: str
    password: str


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age_seconds,
        expires=settings.session_max_age_seconds,
        httponly=True,
        samesite=settings.session_cookie_samesite,
        secure=settings.session_cookie_secure,
        path=settings.session_cookie_path,
    )


def _delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path=settings.session_cookie_path,
        samesite=settings.session_cookie_samesite,
        secure=settings.session_cookie_secure,
        httponly=True,
    )


@router.post("/login")
def login(payload: LoginInput, response: Response, db=Depends(get_db)):
    try:
        token, user = AuthService(db).login(payload.username, payload.password)
    except AuthError as exc:
        raise auth_http_exception(401, exc.code, exc.message) from exc

    _set_session_cookie(response, token)
    csrf_token = set_csrf_cookie(response)
    return {"ok": True, "user": user, "csrf_token": csrf_token}


@router.post("/logout")
def logout(response: Response):
    _delete_session_cookie(response)
    delete_csrf_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {"user": user}


@router.get("/csrf")
def csrf(response: Response):
    token = set_csrf_cookie(response)
    return {"csrf_token": token}

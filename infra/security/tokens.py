from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from infra.config import settings


SALT = "sisges-auth"


class SessionTokenError(ValueError):
    pass


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key)


def create_session_token(payload: dict) -> str:
    return _serializer().dumps(payload, salt=SALT)


def read_session_token(
    token: str,
    max_age: int | None = None,
) -> dict:
    try:
        data = _serializer().loads(
            token,
            salt=SALT,
            max_age=max_age or settings.session_max_age_seconds,
        )
    except SignatureExpired as exc:
        raise SessionTokenError("Sessao expirada.") from exc
    except BadSignature as exc:
        raise SessionTokenError("Sessao invalida.") from exc

    if not isinstance(data, dict):
        raise SessionTokenError("Sessao invalida.")
    return data

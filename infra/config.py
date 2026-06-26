from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


VALID_ENVIRONMENTS = {"dev", "test", "prod"}
LOCAL_DEV_SECRET_KEY = "dev-only-change-this-now"
LOCAL_DEV_VAULT_KEY = "dev-only-vault-key-change-this-now"
MIN_PROD_SECRET_LENGTH = 32
MIN_PROD_VAULT_KEY_LENGTH = 32
VALID_SAMESITE_VALUES = {"lax", "strict", "none"}


def _bool_from_env(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "sim", "on"}


def _int_from_env(name: str, *, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} deve ser um inteiro.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} deve ser maior que zero.")
    return value


def _default_database_url(environment: str, base_dir: Path) -> str:
    db_name = "sisges_test.db" if environment == "test" else "sisges.db"
    return f"sqlite:///{(base_dir / 'data' / db_name).as_posix()}"


def _resolve_sqlite_path(database_url: str, base_dir: Path) -> Path | None:
    if database_url == "sqlite:///:memory:":
        return None
    if not database_url.startswith("sqlite:///"):
        return None

    raw_path = database_url.removeprefix("sqlite:///")
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return base_dir / path


@dataclass(frozen=True)
class AppSettings:
    environment: str
    base_dir: Path
    debug: bool
    database_url: str
    database_path: Path | None
    database_echo: bool
    database_pool_size: int
    database_max_overflow: int
    database_pool_recycle_seconds: int
    database_pool_pre_ping: bool
    secret_key: str
    vault_key: str
    session_cookie_name: str
    session_cookie_secure: bool
    session_cookie_samesite: str
    session_cookie_path: str
    session_max_age_seconds: int
    csrf_enabled: bool
    csrf_cookie_name: str
    csrf_header_name: str
    log_level: str
    log_format: str
    workspace_retention_hours: int

    @property
    def is_dev(self) -> bool:
        return self.environment == "dev"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def is_prod(self) -> bool:
        return self.environment == "prod"


def load_settings() -> AppSettings:
    base_dir = Path(__file__).resolve().parents[1]
    environment = os.getenv("SISGES_ENV", "dev").strip().lower()
    if environment not in VALID_ENVIRONMENTS:
        raise RuntimeError(
            "SISGES_ENV invalido. Use um destes valores: dev, test, prod."
        )

    database_url = os.getenv("SISGES_DATABASE_URL")
    if not database_url:
        if environment == "prod":
            raise RuntimeError("SISGES_DATABASE_URL e obrigatorio em SISGES_ENV=prod.")
        database_url = _default_database_url(environment, base_dir)

    secret_key = os.getenv("SISGES_SECRET_KEY") or LOCAL_DEV_SECRET_KEY
    if environment == "prod":
        if secret_key == LOCAL_DEV_SECRET_KEY or len(secret_key) < MIN_PROD_SECRET_LENGTH:
            raise RuntimeError(
                "SISGES_SECRET_KEY e obrigatorio em prod e deve ter pelo menos "
                f"{MIN_PROD_SECRET_LENGTH} caracteres."
            )

    vault_key = os.getenv("SISGES_VAULT_KEY") or LOCAL_DEV_VAULT_KEY
    if environment == "prod":
        if vault_key == LOCAL_DEV_VAULT_KEY or len(vault_key) < MIN_PROD_VAULT_KEY_LENGTH:
            raise RuntimeError(
                "SISGES_VAULT_KEY e obrigatorio em prod e deve ter pelo menos "
                f"{MIN_PROD_VAULT_KEY_LENGTH} caracteres."
            )
    if environment == "prod" and vault_key == secret_key:
        raise RuntimeError(
            "SISGES_VAULT_KEY deve ser diferente de SISGES_SECRET_KEY em prod."
        )

    default_cookie_samesite = "strict" if environment == "prod" else "lax"
    session_cookie_samesite = os.getenv(
        "SISGES_SESSION_COOKIE_SAMESITE",
        default_cookie_samesite,
    ).lower()
    if session_cookie_samesite not in VALID_SAMESITE_VALUES:
        raise RuntimeError("SISGES_SESSION_COOKIE_SAMESITE deve ser lax, strict ou none.")

    session_cookie_secure = _bool_from_env(
        "SISGES_SESSION_COOKIE_SECURE",
        default=environment == "prod",
    )
    if environment == "prod" and not session_cookie_secure:
        raise RuntimeError("SISGES_SESSION_COOKIE_SECURE=true e obrigatorio em prod.")
    if environment == "prod" and session_cookie_samesite != "strict":
        raise RuntimeError("SISGES_SESSION_COOKIE_SAMESITE=strict e obrigatorio em prod.")
    if session_cookie_samesite == "none" and not session_cookie_secure:
        raise RuntimeError("SISGES_SESSION_COOKIE_SAMESITE=none exige cookie secure.")

    return AppSettings(
        environment=environment,
        base_dir=base_dir,
        debug=_bool_from_env("SISGES_DEBUG", default=environment != "prod"),
        database_url=database_url,
        database_path=_resolve_sqlite_path(database_url, base_dir),
        database_echo=_bool_from_env("SISGES_DATABASE_ECHO", default=False),
        database_pool_size=_int_from_env("SISGES_DATABASE_POOL_SIZE", default=5),
        database_max_overflow=_int_from_env("SISGES_DATABASE_MAX_OVERFLOW", default=10),
        database_pool_recycle_seconds=_int_from_env(
            "SISGES_DATABASE_POOL_RECYCLE_SECONDS",
            default=1800,
        ),
        database_pool_pre_ping=_bool_from_env("SISGES_DATABASE_POOL_PRE_PING", default=True),
        secret_key=secret_key,
        vault_key=vault_key,
        session_cookie_name=os.getenv("SISGES_SESSION_COOKIE_NAME", "session_token"),
        session_cookie_secure=session_cookie_secure,
        session_cookie_samesite=session_cookie_samesite,
        session_cookie_path=os.getenv("SISGES_SESSION_COOKIE_PATH", "/"),
        session_max_age_seconds=_int_from_env(
            "SISGES_SESSION_MAX_AGE_SECONDS",
            default=60 * 60 * 12,
        ),
        csrf_enabled=_bool_from_env("SISGES_CSRF_ENABLED", default=environment == "prod"),
        csrf_cookie_name=os.getenv("SISGES_CSRF_COOKIE_NAME", "csrf_token"),
        csrf_header_name=os.getenv("SISGES_CSRF_HEADER_NAME", "X-CSRF-Token"),
        log_level=os.getenv("SISGES_LOG_LEVEL", "INFO").upper(),
        log_format=os.getenv("SISGES_LOG_FORMAT", "json").lower(),
        workspace_retention_hours=_int_from_env(
            "SISGES_WORKSPACE_RETENTION_HOURS",
            default=24,
        ),
    )


settings = load_settings()

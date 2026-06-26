import pytest

from infra.config import load_settings


def test_prod_environment_requires_database_url(monkeypatch):
    monkeypatch.setenv("SISGES_ENV", "prod")
    monkeypatch.delenv("SISGES_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="SISGES_DATABASE_URL"):
        load_settings()


def test_test_environment_uses_separate_default_database(monkeypatch):
    monkeypatch.setenv("SISGES_ENV", "test")
    monkeypatch.delenv("SISGES_DATABASE_URL", raising=False)

    settings = load_settings()

    assert settings.environment == "test"
    assert settings.database_url.endswith("/data/sisges_test.db")
    assert settings.database_pool_size == 5
    assert settings.database_pool_pre_ping is True


def test_database_pool_settings_from_env(monkeypatch):
    monkeypatch.setenv("SISGES_ENV", "test")
    monkeypatch.setenv("SISGES_DATABASE_POOL_SIZE", "7")
    monkeypatch.setenv("SISGES_DATABASE_MAX_OVERFLOW", "3")
    monkeypatch.setenv("SISGES_DATABASE_POOL_RECYCLE_SECONDS", "900")
    monkeypatch.setenv("SISGES_DATABASE_POOL_PRE_PING", "false")
    monkeypatch.setenv("SISGES_DATABASE_ECHO", "true")

    settings = load_settings()

    assert settings.database_pool_size == 7
    assert settings.database_max_overflow == 3
    assert settings.database_pool_recycle_seconds == 900
    assert settings.database_pool_pre_ping is False
    assert settings.database_echo is True


def test_prod_environment_requires_strong_secret(monkeypatch):
    monkeypatch.setenv("SISGES_ENV", "prod")
    monkeypatch.setenv("SISGES_DATABASE_URL", "postgresql://sisges:secret@localhost/sisges")
    monkeypatch.delenv("SISGES_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SISGES_SECRET_KEY"):
        load_settings()


def test_prod_environment_requires_strong_vault_key(monkeypatch):
    monkeypatch.setenv("SISGES_ENV", "prod")
    monkeypatch.setenv("SISGES_DATABASE_URL", "postgresql://sisges:secret@localhost/sisges")
    monkeypatch.setenv("SISGES_SECRET_KEY", "x" * 32)
    monkeypatch.delenv("SISGES_VAULT_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SISGES_VAULT_KEY"):
        load_settings()


def test_prod_environment_rejects_vault_key_equal_to_secret(monkeypatch):
    monkeypatch.setenv("SISGES_ENV", "prod")
    monkeypatch.setenv("SISGES_DATABASE_URL", "postgresql://sisges:secret@localhost/sisges")
    monkeypatch.setenv("SISGES_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("SISGES_VAULT_KEY", "x" * 32)

    with pytest.raises(RuntimeError, match="SISGES_VAULT_KEY deve ser diferente"):
        load_settings()


def test_prod_environment_defaults_to_secure_cookie(monkeypatch):
    monkeypatch.setenv("SISGES_ENV", "prod")
    monkeypatch.setenv("SISGES_DATABASE_URL", "postgresql://sisges:secret@localhost/sisges")
    monkeypatch.setenv("SISGES_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("SISGES_VAULT_KEY", "y" * 32)

    settings = load_settings()

    assert settings.session_cookie_secure is True
    assert settings.session_cookie_samesite == "strict"
    assert settings.csrf_enabled is True


def test_prod_environment_rejects_insecure_cookie(monkeypatch):
    monkeypatch.setenv("SISGES_ENV", "prod")
    monkeypatch.setenv("SISGES_DATABASE_URL", "postgresql://sisges:secret@localhost/sisges")
    monkeypatch.setenv("SISGES_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("SISGES_VAULT_KEY", "y" * 32)
    monkeypatch.setenv("SISGES_SESSION_COOKIE_SECURE", "false")

    with pytest.raises(RuntimeError, match="SISGES_SESSION_COOKIE_SECURE"):
        load_settings()


def test_prod_environment_requires_strict_samesite(monkeypatch):
    monkeypatch.setenv("SISGES_ENV", "prod")
    monkeypatch.setenv("SISGES_DATABASE_URL", "postgresql://sisges:secret@localhost/sisges")
    monkeypatch.setenv("SISGES_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("SISGES_VAULT_KEY", "y" * 32)
    monkeypatch.setenv("SISGES_SESSION_COOKIE_SAMESITE", "lax")

    with pytest.raises(RuntimeError, match="SISGES_SESSION_COOKIE_SAMESITE"):
        load_settings()

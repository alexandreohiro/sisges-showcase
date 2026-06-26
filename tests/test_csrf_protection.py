from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import infra.persistence.models  # noqa: F401
from apps.web.app import app
from apps.web.middleware import csrf as csrf_middleware
from infra.config import settings
from infra.persistence.db import Base, get_db
from infra.persistence.models import PermissionModel, RoleModel, UserModel
from infra.security.passwords import hash_password


SECURITY_LOGGER = "sisges.security"


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()

    permission = PermissionModel(id="compilador.run", key="compilador.run")
    role = RoleModel(id="csrf-role", name="csrf-role", permissions=[permission])
    user = UserModel(
        id="csrf-user",
        username="csrfuser",
        display_name="CSRF User",
        email="csrf@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        is_dev=False,
        roles=[role],
    )
    db.add_all([permission, role, user])
    db.commit()

    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    csrf_settings = replace(settings, csrf_enabled=True)
    monkeypatch.setattr(csrf_middleware, "settings", csrf_settings)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_login_sets_csrf_cookie_and_token(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"username": "csrfuser", "password": "senha-forte-123"},
    )

    assert response.status_code == 200
    assert response.json()["csrf_token"]
    assert "csrf_token=" in response.headers["set-cookie"]


def test_mutating_authenticated_request_requires_csrf_header(
    client: TestClient,
    caplog,
) -> None:
    caplog.set_level(logging.WARNING, logger=SECURITY_LOGGER)
    login = client.post(
        "/auth/login",
        json={"username": "csrfuser", "password": "senha-forte-123"},
    )
    assert login.status_code == 200

    response = client.post("/compilador/test-compile", json={"text": "teste"})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CSRF_TOKEN_MISSING"
    record = next(
        item
        for item in caplog.records
        if getattr(item, "event_type", None) == "CSRF_VALIDATION_FAILED"
    )
    assert record.security_event is True
    assert record.event_code == "CSRF_TOKEN_MISSING"
    assert record.path == "/compilador/test-compile"
    assert record.session_cookie_present is True
    assert record.csrf_header_present is False


def test_mutating_authenticated_request_accepts_matching_csrf_header(
    client: TestClient,
) -> None:
    login = client.post(
        "/auth/login",
        json={"username": "csrfuser", "password": "senha-forte-123"},
    )
    assert login.status_code == 200
    csrf_token = login.json()["csrf_token"]

    response = client.post(
        "/compilador/test-compile",
        json={"text": "teste"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200


def test_mutating_authenticated_request_rejects_mismatched_csrf_header(
    client: TestClient,
    caplog,
) -> None:
    caplog.set_level(logging.WARNING, logger=SECURITY_LOGGER)
    login = client.post(
        "/auth/login",
        json={"username": "csrfuser", "password": "senha-forte-123"},
    )
    assert login.status_code == 200

    response = client.post(
        "/compilador/test-compile",
        json={"text": "teste"},
        headers={"X-CSRF-Token": "token-errado"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CSRF_TOKEN_INVALID"
    record = next(
        item
        for item in caplog.records
        if getattr(item, "event_type", None) == "CSRF_VALIDATION_FAILED"
        and getattr(item, "event_code", None) == "CSRF_TOKEN_INVALID"
    )
    assert record.csrf_cookie_present is True
    assert record.csrf_header_present is True

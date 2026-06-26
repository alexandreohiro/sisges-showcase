from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import infra.persistence.models  # noqa: F401
from apps.web.app import app
from infra.persistence.db import Base, get_db
from infra.persistence.models import PermissionModel, RoleModel, UserModel
from infra.security.passwords import hash_password


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

    permission = PermissionModel(id="dashboard.view", key="dashboard.view")
    role = RoleModel(id="admin", name="admin", permissions=[permission])
    user = UserModel(
        id="user-1",
        username="admin",
        display_name="Admin",
        email="admin@sisges.local",
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
def client(db_session: Session) -> Iterator[TestClient]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_login_me_and_logout_flow(client: TestClient):
    login_response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "senha-forte-123"},
    )

    assert login_response.status_code == 200
    assert login_response.json()["user"]["username"] == "admin"
    set_cookie = login_response.headers["set-cookie"]
    assert "session_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie

    me_response = client.get("/auth/me")

    assert me_response.status_code == 200
    assert me_response.json()["user"]["permissions"] == ["dashboard.view"]

    logout_response = client.post("/auth/logout")

    assert logout_response.status_code == 200
    assert "session_token=" in logout_response.headers["set-cookie"]
    assert "Max-Age=0" in logout_response.headers["set-cookie"]


def test_login_rejects_invalid_credentials(client: TestClient):
    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "senha-errada"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == {
        "code": "AUTH_INVALID_CREDENTIALS",
        "message": "Credenciais invalidas.",
    }


def test_me_rejects_inactive_user_session(client: TestClient, db_session: Session):
    login_response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "senha-forte-123"},
    )
    assert login_response.status_code == 200

    user = db_session.get(UserModel, "user-1")
    assert user is not None
    user.is_active = False
    db_session.commit()

    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_INVALID_SESSION"

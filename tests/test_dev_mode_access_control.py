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
from infra.persistence.models import FeatureFlagModel, PermissionModel, RoleModel, UserModel
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

    users_manage = PermissionModel(id="users.manage", key="users.manage")
    permissions_manage = PermissionModel(id="permissions.manage", key="permissions.manage")
    dev_mode_access = PermissionModel(id="dev_mode.access", key="dev_mode.access")

    admin_role = RoleModel(
        id="admin",
        name="admin",
        permissions=[users_manage, permissions_manage, dev_mode_access],
    )
    dev_role = RoleModel(
        id="dev",
        name="dev",
        permissions=[users_manage, permissions_manage, dev_mode_access],
    )
    operador_role = RoleModel(id="operador", name="operador", permissions=[])

    admin = UserModel(
        id="admin-user",
        username="admin",
        display_name="Admin",
        email="admin@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        is_dev=False,
        roles=[admin_role],
    )
    dev = UserModel(
        id="dev-user",
        username="dev",
        display_name="Dev",
        email="dev@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        is_dev=True,
        roles=[dev_role],
    )
    operador = UserModel(
        id="operador-user",
        username="operador",
        display_name="Operador",
        email="operador@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        is_dev=False,
        roles=[operador_role],
    )

    db.add_all(
        [
            users_manage,
            permissions_manage,
            dev_mode_access,
            admin_role,
            dev_role,
            operador_role,
            admin,
            dev,
            operador,
            FeatureFlagModel(key="page.configuracoes.modo_dev", enabled=True, dev_only=True),
        ],
    )
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


def _login(client: TestClient, username: str) -> None:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": "senha-forte-123"},
    )
    assert response.status_code == 200, response.text


def test_admin_cannot_create_dev_access(client: TestClient) -> None:
    _login(client, "admin")

    response = client.post(
        "/users",
        json={
            "username": "new-dev",
            "display_name": "New Dev",
            "email": "new-dev@sisges.com",
            "password": "senha-forte-123",
            "role_names": ["operador"],
            "is_dev": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "USER_CREATE_FAILED"


def test_admin_cannot_assign_dev_role_or_toggle_dev_flag(
    client: TestClient,
    db_session: Session,
) -> None:
    _login(client, "admin")

    role_response = client.patch("/users/operador-user", json={"role_names": ["dev"]})
    flag_response = client.patch("/users/operador-user", json={"is_dev": True})

    assert role_response.status_code == 400
    assert flag_response.status_code == 400
    operador = db_session.get(UserModel, "operador-user")
    assert operador is not None
    assert operador.is_dev is False
    assert [role.name for role in operador.roles] == ["operador"]


def test_admin_cannot_modify_or_deactivate_existing_dev(client: TestClient) -> None:
    _login(client, "admin")

    update_response = client.patch("/users/dev-user", json={"display_name": "Dev Editado"})
    reset_response = client.post(
        "/users/dev-user/reset-password",
        json={"new_password": "outra-senha-forte"},
    )
    delete_response = client.delete("/users/dev-user")

    assert update_response.status_code == 400
    assert reset_response.status_code == 400
    assert delete_response.status_code == 400


def test_admin_with_dev_permission_cannot_access_feature_flags(client: TestClient) -> None:
    _login(client, "admin")

    list_response = client.get("/feature-flags")
    patch_response = client.patch(
        "/feature-flags/page.configuracoes.modo_dev",
        json={"enabled": False, "dev_only": True},
    )

    assert list_response.status_code == 403
    assert list_response.json()["detail"]["code"] == "AUTH_DEV_MODE_REQUIRED"
    assert patch_response.status_code == 403
    assert patch_response.json()["detail"]["code"] == "AUTH_DEV_MODE_REQUIRED"


def test_admin_roles_response_hides_dev_role(client: TestClient) -> None:
    _login(client, "admin")

    response = client.get("/roles")

    assert response.status_code == 200
    role_names = {item["name"] for item in response.json()["items"]}
    assert "operador" in role_names
    assert "dev" not in role_names


def test_dev_can_manage_dev_surface(client: TestClient) -> None:
    _login(client, "dev")

    roles_response = client.get("/roles")
    flags_response = client.get("/feature-flags")
    create_response = client.post(
        "/users",
        json={
            "username": "new-dev",
            "display_name": "New Dev",
            "email": "new-dev@sisges.com",
            "password": "senha-forte-123",
            "role_names": ["dev"],
            "is_dev": True,
        },
    )

    assert roles_response.status_code == 200
    assert "dev" in {item["name"] for item in roles_response.json()["items"]}
    assert flags_response.status_code == 200
    assert create_response.status_code == 200, create_response.text
    assert create_response.json()["item"]["is_dev"] is True

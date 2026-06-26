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

    permissions = [
        PermissionModel(id="mod.quadro.view", key="mod.quadro.view"),
        PermissionModel(id="mod.quadro.edit", key="mod.quadro.edit"),
    ]
    role = RoleModel(id="quadro", name="quadro", permissions=permissions)
    admin = UserModel(
        id="admin-user",
        username="admin",
        display_name="Admin",
        email="admin@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        roles=[role],
    )
    other = UserModel(
        id="other-user",
        username="outro",
        display_name="Outro",
        email="outro@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        roles=[role],
    )
    db.add_all([*permissions, role, admin, other])
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
    test_client = TestClient(app)
    login = test_client.post("/auth/login", json={"username": "admin", "password": "senha-forte-123"})
    assert login.status_code == 200
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_quadro_board_crud_persists_content(client: TestClient):
    response = client.post(
        "/quadro/boards",
        json={
            "titulo": "Plantao DIV PES",
            "descricao": "Mapa rapido da secretaria",
            "visibility": "private",
            "content_json": {
                "schema_version": "quadro.sisges.v1",
                "elements": [{"id": "1", "tool": "text", "text": "SECRETARIA"}],
                "viewport": {"zoom": 1, "pan": {"x": 0, "y": 0}},
            },
        },
    )

    assert response.status_code == 200, response.text
    board = response.json()
    assert board["id"]
    assert board["content_json"]["elements"][0]["text"] == "SECRETARIA"

    response = client.patch(
        f"/quadro/boards/{board['id']}",
        json={
            "titulo": "Plantao atualizado",
            "visibility": "shared",
            "content_json": {
                "schema_version": "quadro.sisges.v1",
                "elements": [{"id": "2", "tool": "rectangle"}],
            },
        },
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["titulo"] == "Plantao atualizado"
    assert updated["visibility"] == "shared"
    assert updated["content_json"]["elements"][0]["tool"] == "rectangle"

    response = client.get("/quadro/boards?query=Plantao")

    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()] == [board["id"]]


def test_quadro_private_board_is_not_visible_to_other_user(client: TestClient, db_session: Session):
    response = client.post("/quadro/boards", json={"titulo": "Privado"})
    assert response.status_code == 200, response.text
    board_id = response.json()["id"]

    other_client = TestClient(app)
    login = other_client.post("/auth/login", json={"username": "outro", "password": "senha-forte-123"})
    assert login.status_code == 200

    response = other_client.get(f"/quadro/boards/{board_id}")

    assert response.status_code == 404


def test_quadro_shared_board_is_visible_but_not_editable_to_other_user(client: TestClient):
    response = client.post("/quadro/boards", json={"titulo": "Compartilhado", "visibility": "shared"})
    assert response.status_code == 200, response.text
    board_id = response.json()["id"]

    other_client = TestClient(app)
    login = other_client.post("/auth/login", json={"username": "outro", "password": "senha-forte-123"})
    assert login.status_code == 200

    response = other_client.get(f"/quadro/boards/{board_id}")
    assert response.status_code == 200, response.text

    response = other_client.patch(f"/quadro/boards/{board_id}", json={"titulo": "Nao pode"})
    assert response.status_code == 404


def test_quadro_can_delete_owned_board(client: TestClient):
    response = client.post("/quadro/boards", json={"titulo": "Para excluir"})
    assert response.status_code == 200, response.text
    board_id = response.json()["id"]

    response = client.delete(f"/quadro/boards/{board_id}")

    assert response.status_code == 200, response.text
    assert response.json()["deleted_id"] == board_id
    assert client.get(f"/quadro/boards/{board_id}").status_code == 404


def test_quadro_list_can_hide_shared_boards_from_other_users(client: TestClient):
    response = client.post("/quadro/boards", json={"titulo": "Compartilhado geral", "visibility": "shared"})
    assert response.status_code == 200, response.text

    other_client = TestClient(app)
    login = other_client.post("/auth/login", json={"username": "outro", "password": "senha-forte-123"})
    assert login.status_code == 200

    response = other_client.get("/quadro/boards?include_shared=false")

    assert response.status_code == 200, response.text
    assert response.json() == []


def test_quadro_requires_permission(db_session: Session):
    no_permission = RoleModel(id="sem-quadro", name="sem-quadro", permissions=[])
    user = UserModel(
        id="no-quadro-user",
        username="semquadro",
        display_name="Sem Quadro",
        email="semquadro@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        roles=[no_permission],
    )
    db_session.add_all([no_permission, user])
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    local_client = TestClient(app)
    try:
        login = local_client.post("/auth/login", json={"username": "semquadro", "password": "senha-forte-123"})
        assert login.status_code == 200

        response = local_client.get("/quadro/boards")

        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()

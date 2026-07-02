from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import infra.persistence.models  # noqa: F401
from apps.web.app import app
from infra.persistence.db import Base, get_db
from infra.persistence.models import CredentialAuditModel, MilitarModel, PermissionModel, RoleModel, UserModel
from infra.security.passwords import hash_password
from modules.acessos.application.credential_vault import decrypt_payload
from modules.gestao_pessoal.application.hierarchy_config import (
    GestaoPessoalHierarchyConfig,
    load_hierarchy_config,
    save_hierarchy_config,
)


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
        PermissionModel(id="users.manage", key="users.manage"),
        PermissionModel(id="permissions.manage", key="permissions.manage"),
        PermissionModel(id="mod.gestao_pessoal.view", key="mod.gestao_pessoal.view"),
        PermissionModel(id="mod.gestao_pessoal.create", key="mod.gestao_pessoal.create"),
        PermissionModel(id="mod.gestao_pessoal.edit", key="mod.gestao_pessoal.edit"),
        PermissionModel(id="mod.gestao_pessoal.delete", key="mod.gestao_pessoal.delete"),
    ]
    role = RoleModel(id="admin", name="admin", permissions=permissions)
    admin = UserModel(
        id="admin-user",
        username="admin",
        display_name="Admin",
        email="admin@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        is_dev=True,
        roles=[role],
    )
    operator = UserModel(
        id="operator-user",
        username="operador",
        display_name="Operador",
        email="operador@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        roles=[role],
    )
    militar = MilitarModel(nome_completo="MILITAR CRUD", identidade="1234567890", ativo=True)
    db.add_all([*permissions, role, admin, operator, militar])
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


def test_user_delete_is_logical_and_user_can_be_reactivated(client: TestClient, db_session: Session):
    response = client.delete("/users/operator-user")

    assert response.status_code == 200, response.text
    payload = response.json()["item"]
    assert payload["is_active"] is False
    assert db_session.get(UserModel, "operator-user").is_active is False

    response = client.patch("/users/operator-user/reactivate")

    assert response.status_code == 200, response.text
    payload = response.json()["item"]
    assert payload["is_active"] is True
    assert db_session.get(UserModel, "operator-user").is_active is True


def test_user_cannot_deactivate_own_session(client: TestClient, db_session: Session):
    response = client.delete("/users/admin-user")

    assert response.status_code == 400
    assert db_session.get(UserModel, "admin-user").is_active is True


def test_militar_delete_is_logical_and_can_be_reactivated(client: TestClient, db_session: Session):
    militar = db_session.query(MilitarModel).filter(MilitarModel.identidade == "1234567890").one()

    response = client.delete(f"/gestao-pessoal/{militar.id}")

    assert response.status_code == 200, response.text
    assert response.json()["ativo"] is False
    assert db_session.get(MilitarModel, militar.id).ativo is False

    response = client.patch(f"/gestao-pessoal/{militar.id}/reactivate")

    assert response.status_code == 200, response.text
    assert response.json()["ativo"] is True
    assert db_session.get(MilitarModel, militar.id).ativo is True


def test_militar_permanent_delete_removes_record_from_database(
    client: TestClient,
    db_session: Session,
):
    militar = MilitarModel(nome_completo="MILITAR HARD DELETE", identidade="9998887776", ativo=True)
    db_session.add(militar)
    db_session.commit()

    response = client.delete(f"/gestao-pessoal/{militar.id}/permanent")
    assert response.status_code == 400
    assert db_session.get(MilitarModel, militar.id) is not None

    response = client.delete(f"/gestao-pessoal/{militar.id}/permanent?confirm_permanent=true")

    assert response.status_code == 200, response.text
    deleted = response.json()["deleted"]
    assert deleted["identidade"] == "9998887776"
    archive_path = Path(deleted["archive_path"])
    try:
        assert archive_path.exists()
        assert deleted["archive_sha256"]
        with zipfile.ZipFile(archive_path) as archive:
            assert set(archive.namelist()) >= {"manifest.json", "snapshot.json", "RESTORE_NOTES.txt"}
            snapshot = archive.read("snapshot.json").decode("utf-8")
            assert "MILITAR HARD DELETE" in snapshot
    finally:
        archive_path.unlink(missing_ok=True)
    assert db_session.get(MilitarModel, militar.id) is None


def test_militar_list_can_return_only_inactive(client: TestClient, db_session: Session):
    db_session.add(
        MilitarModel(nome_completo="MILITAR INATIVO", identidade="5554443332", ativo=False),
    )
    db_session.commit()

    response = client.get("/gestao-pessoal?only_inactive=true&view_scope=efetivo_completo")

    assert response.status_code == 200, response.text
    items = response.json()
    assert items
    assert all(item["ativo"] is False for item in items)


def test_militar_list_uses_military_hierarchy_with_command_precedence(
    client: TestClient,
    db_session: Session,
):
    db_session.add_all(
        [
            MilitarModel(
                nome_completo="NILTON CORONEL SILVA",
                nome_guerra="NILTON",
                posto_graduacao="Cel",
                identidade="1111111111",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="ROGERIO CORONEL LIMA",
                nome_guerra="ROGERIO",
                posto_graduacao="Cel",
                identidade="2222222222",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="ALFA MAJOR",
                nome_guerra="ALFA",
                posto_graduacao="Maj",
                identidade="3333333333",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="BRAVO TENENTE CORONEL",
                nome_guerra="BRAVO",
                posto_graduacao="Ten Cel",
                identidade="4444444444",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="CHARLIE SARGENTO",
                nome_guerra="CHARLIE",
                posto_graduacao="1º Sgt",
                identidade="6666666666",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="DELTA SUBTENENTE",
                nome_guerra="DELTA",
                posto_graduacao="STen",
                identidade="6666666667",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="ECHO SEGUNDO SARGENTO",
                nome_guerra="ECHO",
                posto_graduacao="2º Sgt",
                identidade="6666666668",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="FOXTROT TERCEIRO SARGENTO",
                nome_guerra="FOXTROT",
                posto_graduacao="3º Sgt",
                identidade="6666666669",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="GOLF CABO",
                nome_guerra="GOLF",
                posto_graduacao="Cb",
                identidade="6666666670",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="HOTEL SOLDADO",
                nome_guerra="HOTEL",
                posto_graduacao="Sd",
                identidade="6666666671",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="INDIA RECRUTA",
                nome_guerra="INDIA",
                posto_graduacao="Rcr",
                identidade="6666666672",
                ativo=True,
            ),
        ],
    )
    db_session.commit()

    response = client.get("/gestao-pessoal?limit=20&view_scope=efetivo_completo")

    assert response.status_code == 200, response.text
    names = [item["nome_guerra"] for item in response.json()]
    assert names[:5] == ["NILTON", "ROGERIO", "BRAVO", "ALFA", "DELTA"]
    assert names.index("DELTA") < names.index("CHARLIE")
    assert names.index("CHARLIE") < names.index("ECHO")
    assert names.index("ECHO") < names.index("FOXTROT")
    assert names.index("FOXTROT") < names.index("GOLF")
    assert names.index("GOLF") < names.index("HOTEL")
    assert names.index("HOTEL") < names.index("INDIA")


def test_militar_default_list_is_scoped_to_user_section_and_division(
    client: TestClient,
    db_session: Session,
):
    db_session.add_all(
        [
            MilitarModel(
                nome_completo="Admin",
                nome_guerra="ADMIN",
                posto_graduacao="Maj",
                identidade="7777777777",
                secao="1 Secao",
                om="Divisao Alfa",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="MESMA SECAO",
                nome_guerra="MESMA",
                posto_graduacao="3 Sgt",
                identidade="7777777778",
                secao="1 Secao",
                om="Divisao Alfa",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="OUTRA SECAO",
                nome_guerra="OUTRA",
                posto_graduacao="3 Sgt",
                identidade="7777777779",
                secao="2 Secao",
                om="Divisao Alfa",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="OUTRA DIVISAO",
                nome_guerra="DIVISAO",
                posto_graduacao="3 Sgt",
                identidade="7777777780",
                secao="1 Secao",
                om="Divisao Bravo",
                ativo=True,
            ),
        ],
    )
    db_session.commit()

    response = client.get("/gestao-pessoal")

    assert response.status_code == 200, response.text
    names = {item["nome_guerra"] for item in response.json()}
    assert {"ADMIN", "MESMA"} <= names
    assert "OUTRA" not in names
    assert "DIVISAO" not in names


def test_militar_default_list_can_use_user_operational_profile(
    client: TestClient,
    db_session: Session,
):
    admin = db_session.get(UserModel, "admin-user")
    admin.divisao = "DIV PES"
    admin.secao = "SECRETARIA"
    db_session.add(admin)
    db_session.add_all(
        [
            MilitarModel(
                nome_completo="SECRETARIA UM",
                nome_guerra="SECR1",
                posto_graduacao="3 Sgt",
                identidade="7000000001",
                secao="SECRETARIA",
                om="DIV PES",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="OUTRA SECAO PERFIL",
                nome_guerra="OUTSEC",
                posto_graduacao="3 Sgt",
                identidade="7000000002",
                secao="PROTOCOLO",
                om="DIV PES",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="OUTRA DIVISAO PERFIL",
                nome_guerra="OUTDIV",
                posto_graduacao="3 Sgt",
                identidade="7000000003",
                secao="SECRETARIA",
                om="DIV ADM",
                ativo=True,
            ),
        ],
    )
    db_session.commit()

    context_response = client.get("/gestao-pessoal/me/contexto-operacional")
    assert context_response.status_code == 200, context_response.text
    context = context_response.json()
    assert context["source"] == "USER_OPERATIONAL_PROFILE"
    assert context["divisao"] == "DIV PES"
    assert context["secao"] == "SECRETARIA"

    response = client.get("/gestao-pessoal")

    assert response.status_code == 200, response.text
    names = {item["nome_guerra"] for item in response.json()}
    assert "SECR1" in names
    assert "OUTSEC" not in names
    assert "OUTDIV" not in names


def test_militar_list_filters_by_rank_section_and_division(
    client: TestClient,
    db_session: Session,
):
    db_session.add_all(
        [
            MilitarModel(
                nome_completo="FILTRO UM",
                nome_guerra="FILTRO1",
                posto_graduacao="Cap",
                identidade="8888888881",
                secao="Fiscalizacao",
                om="Divisao Operacional",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="FILTRO DOIS",
                nome_guerra="FILTRO2",
                posto_graduacao="3 Sgt",
                identidade="8888888882",
                secao="Fiscalizacao",
                om="Divisao Operacional",
                ativo=True,
            ),
            MilitarModel(
                nome_completo="FILTRO TRES",
                nome_guerra="FILTRO3",
                posto_graduacao="Cap",
                identidade="8888888883",
                secao="Arquivo",
                om="Divisao Operacional",
                ativo=True,
            ),
        ],
    )
    db_session.commit()

    response = client.get(
        "/gestao-pessoal?view_scope=efetivo_completo"
        "&posto_graduacao=Cap&secao=Fiscalizacao&divisao=Divisao Operacional",
    )

    assert response.status_code == 200, response.text
    items = response.json()
    assert [item["nome_guerra"] for item in items] == ["FILTRO1"]


def test_gestao_pessoal_filter_options_include_rank_section_and_division(
    client: TestClient,
    db_session: Session,
):
    db_session.add(
        MilitarModel(
            nome_completo="OPCOES FILTRO",
            nome_guerra="OPCOES",
            posto_graduacao="Ten Cel",
            identidade="9999999991",
            secao="Secretaria",
            om="Divisao Administrativa",
            ativo=True,
        ),
    )
    db_session.commit()

    response = client.get("/gestao-pessoal/filtros")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "Ten Cel" in payload["postos_graduacoes"]
    assert "Secretaria" in payload["secoes"]
    assert "Divisao Administrativa" in payload["divisoes"]


def test_gestao_pessoal_hierarchy_config_is_available_to_dev(client: TestClient):
    response = client.get("/gestao-pessoal/hierarquia-config")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["posto_graduacao_order"]["sten"] == 110
    assert payload["posto_graduacao_order"]["1 sgt"] == 120
    assert payload["posto_graduacao_order"]["2 sgt"] == 130
    assert payload["posto_graduacao_order"]["3 sgt"] == 140
    assert payload["posto_graduacao_order"]["cb"] == 150
    assert payload["posto_graduacao_order"]["sd"] == 160
    assert payload["posto_graduacao_order"]["rec"] == 170
    assert payload["posto_graduacao_order"]["rcr"] == 170


def test_hierarchy_config_can_be_saved_and_loaded_from_local_file(tmp_path):
    config_path = tmp_path / "hierarquia.json"
    saved = save_hierarchy_config(
        GestaoPessoalHierarchyConfig(
            posto_graduacao_order={"cb": 10, "sd": 20, "rcr": 30},
            command_precedence={"comandante": 0},
            default_view_scope="efetivo_completo",
            auto_scope_enabled=False,
            division_fields=["secao"],
            unknown_rank=500,
        ),
        path=config_path,
    )

    loaded = load_hierarchy_config(path=config_path)

    assert saved.default_view_scope == "efetivo_completo"
    assert loaded.posto_graduacao_order["rcr"] == 30
    assert loaded.command_precedence["comandante"] == 0
    assert loaded.auto_scope_enabled is False
    assert loaded.division_fields == ["secao"]
    assert loaded.unknown_rank == 500


def test_militar_photo_upload_updates_foto_path(client: TestClient, db_session: Session):
    militar = db_session.query(MilitarModel).filter(MilitarModel.identidade == "1234567890").one()

    response = client.post(
        f"/gestao-pessoal/{militar.id}/foto",
        files={"foto": ("foto.png", _tiny_png(), "image/png")},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["foto_path"].endswith(f"gestao_pessoal/fotos/{militar.id}.png")

    path = Path("data/uploads/gestao_pessoal/fotos") / f"{militar.id}.png"
    try:
        assert path.exists()
    finally:
        path.unlink(missing_ok=True)


def test_user_avatar_upload_updates_avatar_path(client: TestClient):
    response = client.post(
        "/users/operator-user/avatar",
        files={"avatar": ("avatar.png", _tiny_png(), "image/png")},
    )

    assert response.status_code == 200, response.text
    payload = response.json()["item"]
    assert payload["avatar_path"].endswith("users/operator-user.png")

    path = Path("data/uploads/users/operator-user.png")
    try:
        assert path.exists()
    finally:
        path.unlink(missing_ok=True)


def test_user_operational_profile_is_exposed_and_can_be_cleared(
    client: TestClient,
    db_session: Session,
):
    response = client.patch(
        "/users/operator-user",
        json={
            "identidade": "9990000001",
            "posto_graduacao": "3 Sgt",
            "nome_guerra": "ALEXANDRE",
            "telefone": "61 99999-0000",
            "contato": "Ramal 321",
            "divisao": "DIV PES",
            "secao": "SECRETARIA",
        },
    )

    assert response.status_code == 200, response.text
    item = response.json()["item"]
    assert item["identidade"] == "9990000001"
    assert item["divisao"] == "DIV PES"
    assert item["secao"] == "SECRETARIA"
    user = db_session.get(UserModel, "operator-user")
    assert user.nome_guerra == "ALEXANDRE"

    response = client.patch("/users/operator-user", json={"secao": None})

    assert response.status_code == 200, response.text
    assert response.json()["item"]["secao"] is None
    assert db_session.get(UserModel, "operator-user").secao is None


def test_user_credentials_are_audited_in_encrypted_vault(client: TestClient, db_session: Session):
    response = client.post(
        "/users",
        json={
            "username": "vault_user",
            "display_name": "Vault User",
            "email": "vault_user@sisges.com",
            "password": "SenhaForte@123",
            "role_names": ["admin"],
            "is_dev": False,
            "identidade": "0123456789",
            "posto_graduacao": "3 Sgt",
            "nome_guerra": "VAULT",
            "telefone": "61 99999-0000",
            "contato": "Ramal 123",
            "divisao": "DIV PES",
            "secao": "SECRETARIA",
        },
    )

    assert response.status_code == 200, response.text
    item = response.json()["item"]
    user_id = item["id"]
    assert item["divisao"] == "DIV PES"
    assert item["secao"] == "SECRETARIA"

    created_audit = (
        db_session.query(CredentialAuditModel)
        .filter(
            CredentialAuditModel.user_id == user_id,
            CredentialAuditModel.event_type == "USER_CREATED",
        )
        .one()
    )
    assert "vault_user" not in created_audit.encrypted_payload
    created_payload = decrypt_payload(created_audit.encrypted_payload)
    assert created_payload["username"] == "vault_user"
    assert created_payload["identidade"] == "0123456789"
    assert created_payload["divisao"] == "DIV PES"
    assert created_payload["secao"] == "SECRETARIA"
    assert created_payload["password_hash_sha256"]
    assert "SenhaForte@123" not in created_audit.encrypted_payload

    response = client.post(f"/users/{user_id}/reset-password", json={"new_password": "OutraSenha@456"})

    assert response.status_code == 200, response.text
    password_audit = (
        db_session.query(CredentialAuditModel)
        .filter(
            CredentialAuditModel.user_id == user_id,
            CredentialAuditModel.event_type == "PASSWORD_CHANGED",
        )
        .one()
    )
    assert decrypt_payload(password_audit.encrypted_payload)["username"] == "vault_user"
    assert "OutraSenha@456" not in password_audit.encrypted_payload


def _tiny_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
        b"\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
        b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

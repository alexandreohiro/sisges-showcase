from __future__ import annotations

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

    view_permission = PermissionModel(id="documents.view", key="documents.view")
    download_permission = PermissionModel(id="documents.download", key="documents.download")
    role = RoleModel(
        id="documentos",
        name="documentos",
        permissions=[view_permission, download_permission],
    )
    user = UserModel(
        id="docs-user",
        username="docs",
        display_name="Docs",
        email="docs@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        roles=[role],
    )
    db.add_all([view_permission, download_permission, role, user])
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
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_secretaria_dataset_status_requires_auth(client: TestClient) -> None:
    response = client.get("/documents/secretaria-dataset/status")

    assert response.status_code == 401


def test_secretaria_dataset_status_route_returns_compact_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.web.routes.documents.load_secretaria_dataset_status",
        lambda: {
            "available": True,
            "status": "INVENTARIO_DISPONIVEL",
            "message": "ok",
            "inventory": {"total_files": 10},
            "plan": {"go_no_go": {"lan_pilot": "GO_COM_DRY_RUN"}},
            "lots": [{"filename": "importar.csv"}],
        },
    )
    login = client.post("/auth/login", json={"username": "docs", "password": "senha-forte-123"})
    assert login.status_code == 200, login.text

    response = client.get("/documents/secretaria-dataset/status")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["available"] is True
    assert payload["inventory"]["total_files"] == 10
    assert payload["plan"]["go_no_go"]["lan_pilot"] == "GO_COM_DRY_RUN"


def test_secretaria_review_output_download_returns_allowlisted_file(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "fila.csv"
    queue_path.write_text("relative_path,status\nx.pdf,READY\n", encoding="utf-8")
    monkeypatch.setattr(
        "apps.web.routes.documents.resolve_secretaria_review_output_path",
        lambda output_key: queue_path if output_key == "all" else None,
    )
    login = client.post("/auth/login", json={"username": "docs", "password": "senha-forte-123"})
    assert login.status_code == 200, login.text

    response = client.get("/documents/secretaria-dataset/review-outputs/all/download")

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "relative_path,status" in response.text


def test_secretaria_review_output_download_returns_404_when_key_is_unknown(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.web.routes.documents.resolve_secretaria_review_output_path",
        lambda output_key: None,
    )
    login = client.post("/auth/login", json={"username": "docs", "password": "senha-forte-123"})
    assert login.status_code == 200, login.text

    response = client.get("/documents/secretaria-dataset/review-outputs/desconhecido/download")

    assert response.status_code == 404


def test_secretaria_semester_review_output_download_returns_csv(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "2025_2sem.csv"
    queue_path.write_text("relative_path,status\nx.pdf,READY\n", encoding="utf-8")
    monkeypatch.setattr(
        "apps.web.routes.documents.resolve_secretaria_semester_review_output_path",
        lambda period_key: queue_path if period_key == "2025_2sem" else None,
    )
    login = client.post("/auth/login", json={"username": "docs", "password": "senha-forte-123"})
    assert login.status_code == 200, login.text

    response = client.get("/documents/secretaria-dataset/review-semesters/2025_2sem/download")

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "relative_path,status" in response.text


def test_secretaria_semester_review_output_download_returns_404_for_invalid_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.web.routes.documents.resolve_secretaria_semester_review_output_path",
        lambda period_key: None,
    )
    login = client.post("/auth/login", json={"username": "docs", "password": "senha-forte-123"})
    assert login.status_code == 200, login.text

    response = client.get("/documents/secretaria-dataset/review-semesters/SEM_PERIODO/download")

    assert response.status_code == 404


def test_secretaria_lot_output_download_returns_csv(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lot_path = tmp_path / "importar.csv"
    lot_path.write_text("relative_path\nx.pdf\n", encoding="utf-8")
    monkeypatch.setattr(
        "apps.web.routes.documents.resolve_secretaria_lot_output_path",
        lambda lot_name: lot_path if lot_name == "importar" else None,
    )
    login = client.post("/auth/login", json={"username": "docs", "password": "senha-forte-123"})
    assert login.status_code == 200, login.text

    response = client.get("/documents/secretaria-dataset/lots/importar/download")

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "relative_path" in response.text


def test_secretaria_lot_output_download_returns_404_for_unknown_lot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.web.routes.documents.resolve_secretaria_lot_output_path",
        lambda lot_name: None,
    )
    login = client.post("/auth/login", json={"username": "docs", "password": "senha-forte-123"})
    assert login.status_code == 200, login.text

    response = client.get("/documents/secretaria-dataset/lots/desconhecido/download")

    assert response.status_code == 404


def test_secretaria_report_output_download_returns_allowlisted_file(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "inventario_secretaria.txt"
    report_path.write_text("inventario\n", encoding="utf-8")
    monkeypatch.setattr(
        "apps.web.routes.documents.resolve_secretaria_report_output_path",
        lambda report_key: report_path if report_key == "inventario_txt" else None,
    )
    login = client.post("/auth/login", json={"username": "docs", "password": "senha-forte-123"})
    assert login.status_code == 200, login.text

    response = client.get("/documents/secretaria-dataset/reports/inventario_txt/download")

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "inventario" in response.text


def test_secretaria_report_output_download_returns_404_for_unknown_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.web.routes.documents.resolve_secretaria_report_output_path",
        lambda report_key: None,
    )
    login = client.post("/auth/login", json={"username": "docs", "password": "senha-forte-123"})
    assert login.status_code == 200, login.text

    response = client.get("/documents/secretaria-dataset/reports/desconhecido/download")

    assert response.status_code == 404


def test_secretaria_audit_package_download_returns_zip(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.web.routes.documents.build_secretaria_audit_package",
        lambda: b"PK\x03\x04fake-zip",
    )
    login = client.post("/auth/login", json={"username": "docs", "password": "senha-forte-123"})
    assert login.status_code == 200, login.text

    response = client.get("/documents/secretaria-dataset/audit-package/download")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "pacote_auditoria_secretaria.zip" in response.headers["content-disposition"]


def test_secretaria_audit_package_download_returns_404_when_missing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.web.routes.documents.build_secretaria_audit_package",
        lambda: None,
    )
    login = client.post("/auth/login", json={"username": "docs", "password": "senha-forte-123"})
    assert login.status_code == 200, login.text

    response = client.get("/documents/secretaria-dataset/audit-package/download")

    assert response.status_code == 404

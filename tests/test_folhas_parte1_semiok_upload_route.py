from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import apps.web.routes.folhas as folhas_route
import infra.persistence.models  # noqa: F401
from apps.web.app import app
from infra.persistence.db import Base, get_db
from infra.persistence.models import RoleModel, UserModel
from infra.security.passwords import hash_password
from tests.test_complete_folha_semi_ok_parte1 import write_minimal_odt


def _parte1_txt_bytes() -> bytes:
    return (
        "\n".join(
            [
                "CABECALHO DO RELATORIO",
                "JULHO:",
                "INSTALACAO - Concessao",
                "- a 1, BI No 50:",
                "Texto do evento de julho.",
                "AGOSTO:",
                "Sem Alteracao.",
                "SETEMBRO:",
                "Sem Alteracao.",
                "OUTUBRO:",
                "Sem Alteracao.",
                "NOVEMBRO:",
                "Sem Alteracao.",
                "DEZEMBRO:",
                "Sem Alteracao.",
                "2a PARTE",
            ]
        )
        + "\n"
    ).encode("utf-8")


def _login(client: TestClient, username: str = "operador") -> str:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": "senha-forte-123"},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["csrf_token"])


@contextmanager
def _client(tmp_path: Path) -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db: Session = session_factory()
    role = RoleModel(id="operador", name="operador", permissions=[])
    user = UserModel(
        id="operador-user",
        username="operador",
        display_name="Operador",
        email="operador@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        is_dev=False,
        roles=[role],
    )
    db.add_all([role, user])
    db.commit()

    def override_get_db():
        yield db

    output_root = tmp_path / "data" / "output"
    output_root.mkdir(parents=True)
    previous_output_root = folhas_route.DATA_OUTPUT_ROOT
    folhas_route.DATA_OUTPUT_ROOT = output_root
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        folhas_route.DATA_OUTPUT_ROOT = previous_output_root
        app.dependency_overrides.clear()
        db.close()


def test_common_user_can_generate_parte1_from_semi_ok_upload(tmp_path: Path) -> None:
    odt_path = tmp_path / "004 - BRITO o.odt"
    write_minimal_odt(odt_path)

    with _client(tmp_path) as client:
        csrf_token = _login(client)
        response = client.post(
            "/folhas/geracao/semi-ok-parte1/upload",
            data={"semestre": "2"},
            files={
                "odt_semi_pronto": (
                    odt_path.name,
                    odt_path.read_bytes(),
                    "application/vnd.oasis.opendocument.text",
                ),
                "fonte_parte1": (
                    "2025-07-01_2025-12-31_sten_brito.txt",
                    _parte1_txt_bytes(),
                    "text/plain",
                ),
            },
            headers={"X-CSRF-Token": csrf_token},
        )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["X-Sisges-Folhas-Generation-Status"] in {"OK", "OK_WITH_WARNINGS"}
    with zipfile.ZipFile(BytesIO(response.content)) as package:
        names = set(package.namelist())
    assert "manifest.json" in names
    assert "README_GERACAO_PARTE1.txt" in names
    assert any(name.startswith("ODT_FINAL/") and name.endswith(".odt") for name in names)
    assert any(name.startswith("EVIDENCIAS/") and name.endswith("_parte1_limpa.txt") for name in names)
    assert any(name.startswith("EVIDENCIAS/") and name.endswith("_validacao.json") for name in names)
    assert any(name.startswith("EVIDENCIAS/") and name.endswith("_trace.json") for name in names)


def test_parte1_upload_rejects_invalid_source_extension(tmp_path: Path) -> None:
    odt_path = tmp_path / "004 - BRITO o.odt"
    write_minimal_odt(odt_path)

    with _client(tmp_path) as client:
        csrf_token = _login(client)
        response = client.post(
            "/folhas/geracao/semi-ok-parte1/upload",
            data={"semestre": "2"},
            files={
                "odt_semi_pronto": (
                    odt_path.name,
                    odt_path.read_bytes(),
                    "application/vnd.oasis.opendocument.text",
                ),
                "fonte_parte1": ("fonte.docx", b"invalido", "application/octet-stream"),
            },
            headers={"X-CSRF-Token": csrf_token},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "FOLHA_PARTE1_SOURCE_EXTENSION_INVALID"
    assert response.json()["detail"]["message"] == "Fonte da Parte 1 deve ser TXT oficial ou PDF."

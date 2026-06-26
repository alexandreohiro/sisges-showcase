from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import apps.web.routes.documents as documents_route
import apps.web.routes.folhas as folhas_route
import infra.persistence.models  # noqa: F401
from apps.web.app import app
from infra.persistence.db import Base, get_db
from infra.persistence.models import RoleModel, UserModel
from infra.security.passwords import hash_password
from scripts.complete_folha_semi_ok_parte1 import PairItem, ProcessResult


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

    dev_role = RoleModel(id="dev", name="dev", permissions=[])
    admin_role = RoleModel(id="admin", name="admin", permissions=[])
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
    db.add_all([dev_role, admin_role, dev, admin])
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


def login(client: TestClient, username: str) -> str:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": "senha-forte-123"},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["csrf_token"])


def test_dev_can_process_semi_ok_parte1_route(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "entrada"
    input_dir.mkdir()
    output_root = tmp_path / "data" / "output"
    output_root.mkdir(parents=True)
    fake_pair = PairItem(
        key="alexandre",
        odt=input_dir / "003 - ALEXANDRE o.odt",
        pdf=input_dir / "2025-07-01_2025-12-31_sten_alexandre.pdf",
    )

    monkeypatch.setattr(documents_route, "DATA_OUTPUT_ROOT", output_root)
    monkeypatch.setattr(documents_route, "build_pairs", lambda _: ([fake_pair], []))
    monkeypatch.setattr(documents_route, "write_classification", lambda *_: None)
    monkeypatch.setattr(
        documents_route,
        "process_pair",
        lambda *_: ProcessResult(
            key="alexandre",
            status="OK_WITH_WARNINGS",
            source_semi_odt=str(fake_pair.odt),
            source_pdf=str(fake_pair.pdf),
            output_odt=str(output_root / "saida" / "alexandre.odt"),
            inserted_lines=10,
            warnings=["WARN_POSSIBLE_SENSITIVE_EVENT"],
        ),
    )

    csrf_token = login(client, "dev")
    response = client.post(
        "/documents/folhas/semi-ok-parte1/process",
        json={"input_dir": str(input_dir), "output_dir": "saida", "semestre": "2"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "CONCLUIDO"
    assert payload["total_pares"] == 1
    assert payload["ok_with_warnings"] == 1
    assert Path(payload["output_dir"]).is_relative_to(output_root)


def test_admin_cannot_process_semi_ok_parte1_route(
    client: TestClient,
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "entrada"
    input_dir.mkdir()
    csrf_token = login(client, "admin")

    response = client.post(
        "/documents/folhas/semi-ok-parte1/process",
        json={"input_dir": str(input_dir), "output_dir": "saida", "semestre": "2"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTH_DEV_MODE_REQUIRED"


def test_dev_can_process_semi_ok_parte1_from_folhas_route(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "entrada"
    input_dir.mkdir()
    output_root = tmp_path / "data" / "output"
    output_root.mkdir(parents=True)
    fake_pair = PairItem(
        key="alexandre",
        odt=input_dir / "003 - ALEXANDRE o.odt",
        pdf=input_dir / "2025-07-01_2025-12-31_sten_alexandre.pdf",
    )

    monkeypatch.setattr(folhas_route, "DATA_OUTPUT_ROOT", output_root)
    monkeypatch.setattr(folhas_route, "build_pairs", lambda _: ([fake_pair], []))
    monkeypatch.setattr(folhas_route, "write_classification", lambda *_: None)
    monkeypatch.setattr(
        folhas_route,
        "process_pair",
        lambda *_: ProcessResult(
            key="alexandre",
            status="OK_WITH_WARNINGS",
            source_semi_odt=str(fake_pair.odt),
            source_pdf=str(fake_pair.pdf),
            output_odt=str(output_root / "saida" / "alexandre.odt"),
            inserted_lines=10,
            warnings=["WARN_POSSIBLE_SENSITIVE_EVENT"],
        ),
    )

    csrf_token = login(client, "dev")
    response = client.post(
        "/folhas/geracao/semi-ok-parte1/process",
        json={"input_dir": str(input_dir), "output_dir": "saida", "semestre": "2"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "CONCLUIDO"
    assert payload["total_pares"] == 1
    assert payload["ok_with_warnings"] == 1
    assert Path(payload["output_dir"]).is_relative_to(output_root)


def test_dev_can_download_folha_executable_template(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "data" / "output"
    template_dir = output_root / "modelos"
    template_dir.mkdir(parents=True)
    template_path = template_dir / folhas_route.FOLHA_EXECUTABLE_TEMPLATE_FILENAME
    template_path.write_bytes(b"ODT SISGES")
    monkeypatch.setattr(folhas_route, "DATA_OUTPUT_ROOT", output_root)

    login(client, "dev")
    response = client.get("/folhas/geracao/modelo-executavel/download")

    assert response.status_code == 200, response.text
    assert response.content == b"ODT SISGES"
    assert folhas_route.FOLHA_EXECUTABLE_TEMPLATE_FILENAME in response.headers["content-disposition"]


def test_dev_can_check_folha_executable_template_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "data" / "output"
    template_dir = output_root / "modelos"
    template_dir.mkdir(parents=True)
    template_path = template_dir / folhas_route.FOLHA_EXECUTABLE_TEMPLATE_FILENAME
    template_path.write_bytes(b"ODT SISGES")
    monkeypatch.setattr(folhas_route, "DATA_OUTPUT_ROOT", output_root)

    login(client, "dev")
    response = client.get("/folhas/geracao/modelo-executavel/status")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["available"] is True
    assert payload["filename"] == folhas_route.FOLHA_EXECUTABLE_TEMPLATE_FILENAME
    assert payload["sha256"]
    assert payload["size_bytes"] == len(b"ODT SISGES")


def test_dev_can_prepare_folha_executable_template(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "data" / "output"
    output_root.mkdir(parents=True)
    source_odt = tmp_path / "modelo_base.odt"
    source_odt.write_bytes(b"ODT BASE")
    monkeypatch.setattr(folhas_route, "DATA_OUTPUT_ROOT", output_root)

    def fake_build_template(source, output, contract, report):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"ODT SISGES EXECUTAVEL")
        contract.write_text("{}", encoding="utf-8")
        report.write_text("ok\n", encoding="utf-8")
        return SimpleNamespace(
            status="OK",
            source_odt=str(source),
            output_odt=str(output),
            contract_json=str(contract),
            report_txt=str(report),
            flags_content_xml=["[SISGES_PARTE_1]"],
            flags_styles_xml=["[SISGES_NOME]"],
            structural_checks=["OK_REQUIRED_FLAGS_PRESENT"],
            warnings=[],
        )

    monkeypatch.setattr(folhas_route, "build_template", fake_build_template)

    csrf_token = login(client, "dev")
    response = client.post(
        "/folhas/geracao/modelo-executavel/preparar",
        json={"source_odt": str(source_odt)},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "OK"
    assert payload["sha256"]
    assert (output_root / "modelos" / folhas_route.FOLHA_EXECUTABLE_TEMPLATE_FILENAME).exists()


def test_dev_can_prepare_folha_executable_template_from_upload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "data" / "output"
    output_root.mkdir(parents=True)
    monkeypatch.setattr(folhas_route, "DATA_OUTPUT_ROOT", output_root)

    async def fake_save_upload_to_path(upload, target_path, _policy):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(await upload.read())
        return target_path.stat().st_size

    def fake_build_template(source, output, contract, report):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"ODT SISGES EXECUTAVEL")
        contract.write_text("{}", encoding="utf-8")
        report.write_text("ok\n", encoding="utf-8")
        return SimpleNamespace(
            status="OK",
            source_odt=str(source),
            output_odt=str(output),
            contract_json=str(contract),
            report_txt=str(report),
            flags_content_xml=["[SISGES_PARTE_1]"],
            flags_styles_xml=["[SISGES_NOME]"],
            structural_checks=["OK_REQUIRED_FLAGS_PRESENT"],
            warnings=[],
        )

    monkeypatch.setattr(folhas_route, "save_upload_to_path", fake_save_upload_to_path)
    monkeypatch.setattr(folhas_route, "build_template", fake_build_template)

    csrf_token = login(client, "dev")
    response = client.post(
        "/folhas/geracao/modelo-executavel/preparar-upload",
        files={
            "modelo_odt": (
                "modelo_base.odt",
                b"ODT BASE",
                "application/vnd.oasis.opendocument.text",
            )
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "OK"
    assert payload["sha256"]
    assert "modelo_base.odt" in payload["source_odt"]
    assert (output_root / "modelos" / folhas_route.FOLHA_EXECUTABLE_TEMPLATE_FILENAME).exists()


def test_folha_executable_template_status_reports_missing_template(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "data" / "output"
    output_root.mkdir(parents=True)
    monkeypatch.setattr(folhas_route, "DATA_OUTPUT_ROOT", output_root)

    login(client, "dev")
    response = client.get("/folhas/geracao/modelo-executavel/status")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["available"] is False
    assert payload["sha256"] is None


def test_admin_cannot_prepare_folha_executable_template(
    client: TestClient,
    tmp_path: Path,
) -> None:
    source_odt = tmp_path / "modelo_base.odt"
    source_odt.write_bytes(b"ODT BASE")

    csrf_token = login(client, "admin")
    response = client.post(
        "/folhas/geracao/modelo-executavel/preparar",
        json={"source_odt": str(source_odt)},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTH_DEV_MODE_REQUIRED"


def test_admin_cannot_download_folha_executable_template_without_permission(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "data" / "output"
    template_dir = output_root / "modelos"
    template_dir.mkdir(parents=True)
    (template_dir / folhas_route.FOLHA_EXECUTABLE_TEMPLATE_FILENAME).write_bytes(b"ODT SISGES")
    monkeypatch.setattr(folhas_route, "DATA_OUTPUT_ROOT", output_root)

    login(client, "admin")
    response = client.get("/folhas/geracao/modelo-executavel/download")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTH_FORBIDDEN"


def test_output_dir_must_stay_under_data_output(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "entrada"
    input_dir.mkdir()
    output_root = tmp_path / "data" / "output"
    output_root.mkdir(parents=True)
    outside = tmp_path / "fora"
    csrf_token = login(client, "dev")
    monkeypatch.setattr(documents_route, "DATA_OUTPUT_ROOT", output_root)

    response = client.post(
        "/documents/folhas/semi-ok-parte1/process",
        json={"input_dir": str(input_dir), "output_dir": str(outside), "semestre": "2"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Pasta de saida deve ficar dentro de data/output."

from __future__ import annotations

import json
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import infra.persistence.models  # noqa: F401
from apps.web.app import app
from infra.persistence.db import Base, get_db
from infra.persistence.models import DocumentModel, MilitarModel, PermissionModel, RoleModel, UserModel
from infra.security.passwords import hash_password


RAW_CPF = "12345678901"


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

    review_permission = PermissionModel(id="mod.folhas.review", key="mod.folhas.review")
    secretaria_role = RoleModel(id="secretaria", name="secretaria", permissions=[review_permission])
    militar_role = RoleModel(id="militar", name="militar", permissions=[])
    db.add_all(
        [
            review_permission,
            secretaria_role,
            militar_role,
            MilitarModel(
                nome_completo="MILITAR UPDATE DOCUMENTAL",
                nome_guerra="UPDATE",
                posto_graduacao="3 Sgt",
                identidade="9990000001",
                cpf=RAW_CPF,
                ativo=True,
            ),
            UserModel(
                id="secretaria-user",
                username="secretaria",
                display_name="Secretaria",
                email="secretaria@sisges.local",
                password_hash=hash_password("senha-forte-123"),
                is_active=True,
                roles=[secretaria_role],
            ),
            UserModel(
                id="militar-user",
                username="militar",
                display_name="Militar",
                email="militar@sisges.local",
                password_hash=hash_password("senha-forte-123"),
                is_active=True,
                roles=[militar_role],
            ),
        ]
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
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def _login(client: TestClient, username: str) -> None:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": "senha-forte-123"},
    )
    assert response.status_code == 200, response.text


def test_secretaria_registers_document_update_without_persisting_raw_cpf(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    monkeypatch.setenv("SISGES_DOCUMENT_UPDATE_DIR", str(tmp_path))

    _login(client, "secretaria")
    response = client.post(
        "/folhas/documentos/update",
        json={
            "tipo_documento": "folha_alteracao",
            "ano": 2025,
            "semestre": 2,
            "cpf": "123.456.789-01",
            "codom": "000123",
            "observacao": "Atualizacao solicitada pela secretaria.",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "DOC_UPDATE_REGISTERED"
    assert payload["cpf_masked"] == "***.***.***-01"
    assert payload["militar_nome"] == "MILITAR UPDATE DOCUMENTAL"

    document = db_session.get(DocumentModel, payload["document_id"])
    assert document is not None
    assert document.source_module == "folhas.document_update"
    assert document.metadata_json["cpf_masked"] == "***.***.***-01"
    assert RAW_CPF not in json.dumps(document.metadata_json)

    manifest_text = Path(document.metadata_json["manifest_path"]).read_text(encoding="utf-8")
    assert RAW_CPF not in manifest_text
    assert "***.***.***-01" in manifest_text

    history = client.get("/folhas/documentos/updates")
    assert history.status_code == 200, history.text
    history_payload = history.json()
    assert len(history_payload) == 1
    assert history_payload[0]["document_id"] == payload["document_id"]
    assert history_payload[0]["cpf_masked"] == "***.***.***-01"
    assert history_payload[0]["tipo_documento"] == "folha_alteracao"
    assert history_payload[0]["has_attachment"] is False
    assert history_payload[0]["has_manifest"] is True
    assert "manifest_path" not in history_payload[0]
    assert RAW_CPF not in json.dumps(history_payload)

    download = client.get(f"/folhas/documentos/updates/{payload['document_id']}/download")
    assert download.status_code == 404
    assert download.json()["detail"]["code"] == "DOCUMENT_UPDATE_FILE_NOT_FOUND"

    manifest = client.get(f"/folhas/documentos/updates/{payload['document_id']}/manifest")
    assert manifest.status_code == 200, manifest.text

    audit_package = client.get(f"/folhas/documentos/updates/{payload['document_id']}/audit.zip")
    assert audit_package.status_code == 200, audit_package.text
    with ZipFile(BytesIO(audit_package.content)) as archive:
        names = set(archive.namelist())
        assert f"manifesto_update_{payload['document_id']}.json" in names
        assert not any(name.startswith("anexo/") for name in names)


def test_document_update_requires_folhas_review_permission(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    monkeypatch.setenv("SISGES_DOCUMENT_UPDATE_DIR", str(tmp_path))

    _login(client, "militar")
    response = client.post(
        "/folhas/documentos/update",
        json={
            "tipo_documento": "folha_alteracao",
            "ano": 2025,
            "semestre": 2,
            "cpf": RAW_CPF,
            "codom": "000123",
        },
    )

    assert response.status_code == 403

    history = client.get("/folhas/documentos/updates")
    assert history.status_code == 403


def test_document_update_accepts_optional_pdf_upload(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    monkeypatch.setenv("SISGES_DOCUMENT_UPDATE_DIR", str(tmp_path))

    _login(client, "secretaria")
    response = client.post(
        "/folhas/documentos/update-upload",
        data={
            "tipo_documento": "folha_alteracao",
            "ano": "2025",
            "semestre": "2",
            "cpf": "123.456.789-01",
            "codom": "000123",
            "observacao": "Atualizacao documental com anexo.",
        },
        files={"arquivo": ("folha.pdf", b"%PDF-1.4\n%SISGES\n", "application/pdf")},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "DOC_UPDATE_REGISTERED"
    assert payload["uploaded_filename"] == "folha.pdf"
    assert payload["uploaded_sha256"]

    document = db_session.get(DocumentModel, payload["document_id"])
    assert document is not None
    assert document.filename == "folha.pdf"
    assert document.metadata_json["uploaded_file"]["filename"] == "folha.pdf"
    assert document.metadata_json["uploaded_file"]["sha256"] == payload["uploaded_sha256"]
    assert Path(document.output_path).exists()

    manifest_text = Path(document.metadata_json["manifest_path"]).read_text(encoding="utf-8")
    assert RAW_CPF not in manifest_text
    assert "folha.pdf" in manifest_text

    history = client.get("/folhas/documentos/updates")
    assert history.status_code == 200, history.text
    history_payload = history.json()
    assert history_payload[0]["uploaded_filename"] == "folha.pdf"
    assert history_payload[0]["uploaded_sha256"] == payload["uploaded_sha256"]
    assert history_payload[0]["has_attachment"] is True

    download = client.get(f"/folhas/documentos/updates/{payload['document_id']}/download")
    assert download.status_code == 200, download.text
    assert download.content == b"%PDF-1.4\n%SISGES\n"
    assert "folha.pdf" in download.headers["content-disposition"]

    manifest = client.get(f"/folhas/documentos/updates/{payload['document_id']}/manifest")
    assert manifest.status_code == 200, manifest.text
    assert manifest.headers["content-type"].startswith("application/json")
    assert f"manifesto_update_{payload['document_id']}.json" in manifest.headers["content-disposition"]
    manifest_payload = manifest.json()
    assert manifest_payload["cpf_masked"] == "***.***.***-01"
    assert manifest_payload["uploaded_file"]["filename"] == "folha.pdf"
    assert RAW_CPF not in manifest.text

    audit_package = client.get(f"/folhas/documentos/updates/{payload['document_id']}/audit.zip")
    assert audit_package.status_code == 200, audit_package.text
    assert audit_package.headers["content-type"].startswith("application/zip")
    assert f"auditoria_update_{payload['document_id']}.zip" in audit_package.headers["content-disposition"]
    with ZipFile(BytesIO(audit_package.content)) as archive:
        names = set(archive.namelist())
        assert f"manifesto_update_{payload['document_id']}.json" in names
        assert "anexo/folha.pdf" in names
        assert "README_AUDITORIA.txt" in names
        manifest_in_zip = archive.read(f"manifesto_update_{payload['document_id']}.json").decode("utf-8")
        assert RAW_CPF not in manifest_in_zip
        assert "***.***.***-01" in manifest_in_zip


def test_document_update_upload_rejects_invalid_extension(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    monkeypatch.setenv("SISGES_DOCUMENT_UPDATE_DIR", str(tmp_path))

    _login(client, "secretaria")
    response = client.post(
        "/folhas/documentos/update-upload",
        data={
            "tipo_documento": "folha_alteracao",
            "ano": "2025",
            "semestre": "2",
            "cpf": RAW_CPF,
            "codom": "000123",
        },
        files={"arquivo": ("folha.txt", b"texto", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "DOCUMENT_UPDATE_UPLOAD_EXTENSION_INVALID"


def test_document_update_history_filters_by_metadata(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    monkeypatch.setenv("SISGES_DOCUMENT_UPDATE_DIR", str(tmp_path))

    _login(client, "secretaria")
    folha_response = client.post(
        "/folhas/documentos/update",
        json={
            "tipo_documento": "folha_alteracao",
            "ano": 2025,
            "semestre": 2,
            "cpf": RAW_CPF,
            "codom": "000123",
        },
    )
    ctsm_response = client.post(
        "/folhas/documentos/update",
        json={
            "tipo_documento": "ctsm",
            "ano": 2026,
            "semestre": 1,
            "cpf": RAW_CPF,
            "codom": "ABC999",
        },
    )
    upload_response = client.post(
        "/folhas/documentos/update-upload",
        data={
            "tipo_documento": "declaracao",
            "ano": "2025",
            "semestre": "1",
            "cpf": RAW_CPF,
            "codom": "ABC999",
        },
        files={"arquivo": ("declaracao.pdf", b"%PDF-1.4\n%SISGES\n", "application/pdf")},
    )
    assert folha_response.status_code == 200, folha_response.text
    assert ctsm_response.status_code == 200, ctsm_response.text
    assert upload_response.status_code == 200, upload_response.text

    folha_id = folha_response.json()["document_id"]
    ctsm_id = ctsm_response.json()["document_id"]
    upload_id = upload_response.json()["document_id"]

    by_type = client.get("/folhas/documentos/updates?tipo_documento=ctsm").json()
    assert [item["document_id"] for item in by_type] == [ctsm_id]

    by_period = client.get("/folhas/documentos/updates?ano=2025&semestre=2").json()
    assert [item["document_id"] for item in by_period] == [folha_id]

    by_codom = client.get("/folhas/documentos/updates?codom=ABC").json()
    assert {item["document_id"] for item in by_codom} == {ctsm_id, upload_id}

    with_upload = client.get("/folhas/documentos/updates?has_upload=true").json()
    assert [item["document_id"] for item in with_upload] == [upload_id]

    without_upload = client.get("/folhas/documentos/updates?has_upload=false").json()
    assert {item["document_id"] for item in without_upload} == {folha_id, ctsm_id}

    by_full_cpf = client.get("/folhas/documentos/updates?cpf=123.456.789-01").json()
    assert {item["document_id"] for item in by_full_cpf} == {folha_id, ctsm_id, upload_id}

    by_invalid_cpf_fragment = client.get("/folhas/documentos/updates?cpf=999").json()
    assert by_invalid_cpf_fragment == []

    summary = client.get("/folhas/documentos/updates/summary?cpf=123.456.789-01")
    assert summary.status_code == 200, summary.text
    summary_payload = summary.json()
    assert summary_payload["total"] == 3
    assert summary_payload["with_attachment"] == 1
    assert summary_payload["without_attachment"] == 2
    assert summary_payload["with_manifest"] == 3
    assert summary_payload["is_limited"] is False
    assert summary_payload["by_tipo_documento"] == {
        "ctsm": 1,
        "declaracao": 1,
        "folha_alteracao": 1,
    }
    assert summary_payload["by_status"] == {"DOC_UPDATE_REGISTERED": 3}
    assert summary_payload["oldest_created_at"]
    assert summary_payload["latest_created_at"]
    assert summary_payload["oldest_created_at"] <= summary_payload["latest_created_at"]
    assert summary_payload["applied_filters"] == {"cpf_masked": "***.***.***-01"}
    assert RAW_CPF not in json.dumps(summary_payload)

    filtered_summary = client.get("/folhas/documentos/updates/summary?tipo_documento=declaracao")
    assert filtered_summary.status_code == 200, filtered_summary.text
    assert filtered_summary.json()["total"] == 1
    assert filtered_summary.json()["with_attachment"] == 1
    assert filtered_summary.json()["applied_filters"] == {"tipo_documento": "declaracao"}

    invalid_cpf_summary = client.get("/folhas/documentos/updates/summary?cpf=123456")
    assert invalid_cpf_summary.status_code == 200, invalid_cpf_summary.text
    assert invalid_cpf_summary.json()["applied_filters"] == {"cpf_filter": "invalid_partial"}
    assert "123456" not in json.dumps(invalid_cpf_summary.json())

    limited_summary = client.get("/folhas/documentos/updates/summary?limit=2&cpf=123.456.789-01")
    assert limited_summary.status_code == 200, limited_summary.text
    limited_payload = limited_summary.json()
    assert limited_payload["total"] == 2
    assert limited_payload["limit"] == 2
    assert limited_payload["is_limited"] is True
    assert limited_payload["applied_filters"] == {"cpf_masked": "***.***.***-01"}
    assert RAW_CPF not in json.dumps(limited_payload)


def test_document_update_history_exports_filtered_csv_without_raw_cpf(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    monkeypatch.setenv("SISGES_DOCUMENT_UPDATE_DIR", str(tmp_path))

    _login(client, "secretaria")
    response = client.post(
        "/folhas/documentos/update",
        json={
            "tipo_documento": "folha_alteracao",
            "ano": 2025,
            "semestre": 2,
            "cpf": RAW_CPF,
            "codom": "000123",
        },
    )
    assert response.status_code == 200, response.text

    export = client.get(
        "/folhas/documentos/updates/export.csv?tipo_documento=folha_alteracao&cpf=123.456.789-01"
    )

    assert export.status_code == 200, export.text
    assert export.headers["content-type"].startswith("text/csv")
    assert "folhas_document_updates.csv" in export.headers["content-disposition"]
    assert "document_id,status,tipo_documento" in export.text
    assert response.json()["document_id"] in export.text
    assert "***.***.***-01" in export.text
    assert RAW_CPF not in export.text


def test_document_update_history_exports_filtered_audit_zip_without_raw_cpf(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    monkeypatch.setenv("SISGES_DOCUMENT_UPDATE_DIR", str(tmp_path))

    _login(client, "secretaria")
    folha_response = client.post(
        "/folhas/documentos/update",
        json={
            "tipo_documento": "folha_alteracao",
            "ano": 2025,
            "semestre": 2,
            "cpf": RAW_CPF,
            "codom": "000123",
        },
    )
    upload_response = client.post(
        "/folhas/documentos/update-upload",
        data={
            "tipo_documento": "declaracao",
            "ano": "2025",
            "semestre": "1",
            "cpf": RAW_CPF,
            "codom": "ABC999",
        },
        files={"arquivo": ("declaracao.pdf", b"%PDF-1.4\n%SISGES\n", "application/pdf")},
    )
    assert folha_response.status_code == 200, folha_response.text
    assert upload_response.status_code == 200, upload_response.text

    folha_id = folha_response.json()["document_id"]
    upload_id = upload_response.json()["document_id"]
    export = client.get(
        "/folhas/documentos/updates/audit.zip?tipo_documento=declaracao&cpf=123.456.789-01"
    )

    assert export.status_code == 200, export.text
    assert export.headers["content-type"].startswith("application/zip")
    assert "folhas_document_updates_auditoria.zip" in export.headers["content-disposition"]
    with ZipFile(BytesIO(export.content)) as archive:
        names = set(archive.namelist())
        assert "README_AUDITORIA_LOTE.txt" in names
        assert "contexto_auditoria.json" in names
        assert "indice_auditoria.json" in names
        assert "indice_auditoria.csv" in names
        assert f"updates/{upload_id}/manifesto_update_{upload_id}.json" in names
        assert f"updates/{upload_id}/anexo/declaracao.pdf" in names
        assert not any(folha_id in name for name in names)

        readme = archive.read("README_AUDITORIA_LOTE.txt").decode("utf-8")
        audit_context = json.loads(archive.read("contexto_auditoria.json").decode("utf-8"))
        index_payload = json.loads(archive.read("indice_auditoria.json").decode("utf-8"))
        index_csv = archive.read("indice_auditoria.csv").decode("utf-8")
        manifest_in_zip = archive.read(
            f"updates/{upload_id}/manifesto_update_{upload_id}.json"
        ).decode("utf-8")
        assert "cpf_filter_applied: True" in readme
        assert "contexto: contexto_auditoria.json" in readme
        assert "partial_package: False" in readme
        assert audit_context["schema_version"] == "folhas-document-update-audit-context-v1"
        assert audit_context["package_kind"] == "FOLHAS_DOCUMENT_UPDATES_AUDIT_BATCH"
        assert audit_context["export"] == {
            "export_limit": 100,
            "exported_count": 1,
            "is_partial": False,
            "known_filtered_count": 1,
            "summary_limit": 5000,
        }
        assert audit_context["summary"]["total"] == 1
        assert audit_context["summary"]["is_limited"] is False
        assert audit_context["summary"]["with_attachment"] == 1
        assert audit_context["summary"]["applied_filters"] == {
            "tipo_documento": "declaracao",
            "cpf_masked": "***.***.***-01",
        }
        assert index_payload[0]["document_id"] == upload_id
        assert index_payload[0]["cpf_masked"] == "***.***.***-01"
        assert "document_id,status,tipo_documento" in index_csv
        assert upload_id in index_csv
        assert RAW_CPF not in readme
        assert RAW_CPF not in json.dumps(audit_context)
        assert RAW_CPF not in json.dumps(index_payload)
        assert RAW_CPF not in index_csv
        assert RAW_CPF not in manifest_in_zip
        assert "***.***.***-01" in manifest_in_zip

    partial_export = client.get("/folhas/documentos/updates/audit.zip?limit=1&cpf=123.456.789-01")
    assert partial_export.status_code == 200, partial_export.text
    with ZipFile(BytesIO(partial_export.content)) as archive:
        readme = archive.read("README_AUDITORIA_LOTE.txt").decode("utf-8")
        audit_context = json.loads(archive.read("contexto_auditoria.json").decode("utf-8"))
        assert "partial_package: True" in readme
        assert audit_context["export"] == {
            "export_limit": 1,
            "exported_count": 1,
            "is_partial": True,
            "known_filtered_count": 2,
            "summary_limit": 5000,
        }
        assert audit_context["summary"]["applied_filters"] == {"cpf_masked": "***.***.***-01"}
        assert RAW_CPF not in readme
        assert RAW_CPF not in json.dumps(audit_context)


def test_document_update_rejects_invalid_cpf(client: TestClient):
    _login(client, "secretaria")
    response = client.post(
        "/folhas/documentos/update",
        json={
            "tipo_documento": "folha_alteracao",
            "ano": 2025,
            "semestre": 2,
            "cpf": "123",
            "codom": "000123",
        },
    )

    assert response.status_code == 422

from collections.abc import Iterator
from datetime import date

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
from modules.compilador.application.reference_folha_pdf_parser import ReferenceFolhaPdfParseResult


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
        PermissionModel(id=key, key=key)
        for key in (
            "compilador.memory.view",
            "compilador.memory.upload",
            "compilador.memory.download",
            "compilador.reprocess",
        )
    ]
    role = RoleModel(id="compilador", name="compilador", permissions=permissions)
    user = UserModel(
        id="user-memory",
        username="memory",
        display_name="Memory",
        email="memory@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        is_dev=False,
        roles=[role],
    )
    db.add_all([*permissions, role, user])
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


def test_compilador_memory_reference_pdf_flow(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    import apps.web.routes.compilador_memory as route

    monkeypatch.chdir(tmp_path)

    def fake_parse_reference_folha_pdf(_path):
        return ReferenceFolhaPdfParseResult(
            is_folha_alteracoes=True,
            nome_completo="MILITAR TESTE COMPLETO",
            posto_graduacao="2º Sgt",
            qas_qms="5310 - QMS - INTENDÊNCIA",
            identidade="9990000001",
            semestre="2",
            ano=2024,
            periodo_inicio=date(2024, 7, 1),
            periodo_fim=date(2024, 12, 31),
            meses_detectados=["JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"],
            eventos=[{"mes": "JULHO", "titulo": "ALTERAÇÃO", "referencia": "- a 9, BI Nº 52 :", "corpo": "Evento."}],
            comportamento="EXCEPCIONAL",
            tempos_segunda_parte={"tc": "00a06m00d", "origem": "TRANSCRITO_DE_FOLHA_PDF_MEMORIA"},
            assinatura_nome="SIGNATARIO RESPONSAVEL",
            assinatura_funcao="Cel / S Cmt B Adm QGEx",
            page_count=2,
        )

    monkeypatch.setattr(route, "parse_reference_folha_pdf", fake_parse_reference_folha_pdf)

    login = client.post("/auth/login", json={"username": "memory", "password": "senha-forte-123"})
    assert login.status_code == 200

    upload = client.post(
        "/compilador/memory/reference-pdf",
        files={"pdf": ("folha.pdf", b"%PDF-1.4\nfolha", "application/pdf")},
    )

    assert upload.status_code == 200
    payload = upload.json()
    assert payload["status"] == "STORED"
    assert payload["file_id"]
    assert payload["run_id"]
    assert payload["document_id"]
    assert payload["sha256"]
    assert payload["variables"]["nome_completo"] == "MILITAR TESTE COMPLETO"
    assert "storage_path" in payload

    listing = client.get("/compilador/memory/references")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["file_id"] == payload["file_id"]

    variables = client.get(f"/compilador/memory/references/{payload['file_id']}/variables")
    assert variables.status_code == 200
    assert variables.json()["variables"]["tempos_segunda_parte_origem"] == "TRANSCRITO_DE_FOLHA_PDF_MEMORIA"

    details = client.get(f"/compilador/memory/references/{payload['file_id']}")
    assert details.status_code == 200
    assert any(item["code"] == "OK_FILE_STORED" for item in details.json()["validations"])

    run_detail = client.get(f"/compilador/runs/{payload['run_id']}")
    assert run_detail.status_code == 200
    assert run_detail.json()["run"]["tipo_compilacao"] == "MEMORY_REFERENCE_FOLHA_PDF"
    assert run_detail.json()["files"][0]["id"] == payload["file_id"]

    reprocess = client.post(f"/compilador/runs/{payload['run_id']}/reprocess")
    assert reprocess.status_code == 200
    assert reprocess.json()["status"] == "REPROCESSED"
    assert reprocess.json()["snapshot"]["variables"]["nome_completo"] == "MILITAR TESTE COMPLETO"

    download = client.get(f"/compilador/files/{payload['file_id']}/download")
    assert download.status_code == 200
    assert download.content == b"%PDF-1.4\nfolha"

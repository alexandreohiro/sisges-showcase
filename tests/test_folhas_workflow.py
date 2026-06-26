from __future__ import annotations

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
from infra.persistence.models import (
    FolhaAlteracaoModel,
    MilitarModel,
    NotificacaoModel,
    PermissionModel,
    RoleModel,
    UserModel,
)
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

    folha_permissions = [
        PermissionModel(id="mod.folhas.view", key="mod.folhas.view"),
        PermissionModel(id="mod.folhas.review", key="mod.folhas.review"),
        PermissionModel(id="mod.folhas.finalize", key="mod.folhas.finalize"),
        PermissionModel(id="mod.folhas.edit", key="mod.folhas.edit"),
    ]
    secretaria_role = RoleModel(id="secretaria", name="secretaria", permissions=folha_permissions[:2] + [folha_permissions[3]])
    assinante_role = RoleModel(id="assinante", name="assinante", permissions=[folha_permissions[2]])
    militar_role = RoleModel(id="militar", name="militar", permissions=[])

    militar = MilitarModel(
        nome_completo="MILITAR TESTE FOLHA",
        nome_guerra="TESTE",
        posto_graduacao="3 Sgt",
        identidade="9990000001",
        ativo=True,
    )
    outro_militar = MilitarModel(
        nome_completo="OUTRO MILITAR",
        nome_guerra="OUTRO",
        posto_graduacao="Cb",
        identidade="9990000002",
        ativo=True,
    )

    users = [
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
            identidade="9990000001",
            roles=[militar_role],
        ),
        UserModel(
            id="outro-user",
            username="outro",
            display_name="Outro",
            email="outro@sisges.local",
            password_hash=hash_password("senha-forte-123"),
            is_active=True,
            identidade="9990000002",
            roles=[militar_role],
        ),
        UserModel(
            id="assinante-user",
            username="assinante",
            display_name="Assinante",
            email="assinante@sisges.local",
            password_hash=hash_password("senha-forte-123"),
            is_active=True,
            roles=[assinante_role],
        ),
    ]
    db.add_all([*folha_permissions, secretaria_role, assinante_role, militar_role, militar, outro_militar, *users])
    db.flush()

    # Part2Schema mínimo válido: sem períodos de TC/TNC, TTES zerado.
    # Suficiente para passar o gate de completude (exige estrutura, não dados reais).
    _part2_minimo = {
        "totais": {
            "tscmm": {"anos": 0, "meses": 0, "dias": 0},
            "ttes": {"anos": 0, "meses": 0, "dias": 0},
            "tsnr": {"anos": 0, "meses": 0, "dias": 0},
            "ate_data": "2025-12-31",
        }
    }

    db.add_all(
        [
            FolhaAlteracaoModel(
                militar_id=militar.id,
                periodo_inicio=date(2025, 7, 1),
                periodo_fim=date(2025, 12, 31),
                status="rascunho",
                origem_dados="compilador",
                responsavel_user_id="secretaria-user",
                diagnostico_json={"workflow": {"document_id": "doc-1", "compiler_run_id": "run-1"}},
                part2_json=_part2_minimo,
            ),
            FolhaAlteracaoModel(
                militar_id=outro_militar.id,
                periodo_inicio=date(2025, 7, 1),
                periodo_fim=date(2025, 12, 31),
                status="AGUARDANDO_CIENCIA_MILITAR",
                origem_dados="compilador",
                responsavel_user_id="secretaria-user",
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


def test_secretaria_liberates_and_militar_approves_folha(
    client: TestClient,
    db_session: Session,
):
    folha = db_session.query(FolhaAlteracaoModel).filter_by(status="rascunho").one()

    _login(client, "secretaria")
    response = client.post(f"/folhas/{folha.id}/liberar-ciencia", json={})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "AGUARDANDO_CIENCIA_MILITAR"
    assert payload["document_id"] == "doc-1"
    assert payload["compiler_run_id"] == "run-1"
    assert (
        db_session.query(NotificacaoModel)
        .filter_by(
            user_id="militar-user",
            titulo="Folha liberada para ciencia",
            referencia_id=folha.id,
        )
        .one()
    )

    _login(client, "militar")
    minhas = client.get("/folhas/minhas")

    assert minhas.status_code == 200, minhas.text
    minhas_payload = minhas.json()
    assert len(minhas_payload) == 1
    assert minhas_payload[0]["acoes_permitidas"] == ["aprovar_militar", "devolver_militar"]

    response = client.post(f"/folhas/{folha.id}/aprovar", json={"observacao": "Ciente."})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "APROVADA_PELO_MILITAR"
    assert payload["eventos"][-1]["tipo_evento"] == "aprovar_militar"
    assert db_session.get(FolhaAlteracaoModel, folha.id).status == "APROVADA_PELO_MILITAR"
    assert (
        db_session.query(NotificacaoModel)
        .filter_by(
            user_id="secretaria-user",
            titulo="Folha aprovada pelo militar",
            referencia_id=folha.id,
        )
        .one()
    )


def test_militar_can_download_own_folha_but_not_another_one(
    client: TestClient,
    db_session: Session,
    tmp_path,
):
    folha = db_session.query(FolhaAlteracaoModel).filter_by(status="rascunho").one()
    other_folha = (
        db_session.query(FolhaAlteracaoModel)
        .filter_by(status="AGUARDANDO_CIENCIA_MILITAR")
        .one()
    )
    pdf_path = tmp_path / "folha.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nfolha teste\n")
    folha.pdf_path = str(pdf_path)
    folha.status = "AGUARDANDO_CIENCIA_MILITAR"
    db_session.add(folha)
    db_session.commit()

    _login(client, "militar")
    response = client.get(f"/folhas/{folha.id}/download?tipo=pdf")

    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF-1.4")
    assert response.headers["content-type"].startswith("application/pdf")

    response = client.get(f"/folhas/{other_folha.id}/download?tipo=pdf")

    assert response.status_code == 403


def test_militar_can_open_own_folha_detail_without_secretaria_permission(
    client: TestClient,
    db_session: Session,
):
    folha = db_session.query(FolhaAlteracaoModel).filter_by(status="rascunho").one()
    other_folha = (
        db_session.query(FolhaAlteracaoModel)
        .filter_by(status="AGUARDANDO_CIENCIA_MILITAR")
        .one()
    )
    folha.status = "AGUARDANDO_CIENCIA_MILITAR"
    db_session.add(folha)
    db_session.commit()

    _login(client, "militar")
    response = client.get(f"/folhas/{folha.id}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == folha.id
    assert response.json()["militar_identidade"] == "9990000001"

    response = client.get(f"/folhas/{other_folha.id}")

    assert response.status_code == 403


def test_militar_cannot_approve_folha_from_another_militar(
    client: TestClient,
    db_session: Session,
):
    folha = (
        db_session.query(FolhaAlteracaoModel)
        .filter_by(status="AGUARDANDO_CIENCIA_MILITAR")
        .one()
    )

    _login(client, "militar")
    response = client.post(f"/folhas/{folha.id}/aprovar", json={})

    assert response.status_code == 403
    assert db_session.get(FolhaAlteracaoModel, folha.id).status == "AGUARDANDO_CIENCIA_MILITAR"


def test_approved_folha_can_be_sent_to_signature_and_signed(
    client: TestClient,
    db_session: Session,
):
    folha = db_session.query(FolhaAlteracaoModel).filter_by(status="rascunho").one()

    _login(client, "secretaria")
    response = client.post(f"/folhas/{folha.id}/liberar-ciencia", json={})
    assert response.status_code == 200, response.text

    _login(client, "militar")
    response = client.post(f"/folhas/{folha.id}/aprovar", json={})
    assert response.status_code == 200, response.text

    _login(client, "secretaria")
    response = client.post(
        f"/folhas/{folha.id}/enviar-assinatura",
        json={"assinante_user_id": "assinante-user"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "AGUARDANDO_ASSINATURA"
    assert payload["assinatura_user_id"] == "assinante-user"
    assert (
        db_session.query(NotificacaoModel)
        .filter_by(
            user_id="assinante-user",
            titulo="Folha aguardando assinatura",
            referencia_id=folha.id,
        )
        .one()
    )

    _login(client, "assinante")
    assinatura = client.get("/folhas/assinatura")
    assert assinatura.status_code == 200, assinatura.text
    assert assinatura.json()[0]["acoes_permitidas"] == ["assinar"]

    response = client.post(f"/folhas/{folha.id}/assinar", json={"observacao": "Assinado."})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ASSINADA"
    assert (
        db_session.query(NotificacaoModel)
        .filter_by(
            user_id="militar-user",
            titulo="Folha assinada",
            referencia_id=folha.id,
        )
        .one()
    )


# ---------------------------------------------------------------------------
# F2 — Testes estendidos: assinatura digital, completude bloqueante,
#       download filename, PATCH Part2 inválido
# ---------------------------------------------------------------------------


def test_assinatura_digital_registra_modalidade(
    client: TestClient,
    db_session: Session,
):
    """Port. 063-DGP/2020 Art. 15 — assinatura digital deve ser aceita."""
    folha = db_session.query(FolhaAlteracaoModel).filter_by(status="rascunho").one()

    _login(client, "secretaria")
    client.post(f"/folhas/{folha.id}/liberar-ciencia", json={})

    _login(client, "militar")
    client.post(f"/folhas/{folha.id}/aprovar", json={})

    _login(client, "secretaria")
    client.post(
        f"/folhas/{folha.id}/enviar-assinatura",
        json={"assinante_user_id": "assinante-user"},
    )

    _login(client, "assinante")
    response = client.post(
        f"/folhas/{folha.id}/assinar",
        json={"observacao": "Assinado digitalmente.", "modalidade_assinatura": "digital"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ASSINADA"
    # workflow_updates deve registrar a modalidade
    diagnostico = db_session.get(FolhaAlteracaoModel, folha.id).diagnostico_json or {}
    workflow = diagnostico.get("workflow", {})
    assert workflow.get("modalidade_assinatura") == "digital"


def test_liberar_ciencia_sem_part2_retorna_400(
    client: TestClient,
    db_session: Session,
):
    """Gate B3 — liberar-ciência sem 2ª Parte preenchida deve ser bloqueado."""
    folha = db_session.query(FolhaAlteracaoModel).filter_by(status="rascunho").one()
    # Remove o part2_json do fixture
    folha.part2_json = None
    db_session.add(folha)
    db_session.commit()

    _login(client, "secretaria")
    response = client.post(f"/folhas/{folha.id}/liberar-ciencia", json={})

    assert response.status_code == 400, response.text
    detail = response.json().get("detail", {})
    msg = detail.get("message", "") if isinstance(detail, dict) else str(detail)
    assert "2" in msg or "parte" in msg.lower() or "part" in msg.lower()


def test_patch_part2_invalido_retorna_400(
    client: TestClient,
    db_session: Session,
):
    """PATCH com part2_json estruturalmente inválido deve retornar 400."""
    folha = db_session.query(FolhaAlteracaoModel).filter_by(status="rascunho").one()

    _login(client, "secretaria")
    response = client.patch(
        f"/folhas/{folha.id}",
        json={"part2_json": {"invalido": True}},  # falta 'totais'
    )

    assert response.status_code == 400, response.text
    detail = response.json().get("detail", {})
    msg = detail.get("message", "") if isinstance(detail, dict) else str(detail)
    assert "part2" in msg.lower() or "invalid" in msg.lower() or "inválid" in msg.lower()


def test_patch_part2_valido_aceito(
    client: TestClient,
    db_session: Session,
):
    """PATCH com part2_json válido deve persistir sem erros."""
    folha = db_session.query(FolhaAlteracaoModel).filter_by(status="rascunho").one()
    part2_valido = {
        "tc_periodos": [
            {
                "bucket": "arregimentado",
                "data_inicio": "2025-07-01",
                "data_fim": "2025-12-31",
                "duracao": {"anos": 0, "meses": 6, "dias": 0},
                "referencia_documental": "BI N° 001/2025",
            }
        ],
        "totais": {
            "tscmm": {"anos": 5, "meses": 0, "dias": 0},
            "ttes": {"anos": 0, "meses": 6, "dias": 0},
            "tsnr": {"anos": 0, "meses": 0, "dias": 0},
            "ate_data": "2025-12-31",
        },
    }

    _login(client, "secretaria")
    response = client.patch(f"/folhas/{folha.id}", json={"part2_json": part2_valido})

    assert response.status_code == 200, response.text
    salvo = db_session.get(FolhaAlteracaoModel, folha.id)
    db_session.refresh(salvo)
    assert salvo.part2_json is not None
    assert salvo.part2_json["totais"]["ttes"]["meses"] == 6


def test_download_filename_segue_art27(
    client: TestClient,
    db_session: Session,
    tmp_path,
):
    """Filename do download deve seguir Port. 063-DGP/2020 Art. 27 V."""
    folha = db_session.query(FolhaAlteracaoModel).filter_by(status="rascunho").one()

    # Configura header_json com CodOM numérico e identidade
    folha.header_json = {
        "identidade": "9990000001",
        "ano": 2025,
        "semestre": 2,
        "codom": "9999",
    }
    pdf_file = tmp_path / "folha.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\ntest\n")
    folha.pdf_path = str(pdf_file)
    folha.status = "AGUARDANDO_CIENCIA_MILITAR"
    db_session.add(folha)
    db_session.commit()

    _login(client, "militar")
    response = client.get(f"/folhas/{folha.id}/download?tipo=pdf")

    assert response.status_code == 200, response.text
    content_disp = response.headers.get("content-disposition", "")
    assert "9990000001_2025_2_9999.pdf" in content_disp


def test_download_filename_fallback_sem_codom(
    client: TestClient,
    db_session: Session,
    tmp_path,
):
    """Sem codom numérico, o filename cai para o fallback genérico."""
    folha = db_session.query(FolhaAlteracaoModel).filter_by(status="rascunho").one()

    folha.header_json = {"identidade": "9990000001", "ano": 2025, "semestre": 2}
    pdf_file = tmp_path / "folha.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\ntest\n")
    folha.pdf_path = str(pdf_file)
    folha.status = "AGUARDANDO_CIENCIA_MILITAR"
    db_session.add(folha)
    db_session.commit()

    _login(client, "militar")
    response = client.get(f"/folhas/{folha.id}/download?tipo=pdf")

    assert response.status_code == 200, response.text
    content_disp = response.headers.get("content-disposition", "")
    # Fallback: folha_alteracoes_{id}.pdf
    assert f"folha_alteracoes_{folha.id}.pdf" in content_disp

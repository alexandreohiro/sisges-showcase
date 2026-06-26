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
from infra.persistence.models import MilitarModel, PermissionModel, RoleModel, UserModel, WorkflowItemModel
from infra.security.passwords import hash_password


TASK_PERMISSIONS = [
    "mod.tarefas.view",
    "mod.tarefas.create",
    "mod.tarefas.edit",
    "mod.tarefas.assign",
    "mod.tarefas.close",
]


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

    permissions = [PermissionModel(id=key, key=key) for key in TASK_PERMISSIONS]
    role = RoleModel(id="tarefas", name="tarefas", permissions=permissions)
    user = UserModel(
        id="task-user",
        username="operador",
        display_name="Operador",
        email="operador@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        roles=[role],
        secao="SECRETARIA",
        divisao="DIV PES",
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
    test_client = TestClient(app)
    login = test_client.post("/auth/login", json={"username": "operador", "password": "senha-forte-123"})
    assert login.status_code == 200
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_create_task_assigns_code_actor_and_history(client: TestClient):
    response = client.post(
        "/tarefas",
        json={
            "titulo": "Conferir folha",
            "tipo": "folha_alteracao",
            "prioridade": "alta",
            "origem_modulo": "folhas",
            "secao_responsavel": "SECRETARIA",
            "divisao_responsavel": "DIV PES",
        },
    )

    assert response.status_code == 200, response.text
    task = response.json()
    assert task["codigo"] == "TRF-000001"
    assert task["criado_por_user_id"] == "task-user"
    assert task["secao_responsavel"] == "SECRETARIA"

    history = client.get(f"/tarefas/{task['id']}/historico")

    assert history.status_code == 200, history.text
    assert history.json()[0]["event_type"] == "TAREFA_CREATED"


def test_task_can_link_only_existing_militar(client: TestClient, db_session: Session):
    militar = MilitarModel(
        nome_completo="Militar Teste Tarefas",
        nome_guerra="TESTE",
        identidade="TAREFA0001",
        posto_graduacao="3 Sgt",
        secao="SECRETARIA",
        ativo=True,
    )
    db_session.add(militar)
    db_session.commit()

    response = client.post(
        "/tarefas",
        json={
            "titulo": "Conferir cadastro vinculado",
            "tipo": "cadastro",
            "prioridade": "media",
            "origem_modulo": "gestao_pessoal",
            "militar_id": militar.id,
        },
    )

    assert response.status_code == 200, response.text
    task = response.json()
    assert task["militar_id"] == militar.id

    response = client.get(f"/tarefas?militar_id={militar.id}")
    assert response.status_code == 200, response.text
    assert [item["titulo"] for item in response.json()] == ["Conferir cadastro vinculado"]

    response = client.post(
        "/tarefas",
        json={
            "titulo": "Vinculo inexistente",
            "tipo": "cadastro",
            "prioridade": "media",
            "origem_modulo": "gestao_pessoal",
            "militar_id": 999999,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "TAREFA_CREATE_INVALID"
    assert "Militar vinculado nao encontrado" in response.json()["detail"]["message"]


def test_update_task_rejects_unknown_militar_link(client: TestClient):
    created = client.post(
        "/tarefas",
        json={
            "titulo": "Tarefa sem militar",
            "tipo": "cadastro",
            "prioridade": "media",
            "origem_modulo": "gestao_pessoal",
        },
    ).json()

    response = client.patch(f"/tarefas/{created['id']}", json={"militar_id": 999999})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "TAREFA_UPDATE_INVALID"
    assert "Militar vinculado nao encontrado" in response.json()["detail"]["message"]


def test_list_filters_summary_and_section_scope(client: TestClient):
    first = client.post(
        "/tarefas",
        json={
            "titulo": "Revisar CTSM",
            "tipo": "ctsm",
            "prioridade": "critica",
            "origem_modulo": "ctsm",
            "secao_responsavel": "SECRETARIA",
            "divisao_responsavel": "DIV PES",
            "responsavel_user_id": "task-user",
        },
    )
    second = client.post(
        "/tarefas",
        json={
            "titulo": "Ajustar cadastro",
            "tipo": "cadastro",
            "prioridade": "baixa",
            "origem_modulo": "gestao_pessoal",
            "secao_responsavel": "ARQUIVO",
        },
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    response = client.get("/tarefas?prioridade=critica")
    assert response.status_code == 200, response.text
    assert [item["titulo"] for item in response.json()] == ["Revisar CTSM"]

    response = client.get("/tarefas/secao")
    assert response.status_code == 200, response.text
    assert [item["titulo"] for item in response.json()] == ["Revisar CTSM"]

    summary = client.get("/tarefas/resumo")
    assert summary.status_code == 200, summary.text
    assert summary.json()["abertas"] == 2
    assert summary.json()["minhas_abertas"] == 1
    assert summary.json()["criticas"] == 1


def test_task_transition_requires_artifact_for_documental_task(client: TestClient):
    created = client.post(
        "/tarefas",
        json={
            "titulo": "Emitir certidao",
            "tipo": "ctsm",
            "prioridade": "media",
            "origem_modulo": "ctsm",
        },
    ).json()

    response = client.post(f"/tarefas/{created['id']}/concluir", json={})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "TAREFA_COMPLETE_FAILED"

    response = client.post(
        f"/tarefas/{created['id']}/anexar-artefato",
        json={
            "artefato_tipo": "documento",
            "artefato_path": "data/output/teste/ctsm.pdf",
            "artefato_sha256": "abc123",
        },
    )
    assert response.status_code == 200, response.text

    response = client.post(
        f"/tarefas/{created['id']}/concluir",
        json={"resultado_resumido": "Certidao emitida e anexada."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "concluida"
    assert response.json()["completed_by_user_id"] == "task-user"


def test_block_and_reopen_task(client: TestClient):
    created = client.post(
        "/tarefas",
        json={
            "titulo": "Conferir assinatura",
            "tipo": "assinatura",
            "origem_modulo": "folhas",
        },
    ).json()

    response = client.post(
        f"/tarefas/{created['id']}/bloquear",
        json={"motivo_bloqueio": "Aguardando autoridade."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "bloqueada"
    assert response.json()["bloqueada"] is True

    response = client.post(f"/tarefas/{created['id']}/reabrir", json={"note": "Autoridade confirmada."})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "triagem"


def test_create_task_from_workflow_item_is_idempotent_and_resolves_item(
    client: TestClient,
    db_session: Session,
):
    item = WorkflowItemModel(
        fingerprint="consistencia:ctsm:1",
        modulo="ctsm",
        tipo="documento_sem_artefato",
        severidade="alta",
        score=90,
        status="aberto",
        militar_id=None,
        referencia_tipo="ctsm",
        referencia_id="1",
        titulo="CTSM sem artefato",
        descricao="A certidao foi marcada como emitida sem arquivo.",
        acao_recomendada="ANEXAR_OU_REGISTRAR_ARTEFATO",
        motivo_regra="tarefa concluida sem artefato",
        payload_json={"source": "test"},
    )
    db_session.add(item)
    db_session.commit()

    payload = {"responsavel_user_id": "task-user", "secao_responsavel": "SECRETARIA"}
    first = client.post(f"/tarefas/from-workflow-item/{item.id}", json=payload)
    second = client.post(f"/tarefas/from-workflow-item/{item.id}", json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["created_from_rule"] is True
    assert first.json()["workflow_item_id"] == item.id

    task_id = first.json()["id"]
    client.post(
        f"/tarefas/{task_id}/anexar-artefato",
        json={"artefato_path": "data/output/teste/ctsm.pdf", "artefato_sha256": "abc123"},
    )
    response = client.post(f"/tarefas/{task_id}/concluir", json={"resultado_resumido": "Regularizado."})
    assert response.status_code == 200, response.text

    db_session.refresh(item)
    assert item.status == "resolvido"

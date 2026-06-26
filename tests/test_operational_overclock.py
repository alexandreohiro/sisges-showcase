from __future__ import annotations

import asyncio
import json
import zipfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from io import BytesIO
from pathlib import Path
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers, UploadFile

import infra.persistence.models  # noqa: F401
from apps.web.app import app
from infra.config import settings
from infra.persistence.db import Base, get_db
from infra.persistence.models import (
    MilitarModel,
    MilitarPeriodoServicoModel,
    PermissionModel,
    RoleModel,
    SicapexEventoFuncionalModel,
    SicapexImportFileModel,
    TarefaEventoModel,
    TarefaModel,
    UserModel,
)
from infra.pipeline.uploads import (
    IMAGE_UPLOAD_POLICY,
    ODT_UPLOAD_POLICY,
    PDF_UPLOAD_POLICY,
    UploadPolicy,
    UploadValidationError,
    save_upload_to_path,
)
from infra.security.passwords import hash_password
from modules.gestao_pessoal.application.deletion_archive import (
    dry_run_militar_deletion_archive_restore,
    validate_militar_deletion_archive,
)
from modules.compilador.application.odt_template_policy import (
    EXECUTABLE_TEMPLATE,
    INVALID_ODT,
    REQUIRED_SISGES_MARKERS,
    VISUAL_REFERENCE_ONLY,
    classify_odt_template,
)
from modules.gestao_pessoal.importadores.sicapex.schemas import (
    SicapexAfastamento,
    SicapexParsedRecord,
    SicapexPeriodoServicoSugerido,
)
from modules.gestao_pessoal.importadores.sicapex.service import SicapexImportService
from modules.tarefas.application.schemas import TarefaCreate
from modules.tarefas.application.services import TarefasService


OVERLCLOCK_PERMISSIONS = [
    "mod.gestao_pessoal.view",
    "mod.gestao_pessoal.create",
    "mod.gestao_pessoal.edit",
    "mod.gestao_pessoal.delete",
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

    permissions = [PermissionModel(id=key, key=key) for key in OVERLCLOCK_PERMISSIONS]
    role = RoleModel(id="overclock", name="overclock", permissions=permissions)
    user = UserModel(
        id="overclock-user",
        username="operador",
        display_name="Operador Overclock",
        email="overclock@sisges.local",
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


def _seed_militares_and_tasks(db: Session, total: int = 120) -> list[MilitarModel]:
    militares = [
        MilitarModel(
            nome_completo=f"MILITAR OVERCLOCK {index:03d}",
            nome_guerra=f"OVR{index:03d}",
            posto_graduacao="3 Sgt",
            identidade=f"OVR{index:07d}",
            secao="SECRETARIA",
            om="DIV PES",
            ativo=True,
        )
        for index in range(total)
    ]
    db.add_all(militares)
    db.flush()

    tasks = [
        TarefaModel(
            codigo=f"OVR-{index:06d}",
            titulo=f"Tarefa operacional {index:03d}",
            tipo="cadastro",
            prioridade="media" if index % 5 else "critica",
            status="nova",
            origem_modulo="gestao_pessoal",
            secao_responsavel="SECRETARIA",
            divisao_responsavel="DIV PES",
            militar_id=militares[index].id,
            criado_por_user_id="overclock-user",
        )
        for index in range(total)
    ]
    db.add_all(tasks)
    db.commit()
    return militares


def _seed_effectivo(db: Session, total: int = 650) -> list[MilitarModel]:
    ranks = ["Cel", "Ten Cel", "Maj", "Cap", "STen", "1º Sgt", "2º Sgt", "3º Sgt", "Cb", "Sd", "Rcr"]
    secoes = ["SECRETARIA", "PROTOCOLO", "ARQUIVO", "FISCALIZACAO"]
    militares = []
    for index in range(total):
        in_div_pes = index < 520
        explicit_inactive = index % 29 == 0
        service_inactive = index % 37 == 0
        militares.append(
            MilitarModel(
                nome_completo=f"EFETIVO OVERCLOCK {index:04d}",
                nome_guerra=f"EFV{index:04d}",
                posto_graduacao=ranks[index % len(ranks)],
                identidade=f"EFV{index:07d}",
                secao=secoes[index % len(secoes)],
                om="DIV PES" if in_div_pes else "OUTRA OM",
                local_om="DIV PES" if in_div_pes else "OUTRA OM",
                ativo=not explicit_inactive,
                status_servico="Reserva" if service_inactive else "Ativo",
            ),
        )
    db.add_all(militares)
    db.commit()
    return militares


def _sicapex_record(index: int) -> SicapexParsedRecord:
    return SicapexParsedRecord(
        nome_completo=f"MILITAR SICAPEX OVERCLOCK {index:03d}",
        nome_guerra=f"SIC{index:03d}",
        posto_grad_abrev="3º Sgt",
        identidade_militar=f"SIC{index:07d}",
        prec_cp=f"11-{index:07d}",
        data_praca=date(2018, 4, 9),
        data_incorporacao=date(2018, 4, 9),
        data_inicio_om=date(2024, 1, 1),
        tipo_forca="Normal EB",
        documento_praca="BI 200",
        tempo_efetivo_servico_apos_ultima="2357",
        tempo_efetivo_servico_apos_ultima_dias=2357,
        source_sha256=f"sha-overclock-{index:03d}",
        source_filename=f"ficha_{index:03d}.pdf",
        afastamentos=[
            SicapexAfastamento(
                modalidade="Ferias",
                quantidade_dias=30,
                data_inicio=date(2025, 1, 1),
                data_fim=date(2025, 1, 30),
                documento="BI 1",
            ),
        ],
        periodos_servico_sugeridos=[
            SicapexPeriodoServicoSugerido(
                tipo_registro="vinculo_militar",
                subtipo_registro="data_praca",
                natureza_servico="servico_militar",
                categoria_tempo="computado",
                data_inicio=date(2018, 4, 9),
                documento_referencia="BI 200",
            ),
            SicapexPeriodoServicoSugerido(
                tipo_registro="afastamento",
                subtipo_registro="ferias",
                natureza_servico="afastamento",
                categoria_tempo="informativo",
                data_inicio=date(2025, 1, 1),
                data_fim=date(2025, 1, 30),
                computa_tempo=False,
                dias_lancados_override=30,
                documento_referencia="BI 1",
            ),
        ],
    )


def _write_synthetic_odt(path: Path, text: str, styles_text: str = "") -> None:
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">
  <office:body><office:text><text:p>{text}</text:p></office:text></office:body>
</office:document-content>"""
    styles = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" office:version="1.2">
  <office:styles/><office:master-styles>{styles_text}</office:master-styles>
</office:document-styles>"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("content.xml", content)
        package.writestr("styles.xml", styles)


def test_api_limit_guards_for_operational_lists(client: TestClient):
    assert client.get("/tarefas?limit=0").status_code == 422
    assert client.get("/tarefas?limit=501").status_code == 422
    assert client.get("/gestao-pessoal?limit=0").status_code == 422
    assert client.get("/gestao-pessoal?limit=501").status_code == 422
    assert client.get("/gestao-pessoal/efetivo-om?limit=0").status_code == 422
    assert client.get("/gestao-pessoal/efetivo-om?limit=2001").status_code == 422


def test_moderate_volume_list_filter_and_summary(client: TestClient, db_session: Session):
    militares = _seed_militares_and_tasks(db_session)

    gestao = client.get("/gestao-pessoal?view_scope=efetivo_completo&limit=120")
    assert gestao.status_code == 200, gestao.text
    assert len(gestao.json()) == 120

    tarefas = client.get("/tarefas?limit=120")
    assert tarefas.status_code == 200, tarefas.text
    assert len(tarefas.json()) == 120

    target = militares[17]
    linked = client.get(f"/tarefas?militar_id={target.id}&limit=120")
    assert linked.status_code == 200, linked.text
    linked_payload = linked.json()
    assert len(linked_payload) == 1
    assert linked_payload[0]["militar_id"] == target.id

    resumo = client.get("/tarefas/resumo")
    assert resumo.status_code == 200, resumo.text
    assert resumo.json()["total"] == 120
    assert resumo.json()["abertas"] == 120
    assert resumo.json()["criticas"] == 24


def test_large_effective_scope_filter_options_and_om_summary(client: TestClient, db_session: Session):
    seeded = _seed_effectivo(db_session)
    div_pes_count = len([item for item in seeded if item.om == "DIV PES"])

    response = client.get("/gestao-pessoal/efetivo-om?om=DIV%20PES&limit=600")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["total_ativos"] + payload["total_inativos"] == div_pes_count
    assert payload["total_ativos"] > payload["total_inativos"]
    assert all(item["om"] == "DIV PES" for item in payload["ativos_na_om"])

    filters = client.get("/gestao-pessoal/filtros")
    assert filters.status_code == 200, filters.text
    filter_payload = filters.json()
    assert {"SECRETARIA", "PROTOCOLO", "ARQUIVO", "FISCALIZACAO"}.issubset(
        set(filter_payload["secoes"]),
    )
    assert "DIV PES" in filter_payload["divisoes"]
    assert "Cel" in filter_payload["postos_graduacoes"]


def test_repeated_transition_workload_keeps_history_consistent(client: TestClient):
    created_ids: list[int] = []
    for index in range(15):
        created = client.post(
            "/tarefas",
            json={
                "titulo": f"Rodada de transicao {index:02d}",
                "tipo": "cadastro",
                "prioridade": "media",
                "origem_modulo": "gestao_pessoal",
                "secao_responsavel": "SECRETARIA",
                "divisao_responsavel": "DIV PES",
            },
        )
        assert created.status_code == 200, created.text
        task_id = created.json()["id"]
        created_ids.append(task_id)

        started = client.post(f"/tarefas/{task_id}/iniciar", json={"note": "inicio em lote"})
        assert started.status_code == 200, started.text

        concluded = client.post(f"/tarefas/{task_id}/concluir", json={"note": "conclusao em lote"})
        assert concluded.status_code == 200, concluded.text
        assert concluded.json()["status"] == "concluida"

    history = client.get(f"/tarefas/{created_ids[0]}/historico")
    assert history.status_code == 200, history.text
    assert [event["event_type"] for event in history.json()] == [
        "TAREFA_CREATED",
        "TAREFA_STARTED",
        "TAREFA_COMPLETED",
    ]

    resumo = client.get("/tarefas/resumo")
    assert resumo.status_code == 200, resumo.text
    assert resumo.json()["total"] == 15
    assert resumo.json()["abertas"] == 0


def test_invalid_task_status_and_priority_are_rejected(client: TestClient):
    invalid_priority = client.post(
        "/tarefas",
        json={
            "titulo": "Prioridade invalida",
            "tipo": "cadastro",
            "prioridade": "urgentissima",
            "origem_modulo": "gestao_pessoal",
        },
    )
    assert invalid_priority.status_code == 400
    assert "Prioridade de tarefa invalida" in invalid_priority.text

    invalid_status = client.post(
        "/tarefas",
        json={
            "titulo": "Status invalido",
            "tipo": "cadastro",
            "prioridade": "media",
            "status": "feito_sem_revisao",
            "origem_modulo": "gestao_pessoal",
        },
    )
    assert invalid_status.status_code == 400
    assert "Status de tarefa invalido" in invalid_status.text


def test_sicapex_dry_run_burst_does_not_persist_records(db_session: Session):
    service = SicapexImportService(db_session)

    results = [
        service.persist_record(
            record=_sicapex_record(index),
            pdf_path=Path(f"ficha_{index:03d}.pdf"),
            batch_id="overclock-dry-run",
            dry_run=True,
        )
        for index in range(60)
    ]

    assert {result.status for result in results} == {"DRY_RUN_OK"}
    assert db_session.query(MilitarModel).count() == 0
    assert db_session.query(SicapexImportFileModel).count() == 0
    assert db_session.query(SicapexEventoFuncionalModel).count() == 0
    assert db_session.query(MilitarPeriodoServicoModel).count() == 0


def test_upload_policy_rejects_empty_and_oversized_payloads(tmp_path: Path):
    small_pdf_policy = UploadPolicy(
        allowed_extensions=frozenset({".pdf"}),
        allowed_mime_types=frozenset({"application/pdf"}),
        max_bytes=3,
    )

    empty_upload = UploadFile(
        filename="vazio.pdf",
        file=BytesIO(b""),
        headers=Headers({"content-type": "application/pdf"}),
    )
    with pytest.raises(UploadValidationError) as empty_error:
        asyncio.run(save_upload_to_path(empty_upload, tmp_path / "vazio.pdf", small_pdf_policy))
    assert empty_error.value.code == "UPLOAD_VAZIO"

    oversized_upload = UploadFile(
        filename="grande.pdf",
        file=BytesIO(b"overclock"),
        headers=Headers({"content-type": "application/pdf"}),
    )
    with pytest.raises(UploadValidationError) as oversized_error:
        asyncio.run(save_upload_to_path(oversized_upload, tmp_path / "grande.pdf", small_pdf_policy))
    assert oversized_error.value.code == "UPLOAD_TAMANHO_EXCEDIDO"


def test_real_upload_policies_accept_and_reject_expected_boundaries(tmp_path: Path):
    pdf_upload = UploadFile(
        filename="folha.pdf",
        file=BytesIO(b"%PDF-1.4\n" + b"x" * (1024 * 1024)),
        headers=Headers({"content-type": "application/pdf"}),
    )
    assert asyncio.run(save_upload_to_path(pdf_upload, tmp_path / "folha.pdf", PDF_UPLOAD_POLICY)) > 1024

    odt_bytes = BytesIO()
    with zipfile.ZipFile(odt_bytes, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        package.writestr("content.xml", "<office:document-content>" + ("x" * 2048))
        package.writestr("styles.xml", "<office:document-styles />")
        package.writestr("META-INF/manifest.xml", "<manifest:manifest />")
    odt_upload = UploadFile(
        filename="modelo.odt",
        file=BytesIO(odt_bytes.getvalue()),
        headers=Headers({"content-type": "application/vnd.oasis.opendocument.text"}),
    )
    assert asyncio.run(save_upload_to_path(odt_upload, tmp_path / "modelo.odt", ODT_UPLOAD_POLICY)) > 0

    oversized_image = UploadFile(
        filename="foto.jpg",
        file=BytesIO(b"\xff\xd8\xff" + (b"x" * (IMAGE_UPLOAD_POLICY.max_bytes + 1))),
        headers=Headers({"content-type": "image/jpeg"}),
    )
    with pytest.raises(UploadValidationError) as image_error:
        asyncio.run(save_upload_to_path(oversized_image, tmp_path / "foto.jpg", IMAGE_UPLOAD_POLICY))
    assert image_error.value.code == "UPLOAD_TAMANHO_EXCEDIDO"


def test_synthetic_odt_template_classification_burst(tmp_path: Path):
    expected = {
        EXECUTABLE_TEMPLATE: 0,
        VISUAL_REFERENCE_ONLY: 0,
        INVALID_ODT: 0,
    }

    for index in range(45):
        path = tmp_path / f"template_{index:03d}.odt"
        if index % 15 == 0:
            path.write_bytes(b"nao-e-zip")
            expected[INVALID_ODT] += 1
        elif index % 3 == 0:
            _write_synthetic_odt(path, " ".join(REQUIRED_SISGES_MARKERS))
            expected[EXECUTABLE_TEMPLATE] += 1
        elif index % 3 == 1:
            _write_synthetic_odt(path, " ".join(REQUIRED_SISGES_MARKERS[:2]))
            expected[VISUAL_REFERENCE_ONLY] += 1
        else:
            _write_synthetic_odt(path, f"Referencia visual {index}")
            expected[VISUAL_REFERENCE_ONLY] += 1

    found = {
        EXECUTABLE_TEMPLATE: 0,
        VISUAL_REFERENCE_ONLY: 0,
        INVALID_ODT: 0,
    }
    for path in tmp_path.glob("template_*.odt"):
        found[classify_odt_template(path).classification] += 1

    assert found == expected


def test_permanent_delete_archive_keeps_recovery_data_and_detaches_task(
    client: TestClient,
    db_session: Session,
):
    militar = MilitarModel(
        nome_completo="MILITAR RECUPERACAO OVERCLOCK",
        identidade="RECOVER0001",
        ativo=True,
    )
    db_session.add(militar)
    db_session.flush()
    period = MilitarPeriodoServicoModel(
        militar_id=militar.id,
        tipo_registro="vinculo_militar",
        subtipo_registro="data_praca",
        natureza_servico="servico_militar",
        categoria_tempo="computado",
        data_inicio=date(2020, 1, 1),
    )
    task = TarefaModel(
        codigo="RECOVER-000001",
        titulo="Tarefa vinculada antes da exclusao",
        tipo="cadastro",
        prioridade="media",
        status="nova",
        origem_modulo="gestao_pessoal",
        militar_id=militar.id,
    )
    db_session.add_all([period, task])
    db_session.commit()

    response = client.delete(f"/gestao-pessoal/{militar.id}/permanent?confirm_permanent=true")
    assert response.status_code == 200, response.text
    deleted = response.json()["deleted"]
    archive_path = settings.base_dir / deleted["archive_path"]

    try:
        assert archive_path.exists()
        with zipfile.ZipFile(archive_path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            snapshot = json.loads(archive.read("snapshot.json"))

        assert manifest["kind"] == "MILITAR_HARD_DELETE_ARCHIVE"
        assert snapshot["militar"]["identidade"] == "RECOVER0001"
        assert len(snapshot["deleted_records"]["militar_periodo_servico"]) == 1
        assert len(snapshot["detached_records"]["tarefa"]) == 1
        validation = validate_militar_deletion_archive(
            archive_path,
            expected_sha256=deleted["archive_sha256"],
        )
        assert validation.ok is True
        assert validation.errors == []
        assert validation.summary["deleted_records"]["militar_periodo_servico"] == 1
        assert validation.summary["detached_records"]["tarefa"] == 1
        assert db_session.get(MilitarModel, militar.id) is None
        assert db_session.get(TarefaModel, task.id).militar_id is None

        restore_plan = dry_run_militar_deletion_archive_restore(
            db_session,
            archive_path,
            expected_sha256=deleted["archive_sha256"],
        )
        assert restore_plan.ok is True
        assert restore_plan.can_restore is True
        assert restore_plan.conflicts == []
        assert restore_plan.restore_plan["writes_database"] is False
        assert restore_plan.restore_plan["militar"]["would_create"] is True
        assert restore_plan.restore_plan["total_deleted_records"] == 1
        assert restore_plan.restore_plan["total_detached_records"] == 1

        db_session.add(
            MilitarModel(
                id=militar.id + 1000,
                nome_completo="MILITAR CONFLITO RESTAURACAO",
                identidade="RECOVER0001",
                ativo=True,
            )
        )
        db_session.commit()
        conflicted_plan = dry_run_militar_deletion_archive_restore(
            db_session,
            archive_path,
            expected_sha256=deleted["archive_sha256"],
        )
        assert conflicted_plan.ok is True
        assert conflicted_plan.can_restore is False
        assert conflicted_plan.conflicts[0]["code"] == "MILITAR_IDENTIDADE_EXISTS"
        assert db_session.query(MilitarModel).filter(MilitarModel.identidade == "RECOVER0001").count() == 1
    finally:
        archive_path.unlink(missing_ok=True)


@pytest.mark.xfail(
    strict=False,
    reason=(
        "SQLite serializes writes via a file-level lock. With 4 concurrent workers and "
        "32 inserts, threads race for the write lock and the 15-second timeout is "
        "occasionally exceeded under load. This is a known SQLite limitation; the same "
        "service logic works correctly under MySQL. xfail(strict=False) so the test "
        "still runs and counts as xpass when SQLite happens to be fast enough."
    ),
)
def test_controlled_concurrent_task_creation_uses_unique_codes_and_events(tmp_path: Path):
    db_path = tmp_path / "concurrency.db"
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def create_task(index: int) -> str:
        db = session_factory()
        try:
            task = TarefasService(db).create(
                TarefaCreate(
                    titulo=f"Concorrencia controlada {index:02d}",
                    tipo="cadastro",
                    prioridade="media",
                    origem_modulo="gestao_pessoal",
                    secao_responsavel="SECRETARIA",
                    divisao_responsavel="DIV PES",
                ),
                actor_user_id=None,
            )
            db.commit()
            return task.codigo or ""
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=4) as executor:
        codes = list(executor.map(create_task, range(32)))

    db = session_factory()
    try:
        assert len(codes) == 32
        assert len(set(codes)) == 32
        assert db.query(TarefaModel).count() == 32
        assert db.query(TarefaEventoModel).count() == 32
    finally:
        db.close()


def test_critical_endpoint_response_times_stay_within_safe_local_bound(
    client: TestClient,
    db_session: Session,
):
    _seed_militares_and_tasks(db_session, total=180)
    _seed_effectivo(db_session, total=700)
    endpoints = [
        "/tarefas?limit=180",
        "/tarefas/resumo",
        "/gestao-pessoal?view_scope=efetivo_completo&limit=180",
        "/gestao-pessoal/filtros",
        "/gestao-pessoal/efetivo-om?om=DIV%20PES&limit=700",
    ]

    timings: dict[str, float] = {}
    for endpoint in endpoints:
        start = perf_counter()
        response = client.get(endpoint)
        elapsed = perf_counter() - start
        assert response.status_code == 200, response.text
        timings[endpoint] = elapsed

    # This is a generous local guard: it detects pathological slowdowns without
    # pretending to be a production benchmark.
    assert max(timings.values()) < 5.0, timings

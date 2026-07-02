from collections.abc import Iterator
from datetime import date
from types import SimpleNamespace
import io
import zipfile

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

from modules.compilador.application.folha_alteracoes_compiler import (
    FolhaCompilerResult,
    SicapexProfile,
    TimeSummary,
    calculate_times_from_context,
    format_admin_days,
    hydrate_profile_from_context,
)


def _minimal_odt_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr("content.xml", "<office:document-content />")
        archive.writestr("styles.xml", "<office:document-styles />")
        archive.writestr("META-INF/manifest.xml", "<manifest:manifest />")
    return buffer.getvalue()


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
            "compilador.generate_odt",
            "compilador.memory.view",
            "compilador.reprocess",
        )
    ]
    role = RoleModel(id="compilador", name="compilador", permissions=permissions)
    user = UserModel(
        id="user-compilador",
        username="compilador",
        display_name="Compilador",
        email="compilador@sisges.local",
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


def test_calculate_times_from_context_uses_persisted_sicapex_data():
    fallback = TimeSummary(
        tc="00a06m00d",
        tc_arreg="00a06m00d",
        tc_nao_arreg="00a00m00d",
        tc_transito="00a00m00d",
        tc_instalacao="00a00m00d",
        tnc="00a00m00d",
        tscmm="00a00m00d",
        tssd="00a00m00d",
        tsnr="00a00m00d",
        ttes="00a00m00d",
        origem="SICAPEX_CALCULADO",
        dias_reais_ttes=0,
        dias_reais_tnc=0,
    )
    context = {
        "tempo_efetivo_servico_apos_ultima_dias": 2357,
        "periodos_nao_computaveis": [
            {
                "tipo_registro": "desconto_tempo",
                "data_inicio": "2025-07-10",
                "data_fim": "2025-07-14",
            }
        ],
        "acrescimos": [
            {
                "tipo_registro": "acrescimo_tempo",
                "dias_lancados_override": 30,
            }
        ],
    }

    result = calculate_times_from_context(
        context,
        date(2025, 7, 1),
        date(2025, 12, 31),
        fallback=fallback,
    )

    assert result.origem == "SICAPEX_BANCO_SISGES"
    assert result.ttes == format_admin_days(2357)
    assert result.tnc == format_admin_days(5)
    assert result.tssd == format_admin_days(30)


def test_hydrate_profile_from_context_uses_persisted_personnel_data():
    profile = SicapexProfile(nome_completo="PDF INCOMPLETO")
    context = {
        "data_praca": "2018-04-09",
        "militar": {
            "nome_completo": "MILITAR TESTE COMPLETO",
            "nome_guerra": "TESTE",
            "posto_graduacao": "3º Sgt",
            "qas_qms": "5310 - QMS - INTENDÊNCIA",
            "identidade": "9990000001",
            "data_praca": "2018-04-09",
        },
    }

    result = hydrate_profile_from_context(profile, context)

    assert result.nome_completo == "MILITAR TESTE COMPLETO"
    assert result.nome_guerra == "TESTE"
    assert result.graduacao_abrev == "3º Sgt"
    assert result.graduacao_extenso == "Terceiro-Sargento"
    assert result.qm == "5310 - QMS - INTENDÊNCIA"
    assert result.identidade == "010064645-4"
    assert result.data_praca == date(2018, 4, 9)


def test_compile_folha_endpoint_returns_zip_and_registers_document(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    import apps.web.routes.compilador_folha as route
    import apps.web.routes.compilador_memory as memory_route
    import modules.compilador.application.folha_package_service as svc
    from infra.pipeline.workspace import PipelineWorkspaceManager
    from modules.compilador.application.compiler_memory_service import CompilerMemoryService

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        route,
        "PipelineWorkspaceManager",
        lambda: PipelineWorkspaceManager(base_dir=tmp_path / "t"),
    )
    monkeypatch.setattr(
        svc,
        "CompilerMemoryService",
        lambda db: CompilerMemoryService(db, root=tmp_path / "m"),
    )

    def fake_parse_sicapex_pdf(_path):
        return SimpleNamespace(nome_completo="MILITAR TESTE", identidade_militar="9990000001")

    class FakeImportService:
        def __init__(self, _db):
            pass

        def _find_existing(self, _record):
            return None

    def fake_compile(self, *, output_path, **_kwargs):
        output_path.write_bytes(b"ODT TESTE")
        validation_path = output_path.with_suffix(".validacao.txt")
        justification_path = output_path.with_suffix(".justificativa.txt")
        validation_path.write_text("VALIDACAO\n", encoding="utf-8")
        justification_path.write_text("JUSTIFICATIVA\n", encoding="utf-8")
        return FolhaCompilerResult(
            output_path=output_path,
            validation_path=validation_path,
            justification_path=justification_path,
            output_sha256="out-sha",
            slug="militar_teste",
            profile=SicapexProfile(
                nome_completo="MILITAR TESTE",
                nome_guerra="TESTE",
                identidade="010064645-4",
            ),
            times=TimeSummary(
                tc="00a06m00d",
                tc_arreg="00a06m00d",
                tc_nao_arreg="00a00m00d",
                tc_transito="00a00m00d",
                tc_instalacao="00a00m00d",
                tnc="00a00m00d",
                tscmm="00a00m00d",
                tssd="00a00m00d",
                tsnr="00a00m00d",
                ttes="00a00m00d",
                origem="SICAPEX_CALCULADO",
                dias_reais_ttes=0,
                dias_reais_tnc=0,
            ),
            events_count=1,
            tables_count=1,
            validation=["VALIDACAO"],
            justification=["JUSTIFICATIVA"],
        )

    monkeypatch.setattr(svc, "parse_sicapex_pdf", fake_parse_sicapex_pdf)
    monkeypatch.setattr(svc, "SicapexImportService", FakeImportService)
    monkeypatch.setattr(svc.FolhaAlteracoesCompiler, "compile", fake_compile)
    monkeypatch.setattr(memory_route, "parse_sicapex_pdf", fake_parse_sicapex_pdf)
    monkeypatch.setattr(memory_route, "SicapexImportService", FakeImportService)
    monkeypatch.setattr(memory_route.FolhaAlteracoesCompiler, "compile", fake_compile)
    monkeypatch.setattr(
        memory_route,
        "PipelineWorkspaceManager",
        lambda: PipelineWorkspaceManager(base_dir=tmp_path / "rt"),
    )

    memory_service = CompilerMemoryService(db_session, root=tmp_path / "m")
    reference_pdf = tmp_path / "folha_referencia.pdf"
    reference_pdf.write_bytes(b"%PDF-1.4\nFOLHA REFERENCIA")
    reference_file = memory_service.register_reference_file(
        source_path=reference_pdf,
        role="MEMORY_REFERENCE_FOLHA_PDF",
        original_filename="folha_referencia.pdf",
        mime_type="application/pdf",
        owner_user_id="user-compilador",
        source_kind="folha_alteracoes",
    )
    memory_service.save_variable_snapshot(
        file_id=reference_file.id,
        schema_version="reference_folha_pdf.v1",
        variables_json={"nome_completo": "MILITAR TESTE", "eventos": []},
        warnings_json=[],
        pending_json=[],
        confidence_json={"source": "test"},
    )
    db_session.commit()

    login = client.post(
        "/auth/login",
        json={"username": "compilador", "password": "senha-forte-123"},
    )
    assert login.status_code == 200

    response = client.post(
        "/compilador/folha/compile-odt",
        data={
            "ano": "2025",
            "semestre": "2",
            "reparar_tabelas": "true",
            "preservar_tabelas_odt": "true",
            "gerar_pdf_preview": "false",
            "full_package": "false",
            "memory_reference_file_id": reference_file.id,
            "fonte_eventos": "BI_ODT_PLUS_MEMORY_VALIDATION",
        },
        files={
            "bi_odt": (
                "bi.odt",
                _minimal_odt_bytes(),
                "application/vnd.oasis.opendocument.text",
            ),
            "sicapex_pdf": ("ficha.pdf", b"%PDF-1.4\n", "application/pdf"),
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    document_id = response.headers["x-sisges-document-id"]
    assert document_id

    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        assert sorted(package.namelist()) == [
            "folha_alteracoes_compilada.justificativa.txt",
            "folha_alteracoes_compilada.odt",
            "folha_alteracoes_compilada.validacao.txt",
        ]

    from infra.persistence.models import (
        CompilerFileModel,
        CompilerRunModel,
        CompilerValidationModel,
        CompilerVariableSnapshotModel,
        DocumentModel,
    )

    document = db_session.get(DocumentModel, document_id)
    assert document is not None
    assert document.kind == "FOLHA_ALTERACOES_ZIP"
    assert document.source_module == "compilador.folha"
    assert document.metadata_json["tempo_origem"] == "SICAPEX_CALCULADO"
    run_id = response.headers["x-sisges-compiler-run-id"]
    run = db_session.get(CompilerRunModel, run_id)
    assert run is not None
    assert run.status == "CONCLUIDO"
    assert run.nome_militar_snapshot == "MILITAR TESTE"
    assert run.fonte_eventos == "BI_ODT_PLUS_MEMORY_VALIDATION"
    roles = {
        item.role
        for item in db_session.query(CompilerFileModel).filter(CompilerFileModel.run_id == run_id)
    }
    assert {
        "INPUT_BI_ODT",
        "INPUT_SICAPEX_PDF",
        "OUTPUT_FOLHA_ODT",
        "OUTPUT_VALIDACAO_TXT",
        "OUTPUT_JUSTIFICATIVA_TXT",
        "OUTPUT_ZIP",
    }.issubset(roles)
    run_snapshot = (
        db_session.query(CompilerVariableSnapshotModel)
        .filter(CompilerVariableSnapshotModel.run_id == run_id)
        .one()
    )
    assert run_snapshot.variables_json["memory_reference"]["file_id"] == reference_file.id
    assert (
        db_session.query(CompilerValidationModel)
        .filter(CompilerValidationModel.run_id == run_id)
        .count()
        >= 1
    )

    run_detail = client.get(f"/compilador/runs/{run_id}")
    assert run_detail.status_code == 200
    assert run_detail.json()["run"]["id"] == run_id
    assert len(run_detail.json()["files"]) >= 4

    run_files = client.get(f"/compilador/runs/{run_id}/files")
    assert run_files.status_code == 200
    assert any(item["role"] == "OUTPUT_ZIP" for item in run_files.json()["items"])

    run_variables = client.get(f"/compilador/runs/{run_id}/variables")
    assert run_variables.status_code == 200
    assert run_variables.json()["items"][0]["variables"]["nome_completo"] == "MILITAR TESTE"

    run_validations = client.get(f"/compilador/runs/{run_id}/validations")
    assert run_validations.status_code == 200
    assert any(item["code"] == "OK_DOCUMENT_REGISTERED" for item in run_validations.json()["items"])
    assert any(
        item["code"] == "OK_MEMORY_REFERENCE_LINKED"
        for item in run_validations.json()["items"]
    )

    reprocess = client.post(f"/compilador/runs/{run_id}/reprocess")
    assert reprocess.status_code == 200, reprocess.text
    assert reprocess.json()["status"] == "REPROCESSED"
    assert reprocess.json()["run"]["status"] == "CONCLUIDO"
    assert reprocess.json()["file"]["role"] == "OUTPUT_ZIP"

    reprocessed_validations = client.get(f"/compilador/runs/{run_id}/validations")
    assert any(
        item["code"] == "OK_REPROCESSAMENTO_CONCLUIDO"
        for item in reprocessed_validations.json()["items"]
    )


# ---------------------------------------------------------------------------
# F3 — Compilador: TSSD, LAC, títulos separados (trânsito/instalação)
# ---------------------------------------------------------------------------


def _part2_json_com_tssd_e_lac() -> dict:
    """Part2Schema com TSSD, LAC e TC arregimentado — ttes = TC + TSSD."""
    # TC arregimentado: 150 dias = 5m0d
    # TSSD serv_publico: 30 dias = 1m0d
    # ttes = 150 + 30 = 180 = 6m0d
    return {
        "tc_periodos": [
            {
                "bucket": "arregimentado",
                "data_inicio": "2024-01-01",
                "data_fim": "2024-05-30",
                "duracao": {"anos": 0, "meses": 5, "dias": 0},
                "referencia_documental": "BI 001",
            }
        ],
        "tnc_periodos": [
            {
                "tipo": "LAC",
                "data_inicio": "2024-03-01",
                "data_fim": "2024-03-30",
                "duracao": {"anos": 0, "meses": 1, "dias": 0},
                "descricao": "Acompanhamento de cônjuge transferido",
            }
        ],
        "tssd_averbacoes": [
            {
                "subtipo": "serv_publico",
                "duracao": {"anos": 0, "meses": 1, "dias": 0},
                "documento_referencia": "Portaria 001/2010",
                "descricao": "Serviço público federal anterior",
            }
        ],
        "totais": {
            "tscmm": {"anos": 12, "meses": 3, "dias": 5},
            "ttes": {"anos": 0, "meses": 6, "dias": 0},  # 5m + 1m TSSD = 6m
            "tsnr": {"anos": 0, "meses": 2, "dias": 0},
            "ate_data": "2024-06-30",
        },
    }


def _part2_json_com_transito_instalacao() -> dict:
    """Part2Schema com TC trânsito e instalação separados."""
    # arregimentado: 90d = 3m
    # transito: 30d = 1m
    # instalacao: 10d
    # ttes = 90 + 30 + 10 = 130d = 4m10d
    return {
        "tc_periodos": [
            {
                "bucket": "arregimentado",
                "data_inicio": "2024-02-11",
                "data_fim": "2024-05-10",
                "duracao": {"anos": 0, "meses": 3, "dias": 0},
                "referencia_documental": "BI 001",
            },
            {
                "bucket": "transito",
                "data_inicio": "2024-01-01",
                "data_fim": "2024-01-30",
                "duracao": {"anos": 0, "meses": 1, "dias": 0},
                "referencia_documental": "BI 095",
            },
            {
                "bucket": "instalacao",
                "data_inicio": "2024-01-31",
                "data_fim": "2024-02-09",
                "duracao": {"anos": 0, "meses": 0, "dias": 10},
                "referencia_documental": "BI 009",
            },
        ],
        "totais": {
            "tscmm": {"anos": 8, "meses": 0, "dias": 0},
            "ttes": {"anos": 0, "meses": 4, "dias": 10},  # 3m + 1m + 10d = 4m10d
            "tsnr": {"anos": 0, "meses": 0, "dias": 0},
            "ate_data": "2024-06-30",
        },
    }


def test_calculate_times_from_part2_com_tssd():
    """F3 — TSSD deve ser incluído no TTES e isolado no campo tssd."""
    from modules.compilador.application.folha_time_calc import calculate_times_from_part2

    ts = calculate_times_from_part2(_part2_json_com_tssd_e_lac())
    assert ts is not None
    assert ts.tssd == "00a01m00d"        # 1 mês de serviço público
    assert ts.ttes == "00a06m00d"        # TC(5m) + TSSD(1m) = 6m
    assert ts.tscmm == "12a03m05d"       # acumulado histórico intacto
    assert ts.tsnr == "00a02m00d"        # tsnr acumulado histórico
    assert ts.origem == "PART2_SCHEMA_REVISADO"


def test_calculate_times_from_part2_com_lac():
    """F3 — LAC (Port. 063/2020, novo tipo TNC) deve aparecer no tnc total."""
    from modules.compilador.application.folha_time_calc import calculate_times_from_part2

    ts = calculate_times_from_part2(_part2_json_com_tssd_e_lac())
    assert ts is not None
    assert ts.tnc == "00a01m00d"         # 1 mês de LAC
    # LAC não afeta TTES (TNC é desconto)
    assert ts.ttes == "00a06m00d"


def test_calculate_times_from_part2_titulos_separados():
    """F3 — trânsito e instalação devem aparecer em campos separados no TimeSummary."""
    from modules.compilador.application.folha_time_calc import calculate_times_from_part2

    ts = calculate_times_from_part2(_part2_json_com_transito_instalacao())
    assert ts is not None
    # Campos separados — requisito Port. 063/2020 Art. 24 (6 títulos de TC)
    assert ts.tc_arreg == "00a03m00d"
    assert ts.tc_transito == "00a01m00d"
    assert ts.tc_instalacao == "00a00m10d"
    assert ts.tc_nao_arreg == "00a00m00d"
    assert ts.ttes == "00a04m10d"


def test_calculate_times_from_context_com_part2_json():
    """F3 — context com part2_json deve usar os dados revisados, não recalcular."""
    from modules.compilador.application.folha_time_calc import (
        calculate_times_from_context,
        TimeSummary,
    )

    fallback = TimeSummary(
        tc="00a06m00d", tc_arreg="00a06m00d", tc_nao_arreg="00a00m00d",
        tc_transito="00a00m00d", tc_instalacao="00a00m00d", tnc="00a00m00d",
        tscmm="00a00m00d", tssd="00a00m00d", tsnr="00a00m00d", ttes="00a00m00d",
        origem="FALLBACK_NAO_DEVE_APARECER", dias_reais_ttes=0, dias_reais_tnc=0,
    )
    ctx = {"part2_json": _part2_json_com_transito_instalacao()}
    ts = calculate_times_from_context(ctx, date(2024, 1, 1), date(2024, 6, 30), fallback=fallback)

    assert ts.origem == "PART2_SCHEMA_REVISADO"
    assert ts.tc_transito == "00a01m00d"   # veio do part2, não do fallback
    assert ts.tc_instalacao == "00a00m10d"

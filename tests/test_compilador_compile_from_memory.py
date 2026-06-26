rom collections.abc import Iterator
from types import SimpleNamespace
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import infra.persistence.models  # noqa: F401
from apps.web.app import app
from infra.persistence.db import Base, get_db
from infra.persistence.models import CompilerRunModel, PermissionModel, RoleModel, UserModel
from infra.security.passwords import hash_password
from modules.compilador.application.compiler_memory_service import CompilerMemoryService
from modules.compilador.application.folha_alteracoes_compiler import (
    FolhaCompilerResult,
    SicapexProfile,
    TimeSummary,
)


def _executable_template_odt_bytes() -> bytes:
    flags = " ".join(
        [
            "[SISGES_NOME]",
            "[SISGES_GRADUACAO]",
            "[SISGES_QMS]",
            "[SISGES_IDENTIDADE]",
            "[SISGES_SEMESTRE_TEXTO]",
            "[SISGES_PERIODO]",
            "[SISGES_PARTE_1]",
            "[SISGES_COMPORTAMENTO]",
            "[SISGES_DATA_LOCAL]",
            "[SISGES_ASSINATURA_NOME]",
            "[SISGES_ASSINATURA_FUNCAO]",
        ]
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        package.writestr("content.xml", f"<root>{flags}</root>")
        package.writestr("styles.xml", "<styles />")
        package.writestr("META-INF/manifest.xml", "<manifest />")
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
            "compilador.memory.download",
        )
    ]
    role = RoleModel(id="compilador", name="compilador", permissions=permissions)
    user = UserModel(
        id="user-memory-compile",
        username="memorycompile",
        display_name="Memory Compile",
        email="memorycompile@sisges.local",
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


@pytest.fixture
def logged_client(client: TestClient) -> TestClient:
    login = client.post(
        "/auth/login",
        json={"username": "memorycompile", "password": "senha-forte-123"},
    )
    assert login.status_code == 200
    return client


@pytest.fixture
def memory_root(monkeypatch: pytest.MonkeyPatch, tmp_path):
    import apps.web.routes.compilador_folha as route
    import modules.compilador.application.folha_package_service as svc
    from infra.pipeline.workspace import PipelineWorkspaceManager

    monkeypatch.chdir(tmp_path)
    root = tmp_path / "m"
    monkeypatch.setattr(route, "DATA_OUTPUT_ROOT", tmp_path / "data" / "output")
    monkeypatch.setattr(
        route,
        "PipelineWorkspaceManager",
        lambda: PipelineWorkspaceManager(base_dir=tmp_path / "w"),
    )
    monkeypatch.setattr(svc, "CompilerMemoryService", lambda db: CompilerMemoryService(db, root=root))

    def fake_parse_sicapex_pdf(_path):
        return SimpleNamespace(nome_completo="MILITAR MEMORIA", identidade_militar="9990000001")

    class FakeImportService:
        def __init__(self, _db):
            pass

        def _find_existing(self, _record):
            return None

    def fake_compile(self, *, output_path, **_kwargs):
        output_path.write_bytes(b"ODT MEMORIA")
        parte1_output_path = output_path.with_name("parte_1_alteracoes.odt")
        parte1_output_path.write_bytes(b"ODT PARTE 1")
        validation_path = output_path.with_suffix(".validacao.txt")
        justification_path = output_path.with_suffix(".justificativa.txt")
        validation_path.write_text(
            "OK_TEMPLATE_USED\nOK_ALL_MONTHS_PRESENT\nOK_PARTE1_ODT_GENERATED\n",
            encoding="utf-8",
        )
        justification_path.write_text("Fonte de alterações: memória.\n", encoding="utf-8")
        return FolhaCompilerResult(
            output_path=output_path,
            validation_path=validation_path,
            justification_path=justification_path,
            output_sha256="out-sha",
            slug="militar_memoria",
            profile=SicapexProfile(
                nome_completo="MILITAR MEMORIA",
                nome_guerra="MEMORIA",
                graduacao_abrev="3º Sgt",
                identidade="010064645-4",
                qm="INTENDÊNCIA",
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
            tables_count=0,
            validation=["OK_TEMPLATE_USED", "OK_ALL_MONTHS_PRESENT", "OK_PARTE1_ODT_GENERATED"],
            parte1_output_path=parte1_output_path,
            justification=["Fonte de alterações: memória."],
        )

    monkeypatch.setattr(svc, "parse_sicapex_pdf", fake_parse_sicapex_pdf)
    monkeypatch.setattr(svc, "SicapexImportService", FakeImportService)
    monkeypatch.setattr(svc.FolhaAlteracoesCompiler, "compile", fake_compile)
    return root


def _register_memory_inputs(db_session: Session, root):
    service = CompilerMemoryService(db_session, root=root)
    bi = root.parent / "bi.odt"
    sicapex = root.parent / "ficha.pdf"
    modelo = root.parent / "modelo.odt"
    bi.write_bytes(b"BI ODT")
    sicapex.write_bytes(b"%PDF-1.4\n")
    modelo.write_bytes(b"MODELO ODT")
    bi_file = service.register_reference_file(
        source_path=bi,
        role="MEMORY_REFERENCE_FOLHA_ODT",
        original_filename="bi.odt",
        mime_type="application/vnd.oasis.opendocument.text",
        owner_user_id="user-memory-compile",
        source_kind="folha_alteracoes",
    )
    sicapex_file = service.register_reference_file(
        source_path=sicapex,
        role="INPUT_SICAPEX_PDF",
        original_filename="ficha.pdf",
        mime_type="application/pdf",
        owner_user_id="user-memory-compile",
        source_kind="sicapex",
    )
    modelo_file = service.register_reference_file(
        source_path=modelo,
        role="INPUT_MODELO_ODT",
        original_filename="modelo.odt",
        mime_type="application/vnd.oasis.opendocument.text",
        owner_user_id="user-memory-compile",
        source_kind="modelo_odt",
    )
    db_session.commit()
    return bi_file, sicapex_file, modelo_file


def test_compile_from_memory_generates_full_package_and_run(
    logged_client: TestClient,
    db_session: Session,
    memory_root,
):
    bi_file, sicapex_file, _modelo_file = _register_memory_inputs(db_session, memory_root)

    response = logged_client.post(
        "/compilador/folha/compile-from-memory",
        json={
            "ano": 2025,
            "semestre": "2",
            "alteracoes_file_id": bi_file.id,
            "sicapex_file_id": sicapex_file.id,
            "options": {"full_package": True, "gerar_pdf_preview": False},
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["x-sisges-package-mode"] == "full"
    run_id = response.headers["x-sisges-compiler-run-id"]
    run = db_session.get(CompilerRunModel, run_id)
    assert run is not None
    assert run.fonte_eventos == "MEMORY_REFERENCE_FOLHA_ODT"
    assert run.status == "CONCLUIDO"

    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        assert "manifest.json" in package.namelist()
        assert "parte_1_alteracoes.odt" in package.namelist()
        manifest = json.loads(package.read("manifest.json").decode("utf-8"))
        variables = json.loads(package.read("variables.json").decode("utf-8"))

    assert manifest["run_id"] == run_id
    assert any(item["role"] == "OUTPUT_PARTE1_ODT" for item in manifest["files"])
    assert manifest["source_memory_file_ids"]["alteracoes_file_id"] == bi_file.id
    assert variables["source_memory_file_ids"]["alteracoes_file_id"] == bi_file.id
    assert variables["outputs"]["parte_1_alteracoes_odt"]["filename"] == "parte_1_alteracoes.odt"


def test_compile_from_memory_uses_stored_executable_template(
    logged_client: TestClient,
    db_session: Session,
    memory_root,
):
    import apps.web.routes.compilador_folha as route

    bi_file, sicapex_file, _modelo_file = _register_memory_inputs(db_session, memory_root)
    stored_template = (
        route.DATA_OUTPUT_ROOT
        / "modelos"
        / route.FOLHA_EXECUTABLE_TEMPLATE_FILENAME
    )
    stored_template.parent.mkdir(parents=True, exist_ok=True)
    stored_template.write_bytes(_executable_template_odt_bytes())

    response = logged_client.post(
        "/compilador/folha/compile-from-memory",
        json={
            "ano": 2025,
            "semestre": "2",
            "alteracoes_file_id": bi_file.id,
            "sicapex_file_id": sicapex_file.id,
            "modelo": {"type": "STORED_EXECUTABLE"},
            "options": {"full_package": True, "gerar_pdf_preview": False},
        },
    )

    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        manifest = json.loads(package.read("manifest.json").decode("utf-8"))
        variables = json.loads(package.read("variables.json").decode("utf-8"))

    assert manifest["template"]["role"] == route.STORED_EXECUTABLE_MODELO_ODT
    assert manifest["template"]["source"] == "STORED_EXECUTABLE"
    assert variables["template"]["role"] == route.STORED_EXECUTABLE_MODELO_ODT
    assert variables["template"]["source"] == "STORED_EXECUTABLE"
    assert "OK_STORED_EXECUTABLE_TEMPLATE_USED" in variables["validations"]


def test_compile_from_memory_fails_when_file_id_is_missing(
    logged_client: TestClient,
    memory_root,
):
    response = logged_client.post(
        "/compilador/folha/compile-from-memory",
        json={
            "ano": 2025,
            "semestre": "2",
            "alteracoes_file_id": "arquivo-inexistente",
            "sicapex_file_id": "tambem-inexistente",
            "options": {"full_package": True},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "MEMORY_FILE_NOT_FOUND"


def test_compile_from_memory_parte1_mode_returns_formatted_part_one_odt(
    logged_client: TestClient,
    db_session: Session,
    memory_root,
):
    bi_file, sicapex_file, _modelo_file = _register_memory_inputs(db_session, memory_root)

    response = logged_client.post(
        "/compilador/folha/compile-from-memory",
        json={
            "ano": 2025,
            "semestre": "2",
            "alteracoes_file_id": bi_file.id,
            "sicapex_file_id": sicapex_file.id,
            "options": {
                "full_package": False,
                "gerar_pdf_preview": False,
                "output_mode": "parte1",
            },
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["x-sisges-package-mode"] == "parte1"
    assert response.headers["content-type"].startswith("application/vnd.oasis.opendocument.text")
    assert response.content == b"ODT PARTE 1"

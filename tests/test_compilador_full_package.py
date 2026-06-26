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
from infra.persistence.models import PermissionModel, RoleModel, UserModel
from infra.security.passwords import hash_password
from modules.compilador.application.folha_alteracoes_compiler import (
    FolhaCompilerResult,
    SicapexProfile,
    TimeSummary,
)
from modules.compilador.application.compiler_memory_service import CompilerMemoryService


def _minimal_odt_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        package.writestr("content.xml", "<office:document-content />")
        package.writestr("styles.xml", "<office:document-styles />")
        package.writestr("META-INF/manifest.xml", "<manifest:manifest />")
    return buffer.getvalue()


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
        id="user-full-package",
        username="fullpackage",
        display_name="Full Package",
        email="fullpackage@sisges.local",
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
        json={"username": "fullpackage", "password": "senha-forte-123"},
    )
    assert login.status_code == 200
    return client


@pytest.fixture
def fake_compiler(monkeypatch: pytest.MonkeyPatch, tmp_path):
    import apps.web.routes.compilador_folha as route
    import modules.compilador.application.folha_package_service as svc
    from infra.pipeline.workspace import PipelineWorkspaceManager

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(route, "DATA_OUTPUT_ROOT", tmp_path / "data" / "output")
    monkeypatch.setattr(
        route,
        "PipelineWorkspaceManager",
        lambda: PipelineWorkspaceManager(base_dir=tmp_path / "w"),
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
        parte1_output_path = output_path.with_name("parte_1_alteracoes.odt")
        parte1_output_path.write_bytes(b"ODT PARTE 1")
        validation_path = output_path.with_suffix(".validacao.txt")
        justification_path = output_path.with_suffix(".justificativa.txt")
        validation_path.write_text(
            "OK_TEMPLATE_USED\nOK_ALL_MONTHS_PRESENT\nOK_PARTE1_ODT_GENERATED\n",
            encoding="utf-8",
        )
        justification_path.write_text("Fonte de alterações: ODT de BI.\n", encoding="utf-8")
        return FolhaCompilerResult(
            output_path=output_path,
            validation_path=validation_path,
            justification_path=justification_path,
            output_sha256="out-sha",
            slug="militar_teste",
            profile=SicapexProfile(
                nome_completo="MILITAR TESTE",
                nome_guerra="TESTE",
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
            events_count=2,
            tables_count=0,
            validation=["OK_TEMPLATE_USED", "OK_ALL_MONTHS_PRESENT", "OK_PARTE1_ODT_GENERATED"],
            parte1_output_path=parte1_output_path,
            justification=["Fonte de alterações: ODT de BI."],
        )

    monkeypatch.setattr(svc, "parse_sicapex_pdf", fake_parse_sicapex_pdf)
    monkeypatch.setattr(svc, "SicapexImportService", FakeImportService)
    monkeypatch.setattr(svc.FolhaAlteracoesCompiler, "compile", fake_compile)
    return route


def test_compile_odt_full_package_includes_audit_files(
    logged_client: TestClient,
    fake_compiler,
):
    response = logged_client.post(
        "/compilador/folha/compile-odt",
        data={
            "ano": "2025",
            "semestre": "2",
            "reparar_tabelas": "true",
            "preservar_tabelas_odt": "true",
            "gerar_pdf_preview": "true",
            "full_package": "true",
        },
        files={
            "bi_odt": ("bi.odt", _minimal_odt_bytes(), "application/vnd.oasis.opendocument.text"),
            "sicapex_pdf": ("ficha.pdf", b"%PDF-1.4\n", "application/pdf"),
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["x-sisges-package-mode"] == "full"
    assert response.headers["x-sisges-document-id"]
    assert response.headers["x-sisges-compiler-run-id"]

    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        names = set(package.namelist())
        assert {
            "folha_alteracoes.odt",
            "parte_1_alteracoes.odt",
            "validacao.txt",
            "justificativa.txt",
            "variables.json",
            "compiler_run.json",
            "manifest.json",
        }.issubset(names)
        manifest = json.loads(package.read("manifest.json").decode("utf-8"))
        variables = json.loads(package.read("variables.json").decode("utf-8"))
        compiler_run = json.loads(package.read("compiler_run.json").decode("utf-8"))

    assert manifest["package_mode"] == "full"
    assert manifest["document_id"] == response.headers["x-sisges-document-id"]
    assert manifest["template"]["source"] == variables["template"]["source"]
    assert "WARN_PDF_PREVIEW_NOT_GENERATED" in manifest["warnings"]
    assert any(item["role"] == "OUTPUT_PARTE1_ODT" for item in manifest["files"])
    assert variables["militar"]["nome_completo"] == "MILITAR TESTE"
    assert variables["outputs"]["parte_1_alteracoes_odt"]["filename"] == "parte_1_alteracoes.odt"
    assert variables["template"]["used"] is True
    assert compiler_run["run_id"] == response.headers["x-sisges-compiler-run-id"]
    assert compiler_run["status"] == "CONCLUIDO_COM_PENDENCIAS"


def test_compile_odt_minimal_package_remains_supported(
    logged_client: TestClient,
    fake_compiler,
):
    response = logged_client.post(
        "/compilador/folha/compile-odt",
        data={
            "ano": "2025",
            "semestre": "2",
            "reparar_tabelas": "true",
            "preservar_tabelas_odt": "true",
            "gerar_pdf_preview": "false",
            "full_package": "false",
        },
        files={
            "bi_odt": ("bi.odt", _minimal_odt_bytes(), "application/vnd.oasis.opendocument.text"),
            "sicapex_pdf": ("ficha.pdf", b"%PDF-1.4\n", "application/pdf"),
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["x-sisges-package-mode"] == "minimal"
    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        assert sorted(package.namelist()) == [
            "folha_alteracoes_compilada.justificativa.txt",
            "folha_alteracoes_compilada.odt",
            "folha_alteracoes_compilada.validacao.txt",
        ]


def test_compile_odt_parte1_mode_returns_formatted_part_one_odt(
    logged_client: TestClient,
    fake_compiler,
):
    response = logged_client.post(
        "/compilador/folha/compile-odt",
        data={
            "ano": "2025",
            "semestre": "2",
            "reparar_tabelas": "true",
            "preservar_tabelas_odt": "true",
            "gerar_pdf_preview": "false",
            "full_package": "false",
            "output_mode": "parte1",
        },
        files={
            "bi_odt": ("bi.odt", _minimal_odt_bytes(), "application/vnd.oasis.opendocument.text"),
            "sicapex_pdf": ("sicapex.pdf", b"%PDF-1.4\n", "application/pdf"),
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["x-sisges-package-mode"] == "parte1"
    assert response.headers["content-type"].startswith("application/vnd.oasis.opendocument.text")
    assert response.content == b"ODT PARTE 1"


def test_compile_odt_uses_stored_executable_template_when_requested(
    logged_client: TestClient,
    fake_compiler,
):
    stored_template = (
        fake_compiler.DATA_OUTPUT_ROOT
        / "modelos"
        / fake_compiler.FOLHA_EXECUTABLE_TEMPLATE_FILENAME
    )
    stored_template.parent.mkdir(parents=True, exist_ok=True)
    stored_template.write_bytes(_executable_template_odt_bytes())

    response = logged_client.post(
        "/compilador/folha/compile-odt",
        data={
            "ano": "2025",
            "semestre": "2",
            "reparar_tabelas": "true",
            "preservar_tabelas_odt": "true",
            "gerar_pdf_preview": "false",
            "full_package": "true",
            "usar_modelo_executavel_sisges": "true",
        },
        files={
            "bi_odt": ("bi.odt", _minimal_odt_bytes(), "application/vnd.oasis.opendocument.text"),
            "sicapex_pdf": ("sicapex.pdf", b"%PDF-1.4\n", "application/pdf"),
        },
    )

    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        manifest = json.loads(package.read("manifest.json").decode("utf-8"))
        variables = json.loads(package.read("variables.json").decode("utf-8"))

    assert manifest["template"]["role"] == fake_compiler.STORED_EXECUTABLE_MODELO_ODT
    assert manifest["template"]["source"] == "STORED_EXECUTABLE"
    assert variables["template"]["role"] == fake_compiler.STORED_EXECUTABLE_MODELO_ODT
    assert variables["template"]["source"] == "STORED_EXECUTABLE"
    assert variables["template"]["provided_by_user"] is False
    assert "OK_STORED_EXECUTABLE_TEMPLATE_USED" in variables["validations"]


def test_compile_odt_upload_template_overrides_stored_executable_template(
    logged_client: TestClient,
    fake_compiler,
):
    stored_template = (
        fake_compiler.DATA_OUTPUT_ROOT
        / "modelos"
        / fake_compiler.FOLHA_EXECUTABLE_TEMPLATE_FILENAME
    )
    stored_template.parent.mkdir(parents=True, exist_ok=True)
    stored_template.write_bytes(_executable_template_odt_bytes())

    response = logged_client.post(
        "/compilador/folha/compile-odt",
        data={
            "ano": "2025",
            "semestre": "2",
            "reparar_tabelas": "true",
            "preservar_tabelas_odt": "true",
            "gerar_pdf_preview": "false",
            "full_package": "true",
            "usar_modelo_executavel_sisges": "true",
        },
        files={
            "bi_odt": ("bi.odt", _minimal_odt_bytes(), "application/vnd.oasis.opendocument.text"),
            "sicapex_pdf": ("sicapex.pdf", b"%PDF-1.4\n", "application/pdf"),
            "modelo_odt": (
                "modelo.odt",
                _executable_template_odt_bytes(),
                "application/vnd.oasis.opendocument.text",
            ),
        },
    )

    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        variables = json.loads(package.read("variables.json").decode("utf-8"))

    assert variables["template"]["role"] == fake_compiler.INPUT_MODELO_ODT
    assert variables["template"]["source"] == "UPLOADED_MODEL"
    assert variables["template"]["provided_by_user"] is True
    assert "OK_UPLOADED_TEMPLATE_USED" in variables["validations"]


def test_compile_odt_returns_clear_error_when_stored_template_is_missing(
    logged_client: TestClient,
    fake_compiler,
):
    response = logged_client.post(
        "/compilador/folha/compile-odt",
        data={
            "ano": "2025",
            "semestre": "2",
            "reparar_tabelas": "true",
            "preservar_tabelas_odt": "true",
            "gerar_pdf_preview": "false",
            "full_package": "true",
            "usar_modelo_executavel_sisges": "true",
        },
        files={
            "bi_odt": ("bi.odt", _minimal_odt_bytes(), "application/vnd.oasis.opendocument.text"),
            "sicapex_pdf": ("sicapex.pdf", b"%PDF-1.4\n", "application/pdf"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_STORED_EXECUTABLE_TEMPLATE_NOT_FOUND"

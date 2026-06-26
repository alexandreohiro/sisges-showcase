from __future__ import annotations

from collections.abc import Iterator
from datetime import date
import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import infra.persistence.models  # noqa: F401
from apps.web.app import app
from apps.web.routes import declaracoes as declaracoes_route
from infra.persistence.db import Base, get_db
from infra.persistence.models import (
    CalculoTempoServicoModel,
    DocumentModel,
    MilitarModel,
    PermissionModel,
    RoleModel,
    UserModel,
)
from infra.security.passwords import hash_password
from modules.compilador.application.document_template_classifier import (
    EXECUTABLE_TEMPLATE,
    VISUAL_REFERENCE_ONLY,
    classify_document_template,
)
from scripts.prepare_declaracao_templates import prepare_declaracao_template


@pytest.fixture
def db_session(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    monkeypatch.chdir(tmp_path)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()

    permission = PermissionModel(id="compilador.generate_odt", key="compilador.generate_odt")
    role = RoleModel(id="compilador", name="compilador", permissions=[permission])
    user = UserModel(
        id="user-documentos",
        username="documentos",
        display_name="Documentos",
        email="documentos@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        roles=[role],
    )
    militar = MilitarModel(
        nome_completo="MILITAR TESTE",
        nome_guerra="TESTE",
        posto_graduacao="3º Sgt",
        identidade="0101010101",
        cpf="111.222.333-44",
        om="B Adm QGEx",
        data_praca=date(2020, 1, 1),
        sexo="MASCULINO",
    )
    db.add_all([permission, role, user, militar])
    db.flush()
    db.add(
        CalculoTempoServicoModel(
            militar_id=militar.id,
            referencia_data=date(2026, 5, 22),
            tempo_computado_anos=6,
            tempo_computado_meses=1,
            tempo_computado_dias=2,
            tempo_total_anos=6,
            tempo_total_meses=1,
            tempo_total_dias=2,
            base_legal_json={"snapshot": "ok"},
        ),
    )
    db.commit()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def logged_client(db_session: Session) -> Iterator[TestClient]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    login = client.post("/auth/login", json={"username": "documentos", "password": "senha-forte-123"})
    assert login.status_code == 200
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_classify_document_template_with_markers_is_executable(tmp_path):
    path = tmp_path / "template.odt"
    _write_test_odt(path, "[[SISGES:NOME_COMPLETO]] [[SISGES:TEXTO_DOCUMENTO]] [[SISGES:ASSINATURA_NOME]]")

    result = classify_document_template(path)

    assert result.classification == EXECUTABLE_TEMPLATE
    assert "OK_TEMPLATE_EXECUTABLE" in result.validations


def test_classify_document_template_without_markers_is_visual_reference(tmp_path):
    path = tmp_path / "referencia.odt"
    _write_test_odt(path, "Documento visual sem marcadores")

    result = classify_document_template(path)

    assert result.classification == VISUAL_REFERENCE_ONLY
    assert "WARN_TEMPLATE_VISUAL_REFERENCE_ONLY" in result.validations


def test_compile_declaracao_generates_auditable_package(logged_client: TestClient, db_session: Session):
    militar = db_session.query(MilitarModel).one()
    response = logged_client.post(
        "/compilador/documentos/compile",
        data={
            "tipo_documento": "DECLARACAO_SERVICO_MILITAR",
            "militar_id": str(militar.id),
            "output_mode": "full",
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["x-sisges-package-mode"] == "full"
    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        names = set(package.namelist())
        assert {"validacao.txt", "justificativa.txt", "variables.json", "compiler_run.json", "manifest.json"}.issubset(names)
        assert any(name.endswith(".odt") for name in names)
        assert "OK_DECLARACAO_DATA_FROM_GESTAO_PESSOAL" in package.read("validacao.txt").decode("utf-8")

    document = db_session.query(DocumentModel).filter(DocumentModel.kind == "DECLARACAO_SERVICO_MILITAR").one()
    assert document.output_sha256


def test_compile_declaracao_uses_flag_odt_template(logged_client: TestClient, db_session: Session, tmp_path):
    militar = db_session.query(MilitarModel).one()
    template = tmp_path / "declaracao_flags.odt"
    _write_flag_template_odt(template)

    with template.open("rb") as upload:
        response = logged_client.post(
            "/compilador/documentos/compile",
            data={
                "tipo_documento": "DECLARACAO_SERVICO_MILITAR",
                "militar_id": str(militar.id),
                "output_mode": "full",
                "template_mode": "odt_flags",
                "instituicao_ensino": "Centro de Ensino Teste",
                "data_servico": "15/01/2026",
                "data_extenso": "16 de maio de 2026.",
            },
            files={
                "template_odt": (
                    "declaracao_flags.odt",
                    upload,
                    "application/vnd.oasis.opendocument.text",
                ),
            },
        )

    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        names = set(package.namelist())
        odt_name = next(name for name in names if name.endswith(".odt"))
        validacao = package.read("validacao.txt").decode("utf-8")
        variables = package.read("variables.json").decode("utf-8")
        assert "OK_DECLARACAO_FLAG_TEMPLATE_USED" in validacao
        assert "OK_UPLOADED_TEMPLATE_RENDERED" in validacao
        assert "OK_TEMPLATE_PLACEHOLDERS_REPLACED" in validacao
        assert "UPLOADED_DECLARACAO_FLAG_TEMPLATE" in variables
        with zipfile.ZipFile(io.BytesIO(package.read(odt_name))) as odt:
            assert "Pictures/logo.txt" in odt.namelist()
            text = _odt_text(odt.read("content.xml"))
            assert "Centro de Ensino Teste" in text
            assert "MILITAR TESTE" in text
            assert "111.222.333-44" in text
            assert "[NOME_COMPLETO]" not in text
            assert "[INSTITUICAO_ENSINO]" not in text
            assert odt.read("Pictures/logo.txt").decode("utf-8") == "LOGO"


def test_declaracao_model_catalog_lists_real_template_candidates(
    logged_client: TestClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "006 - DECLARACOES"
    model_dir = root / "004 - FACULDADE" / "2026"
    model_dir.mkdir(parents=True)
    _write_flag_template_odt(model_dir / "MODELO FACULDADE.odt")
    _write_test_odt(model_dir / "Sd Fulano - Declaracao.odt", "Documento preenchido sem flags")

    monkeypatch.setenv("SISGES_DECLARACOES_MODELOS_DIR", str(root))

    response = logged_client.get("/declaracoes/modelos")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["root_configured"] is True
    assert payload["total"] == 1
    assert payload["compilable"] == 1
    assert payload["items"][0]["title"] == "MODELO FACULDADE"
    assert payload["items"][0]["template_kind"] == "ODT_FLAGS"


def test_compile_declaracao_uses_catalog_template_key(
    logged_client: TestClient,
    db_session: Session,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "006 - DECLARACOES"
    model_dir = root / "004 - FACULDADE" / "2026"
    model_dir.mkdir(parents=True)
    _write_flag_template_odt(model_dir / "MODELO FACULDADE.odt")
    monkeypatch.setenv("SISGES_DECLARACOES_MODELOS_DIR", str(root))

    model_payload = logged_client.get("/declaracoes/modelos").json()
    template_key = model_payload["items"][0]["key"]
    militar = db_session.query(MilitarModel).one()

    response = logged_client.post(
        "/compilador/documentos/compile",
        data={
            "tipo_documento": "DECLARACAO_SERVICO_MILITAR",
            "militar_id": str(militar.id),
            "output_mode": "full",
            "template_mode": "odt_flags",
            "template_key": template_key,
            "instituicao_ensino": "Faculdade Teste",
        },
    )

    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        validacao = package.read("validacao.txt").decode("utf-8")
        variables = package.read("variables.json").decode("utf-8")
        assert "OK_DECLARACAO_FLAG_TEMPLATE_USED" in validacao
        assert "OK_TEMPLATE_PLACEHOLDERS_REPLACED" in validacao
        assert "UPLOADED_DECLARACAO_FLAG_TEMPLATE" in variables


def test_prepare_declaracao_visual_reference_creates_flagged_copy(tmp_path):
    source = tmp_path / "MODELO VISUAL.odt"
    output = tmp_path / "MODELO VISUAL_template_sisges.odt"
    _write_test_odt(
        source,
        (
            "DECLARACAO Declaro, para fins de comprovacao junto ao Centro de Ensino Teste, "
            "que o Soldado FULANO DE TAL, brasileiro, Identidade Militar n.º 111927997-2, "
            "inscrito no CPF n. 088.530.111-06, foi regularmente designado para o cumprimento "
            "de servico militar no dia 13 de Maio de 2025. Brasilia-DF, 21 de Maio de 2025 "
            "DIONIZIO SANTOS RODRIGUES DOS ANJOS - Major Ch Div Pes/ B Adm QGEx"
        ),
    )

    result = prepare_declaracao_template(source, output, overwrite=True)

    assert result.status in {"READY", "READY_WITH_WARNINGS"}
    with zipfile.ZipFile(output) as odt:
        text = _odt_text(odt.read("content.xml"))
        assert "[INSTITUICAO_ENSINO]" in text
        assert "[POSTO_GRADUACAO]" in text
        assert "[NOME_COMPLETO]" in text
        assert "[CPF]" in text
        assert "[IDENTIDADE]" in text


def test_prepare_declaracao_templates_endpoint_generates_managed_copies(
    logged_client: TestClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    source_root = tmp_path / "006 - DECLARACOES"
    source_root.mkdir()
    _write_test_odt(
        source_root / "MODELO FACULDADE.odt",
        (
            "DECLARACAO junto ao Centro de Ensino Teste, que o Soldado FULANO DE TAL, "
            "brasileiro, Identidade Militar n.Âº 111927997-2, CPF n. 088.530.111-06, "
            "servico militar no dia 13 de Maio de 2025. Brasilia-DF, 21 de Maio de 2025"
        ),
    )
    output_root = tmp_path / "managed"
    report = tmp_path / "report.json"
    monkeypatch.setattr(declaracoes_route, "DEFAULT_OUTPUT_ROOT", output_root)
    monkeypatch.setattr(declaracoes_route, "DEFAULT_PREPARATION_REPORT", report)
    monkeypatch.setattr(
        declaracoes_route,
        "default_declaracoes_source_root",
        lambda: source_root,
    )

    response = logged_client.post("/declaracoes/modelos/preparar")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "OK"
    assert payload["total"] == 1
    assert payload["ready"] + payload["ready_with_warnings"] == 1
    assert report.exists()
    assert list(output_root.rglob("*_template_sisges.odt"))


def test_compile_ctsm_uses_time_snapshot(logged_client: TestClient, db_session: Session):
    militar = db_session.query(MilitarModel).one()
    response = logged_client.post(
        "/compilador/documentos/compile",
        data={
            "tipo_documento": "CTSM",
            "militar_id": str(militar.id),
            "output_mode": "odt",
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["x-sisges-package-mode"] == "odt"
    assert response.headers["content-type"].startswith("application/vnd.oasis.opendocument.text")
    assert response.content.startswith(b"PK")


def _write_test_odt(path, text: str) -> None:
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2"><office:body><office:text><text:p>{text}</text:p></office:text></office:body></office:document-content>'''
    styles = '''<?xml version="1.0" encoding="UTF-8"?><office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" office:version="1.2"/>'''
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as odt:
        odt.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        odt.writestr("content.xml", content)
        odt.writestr("styles.xml", styles)


def _write_flag_template_odt(path) -> None:
    content = '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2"><office:body><office:text><text:p text:style-name="HeaderCenter">DECLARACAO</text:p><text:p text:style-name="BodyJustify">Declaro junto ao <text:span>[</text:span><text:span text:style-name="BoldText">INSTITUICAO_ENSINO</text:span><text:span>]</text:span>, que <text:span>[</text:span><text:span>NOME_COMPLETO</text:span><text:span>]</text:span>, CPF <text:span>[CPF]</text:span>, serviu em <text:span>[DATA_SERVICO]</text:span>.</text:p><text:p text:style-name="SignatureCenter"><text:span>[ASSINATURA_NOME]</text:span></text:p></office:text></office:body></office:document-content>'''
    styles = '''<?xml version="1.0" encoding="UTF-8"?><office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" office:version="1.2"><office:styles/></office:document-styles>'''
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as odt:
        odt.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        odt.writestr("content.xml", content)
        odt.writestr("styles.xml", styles)
        odt.writestr("Pictures/logo.txt", "LOGO")
        odt.writestr("META-INF/manifest.xml", "<manifest/>")


def _odt_text(content_xml: bytes) -> str:
    from xml.etree import ElementTree as ET

    return "".join(ET.fromstring(content_xml).itertext())

from pathlib import Path

from apps.web.routes import compilador_folha as route


def test_pdf_alteracoes_upload_role_is_input_bi_pdf():
    assert route._alteracoes_role_for_upload(Path("alteracoes.pdf")) == "INPUT_BI_PDF"


def test_odt_alteracoes_upload_role_is_input_bi_odt():
    assert route._alteracoes_role_for_upload(Path("alteracoes.odt")) == "INPUT_BI_ODT"


def test_pdf_alteracoes_never_becomes_input_bi_odt():
    role = route._alteracoes_role_for_upload(Path("boletim.pdf"))

    assert role == "INPUT_BI_PDF"
    assert role != "INPUT_BI_ODT"


def test_modelo_roles_are_separate_from_bi_odt():
    assert "INPUT_MODELO_ODT" in route.MODELO_ROLES
    assert "INTERNAL_DEFAULT_MODELO_ODT" in route.MODELO_ROLES
    assert "INPUT_MODELO_ODT" not in route.ALTERACOES_ODT_ROLES
    assert "INTERNAL_DEFAULT_MODELO_ODT" not in route.ALTERACOES_ODT_ROLES


def test_memory_bi_pdf_and_odt_roles_are_supported():
    assert "MEMORY_REFERENCE_BI_PDF" in route.ALTERACOES_PDF_ROLES
    assert "MEMORY_REFERENCE_BI_ODT" in route.ALTERACOES_ODT_ROLES

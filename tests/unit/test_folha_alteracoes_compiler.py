from datetime import date

from modules.compilador.application.folha_alteracoes_compiler import (
    TableBlock,
    format_admin_days,
    nome_completo_xml,
    period_bounds,
    table_xml,
)


def test_app_import_exposes_app():
    from apps.web.app import app

    assert app is not None


def test_period_bounds_second_semester_2025():
    start, end, label = period_bounds(2025, "2")

    assert start == date(2025, 7, 1)
    assert end == date(2025, 12, 31)
    assert "2025" in label


def test_format_admin_days():
    assert format_admin_days(0) == "00a00m00d"
    assert format_admin_days(180) == "00a06m00d"


def test_nome_completo_xml_bolds_only_nome_guerra():
    xml = nome_completo_xml("JOAO SILVA SANTOS", "SILVA")

    assert "JOAO " in xml
    assert '<text:span text:style-name="Bold">SILVA</text:span>' in xml
    assert " SANTOS" in xml


def test_table_xml_renders_real_odt_table_tags():
    xml = table_xml(
        TableBlock(
            title="Fiscalizacao",
            columns=["Designado", "Funcao"],
            rows=[["1 Sgt SILVA", "Fiscal"]],
        )
    )

    assert "<table:table" in xml
    assert "<table:table-row>" in xml
    assert "<table:table-cell" in xml

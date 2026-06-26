from modules.compilador.application.folha_alteracoes_compiler import CompilerOptions, first_part_xml
from modules.compilador.application.folha_format_contract import (
    EMPTY_MONTH_BLOCK,
    EMPTY_MONTH_COMPACT_PLURAL,
    EMPTY_MONTH_COMPACT_SINGULAR,
)


def test_empty_month_block_mode():
    xml = first_part_xml([], CompilerOptions(semestre="2", empty_month_mode=EMPTY_MONTH_BLOCK))

    assert "DEZEMBRO:" in xml
    assert "Sem alterações." in xml
    assert "DEZEMBRO: Sem Alteração." not in xml


def test_empty_month_compact_singular_mode():
    xml = first_part_xml([], CompilerOptions(semestre="2", empty_month_mode=EMPTY_MONTH_COMPACT_SINGULAR))

    assert "DEZEMBRO: Sem Alteração." in xml
    assert "<text:p text:style-name=\"Standard\">Sem alterações.</text:p>" not in xml


def test_empty_month_compact_plural_mode():
    xml = first_part_xml([], CompilerOptions(semestre="1", empty_month_mode=EMPTY_MONTH_COMPACT_PLURAL))

    assert "JANEIRO: Sem alterações." in xml
    assert "JUNHO: Sem alterações." in xml

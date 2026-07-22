import xml.etree.ElementTree as ET

from modules.compilador.application.folha_alteracoes_compiler import (
    CompilerOptions,
    SicapexProfile,
    TimeSummary,
    sisges_flag_values,
)
from modules.compilador.application.odt_template_policy import (
    SISGES_FLAG_DATA_LOCAL,
    SISGES_FLAG_TC,
    SISGES_FLAG_TSCMM,
    SISGES_FLAG_TSSD,
    SISGES_FLAG_TTES,
    TIME_VALUE_FLAGS,
)


def _times() -> TimeSummary:
    return TimeSummary(
        tc="00a06m00d",
        tc_arreg="00a06m00d",
        tc_nao_arreg="00a00m00d",
        tc_transito="00a00m00d",
        tc_instalacao="00a00m00d",
        tnc="00a00m00d",
        tscmm="36a10m23d",
        tssd="00a00m00d",
        tsnr="02a08m00d",
        ttes="39a06m23d",
        origem="TRANSCRITO_DE_FOLHA_PDF",
        dias_reais_ttes=0,
        dias_reais_tnc=0,
    )


def test_sisges_flag_values_incluem_tempos_da_segunda_parte():
    values = sisges_flag_values(
        SicapexProfile(nome_completo="MILITAR TESTE"),
        [],
        _times(),
        "2º SEMESTRE DE 2025",
        CompilerOptions(ano=2025, semestre="2"),
    )

    assert values[SISGES_FLAG_TC] == "00a06m00d"
    assert values[SISGES_FLAG_TSSD] == "00a00m00d"
    assert values[SISGES_FLAG_TSCMM] == "36a10m23d"
    assert values[SISGES_FLAG_TTES] == "39a06m23d"
    for flag in TIME_VALUE_FLAGS:
        assert flag in values


def test_data_local_configuravel_nas_options():
    custom = "Quartel-General do Exército - Brasília - DF, 05 de fevereiro de 2026"
    values = sisges_flag_values(
        SicapexProfile(),
        [],
        _times(),
        "2º SEMESTRE DE 2025",
        CompilerOptions(ano=2025, semestre="2", data_local=custom),
    )
    assert values[SISGES_FLAG_DATA_LOCAL] == custom

    default_values = sisges_flag_values(
        SicapexProfile(),
        [],
        _times(),
        "2º SEMESTRE DE 2025",
        CompilerOptions(ano=2025, semestre="2"),
    )
    assert "2026" in default_values[SISGES_FLAG_DATA_LOCAL]


def test_data_local_propaga_para_assinatura_e_corpo():
    from modules.compilador.application.folha_alteracoes_compiler import (
        assinatura_xml,
        build_body_xml,
    )

    custom = "Quartel-General do Exército - Brasília - DF, 05 de fevereiro de 2026"

    assert custom in assinatura_xml("FULANO - Cel", "Cmt", custom)
    assert "2026" in assinatura_xml("FULANO - Cel", "Cmt")

    body_custom = build_body_xml(
        SicapexProfile(nome_completo="MILITAR TESTE"),
        [],
        _times(),
        "2º SEMESTRE DE 2025",
        CompilerOptions(ano=2025, semestre="2", data_local=custom),
    )
    assert custom in body_custom

    body_default = build_body_xml(
        SicapexProfile(nome_completo="MILITAR TESTE"),
        [],
        _times(),
        "2º SEMESTRE DE 2025",
        CompilerOptions(ano=2025, semestre="2"),
    )
    assert "1° de janeiro de 2026" in body_default


def test_injecao_de_header_ignora_paragrafo_autofechado():
    """Regressao: <text:p/> antes do header nao pode engolir o paragrafo seguinte."""
    from modules.compilador.application.odt_template_policy import (
        inject_continuation_header_flags,
    )

    styles = (
        '<office:document-styles'
        ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        "<office:master-styles>"
        '<style:master-page style:name="Standard"><style:header>'
        '<text:p text:style-name="MP13"/>'
        "<text:p>2º SEMESTRE DE 2023 PERÍODO: 1º JUL A 31 DEZ</text:p>"
        "</style:header></style:master-page>"
        "</office:master-styles>"
        "</office:document-styles>"
    )

    rewritten, validations = inject_continuation_header_flags(styles)

    assert "OK_HEADER_CONTINUACAO_FLAGS_INJETADOS" in validations
    assert "[SISGES_SEMESTRE_TEXTO]" in rewritten
    assert "2023" not in rewritten
    ET.fromstring(rewritten.encode("utf-8"))  # XML permanece valido

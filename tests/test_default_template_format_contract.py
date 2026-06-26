import zipfile
from xml.etree import ElementTree as ET

from modules.compilador.application.default_odt_template import ensure_default_folha_template
from modules.compilador.application.folha_alteracoes_compiler import (
    CompilerOptions,
    SicapexProfile,
    TimeSummary,
    render_final_odt,
)
from modules.compilador.application.folha_format_contract import (
    EMPTY_MONTH_COMPACT_SINGULAR,
    default_folha_format_contract,
)
from modules.compilador.application.odt_template_policy import REQUIRED_SISGES_MARKERS


def test_default_template_is_valid_odt_with_required_parts(tmp_path):
    template = ensure_default_folha_template(
        tmp_path,
        contract=default_folha_format_contract(empty_month_mode=EMPTY_MONTH_COMPACT_SINGULAR),
    )

    with zipfile.ZipFile(template) as odt:
        names = set(odt.namelist())
        content = odt.read("content.xml").decode("utf-8")
        styles = odt.read("styles.xml").decode("utf-8")

    assert "content.xml" in names
    assert "styles.xml" in names
    ET.fromstring(content.encode("utf-8"))
    ET.fromstring(styles.encode("utf-8"))
    for marker in REQUIRED_SISGES_MARKERS:
        assert marker in content
    assert "ALFA" not in content


def test_render_with_default_template_applies_contract_without_fixed_signer(tmp_path):
    template = ensure_default_folha_template(tmp_path)
    output = tmp_path / "folha.odt"

    render_final_odt(
        output_path=output,
        profile=SicapexProfile(
            nome_completo="MILITAR TESTE",
            nome_guerra="TESTE",
            graduacao_abrev="3o Sgt",
            graduacao_extenso="Terceiro-Sargento",
            qm="COMUNICACOES",
            identidade="0000000000",
            comportamento="EXCEPCIONAL",
        ),
        events=[],
        times=_times(),
        period_label="2o SEMESTRE DE 2025",
        options=CompilerOptions(semestre="2", empty_month_mode=EMPTY_MONTH_COMPACT_SINGULAR),
        template_odt_path=template,
    )

    with zipfile.ZipFile(output) as odt:
        content = odt.read("content.xml").decode("utf-8")

    assert "1ª PARTE" in content
    assert "2ª PARTE" in content
    assert "DEZEMBRO: Sem Alteração." in content
    assert "ASSINATURA_NOME" not in content
    assert "ALFA" not in content


def _times() -> TimeSummary:
    return TimeSummary(
        tc="00a06m00d",
        tc_arreg="00a06m00d",
        tc_nao_arreg="00a00m00d",
        tc_transito="00a00m00d",
        tc_instalacao="00a00m00d",
        tnc="00a00m00d",
        tscmm="16a05m09d",
        tssd="00a00m00d",
        tsnr="01a09m10d",
        ttes="18a02m19d",
        origem="SICAPEX_BANCO_SISGES",
        dias_reais_ttes=6570,
        dias_reais_tnc=0,
    )

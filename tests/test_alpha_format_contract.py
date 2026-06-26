import json
import zipfile

from modules.compilador.application.default_odt_template import ensure_default_folha_template
from modules.compilador.application.event_filter_policy import decide_event_filter
from modules.compilador.application.folha_alteracoes_compiler import (
    CompilerOptions,
    SicapexProfile,
    TimeSummary,
    first_part_xml,
    render_final_odt,
)
from modules.compilador.application.folha_format_contract import (
    EMPTY_MONTH_COMPACT_SINGULAR,
    alpha_visual_format_contract,
)
from scripts.validate_folha_format import validate_format


def test_alpha_contract_accepts_compact_singular_empty_month():
    contract = alpha_visual_format_contract()

    assert contract.empty_month_mode == EMPTY_MONTH_COMPACT_SINGULAR
    assert "DEZEMBRO: Sem Alteração." in first_part_xml(
        [],
        CompilerOptions(semestre="2", empty_month_mode=contract.empty_month_mode),
    )


def test_qms_comunicacoes_is_clean_and_generic_does_not_leak(tmp_path):
    odt = tmp_path / "folha.odt"
    render_final_odt(
        output_path=odt,
        profile=SicapexProfile(
            nome_completo="ALFA SÁ TELES SILVA",
            nome_guerra="ALFA",
            graduacao_abrev="3º Sgt",
            graduacao_extenso="Terceiro-Sargento",
            qm="COMUNICAÇÕES",
            identidade="9990000001",
            comportamento="EXCEPCIONAL",
        ),
        events=[],
        times=_times(),
        period_label="2º SEMESTRE DE 2025",
        options=CompilerOptions(semestre="2", empty_month_mode=EMPTY_MONTH_COMPACT_SINGULAR),
        template_odt_path=ensure_default_folha_template(tmp_path),
    )

    content = _content(odt)
    assert "COMUNICAÇÕES" in content
    assert "QUALQUER QMG" not in content
    assert "MANUTENÇÃO DE VIATURA" not in content


def test_header_can_be_detected_in_styles_or_content(tmp_path):
    template = ensure_default_folha_template(tmp_path)
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(
        json.dumps({"empty_month": {"mode": "COMPACT_SINGULAR"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = validate_format(template, contract_path)

    codes = {item["code"] for item in result["validations"]}
    assert "OK_HEADER_IN_CONTENT_OR_STYLES_XML" in codes
    assert "OK_HEADER_IN_CONTENT_XML" in codes


def test_header_can_be_detected_in_styles_xml(tmp_path):
    odt_path = tmp_path / "header_styles.odt"
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(
        json.dumps({"empty_month": {"mode": "COMPACT_SINGULAR"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    with zipfile.ZipFile(odt_path, "w") as odt:
        odt.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        odt.writestr("content.xml", _content_without_header())
        odt.writestr("styles.xml", _styles_with_header())

    result = validate_format(odt_path, contract_path)

    codes = {item["code"] for item in result["validations"]}
    assert "OK_HEADER_IN_CONTENT_OR_STYLES_XML" in codes
    assert "OK_HEADER_IN_STYLES_XML" in codes
    assert "ERR_HEADER_NOT_FOUND" not in codes


def test_signature_is_validated_as_block_not_fixed_name(tmp_path):
    template = ensure_default_folha_template(tmp_path)
    content = _content(template)

    assert "{{ASSINATURA_NOME}}" in content
    assert "ALFA" not in content


def test_table_filtered_policy_and_beneficiary_filter_are_explainable():
    contract = alpha_visual_format_contract()
    decision = decide_event_filter("DECLARAÇÃO DE BENEFICIÁRIO - Atualização")
    filtered = decision.to_filtered_event(
        titulo="DECLARAÇÃO DE BENEFICIÁRIO - Atualização",
        source_bi="BI Nº 84",
    )

    assert contract.table_policy == "FILTERED_TO_MILITAR_ALLOWED"
    assert filtered["reason"] == "EVENTO_BENEFICIARIO_PRIVACIDADE"


def test_segunda_parte_order_is_contractual():
    xml = _times_xml()

    positions = [xml.index(token) for token in ("TC)", "TNC)", "MEDALHA", "TSSD", "TSNR", "TTES")]
    assert positions == sorted(positions)


def test_final_odt_contains_primeira_parte_comportamento_and_segunda_parte(tmp_path):
    odt = tmp_path / "folha.odt"
    render_final_odt(
        output_path=odt,
        profile=SicapexProfile(
            nome_completo="ALFA SÁ TELES SILVA",
            nome_guerra="ALFA",
            graduacao_abrev="3º Sgt",
            qm="COMUNICAÇÕES",
            identidade="9990000001",
            comportamento="EXCEPCIONAL",
        ),
        events=[],
        times=_times(),
        period_label="2º SEMESTRE DE 2025",
        options=CompilerOptions(semestre="2", empty_month_mode=EMPTY_MONTH_COMPACT_SINGULAR),
        template_odt_path=ensure_default_folha_template(tmp_path),
    )

    content = _content(odt)
    assert "1ª PARTE" in content
    assert "COMPORTAMENTO" in content
    assert "2ª PARTE" in content


def _content(odt_path):
    with zipfile.ZipFile(odt_path) as odt:
        return odt.read("content.xml").decode("utf-8")


def _content_without_header():
    return """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
  office:version="1.2">
  <office:body>
    <office:text>
      <text:p>1ª PARTE</text:p>
      <text:p>DEZEMBRO: Sem Alteração.</text:p>
      <text:p>COMPORTAMENTO</text:p>
      <text:p>2ª PARTE</text:p>
      <text:p>S Cmt B Adm QGEx</text:p>
    </office:text>
  </office:body>
</office:document-content>
"""


def _styles_with_header():
    return """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
  office:version="1.2">
  <office:master-styles>
    <style:master-page style:name="Standard">
      <style:header>
        <text:p xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">NOME</text:p>
      </style:header>
    </style:master-page>
  </office:master-styles>
</office:document-styles>
"""


def _times_xml():
    from modules.compilador.application.folha_alteracoes_compiler import times_table_xml

    return times_table_xml(_times())


def _times():
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

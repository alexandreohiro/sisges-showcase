from __future__ import annotations

import zipfile

from modules.compilador.application.folha_alteracoes_compiler import (
    CompilerOptions,
    SicapexProfile,
    TimeSummary,
    render_final_odt,
)


def test_header_uses_bold_only_for_nome_guerra_and_normalized_qms(tmp_path):
    output = tmp_path / "folha.odt"
    profile = SicapexProfile(
        nome_completo="JOAO MATERIAL BELICO SILVA",
        nome_guerra="MATERIAL BELICO",
        graduacao_abrev="1º Sgt",
        graduacao_extenso="Primeiro-Sargento",
        qm="MATERIAL BÉLICO/MANUTENÇÃO DE VIATURA AUTO",
        identidade="9990000001",
        comportamento="ÓTIMO",
    )
    render_final_odt(
        output_path=output,
        profile=profile,
        events=[],
        times=times(),
        period_label="2º SEMESTRE DE 2025",
        options=CompilerOptions(),
    )

    with zipfile.ZipFile(output) as zin:
        content = zin.read("content.xml").decode("utf-8")

    assert "JOAO " in content
    assert '<text:span text:style-name="Bold">MATERIAL BELICO</text:span>' in content
    assert "Primeiro-Sargento" in content
    assert "9990000001" in content
    assert "MATERIAL BÉLICO" in content
    assert "MANUTENÇÃO DE VIATURA" not in content
    assert "QUALQUER QMG" not in content


def test_header_hides_generic_qms(tmp_path):
    output = tmp_path / "folha.odt"
    profile = SicapexProfile(
        nome_completo="MILITAR TESTE",
        nome_guerra="TESTE",
        graduacao_abrev="3º Sgt",
        graduacao_extenso="3º Sgt",
        qm="QMG 00-QUALQUER QMG / QUALQUER QMP",
        identidade="9990000001",
    )
    render_final_odt(
        output_path=output,
        profile=profile,
        events=[],
        times=times(),
        period_label="2º SEMESTRE DE 2025",
        options=CompilerOptions(),
    )

    with zipfile.ZipFile(output) as zin:
        content = zin.read("content.xml").decode("utf-8")

    assert "QUALQUER QMG" not in content
    assert "QUALQUER QMP" not in content


def times() -> TimeSummary:
    return TimeSummary(
        tc="00a06m00d",
        tc_arreg="00a06m00d",
        tc_nao_arreg="00a00m00d",
        tc_transito="00a00m00d",
        tc_instalacao="00a00m00d",
        tnc="00a00m00d",
        tscmm="01a00m00d",
        tssd="00a00m00d",
        tsnr="00a00m00d",
        ttes="01a00m00d",
        origem="SICAPEX_BANCO_SISGES",
        dias_reais_ttes=360,
        dias_reais_tnc=0,
    )

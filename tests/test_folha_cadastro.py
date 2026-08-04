"""Testes da reconciliacao perfil (PDF) x cadastro de militares (banco).

Fixtures 100% sinteticas (LGPD).
"""

from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

from modules.compilador.application.folha_cadastro import (
    SQLITE_MILITAR_DDL,
    carregar_cadastro,
    reconciliar_perfil,
)
from modules.compilador.application.folha_models import (
    CompilerOptions,
    SicapexProfile,
)
from modules.compilador.application.folha_time_calc import TimeSummary


def _cadastro_sqlite(path: Path) -> Path:
    con = sqlite3.connect(path)
    con.executescript(SQLITE_MILITAR_DDL)
    con.execute(
        "insert into militar (identidade, nome_completo, nome_guerra, posto_graduacao, qas_qms)"
        " values ('9990000001', 'MILITAR SINTETICA DE TESTE', 'TESTE', 'Cap', 'INTENDÊNCIA')"
    )
    con.commit()
    con.close()
    return path


def _times() -> TimeSummary:
    return TimeSummary(
        tc="00a06m00d", tc_arreg="00a06m00d", tc_nao_arreg="00a00m00d",
        tc_transito="00a00m00d", tc_instalacao="00a00m00d", tnc="00a00m00d",
        tscmm="00a00m00d", tssd="00a00m00d", tsnr="00a00m00d", ttes="00a06m00d",
        origem="TRANSCRITO_DE_FOLHA_PDF", dias_reais_ttes=0, dias_reais_tnc=0,
    )


def test_match_por_identidade_preenche_nome_de_guerra_e_reporta_divergencias(tmp_path):
    cadastro = carregar_cadastro(_cadastro_sqlite(tmp_path / "cadastro.db"))
    profile = SicapexProfile(
        nome_completo="MILITAR SINTETICA D TESTE",  # PDF truncou o nome
        identidade="999000000-1",
        graduacao_abrev="S Ten",  # PDF desatualizado
    )

    profile, validations = reconciliar_perfil(profile, cadastro)

    assert profile.nome_completo == "MILITAR SINTETICA DE TESTE"
    assert profile.nome_guerra == "TESTE"
    assert profile.graduacao_abrev == "Cap"
    assert profile.qm == "INTENDÊNCIA"
    assert any(v.startswith("OK_CADASTRO_ENCONTRADO") for v in validations)
    assert any(v.startswith("WARN_NOME_DIVERGENTE_CADASTRO") for v in validations)
    assert any(v.startswith("WARN_GRADUACAO_DIVERGENTE_CADASTRO") for v in validations)


def test_match_por_nome_quando_pdf_nao_tem_identidade(tmp_path):
    cadastro = carregar_cadastro(_cadastro_sqlite(tmp_path / "cadastro.db"))
    profile = SicapexProfile(nome_completo="Militar Sintetica de Teste")

    profile, validations = reconciliar_perfil(profile, cadastro)

    assert profile.identidade == "999000000-1"
    assert profile.nome_guerra == "TESTE"
    assert any(v.startswith("OK_CADASTRO_ENCONTRADO") for v in validations)


def test_sem_cadastro_mantem_pdf_e_avisa(tmp_path):
    cadastro = carregar_cadastro(_cadastro_sqlite(tmp_path / "cadastro.db"))
    profile = SicapexProfile(nome_completo="OUTRA PESSOA QUALQUER", identidade="111111111-1")

    profile, validations = reconciliar_perfil(profile, cadastro)

    assert profile.nome_completo == "OUTRA PESSOA QUALQUER"
    assert profile.nome_guerra == ""
    assert any(v.startswith("WARN_MILITAR_SEM_CADASTRO") for v in validations)


def test_cadastro_csv(tmp_path):
    csv_path = tmp_path / "cadastro.csv"
    csv_path.write_text(
        "identidade,nome_completo,nome_guerra,posto_graduacao,qas_qms\n"
        "9990000002,FULANO EXEMPLO DA SILVA,EXEMPLO,3º Sgt,CAVALARIA\n",
        encoding="utf-8",
    )
    cadastro = carregar_cadastro(csv_path)
    profile, validations = reconciliar_perfil(
        SicapexProfile(identidade="999000000-2"), cadastro
    )

    assert profile.nome_guerra == "EXEMPLO"
    assert any(v.startswith("OK_CADASTRO_ENCONTRADO") for v in validations)


def test_nome_de_guerra_sai_em_negrito_no_render_com_flags(tmp_path):
    """Ponta a ponta: flag [SISGES_NOME] rende span Bold no nome de guerra."""
    from modules.compilador.application.folha_alteracoes_compiler import render_final_odt
    from scripts.parametrizar_modelo_folha import garantir_estilo_bold

    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content'
        ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"'
        ' xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">'
        "<office:automatic-styles/>"
        "<office:body><office:text>"
        "<text:p>NOME: [SISGES_NOME]</text:p>"
        "<text:p>[SISGES_GRADUACAO] [SISGES_QMS] [SISGES_IDENTIDADE]</text:p>"
        "<text:p>[SISGES_SEMESTRE_TEXTO] [SISGES_PERIODO]</text:p>"
        "<text:p>[SISGES_PARTE_1]</text:p><text:p>[SISGES_COMPORTAMENTO]</text:p>"
        "<text:p>[SISGES_DATA_LOCAL]</text:p>"
        "<text:p>[SISGES_ASSINATURA_NOME]</text:p><text:p>[SISGES_ASSINATURA_FUNCAO]</text:p>"
        "</office:text></office:body></office:document-content>"
    )
    content, _ = garantir_estilo_bold(content, "office:automatic-styles")
    template = tmp_path / "modelo.odt"
    with zipfile.ZipFile(template, "w") as zout:
        zout.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        zout.writestr("content.xml", content)
        zout.writestr(
            "styles.xml",
            '<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"/>',
        )
        zout.writestr("META-INF/manifest.xml", "<m/>")

    profile = SicapexProfile(
        nome_completo="MILITAR SINTETICA DE TESTE",
        nome_guerra="TESTE",
        graduacao_abrev="Cap",
        graduacao_extenso="Capitão",
        identidade="999000000-1",
    )
    output = tmp_path / "saida.odt"
    result = render_final_odt(
        output_path=output,
        profile=profile,
        events=[],
        times=_times(),
        period_label="1º SEMESTRE DE 2026",
        options=CompilerOptions(ano=2026, semestre="1"),
        template_odt_path=template,
    )

    assert result.template_used is True
    with zipfile.ZipFile(output) as zout:
        rendered = zout.read("content.xml").decode("utf-8")
    assert 'NOME: MILITAR SINTETICA DE <text:span text:style-name="Bold">TESTE</text:span>' in rendered
    assert 'style:name="Bold"' in rendered

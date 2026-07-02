"""Testes do vínculo militar-OM no compilador de Folhas de Alterações.

Base normativa: EB30-N-10.002 (Port. 063-DGP/C Ex, 25 MAR 2020):
- Art. 20/21: o vínculo começa na inclusão e cessa no desligamento; nenhum
  tempo pode ser contado fora da janela [incorporação, desligamento].
- Art. 24: 2ª Parte com os títulos I-TC, II-TNC, III-TSSD, IV-TSCMM,
  V-TSNR e VI-TTES, nesta ordem, mesmo sem alterações.
- Anexo B: todo mês do período aparece no corpo, ainda que "Sem alterações".

Fixtures 100% sintéticas (LGPD). Caso base: incorporação em 13 FEV 2023,
licenciamento a contar de 31 JAN 2024 (dia do licenciamento NÃO conta —
convenção exclusive; ver docs/decisions/0001-contagem-vinculo-folhas.md).
"""

from datetime import date
from pathlib import Path
import re
import zipfile

from modules.compilador.application.folha_alteracoes_compiler import (
    FolhaAlteracoesCompiler,
    times_table_xml,
)
from modules.compilador.application.folha_event_validation import (
    normalize_semester_events,
)
from modules.compilador.application.folha_models import (
    CompilerOptions,
    EventBlock,
    SicapexProfile,
)
from modules.compilador.application.folha_time_calc import (
    calculate_times_from_sicapex,
)
from modules.compilador.application.odt_template_policy import (
    REQUIRED_SISGES_FLAGS,
)


INCORPORACAO = date(2023, 2, 13)
LICENCIAMENTO = date(2024, 1, 31)  # "a contar de" — dia não conta (exclusive)


def _profile() -> SicapexProfile:
    return SicapexProfile(
        nome_completo="MILITAR SINTETICA DE TESTE",
        nome_guerra="TESTE",
        graduacao_abrev="Sd",
        identidade="9990000001",
        data_praca=INCORPORACAO,
        data_desligamento=LICENCIAMENTO,
    )


def _content_xml(odt_path: Path) -> str:
    with zipfile.ZipFile(odt_path, "r") as zin:
        return zin.read("content.xml").decode("utf-8")


def _styles_xml(odt_path: Path) -> str:
    with zipfile.ZipFile(odt_path, "r") as zin:
        return zin.read("styles.xml").decode("utf-8")


def _write_bi_odt(path: Path, paragraphs: list[str]) -> Path:
    body = "".join(f"<text:p>{text}</text:p>" for text in paragraphs)
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content'
        ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        ' office:version="1.2">'
        f"<office:body><office:text>{body}</office:text></office:body>"
        "</office:document-content>"
    )
    with zipfile.ZipFile(path, "w") as zout:
        zout.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        zout.writestr("content.xml", content)
        zout.writestr("styles.xml", "<office:document-styles xmlns:office=\"urn:oasis:names:tc:opendocument:xmlns:office:1.0\"/>")
        zout.writestr("META-INF/manifest.xml", "<manifest:manifest xmlns:manifest=\"urn:oasis:names:tc:opendocument:xmlns:manifest:1.0\"/>")
    return path


# ---------------------------------------------------------------------------
# RC1 — tempos respeitam a janela do vínculo (Art. 20/21)
# ---------------------------------------------------------------------------


def test_tc_respeita_incorporacao():
    """2023/1: vínculo começa em 13 FEV → TC = 13 FEV a 30 JUN = 00a04m18d."""
    times = calculate_times_from_sicapex(_profile(), date(2023, 1, 1), date(2023, 6, 30))

    assert times.tc == "00a04m18d"
    assert times.tnc == "00a00m00d"
    assert times.ttes == "00a04m18d"


def test_tc_respeita_licenciamento():
    """2024/1: licenciamento a contar de 31 JAN → TC = 1º a 30 JAN = 00a01m00d."""
    times_2023_2 = calculate_times_from_sicapex(_profile(), date(2023, 7, 1), date(2023, 12, 31))
    assert times_2023_2.tc == "00a06m00d"
    assert times_2023_2.ttes == "00a10m18d"

    times_2024_1 = calculate_times_from_sicapex(_profile(), date(2024, 1, 1), date(2024, 6, 30))
    assert times_2024_1.tc == "00a01m00d"
    assert times_2024_1.tnc == "00a00m00d"
    assert times_2024_1.ttes == "00a11m18d"


# ---------------------------------------------------------------------------
# RC2 — eventos filtrados por data completa (dia/mês/ANO), sem descarte mudo
# ---------------------------------------------------------------------------


def test_evento_fora_do_ano_rejeitado(tmp_path):
    """Evento de 17 JAN 24 não pode entrar na folha do 1º semestre de 2023."""
    bi = _write_bi_odt(
        tmp_path / "bi.odt",
        [
            "JANEIRO:",
            "APRESENTACAO DE MILITAR",
            "- a 5, BI Nº 10 :",
            "Apresentou-se em 17 JAN 24 a militar por motivo de convocacao.",
        ],
    )
    result = FolhaAlteracoesCompiler().compile(
        bi_odt_path=bi,
        output_path=tmp_path / "out" / "folha.odt",
        options=CompilerOptions(ano=2023, semestre="1"),
    )

    validation_text = "\n".join(result.validation)
    assert "ERR_EVENT_FORA_DO_PERIODO" in validation_text
    assert "17 JAN 24" not in _content_xml(result.output_path)


def test_evento_sem_data_mantido_com_warn():
    """Evento sem data extraível permanece na folha, com aviso para revisão."""
    events = [
        EventBlock(
            mes="MARÇO",
            titulo="ELOGIO INDIVIDUAL",
            referencia="- a 3, BI Nº 45 :",
            corpo="Militar elogiada pela dedicacao no servico de escala.",
        )
    ]

    kept, validations = normalize_semester_events(events, "1", ano=2023)

    assert len(kept) == 1
    assert kept[0].titulo == "ELOGIO INDIVIDUAL"
    assert any(item.startswith("WARN_EVENT_SEM_DATA") for item in validations)


# ---------------------------------------------------------------------------
# RC3 — headers de continuação sincronizados com o período do documento
# ---------------------------------------------------------------------------


def _write_template_odt(path: Path) -> Path:
    flags = "".join(f"<text:p>{flag}</text:p>" for flag in REQUIRED_SISGES_FLAGS)
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content'
        ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        ' office:version="1.2">'
        f"<office:body><office:text>{flags}</office:text></office:body>"
        "</office:document-content>"
    )
    # Master pages com texto ESTÁTICO de outro período (bug RC3): primeira
    # página e página de continuação, como nos templates de usuário.
    styles = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-styles'
        ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        ' office:version="1.2">'
        "<office:master-styles>"
        '<style:master-page style:name="Primeira">'
        "<style:header>"
        "<text:p>2º SEMESTRE DE 2023 PERÍODO: 1º JUL A 31 DEZ</text:p>"
        "</style:header>"
        "</style:master-page>"
        '<style:master-page style:name="Continuacao">'
        "<style:header>"
        "<text:p>Continuação das Folhas de Alterações</text:p>"
        "<text:p>2º SEMESTRE DE 2023 PERÍODO: 1º JUL A 31 DEZ</text:p>"
        "</style:header>"
        "</style:master-page>"
        "</office:master-styles>"
        "</office:document-styles>"
    )
    with zipfile.ZipFile(path, "w") as zout:
        zout.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        zout.writestr("content.xml", content)
        zout.writestr("styles.xml", styles)
        zout.writestr("META-INF/manifest.xml", "<manifest:manifest xmlns:manifest=\"urn:oasis:names:tc:opendocument:xmlns:manifest:1.0\"/>")
    return path


def test_headers_continuacao_sincronizados(tmp_path):
    """Render de 2024/1 não pode sair com header de continuação de 2023."""
    bi = _write_bi_odt(
        tmp_path / "bi.odt",
        ["JANEIRO:", "APRESENTACAO DE MILITAR", "- a 5, BI Nº 10 :", "Apresentou-se em 17 JAN 24 a militar."],
    )
    template = _write_template_odt(tmp_path / "modelo.odt")

    result = FolhaAlteracoesCompiler().compile(
        bi_odt_path=bi,
        output_path=tmp_path / "out" / "folha.odt",
        options=CompilerOptions(ano=2024, semestre="1"),
        template_odt_path=template,
    )

    styles = _styles_xml(result.output_path)
    header_texts = re.sub(r"<[^>]+>", " ", styles)
    assert "2023" not in header_texts
    validation_text = "\n".join(result.validation)
    assert "ERR_HEADER_CONTINUACAO_DIVERGENTE" not in validation_text


# ---------------------------------------------------------------------------
# Art. 24 / Anexo B — ordem dos títulos da 2ª Parte
# ---------------------------------------------------------------------------


def test_ordem_segunda_parte_anexo_b():
    """2ª Parte deve listar TC, TNC, TSSD, TSCMM, TSNR e TTES, nesta ordem."""
    times = calculate_times_from_sicapex(_profile(), date(2023, 1, 1), date(2023, 6, 30))
    xml = times_table_xml(times)
    plain = re.sub(r"<[^>]+>", "\n", xml)

    titles = [line for line in plain.splitlines() if re.match(r"^\d\.\s", line.strip())]
    siglas = [re.search(r"\((TC|TNC|TSSD|TSCMM|TSNR|TTES)\)", t).group(1) for t in titles]

    assert siglas == ["TC", "TNC", "TSSD", "TSCMM", "TSNR", "TTES"]
    for subitem in ("Arregimentado", "Não arregimentado", "Trânsito", "Instalação"):
        assert subitem in plain


# ---------------------------------------------------------------------------
# Anexo B — meses sem alteração presentes no corpo
# ---------------------------------------------------------------------------


def test_meses_sem_alteracao_presentes(tmp_path):
    """2023/2 com evento só em JUL: SET/OUT/NOV/DEZ constam como sem alteração."""
    bi = _write_bi_odt(
        tmp_path / "bi.odt",
        [
            "JULHO:",
            "APRESENTACAO DE MILITAR",
            "- a 5, BI Nº 120 :",
            "Apresentou-se em 03 JUL 23 a militar de servico.",
        ],
    )
    result = FolhaAlteracoesCompiler().compile(
        bi_odt_path=bi,
        output_path=tmp_path / "out" / "folha.odt",
        options=CompilerOptions(ano=2023, semestre="2"),
    )

    content = _content_xml(result.output_path)
    for month in ("SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"):
        assert month in content
    assert "Sem alterações." in content


# ---------------------------------------------------------------------------
# RC4 — validação de ingestão: data_praca × evento de convocação/inclusão
# ---------------------------------------------------------------------------


def test_data_praca_divergente_do_evento_de_convocacao_gera_warn():
    """data_praca deve casar com o "a contar de" do evento de convocação."""
    from modules.compilador.application.folha_event_validation import (
        validate_data_praca_against_events,
    )

    profile = _profile()
    profile.data_praca = date(2023, 1, 1)  # registro suspeito
    events = [
        EventBlock(
            mes="FEVEREIRO",
            titulo="APRESENTACAO DE MILITAR CONVOCADA",
            referencia="- a 2, BI Nº 30 :",
            corpo="Apresentou-se a militar, convocada a contar de 13 FEV 23.",
        )
    ]

    validations = validate_data_praca_against_events(profile, events)

    assert any(item.startswith("WARN_DATA_PRACA_DIVERGENTE") for item in validations)

    profile.data_praca = INCORPORACAO
    assert validate_data_praca_against_events(profile, events) == []

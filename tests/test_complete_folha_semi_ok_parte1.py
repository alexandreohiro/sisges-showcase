from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from scripts.complete_folha_semi_ok_parte1 import (
    NS,
    PairItem,
    ProcessResult,
    SISGES_PARTE1_STYLE_EVENT_TITLE,
    STYLE_NAME,
    classify_file,
    clean_parte1_lines,
    collect_final_odts,
    ensure_required_months,
    extract_parte1_from_source,
    find_modelo_odt,
    militar_output_stem,
    normalize_parte1_paragraphs,
    pdf_key,
    process_pair,
    remove_inline_pdf_headers,
    render_parte1_into_odt,
    split_embedded_event_titles,
    strip_invalid_xml_chars,
    validate_generated_odt,
)


def write_minimal_odt(path: Path) -> None:
    content_xml = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body>
    <office:text>
      <text:p text:style-name="P37">1\u00aa PARTE</text:p>
      <text:p text:style-name="P35"></text:p>
      <text:p text:style-name="P35"></text:p>
      <text:p text:style-name="P18">2\u00aa PARTE</text:p>
      <text:p text:style-name="P35">Tempo de servico</text:p>
      <text:p text:style-name="P35">SIGNATARIO RESPONSAVEL - Cel</text:p>
      <text:p text:style-name="P35">S Cmt B Adm QGEx</text:p>
    </office:text>
  </office:body>
</office:document-content>
"""
    styles_xml = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0">
</office:document-styles>
"""
    manifest_xml = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest
  xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
</manifest:manifest>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("content.xml", content_xml.encode("utf-8"))
        archive.writestr("styles.xml", styles_xml.encode("utf-8"))
        archive.writestr("META-INF/manifest.xml", manifest_xml.encode("utf-8"))


def test_classify_semi_ok_odt() -> None:
    item = classify_file(Path("003 - ALEXANDRE o.odt"))

    assert item is not None
    assert item.kind == "ODT_SEMI_OK"
    assert item.key == "alexandre"


def test_classify_plain_odt_as_assumed_semi_ok() -> None:
    item = classify_file(Path("003 - MORAES.odt"))

    assert item is not None
    assert item.kind == "ODT_SEMI_OK"
    assert item.key == "moraes"
    assert item.warnings == ["WARN_ODT_ASSUMED_SEMI_OK_BY_FILENAME"]


def test_classify_odt_with_grade_and_semester_prefix() -> None:
    amadeu = classify_file(Path("001- 2° Sgt Amadeu Borges 2°SEM 2025.odt"))
    beatriz = classify_file(Path("002-2 ° SGT BEATRIZ.odt"))
    mariana = classify_file(Path("001- 3° SGT MARIANA CRUZ.odt"))

    assert amadeu is not None
    assert beatriz is not None
    assert mariana is not None
    assert amadeu.key == "amadeu borges"
    assert beatriz.key == "beatriz"
    assert mariana.key == "mariana cruz"


def test_pdf_key_removes_period_and_grade_prefix() -> None:
    assert pdf_key(Path("2025-07-01_2025-12-31_1sgt_moraes.pdf")) == "moraes"
    assert (
        pdf_key(Path("2025-07-01_2025-12-31_1sgt_guilherme_vieira (1).pdf"))
        == "guilherme vieira"
    )
    assert pdf_key(Path("2025-07-01_2025-12-31_3sgt_alfa.pdf")) == "alfa"


def test_classify_txt_as_parte1_source() -> None:
    item = classify_file(Path("2025-01-01_2025-06-30_3sgt_araruna.txt"))

    assert item is not None
    assert item.kind == "TXT_PARTE1"
    assert item.key == "araruna"


def test_extract_parte1_from_txt_source(tmp_path: Path) -> None:
    source = tmp_path / "2025-01-01_2025-06-30_3sgt_araruna.txt"
    source.write_text(
        "\n".join(
            [
                "CABEÇALHO",
                "JANEIRO:",
                "Evento janeiro",
                "FEVEREIRO:",
                "Evento fevereiro",
                "Comportamento: EXCEPCIONAL",
                "2ª PARTE",
            ]
        ),
        encoding="utf-8",
    )

    extracted = extract_parte1_from_source(source, "1")

    assert extracted.startswith("JANEIRO:")
    assert "Evento fevereiro" in extracted
    assert "Comportamento" not in extracted
    assert "2ª PARTE" not in extracted


def test_find_modelo_odt_and_militar_output_stem() -> None:
    modelo = classify_file(Path("000 MODELO.odt"))
    semi = PairItem(
        key="moraes",
        odt=Path("003 - MORAES o.odt"),
        pdf=Path("2025-07-01_2025-12-31_1sgt_moraes.pdf"),
    )

    assert modelo is not None
    assert find_modelo_odt([modelo]) == Path("000 MODELO.odt")
    assert militar_output_stem(semi) == "MORAES"


def test_collect_final_odts_uses_clean_militar_names(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    generated = output_dir / "brito_parte1_experimental.odt"
    generated.write_bytes(b"odt")

    collect_final_odts(
        output_dir,
        [
            ProcessResult(
                key="brito",
                status="OK_WITH_WARNINGS",
                source_semi_odt="004 - BRITO o.odt",
                source_pdf="2025-07-01_2025-12-31_sten_brito.txt",
                output_odt=str(generated),
                warnings=["WARN_REVIEW_BEFORE_SIGNATURE"],
            ),
            ProcessResult(
                key="erro",
                status="ERROR",
                source_semi_odt="999 - ERRO o.odt",
                source_pdf="erro.txt",
                output_odt=str(generated),
            ),
        ],
    )

    final_dir = output_dir / "ODTS_FINAIS"

    assert (final_dir / "BRITO.odt").read_bytes() == b"odt"
    assert not (final_dir / "ERRO.odt").exists()
    assert (final_dir / "manifesto_odts_finais.json").exists()
    assert (final_dir / "manifesto_odts_finais.csv").exists()


def test_clean_parte1_lines_removes_headers_and_invalid_xml() -> None:
    raw = "\n".join(
        [
            "JULHO:",
            "BASE ADMINISTRATIVA DO QUARTEL-GENERAL DO EXERCITO",
            "RELATORIO - Publicacao\x00",
            "Contracheque SiPPes - Ordem",
        ]
    )

    lines, warnings = clean_parte1_lines(raw)

    assert "BASE ADMINISTRATIVA" not in "\n".join(lines)
    assert "RELATORIO - Publicacao" in "\n".join(lines)
    assert any(item.startswith("OK_INVALID_XML_CHARS_REMOVED:") for item in warnings)
    assert any(item.startswith("WARN_POSSIBLE_SENSITIVE_EVENT:") for item in warnings)


def test_clean_parte1_lines_removes_multiline_pdf_headers() -> None:
    raw = "\n".join(
        [
            "AGOSTO:",
            "do 1º Sgt BELTRANO DE SOUZA",
            "2º Semestre de 2025",
            "CP: PERÍODO: 01/07/2025 a 31/12/2025",
            "Evento valido",
        ]
    )

    lines, _warnings = clean_parte1_lines(raw)

    assert lines == ["AGOSTO:", "Evento valido"]


def test_strip_invalid_xml_chars() -> None:
    clean, removed = strip_invalid_xml_chars("abc\x00def")

    assert clean == "abcdef"
    assert removed == 1


def test_remove_inline_pdf_page_header_from_body_line() -> None:
    clean, removed = remove_inline_pdf_headers(
        "Texto antes do 1º Sgt MORAES CP: PERÍODO: 01/07/2025 a 31/12/2025 texto depois"
    )

    assert removed == 1
    assert "CP:" not in clean
    assert clean == "Texto antes texto depois"


def test_split_embedded_event_title_from_body_tail() -> None:
    lines, warnings = split_embedded_event_titles(
        [
            "Texto do evento anterior. RESSARCIMENTO DE APOIO -",
            "Solicitação",
            "- a 28, BAR Nº 41:",
            "Corpo novo",
        ]
    )

    assert lines == [
        "Texto do evento anterior.",
        "RESSARCIMENTO DE APOIO - Solicitação",
        "- a 28, BAR Nº 41:",
        "Corpo novo",
    ]
    assert warnings == ["OK_EVENT_TITLE_SPLIT_RECOVERED:1"]


def test_split_embedded_event_title_prefix_from_body_tail() -> None:
    lines, warnings = split_embedded_event_titles(
        [
            "Texto do evento anterior. RESSARCIMENTO",
            "DE APOIO À NECESSIDADE DE ENSINO ESPECIALIZADO - Solicitação",
            "- a 28, BAR Nº 41:",
            "Corpo novo",
        ]
    )

    assert lines == [
        "Texto do evento anterior.",
        "RESSARCIMENTO DE APOIO À NECESSIDADE DE ENSINO ESPECIALIZADO - Solicitação",
        "- a 28, BAR Nº 41:",
        "Corpo novo",
    ]
    assert warnings == ["OK_EVENT_TITLE_SPLIT_RECOVERED:1"]


def test_split_event_title_fragment_after_month() -> None:
    lines, warnings = split_embedded_event_titles(
        [
            "OUTUBRO:",
            "RESSARCIMENTO",
            "DE APOIO A NECESSIDADE DE ENSINO ESPECIALIZADO - Solicitacao",
            "- a 2, BAR No 46:",
            "Corpo novo",
        ]
    )

    assert lines == [
        "OUTUBRO:",
        "RESSARCIMENTO DE APOIO A NECESSIDADE DE ENSINO ESPECIALIZADO - Solicitacao",
        "- a 2, BAR No 46:",
        "Corpo novo",
    ]
    assert warnings == ["OK_EVENT_TITLE_SPLIT_RECOVERED:1"]


def test_split_event_title_fragment_does_not_merge_mixed_case_body() -> None:
    lines, warnings = split_embedded_event_titles(
        [
            "OUTUBRO:",
            "Corpo solto",
            "CURSO DE HABILITACAO - Conclusao",
            "- a 2, BAR No 46:",
        ]
    )

    assert lines == [
        "OUTUBRO:",
        "Corpo solto",
        "CURSO DE HABILITACAO - Conclusao",
        "- a 2, BAR No 46:",
    ]
    assert warnings == []


def test_normalize_parte1_paragraphs_joins_wrapped_body() -> None:
    paragraphs, warnings = normalize_parte1_paragraphs(
        [
            "JULHO:",
            "TESTE DE AVALIAÇÃO FÍSICA - Nomeação de Comissão de Aplicação",
            "- a 10, BI Nº 53 :",
            "Conforme previsto na Portaria, DESIGNO",
            "para compor a Comissão de Aplicação.",
            "AGOSTO:",
        ],
        "2",
    )

    assert paragraphs == [
        "JULHO:",
        "TESTE DE AVALIAÇÃO FÍSICA - Nomeação de Comissão de Aplicação",
        "- a 10, BI Nº 53:",
        "Conforme previsto na Portaria, DESIGNO para compor a Comissão de Aplicação.",
        "AGOSTO:",
    ]
    assert warnings == ["OK_EVENT_BODY_PARAGRAPHS_NORMALIZED:6->5"]


def test_normalize_parte1_paragraphs_recovers_title_after_body_join() -> None:
    paragraphs, warnings = normalize_parte1_paragraphs(
        [
            "AGOSTO:",
            "Texto do evento anterior.",
            "RESSARCIMENTO",
            "DE APOIO À NECESSIDADE DE ENSINO ESPECIALIZADO - Solicitação",
            "- a 28, BAR Nº 41:",
            "Corpo novo",
        ],
        "2",
    )

    assert paragraphs == [
        "AGOSTO:",
        "Texto do evento anterior.",
        "RESSARCIMENTO DE APOIO À NECESSIDADE DE ENSINO ESPECIALIZADO - Solicitação",
        "- a 28, BAR Nº 41:",
        "Corpo novo",
    ]
    assert "OK_EVENT_TITLE_SPLIT_RECOVERED:1" in warnings


def test_normalize_parte1_paragraphs_recovers_title_fragment_after_month() -> None:
    paragraphs, warnings = normalize_parte1_paragraphs(
        [
            "OUTUBRO:",
            "RESSARCIMENTO",
            "DE APOIO A NECESSIDADE DE ENSINO ESPECIALIZADO - Solicitacao",
            "- a 2, BAR No 46:",
            "Corpo novo",
        ],
        "2",
    )

    assert paragraphs == [
        "OUTUBRO:",
        "RESSARCIMENTO DE APOIO A NECESSIDADE DE ENSINO ESPECIALIZADO - Solicitacao",
        "- a 2, BAR No 46:",
        "Corpo novo",
    ]
    assert "OK_EVENT_TITLE_SPLIT_RECOVERED:1" in warnings


def test_normalize_parte1_paragraphs_splits_compact_empty_month() -> None:
    paragraphs, warnings = normalize_parte1_paragraphs(
        [
            "OUTUBRO:",
            "Evento valido",
            "NOVEMBRO: Sem Alteracao.",
            "DEZEMBRO:",
            "Evento valido",
        ],
        "2",
    )

    assert paragraphs == [
        "OUTUBRO:",
        "Evento valido",
        "NOVEMBRO:",
        "Sem Alteracao.",
        "DEZEMBRO:",
        "Evento valido",
    ]
    assert "OK_EMPTY_MONTH_COMPACT_SPLIT:1" in warnings


def test_normalize_parte1_paragraphs_recovers_title_tail_before_reference() -> None:
    paragraphs, warnings = normalize_parte1_paragraphs(
        [
            "SETEMBRO:",
            "Corpo anterior com base na Portaria No 753, de 30 MAR 15: PALESTRAS PARA A BASE ADMINISTRATIVA DO QUARTEL-GENERAL DO",
            "EXERCITO.",
            "- a 25, BI No 75:",
            "Participou da palestra.",
        ],
        "2",
    )

    assert paragraphs == [
        "SETEMBRO:",
        "Corpo anterior com base na Portaria No 753, de 30 MAR 15:",
        "PALESTRAS PARA A BASE ADMINISTRATIVA DO QUARTEL-GENERAL DO EXERCITO.",
        "- a 25, BI No 75:",
        "Participou da palestra.",
    ]
    assert "OK_EVENT_TITLE_SPLIT_RECOVERED:1" in warnings


def test_normalize_parte1_paragraphs_preserves_sensitive_review_lines() -> None:
    paragraphs, _warnings = normalize_parte1_paragraphs(
        [
            "AGOSTO:",
            "RESSARCIMENTO DE APOIO À NECESSIDADE DE ENSINO ESPECIALIZADO - Solicitação",
            "- a 28, BAR Nº 41 :",
            "Autorizo o ressarcimento conforme processo.",
            "Nome: DEPENDENTE TESTE",
            "CPF: 000.000.000-00",
        ],
        "2",
    )

    assert paragraphs[-3:] == [
        "Autorizo o ressarcimento conforme processo.",
        "Nome: DEPENDENTE TESTE",
        "CPF: 000.000.000-00",
    ]


def test_ensure_required_months_fills_missing_semester_months() -> None:
    lines, warnings = ensure_required_months(
        [
            "JULHO:",
            "Evento",
            "AGOSTO:",
            "Evento",
            "SETEMBRO:",
            "Evento",
        ],
        "2",
    )

    assert "OUTUBRO:" in lines
    assert "NOVEMBRO:" in lines
    assert "DEZEMBRO:" in lines
    assert lines[-1] == "Sem alterações."
    assert warnings == ["OK_EMPTY_MONTHS_FILLED:OUTUBRO,NOVEMBRO,DEZEMBRO"]


def test_render_parte1_between_markers_and_validate(tmp_path: Path) -> None:
    source = tmp_path / "semi_ok.odt"
    output = tmp_path / "saida.odt"
    write_minimal_odt(source)

    blanks, nonblank = render_parte1_into_odt(
        source_odt=source,
        output_odt=output,
        semestre="2",
        parte1_lines=[
            "JULHO:",
            "Evento de teste - Publicacao",
            "- a 1, BI No 1 :",
            "Corpo do evento",
            "AGOSTO:",
            "SETEMBRO:",
            "OUTUBRO:",
            "NOVEMBRO:",
            "DEZEMBRO:",
        ],
    )

    validation = validate_generated_odt(output, "2")
    with zipfile.ZipFile(output, "r") as archive:
        rendered = archive.read("content.xml").decode("utf-8")

    assert blanks == 2
    assert nonblank == []
    assert validation.status == "OK"
    assert not validation.errors
    assert '<text:p text:style-name="P37">1ª PARTE</text:p>' in rendered
    assert '<text:p text:style-name="SISGESParte1Titulo">1ª PARTE</text:p>' not in rendered


def test_render_parte1_adds_spacing_around_months_and_bold_titles(tmp_path: Path) -> None:
    source = tmp_path / "semi_ok.odt"
    output = tmp_path / "saida.odt"
    write_minimal_odt(source)

    render_parte1_into_odt(
        source_odt=source,
        output_odt=output,
        semestre="2",
        parte1_lines=[
            "JULHO:",
            "INSTALAÇÃO – Concessão",
            "- a 1, BI Nº 50:",
            "Corpo do evento - com hífen interno",
            "AGOSTO:",
            "SETEMBRO:",
            "OUTUBRO:",
            "NOVEMBRO:",
            "DEZEMBRO:",
        ],
    )

    with zipfile.ZipFile(output, "r") as archive:
        root = ET.fromstring(archive.read("content.xml"))
    text_node = root.find("office:body", NS).find("office:text", NS)
    rendered_lines = [
        "".join(child.itertext()).strip()
        for child in list(text_node)
        if child.tag.endswith("}p") or child.tag.endswith("}h")
    ]
    julho_index = rendered_lines.index("JULHO:")
    title_index = rendered_lines.index("INSTALAÇÃO – Concessão")
    reference_index = rendered_lines.index("- a 1, BI Nº 50:")
    body_index = rendered_lines.index("Corpo do evento - com hífen interno")

    assert rendered_lines[julho_index - 1] == "1ª PARTE"
    assert rendered_lines[julho_index + 1] == ""
    assert title_index == julho_index + 2
    assert rendered_lines[title_index - 1] == ""
    assert rendered_lines[title_index + 1] == ""
    assert rendered_lines[reference_index - 1] == ""
    assert rendered_lines[body_index - 1] == "- a 1, BI Nº 50:"

    automatic_styles = root.find("office:automatic-styles", NS)
    title_style = next(
        style
        for style in automatic_styles.findall("style:style", NS)
        if style.attrib.get(STYLE_NAME) == SISGES_PARTE1_STYLE_EVENT_TITLE
    )
    text_props = title_style.find("style:text-properties", NS)
    assert text_props is not None
    assert text_props.attrib.get("{urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0}font-weight") == "bold"
    assert text_props.attrib.get(f"{{{NS['style']}}}font-weight-asian") == "bold"
    assert text_props.attrib.get(f"{{{NS['style']}}}font-weight-complex") == "bold"
    body_styles = [
        child.attrib.get(f"{{{NS['text']}}}style-name")
        for child in list(text_node)
        if "".join(child.itertext()).strip() == "Corpo do evento - com hífen interno"
    ]
    assert body_styles == ["SISGESParte1Corpo"]


def test_render_parte1_keeps_table_labels_as_body_style(tmp_path: Path) -> None:
    source = tmp_path / "semi_ok.odt"
    output = tmp_path / "saida.odt"
    write_minimal_odt(source)

    render_parte1_into_odt(
        source_odt=source,
        output_odt=output,
        semestre="2",
        parte1_lines=[
            "JULHO:",
            "TESTE DE AVALIACAO FISICA - Nomeacao",
            "- a 10, BI No 53:",
            "Corpo do evento.",
            "Membro",
            "1. Linha numerada de corpo",
            "AGOSTO:",
            "SETEMBRO:",
            "OUTUBRO:",
            "NOVEMBRO:",
            "DEZEMBRO:",
        ],
    )

    with zipfile.ZipFile(output, "r") as archive:
        root = ET.fromstring(archive.read("content.xml"))
    text_node = root.find("office:body", NS).find("office:text", NS)
    rendered = [
        ("".join(child.itertext()).strip(), child.attrib.get(f"{{{NS['text']}}}style-name"))
        for child in list(text_node)
        if child.tag.endswith("}p") or child.tag.endswith("}h")
    ]

    assert ("Membro", "SISGESParte1Corpo") in rendered
    assert ("1. Linha numerada de corpo", "SISGESParte1Corpo") in rendered


def test_render_parte1_uses_placeholder_without_removing_comportamento(tmp_path: Path) -> None:
    source = tmp_path / "modelo_com_flags.odt"
    output = tmp_path / "saida_flags.odt"
    write_minimal_odt(source)
    with zipfile.ZipFile(source, "r") as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    content = entries["content.xml"].decode("utf-8")
    content = content.replace(
        '<text:p text:style-name="P35"></text:p>\n      <text:p text:style-name="P35"></text:p>',
        '<text:p text:style-name="P35">[SISGES_PARTE_1]</text:p>\n      <text:p text:style-name="P35">[SISGES_COMPORTAMENTO]</text:p>',
    )
    with zipfile.ZipFile(source, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, content.encode("utf-8") if name == "content.xml" else data)

    _blanks, nonblank = render_parte1_into_odt(
        source_odt=source,
        output_odt=output,
        semestre="2",
        parte1_lines=[
            "JULHO:",
            "Evento de teste",
            "AGOSTO:",
            "SETEMBRO:",
            "OUTUBRO:",
            "NOVEMBRO:",
            "DEZEMBRO:",
        ],
    )

    with zipfile.ZipFile(output, "r") as archive:
        rendered = archive.read("content.xml").decode("utf-8")

    assert nonblank == ["[SISGES_PARTE_1]"]
    assert "[SISGES_PARTE_1]" not in rendered
    assert "[SISGES_COMPORTAMENTO]" in rendered
    assert "Evento de teste" in rendered


def test_process_pair_with_model_base_duplicates_model_and_names_militar(
    tmp_path: Path,
    monkeypatch,
) -> None:
    modelo = tmp_path / "000 MODELO.odt"
    semi_ok = tmp_path / "003 - MORAES o.odt"
    pdf = tmp_path / "2025-07-01_2025-12-31_1sgt_moraes.pdf"
    output_dir = tmp_path / "saida"
    output_dir.mkdir()
    write_minimal_odt(modelo)
    write_minimal_odt(semi_ok)
    pdf.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(
        "scripts.complete_folha_semi_ok_parte1.extract_parte1_from_source",
        lambda _pdf, _semestre: "\n".join(
            [
                "JULHO:",
                "Evento de teste",
                "AGOSTO:",
                "SETEMBRO:",
                "OUTUBRO:",
                "NOVEMBRO:",
                "DEZEMBRO:",
            ]
        ),
    )

    result = process_pair(
        PairItem(key="moraes", odt=semi_ok, pdf=pdf),
        output_dir,
        "2",
        base_odt=modelo,
        output_name_mode="militar",
    )

    output_odt = output_dir / "MORAES.odt"
    assert result.output_odt == str(output_odt)
    assert result.source_base_odt == str(modelo)
    assert output_odt.exists()
    assert "OK_MODELO_ODT_DUPLICATED_FOR_MILITAR" in result.warnings
    with zipfile.ZipFile(output_odt, "r") as archive:
        rendered = archive.read("content.xml").decode("utf-8")
    with zipfile.ZipFile(modelo, "r") as archive:
        original = archive.read("content.xml").decode("utf-8")
    assert "Evento de teste" in rendered
    assert "Evento de teste" not in original

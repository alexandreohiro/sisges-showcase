from __future__ import annotations

import zipfile
from pathlib import Path

from scripts.render_folha_modelo_pdf import compare_with_reference, inspect_odt


def write_minimal_odt(path: Path, body: str) -> None:
    content_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body>
    <office:text>
      {body}
    </office:text>
  </office:body>
</office:document-content>
"""
    styles_xml = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0">
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


def test_inspect_odt_detects_required_parts_and_months(tmp_path: Path) -> None:
    odt = tmp_path / "folha.odt"
    write_minimal_odt(
        odt,
        "\n".join(
            [
                '<text:p text:style-name="P1">1ª PARTE</text:p>',
                '<text:p text:style-name="P1">JULHO:</text:p>',
                '<text:p text:style-name="P1">AGOSTO:</text:p>',
                '<text:p text:style-name="P1">SETEMBRO:</text:p>',
                '<text:p text:style-name="P1">OUTUBRO:</text:p>',
                '<text:p text:style-name="P1">NOVEMBRO:</text:p>',
                '<text:p text:style-name="P1">DEZEMBRO:</text:p>',
                '<text:p text:style-name="P1">2ª PARTE</text:p>',
            ]
        ),
    )

    inspection = inspect_odt(odt, "2")

    assert inspection.zip_valid
    assert inspection.content_parseable
    assert inspection.styles_parseable
    assert inspection.first_part_present
    assert inspection.second_part_present
    assert all(inspection.months_present.values())
    assert not inspection.errors


def test_inspect_odt_detects_leftover_placeholders(tmp_path: Path) -> None:
    odt = tmp_path / "folha_placeholder.odt"
    write_minimal_odt(
        odt,
        '<text:p text:style-name="P1">[NOME]</text:p>',
    )

    inspection = inspect_odt(odt, "2")

    assert "ERR_TEMPLATE_PLACEHOLDER_LEFTOVER" in inspection.errors
    assert "[NOME]" in inspection.placeholder_leftovers


def test_compare_with_reference_reports_delta(tmp_path: Path) -> None:
    generated = tmp_path / "generated.odt"
    reference = tmp_path / "reference.odt"
    write_minimal_odt(generated, '<text:p text:style-name="P1">1ª PARTE</text:p>')
    write_minimal_odt(
        reference,
        "\n".join(
            [
                '<text:p text:style-name="P1">1ª PARTE</text:p>',
                '<text:p text:style-name="P1">2ª PARTE</text:p>',
            ]
        ),
    )

    comparison = compare_with_reference(
        inspect_odt(generated, "2"),
        inspect_odt(reference, "2"),
        raw_lines=10,
        normalized_paragraphs=3,
    )

    assert comparison["reference_available"] is True
    assert comparison["line_normalization_ratio"] == 0.3
    assert comparison["paragraph_count_delta"] == -1

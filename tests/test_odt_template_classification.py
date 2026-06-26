from __future__ import annotations

from pathlib import Path
import zipfile

from modules.compilador.application.odt_template_policy import (
    EXECUTABLE_TEMPLATE,
    INVALID_ODT,
    REQUIRED_SISGES_FLAGS,
    REQUIRED_SISGES_MARKERS,
    VISUAL_REFERENCE_ONLY,
    classify_odt_template,
)


def test_odt_with_sisges_markers_is_executable_template(tmp_path):
    path = tmp_path / "modelo.odt"
    make_odt(path, "\n".join(REQUIRED_SISGES_MARKERS))

    classification = classify_odt_template(path)

    assert classification.classification == EXECUTABLE_TEMPLATE
    assert "OK_TEMPLATE_EXECUTABLE" in classification.validations


def test_odt_with_sisges_flags_is_executable_template(tmp_path):
    path = tmp_path / "modelo_flags.odt"
    make_odt(path, "[SISGES_PARTE_1]", styles_text="\n".join(REQUIRED_SISGES_FLAGS))

    classification = classify_odt_template(path)

    assert classification.classification == EXECUTABLE_TEMPLATE
    assert "OK_TEMPLATE_EXECUTABLE_FLAGS" in classification.validations


def test_odt_without_markers_is_visual_reference_only(tmp_path):
    path = tmp_path / "visual.odt"
    make_odt(path, "Modelo visual sem marcadores SISGES.")

    classification = classify_odt_template(path)

    assert classification.classification == VISUAL_REFERENCE_ONLY
    assert "WARN_TEMPLATE_VISUAL_REFERENCE_ONLY" in classification.validations


def test_invalid_odt_is_invalid_template(tmp_path):
    path = tmp_path / "invalido.odt"
    path.write_text("nao e zip", encoding="utf-8")

    classification = classify_odt_template(path)

    assert classification.classification == INVALID_ODT
    assert "ERR_TEMPLATE_ODT_INVALID" in classification.validations


def test_partial_sisges_markers_are_not_executable(tmp_path):
    path = tmp_path / "parcial.odt"
    make_odt(path, REQUIRED_SISGES_MARKERS[0])

    classification = classify_odt_template(path)

    assert classification.classification == VISUAL_REFERENCE_ONLY
    assert "ERR_TEMPLATE_NOT_EXECUTABLE" in classification.validations


def make_odt(path: Path, text: str, styles_text: str = "") -> None:
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2"><office:body><office:text><text:p>{text}</text:p></office:text></office:body></office:document-content>'''
    styles = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" office:version="1.2"><office:styles><style:default-style style:family="paragraph"><style:text-properties fo:font-family="Calibri Light" fo:font-size="12pt"/></style:default-style><office:master-styles>{styles_text}</office:master-styles></office:styles></office:document-styles>'''
    with zipfile.ZipFile(path, "w") as zout:
        zout.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        zout.writestr("content.xml", content)
        zout.writestr("styles.xml", styles)
        zout.writestr("META-INF/manifest.xml", "")

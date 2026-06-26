from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET


EXECUTABLE_TEMPLATE = "EXECUTABLE_TEMPLATE"
VISUAL_REFERENCE_ONLY = "VISUAL_REFERENCE_ONLY"
INVALID_TEMPLATE = "INVALID_TEMPLATE"

DOCUMENT_MARKERS = (
    "[[SISGES:NOME_COMPLETO]]",
    "[[SISGES:NOME_GUERRA]]",
    "[[SISGES:POSTO_GRADUACAO]]",
    "[[SISGES:IDENTIDADE]]",
    "[[SISGES:CPF]]",
    "[[SISGES:OM]]",
    "[[SISGES:TEXTO_DOCUMENTO]]",
    "[[SISGES:TEMPO_SERVICO]]",
    "[[SISGES:ASSINATURA_NOME]]",
    "[[SISGES:ASSINATURA_FUNCAO]]",
    "[[SISGES:DATA_LOCAL]]",
)

MINIMUM_EXECUTABLE_MARKERS = (
    "[[SISGES:NOME_COMPLETO]]",
    "[[SISGES:TEXTO_DOCUMENTO]]",
    "[[SISGES:ASSINATURA_NOME]]",
)


@dataclass(slots=True)
class DocumentTemplateClassification:
    classification: str
    validations: list[str] = field(default_factory=list)
    markers_present: list[str] = field(default_factory=list)
    missing_markers: list[str] = field(default_factory=list)
    content_xml: str = ""
    styles_xml: str = ""

    @property
    def is_executable(self) -> bool:
        return self.classification == EXECUTABLE_TEMPLATE


def classify_document_template(path: Path) -> DocumentTemplateClassification:
    if path.suffix.lower() != ".odt":
        return DocumentTemplateClassification(
            classification=VISUAL_REFERENCE_ONLY,
            validations=["WARN_TEMPLATE_VISUAL_REFERENCE_ONLY"],
            missing_markers=list(MINIMUM_EXECUTABLE_MARKERS),
        )
    try:
        content_xml, styles_xml = _read_odt_xml(path)
        ET.fromstring(content_xml.encode("utf-8"))
        ET.fromstring(styles_xml.encode("utf-8"))
    except Exception:
        return DocumentTemplateClassification(
            classification=INVALID_TEMPLATE,
            validations=["ERR_TEMPLATE_ODT_INVALID"],
        )

    combined = f"{content_xml}\n{styles_xml}"
    present = [marker for marker in DOCUMENT_MARKERS if marker in combined]
    missing_minimum = [marker for marker in MINIMUM_EXECUTABLE_MARKERS if marker not in combined]
    if not missing_minimum:
        return DocumentTemplateClassification(
            classification=EXECUTABLE_TEMPLATE,
            validations=["OK_TEMPLATE_EXECUTABLE"],
            markers_present=present,
            missing_markers=[],
            content_xml=content_xml,
            styles_xml=styles_xml,
        )
    return DocumentTemplateClassification(
        classification=VISUAL_REFERENCE_ONLY,
        validations=["WARN_TEMPLATE_VISUAL_REFERENCE_ONLY"],
        markers_present=present,
        missing_markers=missing_minimum,
        content_xml=content_xml,
        styles_xml=styles_xml,
    )


def _read_odt_xml(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path, "r") as odt:
        names = set(odt.namelist())
        if "content.xml" not in names or "styles.xml" not in names:
            raise ValueError("ERR_TEMPLATE_ODT_INVALID")
        return (
            odt.read("content.xml").decode("utf-8", errors="ignore"),
            odt.read("styles.xml").decode("utf-8", errors="ignore"),
        )

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET


EXECUTABLE_TEMPLATE = "EXECUTABLE_TEMPLATE"
VISUAL_REFERENCE_ONLY = "VISUAL_REFERENCE_ONLY"
ALTERACOES_SOURCE_ODT = "ALTERACOES_SOURCE_ODT"
INVALID_ODT = "INVALID_ODT"

SISGES_HEADER_MARKER = "[[SISGES:HEADER]]"
SISGES_PRIMEIRA_PARTE_MARKER = "[[SISGES:PRIMEIRA_PARTE]]"
SISGES_COMPORTAMENTO_MARKER = "[[SISGES:COMPORTAMENTO]]"
SISGES_SEGUNDA_PARTE_MARKER = "[[SISGES:SEGUNDA_PARTE]]"
SISGES_ASSINATURA_MARKER = "[[SISGES:ASSINATURA]]"

SISGES_FLAG_NOME = "[SISGES_NOME]"
SISGES_FLAG_GRADUACAO = "[SISGES_GRADUACAO]"
SISGES_FLAG_QMS = "[SISGES_QMS]"
SISGES_FLAG_IDENTIDADE = "[SISGES_IDENTIDADE]"
SISGES_FLAG_SEMESTRE_TEXTO = "[SISGES_SEMESTRE_TEXTO]"
SISGES_FLAG_PERIODO = "[SISGES_PERIODO]"
SISGES_FLAG_POSTO_GRADUACAO_CONTINUACAO = "[SISGES_POSTO_GRADUACAO_CONTINUACAO]"
SISGES_FLAG_PARTE_1 = "[SISGES_PARTE_1]"
SISGES_FLAG_COMPORTAMENTO = "[SISGES_COMPORTAMENTO]"
SISGES_FLAG_DATA_LOCAL = "[SISGES_DATA_LOCAL]"
SISGES_FLAG_ASSINATURA_NOME = "[SISGES_ASSINATURA_NOME]"
SISGES_FLAG_ASSINATURA_FUNCAO = "[SISGES_ASSINATURA_FUNCAO]"

REQUIRED_SISGES_MARKERS = (
    SISGES_HEADER_MARKER,
    SISGES_PRIMEIRA_PARTE_MARKER,
    SISGES_COMPORTAMENTO_MARKER,
    SISGES_SEGUNDA_PARTE_MARKER,
    SISGES_ASSINATURA_MARKER,
)

REQUIRED_SISGES_FLAGS = (
    SISGES_FLAG_NOME,
    SISGES_FLAG_GRADUACAO,
    SISGES_FLAG_QMS,
    SISGES_FLAG_IDENTIDADE,
    SISGES_FLAG_SEMESTRE_TEXTO,
    SISGES_FLAG_PERIODO,
    SISGES_FLAG_PARTE_1,
    SISGES_FLAG_COMPORTAMENTO,
    SISGES_FLAG_DATA_LOCAL,
    SISGES_FLAG_ASSINATURA_NOME,
    SISGES_FLAG_ASSINATURA_FUNCAO,
)

LEGACY_BRACKET_PLACEHOLDERS = (
    "[GRADUACAO]",
    "[NOME]",
    "[PERIODO]",
)

LEFTOVER_PLACEHOLDER_PATTERN = re.compile(
    r"(\[GRADUACAO\]|\[NOME\]|\[PERIODO\]|\[SISGES_[A-Z0-9_]+\]|\{\{[^{}]+}}|\[\[SISGES:[^\]]+]])",
    re.I,
)


@dataclass(slots=True)
class TemplateClassification:
    classification: str
    validations: list[str] = field(default_factory=list)
    markers_present: list[str] = field(default_factory=list)
    missing_markers: list[str] = field(default_factory=list)
    content_xml: str = ""
    styles_xml: str = ""

    @property
    def is_executable(self) -> bool:
        return self.classification == EXECUTABLE_TEMPLATE


def classify_odt_template(path: Path) -> TemplateClassification:
    try:
        content_xml, styles_xml = read_odt_text_parts(path)
        parse_odt_xml_parts(content_xml, styles_xml)
    except Exception:
        return TemplateClassification(
            classification=INVALID_ODT,
            validations=["ERR_TEMPLATE_ODT_INVALID"],
        )

    combined = f"{content_xml}\n{styles_xml}"
    present = [marker for marker in REQUIRED_SISGES_MARKERS if marker in combined]
    missing = [marker for marker in REQUIRED_SISGES_MARKERS if marker not in combined]
    flags_present = [flag for flag in REQUIRED_SISGES_FLAGS if flag in combined]
    flags_missing = [flag for flag in REQUIRED_SISGES_FLAGS if flag not in combined]
    if not flags_missing:
        return TemplateClassification(
            classification=EXECUTABLE_TEMPLATE,
            validations=["OK_TEMPLATE_EXECUTABLE", "OK_TEMPLATE_EXECUTABLE_FLAGS"],
            markers_present=flags_present,
            missing_markers=[],
            content_xml=content_xml,
            styles_xml=styles_xml,
        )
    if flags_present:
        return TemplateClassification(
            classification=VISUAL_REFERENCE_ONLY,
            validations=["ERR_TEMPLATE_NOT_EXECUTABLE"],
            markers_present=flags_present,
            missing_markers=flags_missing,
            content_xml=content_xml,
            styles_xml=styles_xml,
        )
    if not missing:
        return TemplateClassification(
            classification=EXECUTABLE_TEMPLATE,
            validations=["OK_TEMPLATE_EXECUTABLE"],
            markers_present=present,
            missing_markers=[],
            content_xml=content_xml,
            styles_xml=styles_xml,
        )
    if present:
        return TemplateClassification(
            classification=VISUAL_REFERENCE_ONLY,
            validations=["ERR_TEMPLATE_NOT_EXECUTABLE"],
            markers_present=present,
            missing_markers=missing,
            content_xml=content_xml,
            styles_xml=styles_xml,
        )
    return TemplateClassification(
        classification=VISUAL_REFERENCE_ONLY,
        validations=["WARN_TEMPLATE_VISUAL_REFERENCE_ONLY"],
        markers_present=[],
        missing_markers=missing,
        content_xml=content_xml,
        styles_xml=styles_xml,
    )


def read_odt_text_parts(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path, "r") as odt:
        names = set(odt.namelist())
        if "content.xml" not in names or "styles.xml" not in names:
            raise ValueError("ERR_TEMPLATE_ODT_INVALID")
        content_xml = odt.read("content.xml").decode("utf-8", errors="ignore")
        styles_xml = odt.read("styles.xml").decode("utf-8", errors="ignore")
    return content_xml, styles_xml


def parse_odt_xml_parts(content_xml: str, styles_xml: str) -> None:
    ET.fromstring(content_xml.encode("utf-8"))
    ET.fromstring(styles_xml.encode("utf-8"))


def validate_no_leftover_placeholders(content_xml: str, styles_xml: str = "") -> list[str]:
    combined = f"{content_xml}\n{styles_xml}"
    leftovers = sorted(set(match.group(1) for match in LEFTOVER_PLACEHOLDER_PATTERN.finditer(combined)))
    if leftovers:
        return [
            "ERR_TEMPLATE_PLACEHOLDER_LEFTOVER",
            *[f"ERR_TEMPLATE_PLACEHOLDER_LEFTOVER:{item}" for item in leftovers],
        ]
    return ["OK_TEMPLATE_PLACEHOLDERS_REPLACED"]


def odt_has_sisges_marker_in_styles(styles_xml: str) -> bool:
    return any(marker in styles_xml for marker in REQUIRED_SISGES_MARKERS)

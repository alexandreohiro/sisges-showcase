from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import unicodedata
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, unescape


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


# ---------------------------------------------------------------------------
# RC3 — headers de continuação sincronizados com o período do documento.
# Templates de usuário costumam trazer master pages com semestre/posto em
# texto FIXO; na ingestão os textos estáticos são trocados pelos flags e um
# gate pós-render rejeita ODT cujo header divirja do período renderizado.
# ---------------------------------------------------------------------------

MASTER_STYLES_PATTERN = re.compile(r"<office:master-styles>.*?</office:master-styles>", re.S)
HEADER_TEXT_P_PATTERN = re.compile(r"(<text:p\b[^>]*>)(.*?)(</text:p>)", re.S)
SEMESTER_HEADER_PATTERN = re.compile(r"[12]\s*[ºo°]?\s*SEMESTRE\s+DE\s+\d{4}", re.I)
PERIODO_HEADER_PATTERN = re.compile(
    r"PER[IÍ]ODO:\s*1\s*[ºo°]?\s*(?:JAN\w*\.?|JUL\w*\.?)\s*A\s*3[01]\s*(?:JUN\w*\.?|DEZ\w*\.?)",
    re.I,
)
CONTINUATION_MARKER_PATTERN = re.compile(r"CONTINUA[ÇC][ÃA]O", re.I)
CONTINUATION_RANK_PATTERN = re.compile(
    r"\b(SUBTENENTE|PRIMEIRO-SARGENTO|SEGUNDO-SARGENTO|TERCEIRO-SARGENTO|CABO|SOLDADO|"
    r"ASPIRANTE|PRIMEIRO-TENENTE|SEGUNDO-TENENTE|CAPIT[ÃA]O|MAJOR|TENENTE-CORONEL|CORONEL)\b",
    re.I,
)


def _plain_paragraph_text(inner_xml: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", inner_xml))


def _normalize_header_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    stripped = re.sub(r"[ºo°]\s*", " ", stripped, flags=re.I)
    return re.sub(r"\s+", " ", stripped).strip().upper()


def inject_continuation_header_flags(styles_xml: str) -> tuple[str, list[str]]:
    """Troca semestre/período/posto ESTÁTICOS dos master pages pelos flags.

    Age em todos os master pages (primeira página e continuação). Quando o
    header já usa flags ou não tem texto de período, é no-op byte a byte.
    """
    master_match = MASTER_STYLES_PATTERN.search(styles_xml)
    if not master_match:
        return styles_xml, []

    changed = False

    def rewrite_paragraph(match: re.Match) -> str:
        nonlocal changed
        opening, inner, closing = match.groups()
        if "[SISGES_" in inner:
            return match.group(0)
        plain = _plain_paragraph_text(inner)
        new_plain = plain
        if SEMESTER_HEADER_PATTERN.search(new_plain):
            new_plain = SEMESTER_HEADER_PATTERN.sub(SISGES_FLAG_SEMESTRE_TEXTO, new_plain)
        if PERIODO_HEADER_PATTERN.search(new_plain):
            new_plain = PERIODO_HEADER_PATTERN.sub(f"PERÍODO: {SISGES_FLAG_PERIODO}", new_plain)
        if CONTINUATION_MARKER_PATTERN.search(plain) and CONTINUATION_RANK_PATTERN.search(new_plain):
            new_plain = CONTINUATION_RANK_PATTERN.sub(
                SISGES_FLAG_POSTO_GRADUACAO_CONTINUACAO, new_plain
            )
        if new_plain == plain:
            return match.group(0)
        changed = True
        return opening + escape(new_plain) + closing

    master_block = HEADER_TEXT_P_PATTERN.sub(rewrite_paragraph, master_match.group(0))
    if not changed:
        return styles_xml, []
    rebuilt = styles_xml[: master_match.start()] + master_block + styles_xml[master_match.end():]
    return rebuilt, ["OK_HEADER_CONTINUACAO_FLAGS_INJETADOS"]


def validate_rendered_odt(
    odt_path: Path,
    *,
    period_label: str,
    posto_continuacao: str = "",
) -> list[str]:
    """Gate pós-render: header de master page deve refletir o período.

    Qualquer texto de semestre nos headers divergente do `period_label`
    (ou posto de continuação divergente do militar) gera
    ERR_HEADER_CONTINUACAO_DIVERGENTE — o ODT não pode ser entregue.
    """
    try:
        with zipfile.ZipFile(odt_path, "r") as odt:
            if "styles.xml" not in odt.namelist():
                return []
            styles_xml = odt.read("styles.xml").decode("utf-8", errors="ignore")
    except Exception:
        return ["ERR_HEADER_GATE_ODT_ILEGIVEL"]

    master_match = MASTER_STYLES_PATTERN.search(styles_xml)
    if not master_match:
        return []

    paragraphs = [
        _plain_paragraph_text(match.group(2))
        for match in HEADER_TEXT_P_PATTERN.finditer(master_match.group(0))
    ]
    expected_semester = _normalize_header_text(period_label)
    expected_posto = _normalize_header_text(posto_continuacao)
    validations: list[str] = []
    checked = False
    for paragraph in paragraphs:
        for match in SEMESTER_HEADER_PATTERN.finditer(paragraph):
            checked = True
            if _normalize_header_text(match.group(0)) != expected_semester:
                validations.append(
                    f"ERR_HEADER_CONTINUACAO_DIVERGENTE:SEMESTRE:{match.group(0)}"
                )
        if expected_posto and CONTINUATION_MARKER_PATTERN.search(paragraph):
            rank = CONTINUATION_RANK_PATTERN.search(paragraph)
            if rank and _normalize_header_text(rank.group(0)) != expected_posto:
                checked = True
                validations.append(
                    f"ERR_HEADER_CONTINUACAO_DIVERGENTE:POSTO:{rank.group(0)}"
                )
    if validations:
        return list(dict.fromkeys(validations))
    if checked:
        return ["OK_HEADER_CONTINUACAO_SINCRONIZADO"]
    return []

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import unicodedata
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pdfplumber


NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

TEXT_P = f"{{{NS['text']}}}p"
TEXT_H = f"{{{NS['text']}}}h"
TEXT_STYLE = f"{{{NS['text']}}}style-name"
TEXT_TAGS = {TEXT_P, TEXT_H}
OFFICE_AUTOMATIC_STYLES = f"{{{NS['office']}}}automatic-styles"
STYLE_STYLE = f"{{{NS['style']}}}style"
STYLE_NAME = f"{{{NS['style']}}}name"
STYLE_FAMILY = f"{{{NS['style']}}}family"
STYLE_PARENT = f"{{{NS['style']}}}parent-style-name"
STYLE_PARAGRAPH_PROPERTIES = f"{{{NS['style']}}}paragraph-properties"
STYLE_TEXT_PROPERTIES = f"{{{NS['style']}}}text-properties"

SISGES_PARTE1_STYLE_TITLE = "SISGESParte1Titulo"
SISGES_PARTE1_STYLE_MONTH = "SISGESParte1Mes"
SISGES_PARTE1_STYLE_EVENT_TITLE = "SISGESParte1EventoTitulo"
SISGES_PARTE1_STYLE_REFERENCE = "SISGESParte1Referencia"
SISGES_PARTE1_STYLE_BODY = "SISGESParte1Corpo"

MONTHS_BY_SEMESTER = {
    "1": ["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO"],
    "2": ["JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"],
}

PLACEHOLDER_RE = re.compile(
    r"(\[GRADUACAO\]|\[NOME\]|\[PERIODO\]|\{\{[^}]+\}\}|\[\[SISGES:[^\]]+\]\])"
)
SENSITIVE_RE = re.compile(
    r"\b("
    r"CPF|BENEFICI|PAGAMENTO|CONTRACHEQUE|SIPPES|CONTA\s+BANC|SIGMA|PAF|CRAF|"
    r"ARMA\s+DE\s+FOGO|FILIACAO|FILIA[CÇ][AÃ]O|ENDERECO|ENDERE[CÇ]O"
    r")\b",
    re.I,
)
PARTE1_PLACEHOLDER = "[SISGES_PARTE_1]"
INLINE_PDF_HEADER_RE = re.compile(
    r"\s+do\s+.{0,140}?\bCP:\s*PER\S*ODO:\s*\d{2}/\d{2}/\d{4}\s+a\s+\d{2}/\d{2}/\d{4}",
    re.I,
)
EMBEDDED_EVENT_TITLE_RE = re.compile(
    r"^(?P<body>.+?)\s+(?P<title>[A-Z0-9À-Ý][A-Z0-9À-ÿ\s/().ºª°–—-]{12,}\s+-)\s*$"
)
EMBEDDED_EVENT_TITLE_PREFIX_RE = re.compile(
    r"^(?P<body>.+?)\s+(?P<title>[A-ZÀ-Ý][A-ZÀ-ÿ]{4,}(?:\s+[A-ZÀ-Ý][A-ZÀ-ÿ]{2,}){0,3})$"
)
PDF_GRADE_PREFIX_RE = re.compile(
    r"^(?:\d{4}[-_]\d{2}[-_]\d{2}[-_]\d{4}[-_]\d{2}[-_]\d{2}[-_])?"
    r"(?:s[\s_-]*ten|sten|sub[\s_-]*ten|1[\s_-]*sgt|2[\s_-]*sgt|3[\s_-]*sgt|"
    r"cb|sd|rec|rcr|asp|2[\s_-]*ten|1[\s_-]*ten|cap|maj|tc|ten[\s_-]*cel|cel)"
    r"(?:[\s_-]+|$)",
    re.I,
)
PDF_COPY_SUFFIX_RE = re.compile(r"\s+\d+$")


@dataclass(slots=True)
class ClassifiedFile:
    path: Path
    kind: str
    key: str
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PairItem:
    key: str
    odt: Path
    pdf: Path


@dataclass(slots=True)
class ValidationResult:
    status: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProcessResult:
    key: str
    status: str
    source_semi_odt: str
    source_pdf: str
    source_base_odt: str = ""
    output_odt: str = ""
    output_text: str = ""
    output_validation: str = ""
    output_sha256: str = ""
    inserted_lines: int = 0
    blank_paragraphs_removed_between_parts: int = 0
    nonblank_between_parts_before_replacement: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def strip_invalid_xml_chars(text: str) -> tuple[str, int]:
    removed = 0
    chars: list[str] = []
    for char in text:
        codepoint = ord(char)
        if (
            codepoint in (0x09, 0x0A, 0x0D)
            or 0x20 <= codepoint <= 0xD7FF
            or 0xE000 <= codepoint <= 0xFFFD
            or 0x10000 <= codepoint <= 0x10FFFF
        ):
            chars.append(char)
        else:
            removed += 1
    return "".join(chars), removed


def normalize_text(text: str) -> str:
    text = text.replace("\u00aa", "A").replace("\u00ba", "O").replace("\u00b0", "O")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().upper()


def normalize_key(value: str) -> str:
    key = Path(value).stem
    key = normalize_text(key).lower()
    key = re.sub(r"^\d+\s*[-_]*\s*", "", key)
    key = re.sub(
        r"\b(?:s\s*ten|sub\s*ten|sten|[123]\s*o?\s*sgt|cb|sd|rec|rcr)\b",
        " ",
        key,
    )
    key = re.sub(r"\b[12]\s*o?\s*sem(?:estre)?\b", " ", key)
    key = re.sub(r"\b(sem|semestre|ok|odt|pdf)\b", " ", key)
    key = re.sub(r"\b20\d{2}\b", " ", key)
    key = re.sub(r"\b\d+o?\b", " ", key)
    key = re.sub(r"\bo$", " ", key)
    key = re.sub(r"[^a-z0-9]+", " ", key)
    return re.sub(r"\s+", " ", key).strip()


def pdf_key(path: Path) -> str:
    stem = normalize_text(path.stem).lower()
    stem = re.sub(r"\s*\(\d+\)\s*$", "", stem)
    stem = stem.replace("-", "_").replace(" ", "_")
    stem = PDF_GRADE_PREFIX_RE.sub("", stem).strip("_ ")
    key = normalize_key(stem)
    return PDF_COPY_SUFFIX_RE.sub("", key).strip()


def classify_file(path: Path) -> ClassifiedFile | None:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return ClassifiedFile(path=path, kind="PDF_PARTE1", key=pdf_key(path))
    if suffix == ".txt":
        return ClassifiedFile(path=path, kind="TXT_PARTE1", key=pdf_key(path))
    if suffix != ".odt":
        return None
    key = normalize_key(path.name)
    name_norm = normalize_text(path.stem)
    if "MODELO" in name_norm:
        return ClassifiedFile(path=path, kind="MODELO_ODT", key=key)
    if re.search(r"\bOK\b", name_norm):
        return ClassifiedFile(path=path, kind="ODT_OK_REFERENCIA", key=key)
    return ClassifiedFile(
        path=path,
        kind="ODT_SEMI_OK",
        key=key,
        warnings=["WARN_ODT_ASSUMED_SEMI_OK_BY_FILENAME"],
    )


def build_pairs(input_dir: Path) -> tuple[list[PairItem], list[ClassifiedFile]]:
    classified = [
        item
        for path in sorted(input_dir.iterdir())
        if path.is_file()
        for item in [classify_file(path)]
        if item is not None
    ]
    sources_by_key = {
        item.key: item.path
        for item in classified
        if item.kind in {"PDF_PARTE1", "TXT_PARTE1"} and item.key
    }
    pairs: list[PairItem] = []
    for item in classified:
        if item.kind != "ODT_SEMI_OK":
            continue
        source = sources_by_key.get(item.key)
        if source:
            pairs.append(PairItem(key=item.key, odt=item.path, pdf=source))
    return pairs, classified


def build_source_pair(source: Path) -> PairItem:
    key = pdf_key(source)
    return PairItem(key=key, odt=source.with_suffix(".odt"), pdf=source)


def find_modelo_odt(classified: list[ClassifiedFile]) -> Path | None:
    modelos = [item.path for item in classified if item.kind == "MODELO_ODT"]
    return sorted(modelos, key=lambda path: path.name.lower())[0] if modelos else None


def militar_output_stem(pair: PairItem) -> str:
    if pair.odt.suffix.lower() != ".odt" or not pair.odt.exists():
        return re.sub(r"\s+", " ", pair.key).strip().upper() or "FOLHA_ALTERACOES"
    stem = pair.odt.stem
    stem = re.sub(r"^\d+\s*[-_]*\s*", "", stem).strip()
    stem = re.sub(r"\b(?:o|ok|odt)\b\s*$", "", stem, flags=re.I).strip()
    stem = re.sub(r"\s+-\s+c[oó]pia$", "", stem, flags=re.I).strip()
    if not stem:
        stem = pair.key.upper()
    stem = re.sub(r'[<>:"/\\|?*]+', " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    return stem or "folha_alteracoes"


def final_odt_stem_from_source(source_semi_odt: str, fallback_key: str) -> str:
    source = Path(source_semi_odt)
    if source.suffix.lower() == ".odt":
        stem = source.stem
        stem = re.sub(r"^\d+\s*[-_]*\s*", "", stem).strip()
        stem = re.sub(r"\b(?:o|ok|odt)\b\s*$", "", stem, flags=re.I).strip()
        stem = re.sub(r"\s+-\s+c[oó]pia$", "", stem, flags=re.I).strip()
    else:
        stem = fallback_key.upper()
    stem = re.sub(r'[<>:"/\\|?*]+', " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    return stem or fallback_key.upper() or "folha_alteracoes"


def extract_parte1_from_text(text: str, semestre: str) -> str:
    expected_months = MONTHS_BY_SEMESTER.get(str(semestre), MONTHS_BY_SEMESTER["2"])
    starts = [text.find(f"{month}:") for month in expected_months if text.find(f"{month}:") >= 0]
    start = min(starts) if starts else 0
    end_candidates = [
        start + match.start()
        for match in re.finditer(r"\bComportamento\s*:", text[start:], flags=re.I)
    ]
    end_candidates.extend(
        start + match.start()
        for match in re.finditer(r"\b2[ªA]?\s+PARTE\b", text[start:], flags=re.I)
    )
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end]


def read_text_source(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="latin-1", errors="replace")


def extract_parte1_from_source(source_path: Path, semestre: str) -> str:
    if source_path.suffix.lower() == ".txt":
        return extract_parte1_from_text(read_text_source(source_path), semestre)
    return extract_parte1_from_pdf(source_path, semestre)


def extract_parte1_from_pdf(pdf_path: Path, semestre: str) -> str:
    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)
    return extract_parte1_from_text("\n".join(pages), semestre)


def remove_inline_pdf_headers(line: str) -> tuple[str, int]:
    return INLINE_PDF_HEADER_RE.subn("", line)


def should_drop_pdf_line(line: str) -> bool:
    normalized = normalize_text(line)
    if not normalized:
        return False
    if "BASE ADMINISTRATIVA DO QUARTEL-GENERAL DO EXERCITO" in normalized:
        return True
    if normalized.startswith("FOLHA N") or normalized.startswith(
        "CONTINUACAO DAS FOLHAS DE ALTERACOES"
    ):
        return True
    if re.match(
        r"^DO\s+(S\s+TEN|STEN|SUB\s+TEN|1O\s+SGT|2O\s+SGT|3O\s+SGT|CB|SD|REC|RCR)\s+",
        normalized,
    ):
        return True
    if normalized.startswith("DO ") and re.search(
        r"\b(SGT|TEN|CEL|MAJ|CAP|CB|SD|REC|RCR)\b",
        normalized[:45],
    ):
        return True
    if " SEMESTRE DE 2025" in normalized and len(normalized) < 40:
        return True
    return normalized == "CP:" or normalized.startswith(("CP: PER", "PERIODO:"))


def clean_parte1_lines(raw_text: str) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    dropped_headers = 0
    dropped_inline_headers = 0
    invalid_xml_removed = 0
    sensitive_hits: set[str] = set()
    possible_table = False

    for raw_line in raw_text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        line, inline_removed = remove_inline_pdf_headers(line)
        dropped_inline_headers += inline_removed
        line = re.sub(r"[ \t]+", " ", line).strip()
        line, removed = strip_invalid_xml_chars(line)
        invalid_xml_removed += removed
        if should_drop_pdf_line(line):
            dropped_headers += 1
            continue
        if line:
            match = SENSITIVE_RE.search(line)
            if match:
                sensitive_hits.add(match.group(1).upper())
            normalized = normalize_text(line)
            if (
                normalized in {"P/G", "NOME", "PERIODO ANTERIOR", "NOVO PERIODO", "SEC/DIV"}
                or "P/G" in normalized
                or "SEC/DIV" in normalized
            ):
                possible_table = True
        lines.append(line)

    compact: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line
        if blank and previous_blank:
            continue
        compact.append(line)
        previous_blank = blank
    while compact and not compact[0]:
        compact.pop(0)
    while compact and not compact[-1]:
        compact.pop()

    warnings: list[str] = []
    if dropped_headers:
        warnings.append(f"OK_PDF_PAGE_HEADERS_REMOVED:{dropped_headers}")
    if dropped_inline_headers:
        warnings.append(f"OK_INLINE_PDF_PAGE_HEADERS_REMOVED:{dropped_inline_headers}")
    if invalid_xml_removed:
        warnings.append(f"OK_INVALID_XML_CHARS_REMOVED:{invalid_xml_removed}")
    if sensitive_hits:
        warnings.append("WARN_POSSIBLE_SENSITIVE_EVENT:" + ",".join(sorted(sensitive_hits)))
        warnings.append("WARN_REVIEW_BEFORE_SIGNATURE")
    if possible_table:
        warnings.append("WARN_POSSIBLE_TABLE_BLOCK")
    return compact, warnings


def is_month_line(line: str, semestre: str) -> bool:
    stripped = line.strip()
    months = set(MONTHS_BY_SEMESTER.get(str(semestre), MONTHS_BY_SEMESTER["2"]))
    return stripped.endswith(":") and normalize_text(stripped.rstrip(":")) in months


def is_reference_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("- a ") or stripped.startswith("- a") or stripped.startswith("- à")


def split_compact_empty_month_line(line: str, semestre: str) -> list[str]:
    stripped = line.strip()
    if ":" not in stripped:
        return [line]
    month_part, body_part = stripped.split(":", 1)
    month = normalize_text(month_part)
    body = body_part.strip()
    months = set(MONTHS_BY_SEMESTER.get(str(semestre), MONTHS_BY_SEMESTER["2"]))
    body_normalized = normalize_text(body).rstrip(".")
    if month not in months or body_normalized not in {"SEM ALTERACAO", "SEM ALTERACOES"}:
        return [line]
    return [f"{month}:", body]


def is_part1_heading_line(line: str) -> bool:
    normalized = normalize_text(line)
    return normalized.startswith("1") and "PARTE" in normalized


def next_nonblank_index(lines: list[str], start: int) -> int | None:
    for index in range(start, len(lines)):
        if lines[index].strip():
            return index
    return None


def is_title_prefix_fragment(line: str) -> bool:
    stripped = line.strip()
    normalized = normalize_text(stripped)
    if not stripped or len(normalized) < 4 or len(normalized) > 60:
        return False
    if is_reference_line(stripped) or is_part1_heading_line(stripped):
        return False
    if normalized.endswith(":") or "." in stripped:
        return False
    alpha_chars = [char for char in stripped if char.isalpha()]
    if alpha_chars:
        uppercase_ratio = sum(char.isupper() for char in alpha_chars) / len(alpha_chars)
        if uppercase_ratio < 0.8:
            return False
    return all(char.isalnum() or char in " /-" for char in normalized)


def split_embedded_event_titles(lines: list[str]) -> tuple[list[str], list[str]]:
    output: list[str] = []
    warnings: list[str] = []
    recovered = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        next_index = next_nonblank_index(lines, index + 1)
        next_line = lines[next_index].strip() if next_index is not None else ""
        reference_index = (
            next_nonblank_index(lines, next_index + 1) if next_index is not None else None
        )
        reference_line = lines[reference_index].strip() if reference_index is not None else ""
        tail_split = split_trailing_uppercase_title(stripped)
        if (
            tail_split is not None
            and next_index == index + 1
            and next_line
            and is_title_prefix_fragment(next_line.rstrip("."))
            and is_reference_line(reference_line)
        ):
            body, title_prefix = tail_split
            output.append(body)
            output.append(re.sub(r"\s+", " ", f"{title_prefix} {next_line}").strip())
            recovered += 1
            index += 2
            continue
        if (
            is_title_prefix_fragment(stripped)
            and next_index == index + 1
            and next_line
            and " - " in next_line
            and is_reference_line(reference_line)
        ):
            output.append(re.sub(r"\s+", " ", f"{stripped} {next_line}").strip())
            recovered += 1
            index += 2
            continue
        match = EMBEDDED_EVENT_TITLE_RE.match(stripped)
        if (
            match
            and next_index == index + 1
            and next_line
            and not is_reference_line(next_line)
            and is_reference_line(reference_line)
        ):
            output.append(match.group("body").strip())
            output.append(re.sub(r"\s+", " ", f"{match.group('title')} {next_line}").strip())
            recovered += 1
            index += 2
            continue
        prefix_match = EMBEDDED_EVENT_TITLE_PREFIX_RE.match(stripped)
        if (
            prefix_match
            and next_index == index + 1
            and next_line
            and " - " in next_line
            and is_reference_line(reference_line)
        ):
            output.append(prefix_match.group("body").strip())
            output.append(
                re.sub(r"\s+", " ", f"{prefix_match.group('title')} {next_line}").strip()
            )
            recovered += 1
            index += 2
            continue
        output.append(line)
        index += 1
    if recovered:
        warnings.append(f"OK_EVENT_TITLE_SPLIT_RECOVERED:{recovered}")
    return output, warnings


def split_trailing_uppercase_title(line: str) -> tuple[str, str] | None:
    if ":" not in line:
        return None
    body, candidate = line.rsplit(":", 1)
    candidate = candidate.strip()
    if len(candidate) < 20:
        return None
    words = candidate.split()
    if len(words) < 4:
        return None
    alpha_chars = [char for char in candidate if char.isalpha()]
    if not alpha_chars:
        return None
    uppercase_ratio = sum(char.isupper() for char in alpha_chars) / len(alpha_chars)
    if uppercase_ratio < 0.8:
        return None
    return f"{body.strip()}:", candidate


def should_keep_body_line_separate(line: str) -> bool:
    stripped = line.strip()
    normalized = normalize_text(stripped)
    if not stripped:
        return False
    label_prefixes = (
        "NOME:",
        "CPF:",
        "NOME TITULAR:",
        "NOME DO ALUNO:",
        "BANCO:",
        "AG:",
        "AGENCIA:",
        "C/C:",
        "CONTA:",
        "VALOR:",
        "- IDT:",
        "- NOME:",
        "- LEGENDA:",
        "P/G",
        "SEC/DIV",
    )
    if any(normalized.startswith(prefix) for prefix in label_prefixes):
        return True
    if normalized in {"MEMBRO", "PERIODO ANTERIOR", "NOVO PERIODO"}:
        return True
    return bool(re.match(r"^\d{1,2}\.\s+[A-Z0-9]", normalized))


def is_structural_body_line(line: str) -> bool:
    return should_keep_body_line_separate(line)


def normalize_parte1_paragraphs(lines: list[str], semestre: str) -> tuple[list[str], list[str]]:
    """Turn PDF-extracted physical lines into document paragraphs.

    The PDF extraction keeps visual line wrapping. The ODT final should keep
    months, titles and BI references isolated, but body text must be merged
    into readable paragraphs.
    """
    output: list[str] = []
    warnings: list[str] = []
    body_buffer: list[str] = []
    expanded_lines: list[str] = []
    compact_empty_months = 0
    for line in lines:
        expanded = split_compact_empty_month_line(line, semestre)
        compact_empty_months += len(expanded) - 1
        expanded_lines.extend(expanded)
    lines = expanded_lines
    if compact_empty_months:
        warnings.append(f"OK_EMPTY_MONTH_COMPACT_SPLIT:{compact_empty_months}")
    lines, split_warnings = split_embedded_event_titles(lines)
    warnings.extend(split_warnings)

    def flush_body() -> None:
        if not body_buffer:
            return
        paragraph = re.sub(r"\s+", " ", " ".join(body_buffer)).strip()
        if paragraph:
            output.append(paragraph)
        body_buffer.clear()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            flush_body()
            continue

        next_index = next_nonblank_index(lines, index + 1)
        next_line = lines[next_index].strip() if next_index is not None else ""
        is_title_followed_by_reference = bool(next_line and is_reference_line(next_line))

        if is_month_line(stripped, semestre):
            flush_body()
            output.append(stripped)
            continue
        if is_reference_line(stripped):
            flush_body()
            output.append(re.sub(r"\s+:", ":", stripped))
            continue
        if is_title_followed_by_reference:
            flush_body()
            output.append(stripped)
            continue
        if should_keep_body_line_separate(stripped):
            flush_body()
            output.append(stripped)
            continue
        body_buffer.append(stripped)

    flush_body()
    output, post_split_warnings = split_embedded_event_titles(output)
    warnings.extend(post_split_warnings)
    if len(output) < len([line for line in lines if line.strip()]):
        warnings.append(f"OK_EVENT_BODY_PARAGRAPHS_NORMALIZED:{len(lines)}->{len(output)}")
    return output, warnings


def ensure_required_months(lines: list[str], semestre: str) -> tuple[list[str], list[str]]:
    expected_months = MONTHS_BY_SEMESTER.get(str(semestre), MONTHS_BY_SEMESTER["2"])
    prefix: list[str] = []
    blocks: dict[str, list[str]] = {}
    current_month: str | None = None

    for line in lines:
        if is_month_line(line, semestre):
            current_month = normalize_text(line.strip().rstrip(":"))
            blocks.setdefault(current_month, [f"{current_month}:"])
            continue
        if current_month:
            blocks.setdefault(current_month, [f"{current_month}:"]).append(line)
        else:
            prefix.append(line)

    output = list(prefix)
    missing: list[str] = []
    for month in expected_months:
        block = blocks.get(month)
        if block:
            output.extend(block)
            continue
        missing.append(month)
        output.extend([f"{month}:", "Sem alterações."])

    warnings = [f"OK_EMPTY_MONTHS_FILLED:{','.join(missing)}"] if missing else []
    return output, warnings


def paragraph_text(element: ET.Element) -> str:
    return "".join(element.itertext()).strip()


def is_part_label(label: str, number: int) -> bool:
    normalized = normalize_text(label)
    return normalized.startswith(str(number)) and "PARTE" in normalized


def find_part_indices(parent: ET.Element) -> tuple[int, int]:
    first = second = None
    labels: list[tuple[int, str]] = []
    for index, child in enumerate(list(parent)):
        if child.tag not in TEXT_TAGS:
            continue
        label = paragraph_text(child)
        if "PARTE" in normalize_text(label):
            labels.append((index, label))
        if first is None and is_part_label(label, 1):
            first = index
        elif second is None and is_part_label(label, 2):
            second = index
    if first is None or second is None or first >= second:
        raise ValueError(f"Marcadores 1a/2a PARTE invalidos: {labels}")
    return first, second


def looks_like_event_title(line: str) -> bool:
    stripped = line.strip()
    normalized = normalize_text(stripped)
    if not stripped or is_reference_line(stripped) or normalized.endswith(":"):
        return False
    if is_structural_body_line(stripped):
        return False
    if stripped and stripped.upper() == stripped and len(stripped) > 8 and not re.match(r"^\d", stripped):
        return True
    return False


def style_for_line_at(lines: list[str], index: int, semestre: str) -> str:
    line = lines[index]
    stripped = line.strip()
    if is_part1_heading_line(stripped):
        return SISGES_PARTE1_STYLE_TITLE
    if is_month_line(stripped, semestre):
        return SISGES_PARTE1_STYLE_MONTH
    if is_reference_line(stripped):
        return SISGES_PARTE1_STYLE_REFERENCE
    next_index = next_nonblank_index(lines, index + 1)
    next_line = lines[next_index].strip() if next_index is not None else ""
    if next_line and is_reference_line(next_line):
        return SISGES_PARTE1_STYLE_EVENT_TITLE
    if looks_like_event_title(stripped):
        return SISGES_PARTE1_STYLE_EVENT_TITLE
    return SISGES_PARTE1_STYLE_BODY


def style_for_line(line: str, semestre: str) -> str:
    stripped = line.strip()
    if is_part1_heading_line(stripped):
        return SISGES_PARTE1_STYLE_TITLE
    if is_month_line(stripped, semestre):
        return SISGES_PARTE1_STYLE_MONTH
    if is_reference_line(stripped):
        return SISGES_PARTE1_STYLE_REFERENCE
    if looks_like_event_title(stripped):
        return SISGES_PARTE1_STYLE_EVENT_TITLE
    return SISGES_PARTE1_STYLE_BODY


def ensure_paragraph_style(
    automatic_styles: ET.Element,
    *,
    name: str,
    underline: bool = False,
    text_align: str = "justify",
    font_weight: str = "normal",
    margin_bottom: str = "0cm",
) -> None:
    for child in automatic_styles.findall(STYLE_STYLE):
        if child.attrib.get(STYLE_NAME) == name:
            return

    style = ET.Element(STYLE_STYLE)
    style.set(STYLE_NAME, name)
    style.set(STYLE_FAMILY, "paragraph")
    style.set(STYLE_PARENT, "Standard")

    paragraph_properties = ET.SubElement(style, STYLE_PARAGRAPH_PROPERTIES)
    paragraph_properties.set(f"{{{NS['fo']}}}margin-left", "0cm")
    paragraph_properties.set(f"{{{NS['fo']}}}margin-right", "0cm")
    paragraph_properties.set(f"{{{NS['fo']}}}margin-top", "0cm")
    paragraph_properties.set(f"{{{NS['fo']}}}margin-bottom", margin_bottom)
    paragraph_properties.set(f"{{{NS['fo']}}}text-align", text_align)
    paragraph_properties.set(f"{{{NS['style']}}}justify-single-word", "false")
    paragraph_properties.set(f"{{{NS['fo']}}}text-indent", "0cm")
    paragraph_properties.set(f"{{{NS['style']}}}auto-text-indent", "false")

    text_properties = ET.SubElement(style, STYLE_TEXT_PROPERTIES)
    text_properties.set(f"{{{NS['style']}}}font-name", "Calibri Light1")
    text_properties.set(f"{{{NS['fo']}}}font-size", "12pt")
    text_properties.set(f"{{{NS['fo']}}}font-weight", font_weight)
    text_properties.set(f"{{{NS['style']}}}font-size-asian", "12pt")
    text_properties.set(f"{{{NS['style']}}}font-weight-asian", font_weight)
    text_properties.set(f"{{{NS['style']}}}font-size-complex", "12pt")
    text_properties.set(f"{{{NS['style']}}}font-weight-complex", font_weight)
    if underline:
        text_properties.set(f"{{{NS['style']}}}text-underline-style", "solid")
        text_properties.set(f"{{{NS['style']}}}text-underline-width", "auto")
        text_properties.set(f"{{{NS['style']}}}text-underline-color", "font-color")
    else:
        text_properties.set(f"{{{NS['style']}}}text-underline-style", "none")

    automatic_styles.append(style)


def ensure_parte1_styles(root: ET.Element) -> None:
    automatic_styles = root.find("office:automatic-styles", NS)
    if automatic_styles is None:
        automatic_styles = ET.Element(OFFICE_AUTOMATIC_STYLES)
        root.insert(0, automatic_styles)
    ensure_paragraph_style(
        automatic_styles,
        name=SISGES_PARTE1_STYLE_TITLE,
        underline=True,
    )
    ensure_paragraph_style(
        automatic_styles,
        name=SISGES_PARTE1_STYLE_MONTH,
        underline=True,
    )
    ensure_paragraph_style(
        automatic_styles,
        name=SISGES_PARTE1_STYLE_EVENT_TITLE,
        font_weight="bold",
    )
    ensure_paragraph_style(
        automatic_styles,
        name=SISGES_PARTE1_STYLE_REFERENCE,
    )
    ensure_paragraph_style(
        automatic_styles,
        name=SISGES_PARTE1_STYLE_BODY,
    )


def make_paragraph(text: str, style: str) -> ET.Element:
    paragraph = ET.Element(TEXT_P)
    paragraph.set(TEXT_STYLE, style)
    paragraph.text = text
    return paragraph


def is_event_title_line(line: str, semestre: str) -> bool:
    return style_for_line(line, semestre) == SISGES_PARTE1_STYLE_EVENT_TITLE


def should_add_spacing_around(line: str, semestre: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and (
        is_month_line(stripped, semestre) or is_event_title_line(stripped, semestre)
    )


def build_spaced_parte1_paragraphs(parte1_lines: list[str], semestre: str) -> list[ET.Element]:
    paragraphs: list[ET.Element] = []

    def append_blank_once() -> None:
        if paragraphs and paragraph_text(paragraphs[-1]):
            paragraphs.append(make_paragraph("", SISGES_PARTE1_STYLE_BODY))

    for index, line in enumerate(parte1_lines):
        style = style_for_line_at(parte1_lines, index, semestre)
        add_spacing = style in {SISGES_PARTE1_STYLE_MONTH, SISGES_PARTE1_STYLE_EVENT_TITLE}
        if add_spacing and paragraphs:
            append_blank_once()
        paragraphs.append(make_paragraph(line, style))
        if add_spacing:
            append_blank_once()
    paragraphs.append(make_paragraph("", "P35"))
    return paragraphs


def render_parte1_into_odt(
    *,
    source_odt: Path,
    output_odt: Path,
    parte1_lines: list[str],
    semestre: str,
) -> tuple[int, list[str]]:
    with zipfile.ZipFile(source_odt, "r") as archive:
        infos = {info.filename: info for info in archive.infolist()}
        names = archive.namelist()
        data = {name: archive.read(name) for name in names}

    root = ET.fromstring(data["content.xml"])
    ensure_parte1_styles(root)
    body = root.find("office:body", NS)
    text_node = body.find("office:text", NS) if body is not None else None
    if text_node is None:
        raise ValueError("office:text nao encontrado no ODT.")

    first_index, second_index = find_part_indices(text_node)
    children = list(text_node)
    placeholder_child = next(
        (
            child
            for child in children[first_index + 1 : second_index]
            if child.tag in TEXT_TAGS and PARTE1_PLACEHOLDER in paragraph_text(child)
        ),
        None,
    )
    if placeholder_child is not None:
        blank_removed = 0
        nonblank_before = [PARTE1_PLACEHOLDER]
        insert_after = list(text_node).index(placeholder_child)
        text_node.remove(placeholder_child)
    else:
        between = children[first_index + 1 : second_index]
        blank_removed = sum(
            1 for child in between if child.tag in TEXT_TAGS and not paragraph_text(child)
        )
        nonblank_before = [
            paragraph_text(child)[:160]
            for child in between
            if child.tag in TEXT_TAGS and paragraph_text(child)
        ]
        for child in between:
            text_node.remove(child)
        insert_after = list(text_node).index(children[first_index]) + 1

    paragraphs = build_spaced_parte1_paragraphs(parte1_lines, semestre)
    for offset, paragraph in enumerate(paragraphs):
        text_node.insert(insert_after + offset, paragraph)

    data["content.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(output_odt, "w") as output:
        for name in names:
            output.writestr(infos[name], data[name])
    return blank_removed, nonblank_before


def validate_generated_odt(path: Path, semestre: str) -> ValidationResult:
    result = ValidationResult(status="OK")
    content = b""
    styles = b""
    try:
        with zipfile.ZipFile(path, "r") as archive:
            bad = archive.testzip()
            if bad:
                result.errors.append(f"ERR_ODT_ZIP_CORRUPTED:{bad}")
            else:
                result.checks.append("OK_ODT_ZIP_VALID")
            names = set(archive.namelist())
            for required in ("content.xml", "styles.xml", "META-INF/manifest.xml"):
                if required in names:
                    result.checks.append(f"OK_ODT_ENTRY_PRESENT:{required}")
                else:
                    result.errors.append(f"ERR_ODT_ENTRY_MISSING:{required}")
            content = archive.read("content.xml") if "content.xml" in names else b""
            styles = archive.read("styles.xml") if "styles.xml" in names else b""
    except Exception as exc:
        result.errors.append(f"ERR_ODT_OPEN_FAILED:{exc}")

    if content:
        try:
            root = ET.fromstring(content)
            result.checks.append("OK_CONTENT_XML_PARSEABLE")
            plain = "".join(root.itertext())
            normalized = normalize_text(plain)
            for token in ("1A PARTE", "2A PARTE"):
                if token in normalized:
                    result.checks.append(f"OK_TEXT_PRESENT:{token}")
                else:
                    result.errors.append(f"ERR_EXPECTED_TEXT_MISSING:{token}")
            expected_months = MONTHS_BY_SEMESTER.get(str(semestre), MONTHS_BY_SEMESTER["2"])
            for month in expected_months:
                count = normalized.count(f"{month}:")
                if count >= 1:
                    result.checks.append(f"OK_MONTH_PRESENT:{month}:{count}")
                else:
                    result.errors.append(f"ERR_MONTH_MISSING:{month}")
                if count > 1:
                    result.warnings.append(f"WARN_MONTH_REPEATED_IN_TEXT:{month}:{count}")
            if PLACEHOLDER_RE.search(plain):
                result.errors.append("ERR_TEMPLATE_PLACEHOLDER_LEFTOVER")
            else:
                result.checks.append("OK_TEMPLATE_PLACEHOLDERS_REPLACED")
            if "QUALQUER QMG" in normalized or "QUALQUER QMP" in normalized:
                result.errors.append("ERR_QMS_RAW_LEAKED")
            else:
                result.checks.append("OK_QMS_RAW_NOT_FOUND")
            if any(
                marker in normalized
                for marker in ("CONTRACHEQUE", "SIPPES", "PAGAMENTO", "BENEFICIARIO")
            ):
                result.warnings.append("WARN_POSSIBLE_SENSITIVE_EVENT")
        except Exception as exc:
            result.errors.append(f"ERR_CONTENT_XML_INVALID:{exc}")
    if styles:
        try:
            ET.fromstring(styles)
            result.checks.append("OK_STYLES_XML_PARSEABLE")
        except Exception as exc:
            result.errors.append(f"ERR_STYLES_XML_INVALID:{exc}")

    if result.errors:
        result.status = "ERROR"
    elif result.warnings:
        result.status = "OK_WITH_WARNINGS"
    return result


def process_pair(
    pair: PairItem,
    output_dir: Path,
    semestre: str,
    *,
    base_odt: Path | None = None,
    output_name_mode: str = "experimental",
) -> ProcessResult:
    safe_key = re.sub(r"[^A-Za-z0-9_-]+", "_", pair.key).strip("_") or pair.odt.stem
    source_base_odt = base_odt or pair.odt
    output_odt = (
        output_dir / f"{militar_output_stem(pair)}.odt"
        if output_name_mode == "militar"
        else output_dir / f"{safe_key}_parte1_experimental.odt"
    )
    output_text = output_dir / f"{safe_key}_parte1_limpa.txt"
    output_validation = output_dir / f"{safe_key}_validacao.json"
    output_trace = output_dir / f"{safe_key}_trace.json"
    try:
        raw = extract_parte1_from_source(pair.pdf, semestre)
        lines, warnings = clean_parte1_lines(raw)
        paragraphs, paragraph_warnings = normalize_parte1_paragraphs(lines, semestre)
        paragraphs, month_warnings = ensure_required_months(paragraphs, semestre)
        output_text.write_text("\n".join(paragraphs) + "\n", encoding="utf-8")
        if base_odt is not None:
            shutil.copy2(source_base_odt, output_odt)
            render_source = output_odt
            extra_warnings = ["OK_MODELO_ODT_DUPLICATED_FOR_MILITAR"]
        else:
            render_source = source_base_odt
            extra_warnings = []
        blanks, nonblank_before = render_parte1_into_odt(
            source_odt=render_source,
            output_odt=output_odt,
            parte1_lines=paragraphs,
            semestre=semestre,
        )
        validation = validate_generated_odt(output_odt, semestre)
        output_validation.write_text(
            json.dumps(asdict(validation), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result = ProcessResult(
            key=pair.key,
            status=validation.status,
            source_semi_odt=str(pair.odt),
            source_pdf=str(pair.pdf),
            source_base_odt=str(source_base_odt),
            output_odt=str(output_odt),
            output_text=str(output_text),
            output_validation=str(output_validation),
            output_sha256=sha256_file(output_odt),
            inserted_lines=len(paragraphs),
            blank_paragraphs_removed_between_parts=blanks,
            nonblank_between_parts_before_replacement=nonblank_before,
            warnings=(
                warnings
                + paragraph_warnings
                + month_warnings
                + extra_warnings
                + validation.warnings
            ),
            errors=validation.errors,
        )
    except Exception as exc:
        result = ProcessResult(
            key=pair.key,
            status="ERROR",
            source_semi_odt=str(pair.odt),
            source_pdf=str(pair.pdf),
            source_base_odt=str(source_base_odt),
            errors=[repr(exc)],
        )
    output_trace.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def write_classification(output_dir: Path, classified: list[ClassifiedFile], pairs: list[PairItem]) -> None:
    paired_keys = {pair.key for pair in pairs}
    path = output_dir / "matriz_pares_semi_ok.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["arquivo", "tipo", "chave", "pareado", "warnings"],
        )
        writer.writeheader()
        for item in classified:
            writer.writerow(
                {
                    "arquivo": item.path.name,
                    "tipo": item.kind,
                    "chave": item.key,
                    "pareado": item.kind == "ODT_SEMI_OK" and item.key in paired_keys,
                    "warnings": ";".join(item.warnings),
                }
            )


def write_reports(output_dir: Path, input_dir: Path, results: list[ProcessResult]) -> None:
    payload = {
        "schema_version": "sisges-semi-ok-parte1-batch-v1",
        "generated_at": now_iso(),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "total": len(results),
        "ok": sum(item.status == "OK" for item in results),
        "ok_with_warnings": sum(item.status == "OK_WITH_WARNINGS" for item in results),
        "errors": sum(item.status == "ERROR" for item in results),
        "items": [asdict(item) for item in results],
    }
    (output_dir / "resumo_lote_semi_ok_parte1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (output_dir / "resumo_lote_semi_ok_parte1.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "key",
                "status",
                "errors",
                "warnings",
                "inserted_lines",
                "output_odt",
                "source_pdf",
                "sha256",
            ],
        )
        writer.writeheader()
        for item in results:
            writer.writerow(
                {
                    "key": item.key,
                    "status": item.status,
                    "errors": len(item.errors),
                    "warnings": len(item.warnings),
                    "inserted_lines": item.inserted_lines,
                    "output_odt": item.output_odt,
                    "source_pdf": item.source_pdf,
                    "sha256": item.output_sha256,
                }
            )
    lines = [
        "RELATORIO SISGES - COMPLETAR ODT SEMI OK COM PARTE 1",
        f"Gerado em: {payload['generated_at']}",
        "",
        f"Entrada: {input_dir}",
        f"Saida: {output_dir}",
        "",
        f"Total processado: {payload['total']}",
        f"OK: {payload['ok']}",
        f"OK com warnings: {payload['ok_with_warnings']}",
        f"Erros: {payload['errors']}",
        "",
        "Itens:",
    ]
    for item in results:
        lines.append(f"- {item.key}: {item.status}")
        lines.append(f"  ODT: {item.output_odt or '-'}")
        if item.warnings:
            lines.append(f"  Warnings: {', '.join(item.warnings)}")
        if item.errors:
            lines.append(f"  Erros: {', '.join(item.errors)}")
    lines.extend(
        [
            "",
            "Leitura operacional:",
            "- Este comando nao altera a pasta original.",
            "- Status OK_WITH_WARNINGS exige conferencia visual antes de assinatura.",
            "- Tabelas e conteudo sensivel devem ser revisados manualmente.",
        ]
    )
    (output_dir / "RELATORIO_LOTE_SEMI_OK_PARTE1.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def collect_final_odts(output_dir: Path, results: list[ProcessResult]) -> None:
    final_dir = output_dir / "ODTS_FINAIS"
    final_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []
    used_names: set[str] = set()

    for item in results:
        if item.status not in {"OK", "OK_WITH_WARNINGS"} or not item.output_odt:
            continue
        source = Path(item.output_odt)
        if not source.exists():
            continue
        stem = final_odt_stem_from_source(item.source_semi_odt, item.key)
        filename = f"{stem}.odt"
        counter = 2
        while filename.lower() in used_names:
            filename = f"{stem} ({counter}).odt"
            counter += 1
        used_names.add(filename.lower())
        target = final_dir / filename
        shutil.copy2(source, target)
        manifest.append(
            {
                "key": item.key,
                "status": item.status,
                "source_odt": item.source_semi_odt,
                "source_parte1": item.source_pdf,
                "output_odt": item.output_odt,
                "final_odt": str(target),
                "sha256": sha256_file(target),
                "warnings": ";".join(item.warnings),
            }
        )

    (final_dir / "manifesto_odts_finais.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (final_dir / "manifesto_odts_finais.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "key",
                "status",
                "source_odt",
                "source_parte1",
                "output_odt",
                "final_odt",
                "sha256",
                "warnings",
            ],
        )
        writer.writeheader()
        writer.writerows(manifest)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Completa ODTs semi OK de Folhas de Alteracoes com a 1a Parte extraida de PDFs."
    )
    parser.add_argument("--input", required=True, help="Pasta com ODTs semi OK e PDFs.")
    parser.add_argument("--output", required=True, help="Pasta de saida.")
    parser.add_argument(
        "--source",
        action="append",
        help="Arquivo PDF ou TXT especifico para usar como fonte da Parte 1. Pode repetir.",
    )
    parser.add_argument("--semestre", choices=["1", "2"], default="2")
    parser.add_argument(
        "--base",
        choices=["semi-ok", "modelo"],
        default="semi-ok",
        help="Base do ODT final: ODT semi pronto de cada militar ou MODELO.odt duplicado.",
    )
    parser.add_argument(
        "--modelo",
        help="Caminho opcional do MODELO.odt. Se omitido, usa o primeiro MODELO da pasta de entrada.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Pasta de entrada invalida: {input_dir}")
    if args.source and args.base != "modelo":
        raise SystemExit("O uso de --source exige --base modelo.")

    pairs, classified = build_pairs(input_dir)
    if args.source:
        source_paths = [Path(source) for source in args.source]
        missing_sources = [source for source in source_paths if not source.exists()]
        if missing_sources:
            raise SystemExit(
                "Fonte de Parte 1 nao encontrada: "
                + ", ".join(str(source) for source in missing_sources)
            )
        pairs = [build_source_pair(source) for source in source_paths]
    modelo_odt: Path | None = None
    if args.base == "modelo":
        modelo_odt = Path(args.modelo) if args.modelo else find_modelo_odt(classified)
        if modelo_odt is None or not modelo_odt.exists():
            raise SystemExit("Modo --base modelo exige um MODELO.odt valido.")
    write_classification(output_dir, classified, pairs)
    results = [
        process_pair(
            pair,
            output_dir,
            args.semestre,
            base_odt=modelo_odt,
            output_name_mode="militar" if args.base == "modelo" else "experimental",
        )
        for pair in pairs
    ]
    write_reports(output_dir, input_dir, results)
    collect_final_odts(output_dir, results)

    print("PROCESSAMENTO SEMI OK PARTE 1 CONCLUIDO")
    print(f"Entrada: {input_dir}")
    print(f"Saida: {output_dir}")
    print(f"Pares processados: {len(results)}")
    print(f"OK: {sum(item.status == 'OK' for item in results)}")
    print(f"OK com warnings: {sum(item.status == 'OK_WITH_WARNINGS' for item in results)}")
    print(f"Erros: {sum(item.status == 'ERROR' for item in results)}")


if __name__ == "__main__":
    main()

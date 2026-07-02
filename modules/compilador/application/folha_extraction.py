"""Extracao de dados de entrada do compilador de Folhas de Alteracoes.

Cobre leitura de PDF da Ficha SiCaPEx (perfil do militar), leitura de blocos
ODT do BI/alteracoes e extracao/parsing de eventos a partir de ODT ou PDF.
"""

from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

import pdfplumber

from modules.compilador.application.folha_models import (
    CompilerOptions,
    EventBlock,
    SicapexProfile,
    TableBlock,
)
from modules.compilador.application.folha_time_calc import parse_iso_date
from modules.compilador.application.folha_xml_utils import (
    REFERENCE_PATTERN,
    classify_tipo_militar,
    clean_noise,
    collect_text,
    expand_graduacao,
    extract_regex,
    format_identity,
    infer_month_from_reference,
    is_probable_title,
    normalize_month,
    normalize_space,
    parse_date_br,
    semester_months,
    strip_ns,
)


MONTH_PATTERN = re.compile(r"^(JANEIRO|FEVEREIRO|MARÇO|MARCO|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO):?$", re.I)


def extract_pdf_text(path: Path) -> str:
    parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text)
    return "\n".join(parts)


def parse_sicapex_profile(text: str) -> SicapexProfile:
    lines = [normalize_space(line) for line in text.splitlines() if normalize_space(line)]
    joined = "\n".join(lines)
    profile = SicapexProfile()

    profile.nome_completo = extract_regex(joined, r"Nome:\s*([^\n]+)")
    idt = extract_regex(joined, r"\bIdt\s*(\d{7,12})")
    profile.identidade = format_identity(idt)

    grad_name = infer_grad_and_nome_guerra(lines)
    profile.graduacao_abrev = grad_name[0]
    profile.nome_guerra = grad_name[1]
    profile.graduacao_extenso = expand_graduacao(profile.graduacao_abrev)
    profile.tipo_militar = classify_tipo_militar(profile.graduacao_abrev)

    qm_raw = extract_qm(joined)
    profile.qm = normalize_qm(qm_raw)

    data_praca_raw = extract_data_praca(joined)
    profile.data_praca = parse_date_br(data_praca_raw) if data_praca_raw else None
    desligamento_raw = extract_data_desligamento(joined)
    profile.data_desligamento = parse_date_br(desligamento_raw) if desligamento_raw else None

    comportamento = extract_comportamento(joined)
    profile.comportamento = comportamento[0]
    profile.comportamento_data = comportamento[1]
    profile.comportamento_boletim = comportamento[2]

    profile.descontos = extract_period_section(joined, "Desconto de Tempos de Serviços")
    profile.acrescimos = extract_acrescimos(joined)
    return profile


def hydrate_profile_from_context(profile: SicapexProfile, context: dict) -> SicapexProfile:
    militar = context.get("militar") or {}
    nome_completo = normalize_space(str(militar.get("nome_completo") or ""))
    nome_guerra = normalize_space(str(militar.get("nome_guerra") or ""))
    posto_graduacao = normalize_space(str(militar.get("posto_graduacao") or ""))
    qas_qms = normalize_space(str(militar.get("qas_qms") or ""))
    identidade = normalize_space(str(militar.get("identidade") or ""))
    comportamento = normalize_space(str(militar.get("comportamento") or ""))
    data_praca = parse_iso_date(militar.get("data_praca") or context.get("data_praca"))
    data_desligamento = parse_iso_date(
        militar.get("data_licenciamento")
        or militar.get("data_desligamento")
        or context.get("data_licenciamento")
        or context.get("data_desligamento")
    )

    if nome_completo:
        profile.nome_completo = nome_completo
    if nome_guerra:
        profile.nome_guerra = nome_guerra
    if posto_graduacao:
        profile.graduacao_abrev = posto_graduacao
        profile.graduacao_extenso = expand_graduacao(posto_graduacao)
        profile.tipo_militar = classify_tipo_militar(posto_graduacao)
    if qas_qms:
        profile.qm = qas_qms
    if identidade:
        profile.identidade = format_identity(identidade)
    if data_praca:
        profile.data_praca = data_praca
    if data_desligamento:
        profile.data_desligamento = data_desligamento
    if comportamento:
        profile.comportamento = comportamento

    return profile


def extract_events_from_bi_odt(path: Path, options: CompilerOptions) -> tuple[list[EventBlock], int]:
    from modules.compilador.application.folha_event_validation import repair_tables_inside_event

    blocks = read_odt_blocks(path)
    events: list[EventBlock] = []
    current_month = ""
    current_event: EventBlock | None = None
    pending_title = ""
    detected_tables = 0

    def flush_event() -> None:
        nonlocal current_event
        if current_event:
            current_event.corpo = current_event.corpo.strip()
            events.append(current_event)
            current_event = None

    for block in blocks:
        if block["type"] == "table":
            detected_tables += 1
            table = TableBlock(
                title=block.get("title", "Tabela"),
                columns=block.get("columns") or [],
                rows=block.get("rows") or [],
            )
            if current_event:
                current_event.tables.append(table)
            continue

        line = normalize_space(block.get("text", ""))
        if not line:
            continue
        line = clean_noise(line)
        if not line:
            continue

        month_match = MONTH_PATTERN.match(line.upper())
        if month_match:
            flush_event()
            current_month = normalize_month(month_match.group(1))
            pending_title = ""
            continue

        if REFERENCE_PATTERN.match(line):
            flush_event()
            current_event = EventBlock(
                mes=current_month or infer_month_from_reference(line),
                titulo=pending_title.strip(),
                referencia=line,
                corpo="",
            )
            pending_title = ""
            continue

        if is_probable_title(line) and current_month:
            if current_event and current_event.corpo.strip():
                flush_event()
            pending_title = line
            continue

        if current_event:
            current_event.corpo += ("\n" if current_event.corpo else "") + line
        elif current_month:
            pending_title = line if not pending_title else f"{pending_title} {line}"

    flush_event()

    if options.reparar_tabelas:
        for event in events:
            repaired = repair_tables_inside_event(event.corpo)
            if repaired:
                event.corpo = repaired[0]
                event.tables.extend(repaired[1])

    return events, detected_tables


def extract_events_from_bi_source(path: Path, options: CompilerOptions) -> tuple[list[EventBlock], int]:
    if path.suffix.lower() == ".pdf":
        return extract_events_from_bi_pdf(path, options), 0
    return extract_events_from_bi_odt(path, options)


def extract_events_from_bi_pdf(path: Path, options: CompilerOptions) -> list[EventBlock]:
    text = extract_pdf_text(path)
    events: list[EventBlock] = []
    current_month = ""
    pending_title = ""
    current_event: EventBlock | None = None

    def flush_event() -> None:
        nonlocal current_event
        if current_event:
            current_event.corpo = normalize_space(current_event.corpo)
            events.append(current_event)
            current_event = None

    for raw_line in text.splitlines():
        line = clean_noise(normalize_space(raw_line))
        if not line:
            continue
        month = normalize_month(line.rstrip(":"))
        if month in semester_months(options.semestre):
            flush_event()
            current_month = month
            pending_title = ""
            continue
        if REFERENCE_PATTERN.match(line):
            flush_event()
            current_event = EventBlock(
                mes=current_month,
                titulo=pending_title,
                referencia=line,
                corpo="",
            )
            pending_title = ""
            continue
        if current_event:
            current_event.corpo = f"{current_event.corpo} {line}".strip()
        elif current_month:
            pending_title = line
    flush_event()
    return events


def read_odt_blocks(path: Path) -> list[dict]:
    with zipfile.ZipFile(path, "r") as zin:
        content = zin.read("content.xml")
    root = ET.fromstring(content)
    ns = {
        "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
        "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    }
    body = root.find(".//text:body", ns)
    blocks: list[dict] = []
    if body is None:
        return blocks
    office_text = list(body)[0] if list(body) else body
    last_paragraph = ""
    for element in list(office_text):
        tag = strip_ns(element.tag)
        if tag == "p" or tag == "h":
            text = collect_text(element)
            blocks.append({"type": "paragraph", "text": text})
            if text.strip():
                last_paragraph = text.strip()
        elif tag == "table":
            rows = extract_odt_table_rows(element)
            columns = rows[0] if rows else []
            data_rows = rows[1:] if len(rows) > 1 else []
            blocks.append(
                {
                    "type": "table",
                    "title": last_paragraph,
                    "columns": columns,
                    "rows": data_rows,
                }
            )
    return blocks


def infer_grad_and_nome_guerra(lines: list[str]) -> tuple[str, str]:
    for line in lines:
        match = re.match(r"^(1º\s*Sgt|2º\s*Sgt|3º\s*Sgt|S\s*Ten|Cap|Maj|Cel|1º\s*Ten|2º\s*Ten)\s+(.+)$", line, re.I)
        if match:
            return normalize_space(match.group(1)), normalize_space(match.group(2))
    return "", ""


def extract_qm(text: str) -> str:
    match = re.search(r"\d{3,6}\s*-\s*([^\n]+)", text)
    return normalize_space(match.group(1)) if match else ""


def normalize_qm(raw: str) -> str:
    raw = normalize_space(raw)
    upper = raw.upper()
    if not raw or "QUALQUER QMG" in upper or "QUALQUER QMP" in upper:
        return ""
    for marker in ["INTENDÊNCIA", "INFANTARIA", "COMUNICAÇÕES", "ADMINISTRAÇÃO GERAL"]:
        if marker in upper:
            return marker
    return raw


def extract_data_praca(text: str) -> str:
    match = re.search(r"Dt Praça\s+Dt Desligamento\s+Tipo de Força\s+Documento\s*\n\s*(\d{2}/\d{2}/\d{4})", text, re.I)
    if match:
        return match.group(1)
    match = re.search(r"\n(\d{2}/\d{2}/\d{4})\s+(?:Normal|EB)", text)
    return match.group(1) if match else ""


def extract_data_desligamento(text: str) -> str:
    match = re.search(
        r"Dt Praça\s+Dt Desligamento\s+Tipo de Força\s+Documento\s*\n\s*\d{2}/\d{2}/\d{4}\s+(\d{2}/\d{2}/\d{4})",
        text,
        re.I,
    )
    if match:
        return match.group(1)
    match = re.search(r"\n\d{2}/\d{2}/\d{4}\s+(\d{2}/\d{2}/\d{4})\s+(?:Normal|EB)", text)
    return match.group(1) if match else ""


def extract_comportamento(text: str) -> tuple[str, str, str]:
    match = re.search(r"\b(Bom|Ótimo|Otimo|Excepcional)\s+(\d{2}/\d{2}/\d{4})\s+([^\n]+)", text, re.I)
    if not match:
        return "", "", ""
    return normalize_space(match.group(1)), match.group(2), normalize_space(match.group(3))


def extract_period_section(text: str, section: str) -> list[tuple[date, date, str]]:
    if section not in text:
        return []
    result: list[tuple[date, date, str]] = []
    for match in re.finditer(r"([^\n]+)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})", text):
        motivo = normalize_space(match.group(1))
        if len(motivo) > 80:
            continue
        inicio = parse_date_br(match.group(2))
        fim = parse_date_br(match.group(3))
        if inicio and fim:
            result.append((inicio, fim, motivo))
    return result


def extract_acrescimos(text: str) -> list[tuple[date, date, str, str]]:
    if "Acréscimos de Tempo de Serviço" not in text:
        return []
    result: list[tuple[date, date, str, str]] = []
    for match in re.finditer(r"([^\n]+)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+([^\n]+)", text):
        inicio = parse_date_br(match.group(2))
        fim = parse_date_br(match.group(3))
        if inicio and fim:
            result.append((inicio, fim, normalize_space(match.group(4)), normalize_space(match.group(1))))
    return result


def extract_odt_table_rows(element: ET.Element) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in element:
        if strip_ns(row.tag) != "table-row":
            continue
        values = []
        for cell in row:
            if strip_ns(cell.tag) == "table-cell":
                values.append(collect_text(cell))
        if any(values):
            rows.append(values)
    return rows

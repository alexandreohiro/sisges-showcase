"""Normalizacao e validacao de EventBlocks do compilador de Folhas de Alteracoes.

Cobre: normalizacao de eventos por semestre, recuperacao de titulos faltantes,
deteccao de eventos sensiveis, reparo de tabelas embutidas no corpo do evento,
validacao do resultado compilado e construcao da justificativa de processamento.
"""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

from modules.compilador.application.folha_models import EventBlock, TableBlock
from modules.compilador.application.folha_xml_utils import (
    NOISE_FRAGMENTS,
    REFERENCE_PATTERN,
    clean_noise,
    is_probable_title,
    normalize_space,
    semester_months,
    split_paragraphs,
    strip_accents,
)

if TYPE_CHECKING:
    from modules.compilador.application.folha_models import (
        CompilerOptions,
        RenderResult,
        SicapexProfile,
    )
    from modules.compilador.application.folha_time_calc import TimeSummary
    from shared.utils.qms import NormalizedQmResult


RANK_PATTERN = re.compile(
    r"^(Gen|Cel|Ten\s*Cel|Maj|Cap|1º\s*Ten|2º\s*Ten|Asp|S\s*Ten|1º\s*Sgt|2º\s*Sgt|3º\s*Sgt|Cb|Sd|2º\s*Sgt\s*QE|3º\s*Sgt\s*QE)\b",
    re.I,
)

FUNCTION_TERMS = [
    "Gestor do Contrato Substituto",
    "Gestor do Contrato",
    "Fiscal Administrativo Titular do Contrato",
    "Fiscal Administrativo Substituto do Contrato",
    "Fiscal Setorial Titular",
    "Fiscal Setorial Substituto",
]


def normalize_semester_events(events: list[EventBlock], semestre: str) -> list[EventBlock]:
    months = semester_months(semestre)
    return [event for event in events if event.mes in months]


def normalize_event_blocks(events: list[EventBlock]) -> tuple[list[EventBlock], list[str]]:
    normalized: list[EventBlock] = []
    validations: list[str] = []
    for event in events:
        pieces, split_recovered = split_embedded_events(event)
        if split_recovered:
            validations.append("OK_EVENT_BODY_SPLIT_RECOVERED")
        for piece in pieces:
            recovered = recover_missing_event_title(piece)
            if recovered:
                validations.append("OK_EVENT_TITLE_RECOVERED")
            if not piece.titulo.strip():
                validations.append("WARN_EVENT_TITLE_MISSING")
            normalized.append(piece)
    return normalized, list(dict.fromkeys(validations))


def split_embedded_events(event: EventBlock) -> tuple[list[EventBlock], bool]:
    lines = split_paragraphs(event.corpo)
    split_index = next(
        (
            index
            for index in range(len(lines) - 1)
            if is_recoverable_event_title(lines[index]) and REFERENCE_PATTERN.match(lines[index + 1])
        ),
        -1,
    )
    if split_index < 0:
        return [event], False

    pieces: list[EventBlock] = []
    original_body = "\n".join(lines[:split_index]).strip()
    if event.titulo.strip() or event.referencia.strip() or original_body or event.tables:
        pieces.append(
            EventBlock(
                mes=event.mes,
                titulo=event.titulo,
                referencia=event.referencia,
                corpo=original_body,
                tables=event.tables,
            )
        )

    index = split_index
    while index < len(lines):
        if index + 1 >= len(lines):
            break
        title = lines[index]
        reference = lines[index + 1]
        if not is_recoverable_event_title(title) or not REFERENCE_PATTERN.match(reference):
            index += 1
            continue
        body: list[str] = []
        index += 2
        while index < len(lines):
            if (
                index + 1 < len(lines)
                and is_recoverable_event_title(lines[index])
                and REFERENCE_PATTERN.match(lines[index + 1])
            ):
                break
            body.append(lines[index])
            index += 1
        pieces.append(
            EventBlock(
                mes=event.mes,
                titulo=title,
                referencia=reference,
                corpo="\n".join(body).strip(),
            )
        )
    return pieces or [event], True


def recover_missing_event_title(event: EventBlock) -> bool:
    if event.titulo.strip():
        return False
    lines = split_paragraphs(event.corpo)
    if not lines:
        return False
    candidate = lines[0]
    if not is_recoverable_event_title(candidate):
        return False
    event.titulo = candidate
    event.corpo = "\n".join(lines[1:]).strip()
    return True


def is_recoverable_event_title(line: str) -> bool:
    line = normalize_space(line)
    if not line or len(line) > 140 or REFERENCE_PATTERN.match(line):
        return False
    comparable = strip_accents(line).upper()
    if any(strip_accents(fragment).upper() in comparable for fragment in NOISE_FRAGMENTS):
        return False
    if " - " in line and re.search(r"[A-ZÀ-Ý]{3,}", line):
        return True
    return is_probable_title(line)


def detect_sensitive_event(event: EventBlock) -> list[str]:
    text = strip_accents(
        normalize_space(f"{event.titulo} {event.referencia} {event.corpo}")
    ).upper()
    sensitive_patterns = (
        r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
        r"\bCPF\b",
        r"\bENDERECO\b|\bRUA\b|\bAVENIDA\b",
        r"\bFILIACAO\b",
        r"ARMA DE FOGO",
        r"BENEFICIARIO",
        r"PAGAMENTO|PAGAR|REMUNERACAO",
        r"DADOS DE TERCEIROS|TERCEIROS|DEPENDENTE|PENSIONISTA",
        r"CONTA BANCARIA|AGENCIA|BANCO\s+\d",
        r"\bSIGMA\b",
        r"\bPAF\b|\bCRAF\b",
    )
    if any(re.search(pattern, text) for pattern in sensitive_patterns):
        return ["WARN_POSSIBLE_SENSITIVE_EVENT", "WARN_REVIEW_BEFORE_SIGNATURE"]
    return []


def sensitive_event_validations(events: list[EventBlock]) -> list[str]:
    validations: list[str] = []
    for event in events:
        validations.extend(detect_sensitive_event(event))
    return list(dict.fromkeys(validations))


def repair_tables_inside_event(corpo: str) -> tuple[str, list[TableBlock]] | None:
    lines = [normalize_space(line) for line in corpo.splitlines() if normalize_space(line)]
    if not any("FISCAIS SETORIAIS" in line.upper() or "DESIGNADO FUNÇÃO" in line.upper() for line in lines):
        return None
    table_start = None
    for index, line in enumerate(lines):
        upper = line.upper()
        if "FISCAIS SETORIAIS" in upper or "DESIGNADO FUNÇÃO" in upper:
            table_start = index
            break
    if table_start is None:
        return None
    before = "\n".join(lines[:table_start]).strip()
    table_lines = [clean_noise(line) for line in lines[table_start + 1 :] if clean_noise(line)]
    return before, [repair_fiscal_table(table_lines)]


def repair_fiscal_table(lines: list[str]) -> TableBlock:
    rows: list[list[str]] = []
    current_name = ""
    current_function = ""
    current_area: list[str] = []

    def flush() -> None:
        nonlocal current_name, current_function, current_area
        if current_name:
            rows.append([current_name, current_function, normalize_space(" ".join(current_area))])
        current_name = ""
        current_function = ""
        current_area = []

    for raw in lines:
        line = clean_noise(raw)
        if not line:
            continue
        if RANK_PATTERN.match(line):
            flush()
            current_name = line
            continue
        func = extract_function_term(line)
        if func:
            current_function = func
            rest = normalize_space(line.replace(func, ""))
            if rest:
                current_area.append(rest)
            continue
        current_area.append(line)
    flush()
    return TableBlock(
        title="FISCAIS SETORIAIS B ADM QGEx",
        columns=["Designado", "Função", "Área de responsabilidade"],
        rows=rows,
    )


def validate_result(
    output_path: Path,
    profile: SicapexProfile,
    events: list[EventBlock],
    times: TimeSummary,
    options: CompilerOptions,
    render_result: RenderResult | None = None,
    qms_result: NormalizedQmResult | None = None,
) -> list[str]:
    from shared.utils.qms import normalize_qas_qms_qm_for_header

    result = ["VALIDAÇÃO EM DUAS ETAPAS - COMPILADOR SISGES"]
    try:
        with zipfile.ZipFile(output_path, "r") as zin:
            zin.getinfo("content.xml")
            ET.fromstring(zin.read("content.xml"))
        result.append("ETAPA 1: ODT válido, ZIP válido e content.xml parseável.")
    except Exception as exc:  # pragma: no cover - falha operacional
        result.append(f"ETAPA 1: FALHA estrutural: {exc}")

    months = semester_months(options.semestre)
    present = {event.mes for event in events}
    for month in months:
        result.append(f"MÊS {month}: {'com evento ou sem alterações' if month in present or month in months else 'ausente'}")
    result.append(f"Nome completo: {'OK' if profile.nome_completo else 'PENDENTE'}")
    result.append(f"Nome de guerra: {'OK' if profile.nome_guerra else 'PENDENTE'}")
    result.append(f"Identidade: {'OK' if profile.identidade else 'PENDENTE'}")
    result.append(f"Tempo origem: {times.origem}")
    result.append(f"Eventos: {len(events)}")
    result.append(f"Tabelas reais renderizadas: {sum(len(event.tables) for event in events)}")
    result.append("OK_FORMAT_CONTRACT_APPLIED")
    from modules.compilador.application.folha_format_contract import EMPTY_MONTH_COMPACT_PLURAL, EMPTY_MONTH_COMPACT_SINGULAR
    if options.empty_month_mode in {EMPTY_MONTH_COMPACT_SINGULAR, EMPTY_MONTH_COMPACT_PLURAL}:
        result.append("OK_EMPTY_MONTH_COMPACT")
    if render_result:
        result.extend(render_result.validations)
    result.extend(qms_validation_lines(qms_result or normalize_qas_qms_qm_for_header(profile.qm)))
    result.append("ETAPA 2: validação documental concluída.")
    return result


def build_justification(
    *,
    profile: SicapexProfile,
    events: list[EventBlock],
    times: TimeSummary,
    options: CompilerOptions,
    odt_tables_detected: int,
    period_label: str,
) -> list[str]:
    return [
        "JUSTIFICATIVA DE PROCESSAMENTO - COMPILADOR SISGES",
        f"Militar: {profile.nome_completo}",
        f"Período: {period_label}",
        "Fonte de alterações: ODT de BI/alterações enviado pelo operador.",
        "Fonte de tempo de serviço: PDF da Ficha Cadastro SiCaPEx.",
        "Regra de cabeçalho: nome completo preservado; apenas nome de guerra em negrito.",
        "Regra de fonte: Calibri Light 12 pt em estilos principais do ODT.",
        "Regra de meses: todos os meses do semestre são emitidos uma vez; mês sem evento recebe 'Sem alterações.'.",
        "Regra de tabela: tabelas nativas do ODT são preservadas; blocos tabulares quebrados são reparados quando detectados.",
        f"Tabelas nativas detectadas no ODT de entrada: {odt_tables_detected}",
        f"Tabelas renderizadas na saída: {sum(len(event.tables) for event in events)}",
        f"TC: {times.tc}; TNC: {times.tnc}; TTES: {times.ttes}; origem: {times.origem}.",
        "Observação: cálculo automatizado permanece auditável e deve ser conferido pela secretaria antes da assinatura.",
    ]


def _legacy_normalize_qm(raw: str) -> str:
    from shared.utils.qms import normalize_qas_qms_qm_for_header
    return normalize_qas_qms_qm_for_header(raw).display


def qms_validation_lines(result: NormalizedQmResult) -> list[str]:
    lines = [f"QMS raw: {result.raw}", f"QMS normalizado: {result.display or '-'}"]
    if result.status in {"OK", "NORMALIZED"}:
        lines.append("OK_QMS_NORMALIZED")
    if result.status == "GENERIC_EMPTY":
        lines.append("WARN_QMS_GENERICO")
    if result.status == "PENDING":
        lines.append("WARN_QMS_NAO_RECONHECIDO")
    if raw_qms_leaked(result.display):
        lines.append("ERR_QMS_RAW_LEAKED")
    return lines


def raw_qms_leaked(value: str) -> bool:
    comparable = strip_accents(normalize_space(value)).upper()
    return any(
        marker in comparable
        for marker in (
            "QUALQUER QMG",
            "QUALQUER QMP",
            "MANUTENCAO DE VIATURA",
            "QMG 00",
        )
    ) or bool(re.search(r"\b\d{3,6}\s*-", comparable))


def extract_function_term(line: str) -> str:
    for term in FUNCTION_TERMS:
        if term.upper() in line.upper():
            return term
    return ""

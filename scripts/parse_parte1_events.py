from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts.complete_folha_semi_ok_parte1 import (
    SISGES_PARTE1_STYLE_EVENT_TITLE,
    SENSITIVE_RE,
    clean_parte1_lines,
    ensure_required_months,
    extract_parte1_from_source,
    is_month_line,
    is_part1_heading_line,
    is_reference_line,
    normalize_parte1_paragraphs,
    normalize_text,
    style_for_line_at,
)


SCHEMA_VERSION = "sisges-parte1-events-v1"
STRUCTURAL_BODY_LABEL_PREFIXES = (
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
STRUCTURAL_BODY_LABELS = {"MEMBRO", "PERIODO ANTERIOR", "NOVO PERIODO"}


@dataclass(slots=True)
class ParsedBI:
    referencia: str = ""
    corpo: str = ""
    source_lines: list[int] = field(default_factory=list)


@dataclass(slots=True)
class ParsedEvento:
    titulo: str = ""
    bi: ParsedBI = field(default_factory=ParsedBI)
    warnings: list[str] = field(default_factory=list)
    source_lines: list[int] = field(default_factory=list)


@dataclass(slots=True)
class ParsedMes:
    mes: str
    eventos: list[ParsedEvento] = field(default_factory=list)
    sem_alteracoes: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParseResult:
    schema_version: str = SCHEMA_VERSION
    source_path: str = ""
    semestre: str = "2"
    meses: list[ParsedMes] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def is_empty_month_body(line: str) -> bool:
    normalized = normalize_text(line).rstrip(".")
    return normalized in {"SEM ALTERACAO", "SEM ALTERACOES"}


def is_structural_body_label(line: str) -> bool:
    normalized = normalize_text(line)
    if normalized in STRUCTURAL_BODY_LABELS:
        return True
    return any(normalized.startswith(prefix) for prefix in STRUCTURAL_BODY_LABEL_PREFIXES)


def is_numbered_body_line(line: str) -> bool:
    return bool(re.match(r"^\d{1,2}\.\s+", line.strip()))


def normalize_reference(line: str) -> str:
    return re.sub(r"\s+:", ":", line.strip())


def append_body(event: ParsedEvento, line: str, source_line: int) -> None:
    text = line.strip()
    if not text:
        return
    event.bi.corpo = f"{event.bi.corpo}\n{text}" if event.bi.corpo else text
    event.bi.source_lines.append(source_line)
    event.source_lines.append(source_line)


def add_sensitive_warnings(event: ParsedEvento) -> None:
    combined = "\n".join([event.titulo, event.bi.referencia, event.bi.corpo])
    if SENSITIVE_RE.search(combined):
        append_unique(event.warnings, "WARN_POSSIBLE_SENSITIVE_EVENT")
        append_unique(event.warnings, "WARN_REVIEW_BEFORE_SIGNATURE")


def finalize_event(event: ParsedEvento | None, month: ParsedMes | None) -> int:
    if event is None or month is None:
        return 0
    if not event.titulo.strip():
        append_unique(event.warnings, "WARN_EVENT_TITLE_MISSING")
    if not event.bi.referencia.strip():
        append_unique(event.warnings, "WARN_EVENT_REFERENCE_MISSING")
    add_sensitive_warnings(event)
    month.eventos.append(event)
    return 1


def month_name(line: str) -> str:
    return normalize_text(line.strip().rstrip(":"))


def parse_parte1_paragraphs(
    paragraphs: list[str], *, semestre: str = "2", source_path: str = ""
) -> ParseResult:
    result = ParseResult(source_path=source_path, semestre=str(semestre))
    current_month: ParsedMes | None = None
    current_event: ParsedEvento | None = None
    parsed_events = 0

    for index, raw_line in enumerate(paragraphs):
        source_line = index + 1
        line = raw_line.strip()
        if not line or is_part1_heading_line(line):
            continue

        if is_month_line(line, result.semestre):
            parsed_events += finalize_event(current_event, current_month)
            current_event = None
            current_month = ParsedMes(mes=month_name(line))
            result.meses.append(current_month)
            continue

        if current_month is None:
            append_unique(result.warnings, "WARN_TEXT_OUTSIDE_MONTH")
            continue

        if is_empty_month_body(line) and current_event is None:
            current_month.sem_alteracoes = True
            append_unique(current_month.warnings, "OK_EMPTY_MONTH")
            continue

        if is_structural_body_label(line):
            if current_event is None:
                current_event = ParsedEvento(
                    warnings=["WARN_EVENT_TITLE_MISSING"], source_lines=[source_line]
                )
            append_body(current_event, line, source_line)
            continue

        if is_numbered_body_line(line) and current_event is not None:
            append_body(current_event, line, source_line)
            continue

        style = style_for_line_at(paragraphs, index, result.semestre)
        if style == SISGES_PARTE1_STYLE_EVENT_TITLE:
            parsed_events += finalize_event(current_event, current_month)
            current_event = ParsedEvento(titulo=line, source_lines=[source_line])
            continue

        if is_reference_line(line):
            if current_event is None or current_event.bi.referencia:
                parsed_events += finalize_event(current_event, current_month)
                current_event = ParsedEvento(
                    warnings=["WARN_EVENT_TITLE_MISSING"], source_lines=[source_line]
                )
            current_event.bi.referencia = normalize_reference(line)
            current_event.bi.source_lines.append(source_line)
            current_event.source_lines.append(source_line)
            continue

        if current_event is None:
            current_event = ParsedEvento(
                warnings=["WARN_EVENT_TITLE_MISSING"], source_lines=[source_line]
            )
        append_body(current_event, line, source_line)

    parsed_events += finalize_event(current_event, current_month)
    append_unique(result.warnings, f"OK_PARTE1_EVENTS_PARSED:{parsed_events}")
    return result


def normalize_source_to_paragraphs(source_path: Path, semestre: str) -> tuple[list[str], list[str]]:
    raw_text = extract_parte1_from_source(source_path, semestre)
    clean_lines, clean_warnings = clean_parte1_lines(raw_text)
    paragraphs, paragraph_warnings = normalize_parte1_paragraphs(clean_lines, semestre)
    paragraphs, month_warnings = ensure_required_months(paragraphs, semestre)
    return paragraphs, [*clean_warnings, *paragraph_warnings, *month_warnings]


def parse_parte1_source(source_path: Path, *, semestre: str = "2") -> ParseResult:
    paragraphs, warnings = normalize_source_to_paragraphs(source_path, str(semestre))
    result = parse_parte1_paragraphs(
        paragraphs, semestre=str(semestre), source_path=str(source_path)
    )
    for warning in warnings:
        append_unique(result.warnings, warning)
    return result


def write_result(result: ParseResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parseia a 1a Parte em estrutura Mes -> Evento -> BI(Corpo)."
    )
    parser.add_argument("--source", required=True, type=Path, help="TXT ou PDF da Parte 1.")
    parser.add_argument("--semestre", default="2", choices=("1", "2"))
    parser.add_argument("--output", required=True, type=Path, help="JSON de saida.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = parse_parte1_source(args.source, semestre=args.semestre)
    write_result(result, args.output)
    print(f"Parte 1 parseada: {args.output}")


if __name__ == "__main__":
    main()

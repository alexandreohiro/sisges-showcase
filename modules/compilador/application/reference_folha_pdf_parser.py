from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
import re

import pdfplumber


MONTHS = [
    "JANEIRO",
    "FEVEREIRO",
    "MARÇO",
    "ABRIL",
    "MAIO",
    "JUNHO",
    "JULHO",
    "AGOSTO",
    "SETEMBRO",
    "OUTUBRO",
    "NOVEMBRO",
    "DEZEMBRO",
]
MONTH_ALIASES = {"MARCO": "MARÇO"}
NOISE_PREFIXES = (
    "BASE ADMINISTRATIVA DO QUARTEL-GENERAL",
    "CONTINUAÇÃO DAS FOLHAS DE ALTERAÇÕES",
    "CONTINUACAO DAS FOLHAS DE ALTERACOES",
    "FOLHA Nº",
    "FOLHA N°",
    "CP: PERÍODO",
    "CP: PERIODO",
)
REFERENCE_RE = re.compile(r"^[-–]\s*a\s+\d{1,2},\s*(BI|BAR|ADT|ADIT|ADITAMENTO|Adt|Adt Pes|Adt Aces)", re.I)
TIME_RE = re.compile(r"(?P<anos>\d{1,2})\s*a\s*(?P<meses>\d{1,2})\s*m\s*(?P<dias>\d{1,2})\s*d", re.I)


@dataclass(slots=True)
class ReferenceFolhaPdfParseResult:
    is_folha_alteracoes: bool
    nome_completo: str = ""
    posto_graduacao: str = ""
    qas_qms: str = ""
    identidade: str = ""
    om: str = ""
    guarnicao: str = ""
    folha_numero: str = ""
    semestre: str = ""
    ano: int | None = None
    periodo_inicio: date | None = None
    periodo_fim: date | None = None
    meses_detectados: list[str] = field(default_factory=list)
    eventos: list[dict] = field(default_factory=list)
    comportamento: str = ""
    tempos_segunda_parte: dict = field(default_factory=dict)
    assinatura_nome: str = ""
    assinatura_funcao: str = ""
    page_count: int = 0
    warnings: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    raw_excerpt: str = ""

    def to_variables(self) -> dict:
        data = asdict(self)
        data["periodo_inicio"] = self.periodo_inicio.isoformat() if self.periodo_inicio else None
        data["periodo_fim"] = self.periodo_fim.isoformat() if self.periodo_fim else None
        data["tempos_segunda_parte_origem"] = "TRANSCRITO_DE_FOLHA_PDF_MEMORIA"
        data["tempos_segunda_parte_status"] = "HISTORICO_NAO_RECALCULADO"
        return data


def parse_reference_folha_pdf(path: Path | str) -> ReferenceFolhaPdfParseResult:
    pdf_path = Path(path)
    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)
    text = "\n".join(pages)
    if not text.strip():
        return ReferenceFolhaPdfParseResult(
            is_folha_alteracoes=False,
            page_count=page_count,
            pending=["ERR_EMPTY_TEXT"],
            warnings=["Texto extraido do PDF esta vazio."],
        )
    return parse_reference_folha_text(text, page_count=page_count)


def parse_reference_folha_text(text: str, *, page_count: int = 0) -> ReferenceFolhaPdfParseResult:
    lines = [normalize_space(line) for line in text.splitlines() if normalize_space(line)]
    clean_lines = [line for line in lines if not is_noise(line)]
    joined = "\n".join(clean_lines)
    result = ReferenceFolhaPdfParseResult(
        is_folha_alteracoes=looks_like_folha(joined),
        page_count=page_count,
        raw_excerpt=joined[:2000],
    )
    result.nome_completo = extract_field(joined, r"NOME:\s*([^\n]+)")
    result.posto_graduacao = extract_field(joined, r"POSTO/GRADUA[ÇC][ÃA]O:\s*([^\n]+)")
    result.qas_qms = extract_field(joined, r"(?:QAS/QMS|ARMA/QUADRO/SERVI[ÇC]O):\s*([^\n]+)")
    result.identidade = extract_field(joined, r"IDENTIDADE:\s*([0-9.\-]+)")
    result.guarnicao = extract_field(joined, r"GUARNI[ÇC][ÃA]O(?:\s+DE)?\s*:?\s*([^\n]+)")
    result.om = extract_om(clean_lines)
    result.folha_numero = extract_field(joined, r"FOLHA\s*N[º°]?\s*([0-9]+)")
    semestre, ano = extract_semestre_ano(joined)
    result.semestre = semestre
    result.ano = ano
    result.periodo_inicio, result.periodo_fim = extract_periodo(text)
    if (not result.periodo_inicio or not result.periodo_fim) and result.ano and result.semestre:
        result.periodo_inicio, result.periodo_fim = period_bounds_from_semester(
            result.ano,
            result.semestre,
        )
    result.meses_detectados = extract_months(clean_lines)
    result.eventos = extract_events(clean_lines)
    result.comportamento = normalize_comportamento(
        extract_field(joined, r"Comportamento:\s*([A-Za-zÀ-ÿ]+)")
    )
    result.tempos_segunda_parte = extract_times(joined)
    result.assinatura_nome, result.assinatura_funcao = extract_signature(clean_lines)
    add_validations(result)
    return result


def compiler_validations_from_parse(
    result: ReferenceFolhaPdfParseResult,
    *,
    run_id: str | None = None,
    file_id: str | None = None,
) -> list[dict]:
    validations = [
        {
            "level": "OK" if result.is_folha_alteracoes else "ERROR",
            "code": "OK_VARIABLES_EXTRACTED" if result.is_folha_alteracoes else "ERR_NOT_FOLHA_ALTERACOES",
            "message": "Variaveis extraidas do PDF de Folha." if result.is_folha_alteracoes else "PDF nao parece ser Folha de Alteracoes.",
            "run_id": run_id,
            "file_id": file_id,
        },
        {
            "level": "OK",
            "code": "OK_MONTHS_DETECTED",
            "message": f"Meses detectados: {', '.join(result.meses_detectados) or '-'}",
            "run_id": run_id,
            "file_id": file_id,
        },
    ]
    if result.tempos_segunda_parte:
        validations.append(
            {
                "level": "WARNING",
                "code": "WARN_TEMPO_TRANSCRITO_NAO_RECALCULADO",
                "message": "Tempos da 2a Parte foram transcritos de PDF de memoria e nao recalculados.",
                "run_id": run_id,
                "file_id": file_id,
            }
        )
    for code in result.pending:
        validations.append(
            {
                "level": "WARNING" if code.startswith("WARN_") else "ERROR",
                "code": code,
                "message": human_validation_message(code),
                "run_id": run_id,
                "file_id": file_id,
            }
        )
    return validations


def add_validations(result: ReferenceFolhaPdfParseResult) -> None:
    if not result.is_folha_alteracoes:
        result.pending.append("ERR_NOT_FOLHA_ALTERACOES")
    checks = [
        ("nome_completo", "WARN_NOME_AUSENTE"),
        ("identidade", "WARN_IDENTIDADE_AUSENTE"),
        ("periodo_inicio", "WARN_PERIODO_AUSENTE"),
        ("comportamento", "WARN_COMPORTAMENTO_AUSENTE"),
        ("assinatura_nome", "WARN_ASSINATURA_AUSENTE"),
    ]
    for attr, code in checks:
        if not getattr(result, attr):
            result.pending.append(code)
    if not result.tempos_segunda_parte:
        result.pending.append("WARN_SEGUNDA_PARTE_AUSENTE")
    expected_months = expected_semester_months(result.semestre)
    for month in expected_months:
        if month not in result.meses_detectados:
            result.pending.append("WARN_MES_AUSENTE")
            result.warnings.append(f"Mes esperado ausente: {month}")
    if len(result.meses_detectados) != len(set(result.meses_detectados)):
        result.pending.append("WARN_MES_DUPLICADO")
    if any(not event.get("titulo") for event in result.eventos):
        result.pending.append("WARN_EVENT_TITLE_MISSING")


def looks_like_folha(text: str) -> bool:
    upper = strip_accents(text.upper())
    return "FOLHAS DE ALTERACOES" in upper or "FOLHA DE ALTERACOES" in upper


def extract_events(lines: list[str]) -> list[dict]:
    events: list[dict] = []
    current_month = ""
    pending_title = ""
    current_event: dict | None = None
    previous_relevant_line = ""

    def flush() -> None:
        nonlocal current_event
        if current_event:
            current_event["corpo"] = normalize_space(current_event.get("corpo", ""))
            if not current_event.get("titulo"):
                current_event.setdefault("warnings", []).append("WARN_EVENT_TITLE_MISSING")
            events.append(current_event)
            current_event = None

    for line in lines:
        month = normalize_month(line.rstrip(":"))
        if month:
            flush()
            current_month = month
            pending_title = ""
            continue
        if strip_accents(line.upper()).startswith("2A PARTE"):
            flush()
            break
        if REFERENCE_RE.match(line):
            if not pending_title and is_probable_title(previous_relevant_line):
                pending_title = previous_relevant_line
            flush()
            current_event = {"mes": current_month, "titulo": pending_title, "referencia": line, "corpo": ""}
            pending_title = ""
            previous_relevant_line = line
            continue
        if current_event:
            if current_month and is_probable_title(line):
                pending_title = line
                previous_relevant_line = line
                continue
            current_event["corpo"] = f"{current_event['corpo']} {line}".strip()
        elif current_month and is_probable_title(line):
            pending_title = line
        if not is_noise(line):
            previous_relevant_line = line
    flush()
    return events


def extract_times(text: str) -> dict:
    normalized = strip_accents(normalize_space(text).upper())
    filler = r".{0,140}?"
    time_pattern = r"([0-9]{1,2}\s*A\s*[0-9]{1,2}\s*M\s*[0-9]{1,2}\s*D)"
    mapping = {
        "tc": rf"(?:TEMPO COMPUTADO.*?\(TC\)|\bTC\b){filler}{time_pattern}",
        "tc_arregimentado": rf"\bA\.\s*ARREGIMENTADO{filler}{time_pattern}",
        "tc_nao_arregimentado": rf"\bB\.\s*NAO ARREGIMENTADO{filler}{time_pattern}",
        "tnc": rf"(?:TEMPO NAO COMPUTADO.*?\(TNC\)|\bTNC\b){filler}{time_pattern}",
        "tscmm": rf"(?:TSCMM|MEDALHA MILITAR){filler}{time_pattern}",
        "tssd": rf"(?:TSSD|SITUACOES DIVERSAS){filler}{time_pattern}",
        "tsnr": rf"(?:TSNR|NACIONAL RELEVANTE){filler}{time_pattern}",
        "ttes": rf"(?:TTES|TOTAL DE EFETIVO SERVICO){filler}{time_pattern}",
    }
    values: dict[str, str] = {}
    for key, pattern in mapping.items():
        match = re.search(pattern, normalized, re.I)
        if match:
            values[key] = normalize_time(match.group(1).lower())
    if values:
        values["origem"] = "TRANSCRITO_DE_FOLHA_PDF_MEMORIA"
        values["status"] = "HISTORICO_NAO_RECALCULADO"
    return values

def extract_signature(lines: list[str]) -> tuple[str, str]:
    tail = [line for line in lines[-15:] if line and not is_noise(line)]
    for index, line in enumerate(tail):
        if re.search(r"\b(Cel|Ten|Sgt|Cmt|S Cmt)\b", line) and index > 0:
            return tail[index - 1], line
    return "", ""


def extract_field(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.I)
    return normalize_space(match.group(1)) if match else ""


def extract_om(lines: list[str]) -> str:
    for line in lines:
        if re.search(r"\b\d{6}\b", line) and ("B ADM" in strip_accents(line.upper()) or "QGEX" in strip_accents(line.upper())):
            return line
    return ""


def extract_semestre_ano(text: str) -> tuple[str, int | None]:
    match = re.search(r"([12])[º°]?\s*Semestre\s+de\s+(\d{4})", text, re.I)
    if not match:
        return "", None
    return match.group(1), int(match.group(2))


def extract_periodo(text: str) -> tuple[date | None, date | None]:
    match = re.search(r"(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})", text)
    if not match:
        return None, None
    return parse_br_date(match.group(1)), parse_br_date(match.group(2))


def extract_months(lines: list[str]) -> list[str]:
    months: list[str] = []
    for line in lines:
        month = normalize_month(line.rstrip(":"))
        if month and month not in months:
            months.append(month)
    return months


def expected_semester_months(semestre: str) -> list[str]:
    if semestre == "1":
        return MONTHS[:6]
    if semestre == "2":
        return MONTHS[6:]
    return []


def normalize_time(value: str) -> str:
    match = TIME_RE.search(value)
    if not match:
        return normalize_space(value)
    return f"{int(match.group('anos')):02d}a{int(match.group('meses')):02d}m{int(match.group('dias')):02d}d"


def normalize_comportamento(value: str) -> str:
    normalized = strip_accents(value).upper()
    mapping = {
        "BOM": "BOM",
        "OTIMO": "ÓTIMO",
        "EXCEPCIONAL": "EXCEPCIONAL",
        "INSUFICIENTE": "INSUFICIENTE",
    }
    return mapping.get(normalized, value.upper())


def normalize_month(value: str) -> str:
    normalized = strip_accents(normalize_space(value)).upper()
    if normalized in MONTH_ALIASES:
        normalized = MONTH_ALIASES[normalized]
    for month in MONTHS:
        month_key = strip_accents(month)
        if normalized == month_key or normalized.startswith(f"{month_key}:"):
            return month
    return ""


def period_bounds_from_semester(ano: int, semestre: str) -> tuple[date | None, date | None]:
    if semestre == "1":
        return date(ano, 1, 1), date(ano, 6, 30)
    if semestre == "2":
        return date(ano, 7, 1), date(ano, 12, 31)
    return None, None


def is_probable_title(line: str) -> bool:
    if len(line) < 4 or is_noise(line):
        return False
    return not REFERENCE_RE.match(line) and not re.search(r"\d{2}/\d{2}/\d{4}", line)


def is_noise(line: str) -> bool:
    upper = strip_accents(line.upper())
    return any(upper.startswith(strip_accents(prefix)) for prefix in NOISE_PREFIXES)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def strip_accents(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char))


def parse_br_date(value: str) -> date | None:
    try:
        day, month, year = [int(part) for part in value.split("/")]
        return date(year, month, day)
    except ValueError:
        return None


def human_validation_message(code: str) -> str:
    messages = {
        "ERR_NOT_FOLHA_ALTERACOES": "PDF nao identificado como Folha de Alteracoes.",
        "WARN_NOME_AUSENTE": "Nome completo ausente.",
        "WARN_IDENTIDADE_AUSENTE": "Identidade ausente.",
        "WARN_PERIODO_AUSENTE": "Periodo ausente.",
        "WARN_COMPORTAMENTO_AUSENTE": "Comportamento ausente.",
        "WARN_ASSINATURA_AUSENTE": "Assinatura ausente.",
        "WARN_SEGUNDA_PARTE_AUSENTE": "2a Parte ausente.",
        "WARN_MES_AUSENTE": "Mes esperado ausente.",
        "WARN_MES_DUPLICADO": "Mes duplicado.",
    }
    return messages.get(code, code)

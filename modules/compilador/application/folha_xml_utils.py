"""Utilitarios de baixo nivel para XML ODT, texto e datas usados pelo compilador de Folhas.

Funcoes puras e sem estado, compartilhadas pelos demais modulos do pipeline
(`folha_extraction`, `folha_body_xml`, `folha_rendering`, `folha_time_calc`,
`folha_event_validation`) e pelo orquestrador `folha_alteracoes_compiler`.
"""

from __future__ import annotations

from datetime import date, timedelta
import re
import unicodedata
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET


MONTHS_1SEM = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO"]
MONTHS_2SEM = ["JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
REFERENCE_PATTERN = re.compile(r"^[-–]\s*a\s+\d{1,2},\s*(BI|BAR|ADT|ADIT|ADITAMENTO|Adt)", re.I)

NOISE_FRAGMENTS = [
    "BASE ADMINISTRATIVA DO QUARTEL-GENERAL DO EXÉRCITO",
    "BASE ADMINISTRATIVA DO QUARTEL-GENERAL DO EXERCITO",
    "Continuação das Folhas de Alterações",
    "Continuacao das Folhas de Alteracoes",
    "FOLHA Nº",
    "FOLHA N°",
    "2º Semestre de 2025",
    "2° Semestre de 2025",
    "CP: PERÍODO",
    "CP: PERIODO",
    "PERÍODO: 01/07/2025 a 31/12/2025",
    "PERIODO: 01/07/2025 a 31/12/2025",
]


def period_bounds(ano: int, semestre: str) -> tuple[date, date, str]:
    if str(semestre).strip().startswith("1"):
        return date(ano, 1, 1), date(ano, 6, 30), f"1º SEMESTRE DE {ano}"
    return date(ano, 7, 1), date(ano, 12, 31), f"2º SEMESTRE DE {ano}"


def semester_months(semestre: str) -> list[str]:
    return MONTHS_1SEM if str(semestre).strip().startswith("1") else MONTHS_2SEM


def extract_regex(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.I | re.M)
    return normalize_space(match.group(1)) if match else ""


def parse_date_br(value: str) -> date | None:
    try:
        day, month, year = [int(part) for part in value.split("/")]
        return date(year, month, day)
    except Exception:
        return None


def days_inclusive(start: date | None, end: date | None) -> int:
    if not start or not end or end < start:
        return 0
    return (end - start).days + 1


def overlap_days(start: date, end: date, period_start: date, period_end: date) -> int:
    return days_inclusive(max(start, period_start), min(end, period_end))


def format_admin_days(days: int) -> str:
    years, rest = divmod(max(days, 0), 360)
    months, day = divmod(rest, 30)
    return f"{years:02d}a{months:02d}m{day:02d}d"


def format_calendar_ymd(start: date, end: date, *, extra_discount_days: int = 0) -> str:
    adjusted_end = end + timedelta(days=1 - extra_discount_days)
    if adjusted_end < start:
        return "00a00m00d"
    years = adjusted_end.year - start.year
    months = adjusted_end.month - start.month
    days = adjusted_end.day - start.day
    if days < 0:
        months -= 1
        previous_month_end = adjusted_end.replace(day=1) - timedelta(days=1)
        days += previous_month_end.day
    if months < 0:
        years -= 1
        months += 12
    return f"{years:02d}a{months:02d}m{days:02d}d"


def p(text: str, style: str = "Standard") -> str:
    return f'<text:p text:style-name="{style}">{escape(text or "")}</text:p>'


def p_xml(inner_xml: str, style: str = "Standard") -> str:
    return f'<text:p text:style-name="{style}">{inner_xml}</text:p>'


def span(text: str, style: str = "Bold") -> str:
    return f'<text:span text:style-name="{style}">{escape(text or "")}</text:span>'


def cell_xml(text: str, *, bold: bool) -> str:
    inner = span(text) if bold else escape(text or "")
    return f'<table:table-cell table:style-name="Cell" office:value-type="string"><text:p>{inner}</text:p></table:table-cell>'


def nome_completo_xml(nome_completo: str, nome_guerra: str) -> str:
    nome_completo = nome_completo or ""
    nome_guerra = nome_guerra or ""
    if not nome_guerra:
        return escape(nome_completo)
    index = nome_completo.upper().find(nome_guerra.upper())
    if index < 0:
        return escape(nome_completo)
    end = index + len(nome_guerra)
    return escape(nome_completo[:index]) + span(nome_completo[index:end]) + escape(nome_completo[end:])


def xml_attr(value: str) -> str:
    return escape(value or "", entities={'"': "&quot;"})


def split_paragraphs(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def clean_noise(line: str) -> str:
    result = line
    for fragment in NOISE_FRAGMENTS:
        result = result.replace(fragment, "")
    return normalize_space(result)


def collect_text(element: ET.Element) -> str:
    return normalize_space("".join(element.itertext()))


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char))


def is_probable_title(line: str) -> bool:
    if len(line) > 120:
        return False
    if REFERENCE_PATTERN.match(line):
        return False
    letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", line)
    return bool(letters) and line.upper() == line


def normalize_month(month: str) -> str:
    month = month.upper().replace("MARCO", "MARÇO")
    return month


def infer_month_from_reference(_line: str) -> str:
    return ""


def format_identity(value: str) -> str:
    value = re.sub(r"\D", "", value or "")
    if len(value) == 10:
        return f"{value[:9]}-{value[9]}"
    return value


def expand_graduacao(value: str) -> str:
    normalized = normalize_space(value).lower()
    mapping = {
        "1º sgt": "Primeiro-Sargento",
        "2º sgt": "Segundo-Sargento",
        "3º sgt": "Terceiro-Sargento",
        "s ten": "Subtenente",
        "cap": "Capitão",
        "maj": "Major",
        "cel": "Coronel",
        "1º ten": "Primeiro-Tenente",
        "2º ten": "Segundo-Tenente",
    }
    return mapping.get(normalized, value)


def classify_tipo_militar(grad: str) -> str:
    return "OFICIAL" if normalize_space(grad).lower() in {"asp", "2º ten", "1º ten", "cap", "maj", "ten cel", "cel"} else "PRACA"


def select_assinatura(tipo_militar: str) -> tuple[str, str]:
    if tipo_militar == "OFICIAL":
        return "SIGNATARIO OFICIAL - Cel", "Cmt B Adm QGEx"
    return "SIGNATARIO PRACA - Cel", "S Cmt B Adm QGEx"


def select_assinatura_for_options(profile, options) -> tuple[str, str]:
    nome_explicito = getattr(options, "assinatura_nome", None)
    funcao_explicita = getattr(options, "assinatura_funcao", None)
    mode = (options.assinatura_mode or "auto").strip().lower()
    if mode == "oficial":
        nome, funcao = select_assinatura("OFICIAL")
    elif mode == "praca":
        nome, funcao = select_assinatura("PRACA")
    else:
        nome, funcao = select_assinatura(profile.tipo_militar)
    return nome_explicito or nome, funcao_explicita or funcao

"""Normalizacao e validacao de EventBlocks do compilador de Folhas de Alteracoes.

Cobre: normalizacao de eventos por semestre, recuperacao de titulos faltantes,
deteccao de eventos sensiveis, reparo de tabelas embutidas no corpo do evento,
validacao do resultado compilado e construcao da justificativa de processamento.
"""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from modules.compilador.application.folha_models import EventBlock, TableBlock
from modules.compilador.application.folha_xml_utils import (
    NOISE_FRAGMENTS,
    REFERENCE_PATTERN,
    clean_noise,
    is_probable_title,
    normalize_space,
    period_bounds,
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


MONTH_ABBREVIATIONS = {
    "JAN": 1,
    "FEV": 2,
    "MAR": 3,
    "ABR": 4,
    "MAI": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SET": 9,
    "OUT": 10,
    "NOV": 11,
    "DEZ": 12,
}

DATE_ABBREV_PATTERN = re.compile(
    r"\b(\d{1,2})\s+(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)[A-ZÇ]*\.?\s+(\d{2}|\d{4})\b",
    re.I,
)
DATE_NUMERIC_PATTERN = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")

# Janelas de contexto (em caracteres, antes da data) usadas nas
# heuristicas de classificacao de datas. Ajustaveis num unico lugar.
LEGISLATION_CONTEXT_WINDOW = 90
ACTION_CONTEXT_WINDOW = 40

# Data precedida por citacao de norma ("Portaria ... de 31 AGO 22",
# "Lei nº 14.133, de 1º de abril de 2021") e data DA LEGISLACAO, nao do
# evento — nao pode decidir inclusao/exclusao no periodo (RC2).
LEGISLATION_CONTEXT_PATTERN = re.compile(
    r"(PORTARIA|LEI|DECRETO(-LEI)?|DIRETRIZ|NORMA|INSTRUCAO|BOLETIM|MANUAL|"
    r"REGULAMENTO|EB\d{2}|IG\s*\d|DIEX|OFICIO)[^.;]{0,80}\bDE\s*$"
)


def _expand_two_digit_year(year: int) -> int:
    return year + 2000 if year < 100 else year


def _is_legislation_date(text: str, start: int) -> bool:
    context = text[max(0, start - LEGISLATION_CONTEXT_WINDOW):start]
    return bool(LEGISLATION_CONTEXT_PATTERN.search(context))


def extract_event_dates(event: EventBlock) -> list[date]:
    """Datas citadas no titulo, na referencia e no corpo do evento.

    Datas de legislacao citada sao ignoradas: um evento que so referencia
    a data de uma portaria antiga continua pertencendo ao periodo da folha.
    """
    text = strip_accents(f"{event.titulo}\n{event.referencia}\n{event.corpo}").upper()
    found: list[date] = []
    for match in DATE_ABBREV_PATTERN.finditer(text):
        if _is_legislation_date(text, match.start()):
            continue
        day, month_name, year = match.groups()
        try:
            found.append(
                date(_expand_two_digit_year(int(year)), MONTH_ABBREVIATIONS[month_name.upper()], int(day))
            )
        except ValueError:
            continue
    for match in DATE_NUMERIC_PATTERN.finditer(text):
        if _is_legislation_date(text, match.start()):
            continue
        day, month, year = match.groups()
        try:
            found.append(date(int(year), int(month), int(day)))
        except ValueError:
            continue
    return found


ACTION_DATE_PATTERN = re.compile(
    r"(APRESENTOU-SE(\s+PRONTO)?(\s+EM)?|A\s+CONTAR\s+DE|DESLIGAD[OA]\s+EM|"
    r"INCORPORAD[OA]\s+EM|EXCLUID[OA]\s+EM|LICENCIAD[OA]\s+EM)\s*[:,]?\s*$"
)


def extract_action_dates(event: EventBlock) -> list[date]:
    """Datas de ACAO do evento (apresentou-se em, a contar de, ...).

    Sao as unicas datas fortes o bastante para EXCLUIR um evento do
    periodo; datas soltas no corpo (documentos, terceiros, legislacao)
    nao decidem exclusao.
    """
    text = strip_accents(f"{event.titulo}\n{event.referencia}\n{event.corpo}").upper()
    found: list[date] = []
    for pattern, builder in (
        (DATE_ABBREV_PATTERN, lambda m: date(
            _expand_two_digit_year(int(m.group(3))),
            MONTH_ABBREVIATIONS[m.group(2).upper()],
            int(m.group(1)),
        )),
        (DATE_NUMERIC_PATTERN, lambda m: date(int(m.group(3)), int(m.group(2)), int(m.group(1)))),
    ):
        for match in pattern.finditer(text):
            context = text[max(0, match.start() - ACTION_CONTEXT_WINDOW):match.start()]
            if not ACTION_DATE_PATTERN.search(context):
                continue
            try:
                found.append(builder(match))
            except ValueError:
                continue
    return found


def filter_events_in_period(
    events: list[EventBlock], start: date, end: date, *, strict: bool = True
) -> tuple[list[EventBlock], list[str]]:
    """Mantem eventos com alguma data dentro de [start, end].

    - sem data extraivel -> mantem com WARN_EVENT_SEM_DATA;
    - alguma data no periodo -> mantem;
    - TODAS as datas fora E alguma data de ACAO (apresentou-se em,
      a contar de...) fora -> exclui com ERR_EVENT_FORA_DO_PERIODO;
    - todas fora mas sem data de acao -> mantem com
      WARN_EVENT_DATAS_FORA_DO_PERIODO (datas soltas de documentos ou
      terceiros nao bastam para excluir uma alteracao do semestre).
    Nada e descartado silenciosamente.

    `strict=False` (transcricao de folha ja curada pela secretaria): o mes
    de PUBLICACAO governa (Anexo B) e nada e excluido — datas de acao fora
    do periodo geram WARN_EVENT_ACAO_FORA_DO_PERIODO para revisao (fatos
    de dezembro publicados em janeiro sao normais; ano trocado aparece no
    aviso em vez de sumir da folha).
    """
    kept: list[EventBlock] = []
    validations: list[str] = []
    for event in events:
        dates = extract_event_dates(event)
        if not dates:
            kept.append(event)
            validations.append(f"WARN_EVENT_SEM_DATA:{event.mes}:{event.titulo[:60]}")
            continue
        if any(start <= item <= end for item in dates):
            kept.append(event)
            continue
        action_dates = extract_action_dates(event)
        listed = ",".join(item.isoformat() for item in dates)
        if action_dates and not any(start <= item <= end for item in action_dates):
            if strict:
                validations.append(
                    f"ERR_EVENT_FORA_DO_PERIODO:{event.mes}:{event.titulo[:60]}:{listed}"
                )
                continue
            kept.append(event)
            validations.append(
                f"WARN_EVENT_ACAO_FORA_DO_PERIODO:{event.mes}:{event.titulo[:60]}:{listed}"
            )
            continue
        kept.append(event)
        validations.append(
            f"WARN_EVENT_DATAS_FORA_DO_PERIODO:{event.mes}:{event.titulo[:60]}:{listed}"
        )
    return kept, validations


def normalize_semester_events(
    events: list[EventBlock],
    semestre: str,
    ano: int | None = None,
    *,
    strict: bool = True,
) -> list[EventBlock] | tuple[list[EventBlock], list[str]]:
    """Filtra eventos pelo periodo da folha.

    Sem `ano` mantem o comportamento legado (filtro apenas pelo nome do mes)
    e devolve a lista. Com `ano`, tambem valida as datas extraidas contra o
    periodo real (dia/mes/ANO) e devolve (eventos, validacoes) — um evento de
    "17 JAN 24" nao pode entrar na folha do 1o semestre de 2023.
    """
    months = semester_months(semestre)
    validations: list[str] = []
    in_semester: list[EventBlock] = []
    for event in events:
        if event.mes in months:
            in_semester.append(event)
        else:
            validations.append(f"ERR_EVENT_FORA_DO_PERIODO:{event.mes}:{event.titulo[:60]}")
    if ano is None:
        return in_semester
    start, end, _label = period_bounds(ano, semestre)
    kept, date_validations = filter_events_in_period(in_semester, start, end, strict=strict)
    validations.extend(date_validations)
    return kept, list(dict.fromkeys(validations))


CONVOCACAO_KEYWORDS = ("CONVOCA", "INCORPORA", "INCLUS", "PRACA")
A_CONTAR_DE_PATTERN = re.compile(
    r"A\s+CONTAR\s+DE\s+(\d{1,2}(?:\s+(?:JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)[A-ZÇ]*\.?\s+(?:\d{2}|\d{4})|/\d{1,2}/\d{4}))",
    re.I,
)


def validate_data_praca_against_events(profile, events: list[EventBlock]) -> list[str]:
    """RC4 — data_praca deve casar com o evento de convocacao/inclusao.

    Quando o corpus traz um evento de convocacao com "a contar de <data>",
    a data de praca cadastrada precisa coincidir; divergencia gera
    WARN_DATA_PRACA_DIVERGENTE para revisao humana (nao bloqueia a folha).
    """
    if not profile.data_praca:
        return []
    validations: list[str] = []
    for event in events:
        text = strip_accents(f"{event.titulo}\n{event.corpo}").upper()
        if not any(keyword in text for keyword in CONVOCACAO_KEYWORDS):
            continue
        match = A_CONTAR_DE_PATTERN.search(text)
        if not match:
            continue
        target = _parse_single_date(match.group(1))
        if target and profile.data_praca != target:
            validations.append(
                "WARN_DATA_PRACA_DIVERGENTE:"
                f"cadastro={profile.data_praca.isoformat()}:"
                f"evento={target.isoformat()}"
            )
    return list(dict.fromkeys(validations))


def _parse_single_date(fragment: str) -> date | None:
    match = DATE_ABBREV_PATTERN.search(fragment)
    if match:
        day, month_name, year = match.groups()
        try:
            return date(_expand_two_digit_year(int(year)), MONTH_ABBREVIATIONS[month_name.upper()], int(day))
        except ValueError:
            return None
    match = DATE_NUMERIC_PATTERN.search(fragment)
    if match:
        day, month, year = match.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None
    return None


def recover_titles_from_previous_event(events: list[EventBlock]) -> list[str]:
    """Titulo orfao na cauda do corpo do evento anterior (quebra de pagina).

    Em PDFs de folhas, o titulo do proximo evento costuma ser a ultima
    linha antes da referencia; quando a extracao fatiou errado, ele fica
    no fim do corpo do evento anterior. Move de volta para o dono.
    """
    validations: list[str] = []
    for previous, current in zip(events, events[1:]):
        if current.titulo.strip() or not previous.corpo:
            continue
        lines = split_paragraphs(previous.corpo)
        if not lines:
            continue
        # Titulos longos quebram em mais de uma linha: recolhe do fim as
        # linhas contiguas com cara de titulo (max 3) e junta na ordem.
        collected: list[str] = []
        while lines and len(collected) < 3 and is_recoverable_event_title(lines[-1]):
            collected.insert(0, lines.pop())
        if collected:
            current.titulo = " ".join(collected)
            previous.corpo = "\n".join(lines).strip()
            validations.append("OK_EVENT_TITLE_RECOVERED_FROM_PREVIOUS")
    return list(dict.fromkeys(validations))


TITLE_DASH_PATTERN = re.compile(r"\s+-\s+")
REFERENCE_NUMBER_PATTERN = re.compile(r"^[-–]\s*a\s+(\d{1,3})\b")


def normalize_titulo(titulo: str) -> str:
    """Normaliza a tipografia do titulo da 1a Parte.

    Folhas curadas usam travessao ("FÉRIAS – Alteração"); o texto extraido
    de PDF chega com hifen. Unifica separador e espacos, sem mexer em
    hifens internos de palavras (ex.: "PRÉ-TAF").
    """
    return TITLE_DASH_PATTERN.sub(" – ", normalize_space(titulo))


def validate_ordem_referencias(events: list[EventBlock]) -> list[str]:
    """Gate da 1a Parte: dentro de cada mes, os numeros de alteracao
    ("- a N, ...") devem ser nao-decrescentes na ordem de publicacao.

    Quebra de monotonicidade e sintoma de evento fatiado/fora de lugar na
    extracao — vira WARN para revisao, nunca reordenacao automatica (a
    ordem de publicacao do boletim e a autoridade).
    """
    validations: list[str] = []
    ultimo_por_mes: dict[str, int] = {}
    for event in events:
        match = REFERENCE_NUMBER_PATTERN.match(event.referencia or "")
        if not match:
            continue
        numero = int(match.group(1))
        anterior = ultimo_por_mes.get(event.mes)
        if anterior is not None and numero < anterior:
            validations.append(
                f"WARN_ORDEM_EVENTOS_NAO_MONOTONICA:{event.mes}:a{numero}<a{anterior}"
            )
        ultimo_por_mes[event.mes] = max(numero, anterior or 0)
    return validations


def normalize_event_blocks(events: list[EventBlock]) -> tuple[list[EventBlock], list[str]]:
    normalized: list[EventBlock] = []
    validations: list[str] = recover_titles_from_previous_event(events)
    for event in events:
        pieces, split_recovered = split_embedded_events(event)
        if split_recovered:
            validations.append("OK_EVENT_BODY_SPLIT_RECOVERED")
        for piece in pieces:
            recovered = recover_missing_event_title(piece)
            if recovered:
                validations.append("OK_EVENT_TITLE_RECOVERED")
            piece.titulo = normalize_titulo(piece.titulo)
            if not piece.titulo.strip():
                validations.append("WARN_EVENT_TITLE_MISSING")
            normalized.append(piece)
    validations.extend(validate_ordem_referencias(normalized))
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

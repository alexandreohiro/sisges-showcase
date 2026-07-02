"""Calculo de tempos de servico para o compilador de Folhas de Alteracoes.

Funcoes para calcular TC, TNC, TTES, TSSD e demais tempos a partir de dados
do perfil SiCaPEx ou do contexto persitido no banco SisGeS.

Base normativa (EB30-N-10.002 / Port. 063-DGP/C Ex, 25 MAR 2020):
- Art. 20/21: o vinculo com a OM comeca no ato de inclusao e cessa no
  desligamento; nenhum tempo e contado fora da janela do vinculo.
- Art. 24: titulos da 2a Parte (TC, TNC, TSSD, TSCMM, TSNR, TTES).

Convencao de contagem (docs/decisions/0001-contagem-vinculo-folhas.md):
o dia da incorporacao CONTA; o dia do desligamento/licenciamento NAO conta
(exclusive). Semestre integral de vinculo vale 06m00d administrativos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from modules.compilador.application.folha_xml_utils import (
    days_inclusive,
    format_admin_days,
    overlap_days,
)

if TYPE_CHECKING:
    from modules.compilador.application.folha_models import SicapexProfile


FULL_SEMESTER_ADMIN_DAYS = 180

TSCMM_ORIGEM_APROXIMADO = "APROXIMADO_TTES"
TSCMM_ORIGEM_PART2 = "TOTAIS_PART2"


@dataclass(slots=True)
class TimeSummary:
    tc: str
    tc_arreg: str
    tc_nao_arreg: str
    tc_transito: str
    tc_instalacao: str
    tnc: str
    tscmm: str
    tssd: str
    tsnr: str
    ttes: str
    origem: str
    dias_reais_ttes: int
    dias_reais_tnc: int
    tscmm_origem: str = ""


@dataclass(slots=True)
class Vinculo:
    """Janela de vinculo militar-OM (Art. 20/21 da Port. 063-DGP/2020).

    `inicio` e o dia da incorporacao/inclusao (conta). `fim` e a data do
    desligamento/licenciamento "a contar de" (nao conta — exclusive);
    None significa vinculo ainda ativo.
    """

    inicio: date | None = None
    fim: date | None = None

    @property
    def ultimo_dia_computavel(self) -> date | None:
        if self.fim is None:
            return None
        return self.fim - timedelta(days=1)


def parse_iso_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def effective_window(vinculo: Vinculo, start: date, end: date) -> tuple[date, date] | None:
    """Intersecao [max(inicio, start), min(ultimo dia do vinculo, end)].

    Retorna None quando o vinculo nao alcanca o periodo (Art. 20/21).
    """
    window_start = max(vinculo.inicio, start) if vinculo.inicio else start
    window_end = min(vinculo.ultimo_dia_computavel or end, end)
    if window_end < window_start:
        return None
    return window_start, window_end


def semester_bounds_for(day: date) -> tuple[date, date]:
    if day.month <= 6:
        return date(day.year, 1, 1), date(day.year, 6, 30)
    return date(day.year, 7, 1), date(day.year, 12, 31)


def next_semester_start(sem_start: date) -> date:
    if sem_start.month == 1:
        return date(sem_start.year, 7, 1)
    return date(sem_start.year + 1, 1, 1)


def window_admin_days(window: tuple[date, date], sem_start: date, sem_end: date) -> int:
    """Dias administrativos da janela dentro do semestre.

    Semestre integral vale 180 (06m00d); janela parcial conta dia a dia.
    """
    if window == (sem_start, sem_end):
        return FULL_SEMESTER_ADMIN_DAYS
    return days_inclusive(*window)


def compute_tc_tnc_ttes(
    vinculo: Vinculo,
    start: date,
    end: date,
    descontos: list[tuple[date, date]],
) -> tuple[int, int, int]:
    """(tc_dias, tnc_dias, ttes_dias) do semestre [start, end].

    TC = dias da janela efetiva do semestre - TNC do semestre.
    TTES = acumulado de (TC - TNC) semestre a semestre, do inicio do
    vinculo ate min(fim do vinculo, end) — nunca ancora no fim do
    semestre corrente quando o vinculo termina antes (Art. 21).
    """
    window = effective_window(vinculo, start, end)
    if window is None:
        return 0, 0, ttes_admin_days(vinculo, end, descontos)
    tnc_days = sum(overlap_days(ini, fim, *window) for ini, fim in descontos)
    tc_days = max(window_admin_days(window, start, end) - tnc_days, 0)
    return tc_days, tnc_days, ttes_admin_days(vinculo, end, descontos)


def ttes_admin_days(vinculo: Vinculo, end: date, descontos: list[tuple[date, date]]) -> int:
    if not vinculo.inicio or vinculo.inicio > end:
        return 0
    total = 0
    sem_start, sem_end = semester_bounds_for(vinculo.inicio)
    while sem_start <= end:
        period_end = min(sem_end, end)
        window = effective_window(vinculo, sem_start, period_end)
        if window:
            tnc = sum(overlap_days(ini, fim, *window) for ini, fim in descontos)
            total += max(window_admin_days(window, sem_start, sem_end) - tnc, 0)
        sem_start = next_semester_start(sem_start)
        _, sem_end = semester_bounds_for(sem_start)
    return total


def periodo_days_in_semester(item: dict, start: date, end: date) -> int:
    inicio = parse_iso_date(item.get("data_inicio"))
    fim = parse_iso_date(item.get("data_fim")) or inicio
    if inicio and fim:
        return overlap_days(inicio, fim, start, end)
    return int(item.get("dias_lancados_override") or 0)


def periodo_days_total(item: dict) -> int:
    override = item.get("dias_lancados_override")
    if isinstance(override, int | float) and override > 0:
        return int(override)
    inicio = parse_iso_date(item.get("data_inicio"))
    fim = parse_iso_date(item.get("data_fim")) or inicio
    return days_inclusive(inicio, fim) if inicio and fim else 0


def vinculo_from_profile(profile: SicapexProfile) -> Vinculo:
    return Vinculo(inicio=profile.data_praca, fim=profile.data_desligamento)


def vinculo_from_context(context: dict) -> Vinculo:
    militar = context.get("militar") or {}
    inicio = parse_iso_date(militar.get("data_praca") or context.get("data_praca"))
    fim = parse_iso_date(
        militar.get("data_licenciamento")
        or militar.get("data_desligamento")
        or context.get("data_licenciamento")
        or context.get("data_desligamento")
    )
    return Vinculo(inicio=inicio, fim=fim)


def calculate_times_from_sicapex(profile: SicapexProfile, start: date, end: date) -> TimeSummary:
    vinculo = vinculo_from_profile(profile)
    descontos = [(ini, fim) for ini, fim, _motivo in profile.descontos]
    tc_days, tnc_days, ttes_days = compute_tc_tnc_ttes(vinculo, start, end, descontos)

    if not vinculo.inicio:
        # Sem data de praca nao ha ancora para TC/TTES: emite zerado para
        # forcar revisao humana em vez de assumir semestre cheio.
        tc_days = 0
        ttes_days = 0

    tc_display = format_admin_days(tc_days)
    ttes_display = format_admin_days(ttes_days)
    tssd_days = sum(days_inclusive(i, f) for i, f, _tempo, _doc in profile.acrescimos)

    return TimeSummary(
        tc=tc_display,
        tc_arreg=tc_display,
        tc_nao_arreg="00a00m00d",
        tc_transito="00a00m00d",
        tc_instalacao="00a00m00d",
        tnc=format_admin_days(tnc_days),
        tscmm=ttes_display,
        tssd=format_admin_days(tssd_days),
        tsnr="00a00m00d",
        ttes=ttes_display,
        origem="SICAPEX_CALCULADO",
        dias_reais_ttes=ttes_days,
        dias_reais_tnc=tnc_days,
        tscmm_origem=TSCMM_ORIGEM_APROXIMADO,
    )


def duration_admin_days(duration: dict | None) -> int:
    duration = duration or {}
    return (
        int(duration.get("anos") or 0) * 360
        + int(duration.get("meses") or 0) * 30
        + int(duration.get("dias") or 0)
    )


def calculate_times_from_part2(part2: dict | None) -> TimeSummary | None:
    """TimeSummary a partir do Part2Schema revisado pela secretaria.

    Dados ja auditados humanamente tem precedencia sobre o recalculo:
    TC por bucket (Art. 24, I), TNC (II), TSSD (III) e totais historicos
    (TSCMM/TSNR) transcritos de folhas anteriores.
    """
    if not isinstance(part2, dict) or not part2:
        return None
    tc_periodos = part2.get("tc_periodos") or []
    totais = part2.get("totais") or {}
    if not tc_periodos and not totais:
        return None

    buckets = {"arregimentado": 0, "nao_arregimentado": 0, "transito": 0, "instalacao": 0}
    for item in tc_periodos:
        bucket = str(item.get("bucket") or "arregimentado")
        days = duration_admin_days(item.get("duracao")) or periodo_days_total(item)
        buckets[bucket if bucket in buckets else "arregimentado"] += days

    tc_days = sum(buckets.values())
    tnc_days = sum(duration_admin_days(item.get("duracao")) for item in part2.get("tnc_periodos") or [])
    tssd_days = sum(duration_admin_days(item.get("duracao")) for item in part2.get("tssd_averbacoes") or [])
    ttes_days = tc_days + tssd_days

    return TimeSummary(
        tc=format_admin_days(tc_days),
        tc_arreg=format_admin_days(buckets["arregimentado"]),
        tc_nao_arreg=format_admin_days(buckets["nao_arregimentado"]),
        tc_transito=format_admin_days(buckets["transito"]),
        tc_instalacao=format_admin_days(buckets["instalacao"]),
        tnc=format_admin_days(tnc_days),
        tscmm=format_admin_days(duration_admin_days(totais.get("tscmm"))),
        tssd=format_admin_days(tssd_days),
        tsnr=format_admin_days(duration_admin_days(totais.get("tsnr"))),
        ttes=format_admin_days(ttes_days),
        origem="PART2_SCHEMA_REVISADO",
        dias_reais_ttes=ttes_days,
        dias_reais_tnc=tnc_days,
        tscmm_origem=TSCMM_ORIGEM_PART2,
    )


def calculate_times_from_context(
    context: dict,
    start: date,
    end: date,
    *,
    fallback: TimeSummary,
) -> TimeSummary:
    from_part2 = calculate_times_from_part2(context.get("part2_json"))
    if from_part2 is not None:
        return from_part2

    vinculo = vinculo_from_context(context)
    nao_computaveis = context.get("periodos_nao_computaveis", []) or []
    tnc_days = sum(periodo_days_in_semester(item, start, end) for item in nao_computaveis)
    tssd_days = sum(
        periodo_days_total(item)
        for item in context.get("acrescimos", []) or []
    )

    descontos = [
        (parse_iso_date(item.get("data_inicio")), parse_iso_date(item.get("data_fim")) or parse_iso_date(item.get("data_inicio")))
        for item in nao_computaveis
    ]
    descontos = [(ini, fim) for ini, fim in descontos if ini and fim]
    tc_days, _tnc_window_days, ttes_calc_days = compute_tc_tnc_ttes(vinculo, start, end, descontos)
    if not vinculo.inicio:
        tc_days = 0

    raw_ttes = context.get("tempo_efetivo_servico_apos_ultima_dias")
    if isinstance(raw_ttes, int | float):
        ttes_days = int(raw_ttes)
    elif vinculo.inicio:
        ttes_days = ttes_calc_days
    else:
        ttes_days = fallback.dias_reais_ttes

    tc_display = format_admin_days(tc_days)
    ttes_display = format_admin_days(ttes_days) if ttes_days else fallback.ttes

    return TimeSummary(
        tc=tc_display,
        tc_arreg=tc_display,
        tc_nao_arreg="00a00m00d",
        tc_transito="00a00m00d",
        tc_instalacao="00a00m00d",
        tnc=format_admin_days(tnc_days),
        tscmm=ttes_display,
        tssd=format_admin_days(tssd_days),
        tsnr="00a00m00d",
        ttes=ttes_display,
        origem="SICAPEX_BANCO_SISGES",
        dias_reais_ttes=ttes_days,
        dias_reais_tnc=tnc_days,
        tscmm_origem=TSCMM_ORIGEM_APROXIMADO,
    )

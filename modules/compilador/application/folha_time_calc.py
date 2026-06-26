"""Calculo de tempos de servico para o compilador de Folhas de Alteracoes.

Funcoes para calcular TC, TNC, TTES, TSSD e demais tempos a partir de dados
do perfil SiCaPEx ou do contexto persitido no banco SisGeS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from modules.compilador.application.folha_xml_utils import (
    days_inclusive,
    format_admin_days,
    format_calendar_ymd,
    overlap_days,
)

if TYPE_CHECKING:
    from modules.compilador.application.folha_models import SicapexProfile


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


def parse_iso_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


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


def calculate_times_from_sicapex(profile: SicapexProfile, start: date, end: date) -> TimeSummary:
    tnc_days = 0
    for inicio, fim, _motivo in profile.descontos:
        tnc_days += overlap_days(inicio, fim, start, end)

    tc_display = "00a06m00d" if (start.month, end.month) in [(1, 6), (7, 12)] else format_admin_days(days_inclusive(start, end))
    tnc_display = format_admin_days(tnc_days)
    ttes_days = days_inclusive(profile.data_praca, end) - tnc_days if profile.data_praca else 0
    ttes_display = format_calendar_ymd(profile.data_praca, end, extra_discount_days=tnc_days) if profile.data_praca else "00a00m00d"
    tssd_days = sum(days_inclusive(i, f) for i, f, _tempo, _doc in profile.acrescimos)

    return TimeSummary(
        tc=tc_display,
        tc_arreg=tc_display,
        tc_nao_arreg="00a00m00d",
        tc_transito="00a00m00d",
        tc_instalacao="00a00m00d",
        tnc=tnc_display,
        tscmm=ttes_display,
        tssd=format_admin_days(tssd_days),
        tsnr="00a00m00d",
        ttes=ttes_display,
        origem="SICAPEX_CALCULADO",
        dias_reais_ttes=ttes_days,
        dias_reais_tnc=tnc_days,
    )


def calculate_times_from_context(
    context: dict,
    start: date,
    end: date,
    *,
    fallback: TimeSummary,
) -> TimeSummary:
    tnc_days = sum(
        periodo_days_in_semester(item, start, end)
        for item in context.get("periodos_nao_computaveis", []) or []
    )
    tssd_days = sum(
        periodo_days_total(item)
        for item in context.get("acrescimos", []) or []
    )
    raw_ttes = context.get("tempo_efetivo_servico_apos_ultima_dias")
    ttes_days = int(raw_ttes) if isinstance(raw_ttes, int | float) else fallback.dias_reais_ttes

    tc_display = (
        "00a06m00d"
        if (start.month, end.month) in [(1, 6), (7, 12)]
        else format_admin_days(days_inclusive(start, end))
    )
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
    )

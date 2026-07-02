"""Dataclasses de dominio do compilador de Folhas de Alteracoes.

Modulo sem dependencias internas ao pipeline — importavel por qualquer
submodulo (folha_extraction, folha_time_calc, folha_event_validation,
folha_rendering) sem risco de import circular.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from modules.compilador.application.folha_format_contract import EMPTY_MONTH_BLOCK


@dataclass(slots=True)
class CompilerOptions:
    ano: int = 2025
    semestre: str = "2"
    reparar_tabelas: bool = True
    preservar_tabelas_odt: bool = True
    qmg_generico_em_branco: bool = True
    fonte: str = "Calibri Light"
    tamanho_fonte: int = 12
    empty_month_mode: str = EMPTY_MONTH_BLOCK
    assinatura_mode: str = "auto"
    assinatura_nome: str | None = None
    assinatura_funcao: str | None = None


@dataclass(slots=True)
class SicapexProfile:
    nome_completo: str = ""
    nome_guerra: str = ""
    graduacao_abrev: str = ""
    graduacao_extenso: str = ""
    qm: str = ""
    identidade: str = ""
    data_praca: date | None = None
    data_desligamento: date | None = None
    tipo_militar: str = "PRACA"
    comportamento: str = ""
    comportamento_data: str = ""
    comportamento_boletim: str = ""
    descontos: list[tuple[date, date, str]] = field(default_factory=list)
    acrescimos: list[tuple[date, date, str, str]] = field(default_factory=list)


@dataclass(slots=True)
class TableBlock:
    title: str
    columns: list[str]
    rows: list[list[str]]


@dataclass(slots=True)
class EventBlock:
    mes: str
    titulo: str
    referencia: str
    corpo: str
    tables: list[TableBlock] = field(default_factory=list)


@dataclass(slots=True)
class RenderResult:
    template_provided: bool = False
    template_used: bool = False
    template_sha256: str = ""
    strategy: str = "internal"
    warnings: list[str] = field(default_factory=list)
    validations: list[str] = field(default_factory=list)

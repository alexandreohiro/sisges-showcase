from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class HeaderData:
    nome_completo: str = ""
    nome_guerra: str = ""
    graduacao: str = ""
    identidade: str = ""
    qm: str = ""
    periodo: str = ""
    data_de_praca: str = ""


@dataclass(slots=True)
class Part1Entry:
    mes: str
    titulo: str
    referencia: str
    corpo: str


@dataclass(slots=True)
class Part2Times:
    tc: str = ""
    tc_arreg: str = ""
    tc_nao_arreg: str = ""
    tc_transito: str = ""
    tc_instalacao: str = ""
    tnc: str = ""
    tscmm: str = ""
    tssd: str = ""
    tsnr: str = ""
    ttes: str = ""
    origem: str = ""  # "extraido" | "fallback"


@dataclass(slots=True)
class PendingField:
    field_name: str
    reason: str
    suggested_value: str = ""
    source: str = "pending"


@dataclass(slots=True)
class CompilationRecord:
    header: HeaderData = field(default_factory=HeaderData)
    part1: list[Part1Entry] = field(default_factory=list)
    part2: Part2Times = field(default_factory=Part2Times)
    pending_fields: list[PendingField] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    raw_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
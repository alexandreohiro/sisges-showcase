from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any


@dataclass(slots=True)
class SicapexAfastamento:
    modalidade: str = ""
    quantidade_dias: int | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    documento: str = ""
    raw: str = ""


@dataclass(slots=True)
class SicapexMovimentacao:
    codom: str = ""
    om: str = ""
    cidade: str = ""
    data_inicio: date | None = None
    data_fim: date | None = None
    tipo: str = ""
    situacao: str = ""
    raw: str = ""


@dataclass(slots=True)
class SicapexSituacaoRegulamentar:
    codom: str = ""
    om: str = ""
    motivo: str = ""
    situacao: str = ""
    data_inicio: date | None = None
    data_fim: date | None = None
    raw: str = ""


@dataclass(slots=True)
class SicapexDataPraca:
    data_praca: date | None = None
    data_desligamento: date | None = None
    tipo_forca: str = ""
    documento: str = ""
    raw: str = ""


@dataclass(slots=True)
class SicapexTempoServico:
    tipo: str = ""
    subtipo: str = ""
    tempo: str = ""
    dias: int | None = None
    documento: str = ""
    data_inicio: date | None = None
    data_fim: date | None = None
    raw: str = ""


@dataclass(slots=True)
class SicapexComportamento:
    tipo: str = ""
    data: date | None = None
    documento: str = ""
    raw: str = ""


@dataclass(slots=True)
class SicapexPeriodoServicoSugerido:
    tipo_registro: str
    subtipo_registro: str = ""
    natureza_servico: str = ""
    categoria_tempo: str = ""
    origem: str = "sicapex"
    data_inicio: date | None = None
    data_fim: date | None = None
    computa_tempo: bool = True
    arregimentado: bool = False
    dias_lancados_override: int | None = None
    documento_referencia: str = ""
    status_calculo: str = "pendente_validacao"
    om_origem: str = ""
    om_destino: str = ""
    descricao: str = ""
    observacoes: str = ""
    payload_json: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SicapexParsedRecord:
    nome_completo: str = ""
    nome_guerra: str = ""
    sexo: str = ""
    estado_civil: str = ""
    posto_grad_abrev: str = ""
    posto_grad_extenso: str = ""
    qas_qms_qm: str = ""
    om_atual_nome: str = ""
    om_atual_codom: str = ""
    data_inicio_om: date | None = None
    situacao_militar: str = ""
    situacao_servico: str = ""
    identidade_militar: str = ""
    prec_cp: str = ""
    data_praca: date | None = None
    datas_praca: list[SicapexDataPraca] = field(default_factory=list)
    apresentacao_gu: date | None = None
    data_incorporacao: date | None = None
    data_engajamento: date | None = None
    data_reengajamento: date | None = None
    data_desengajamento: date | None = None
    data_licenciamento: date | None = None
    data_exclusao_servico_ativo: date | None = None
    ultima_promocao: date | None = None
    tipo_forca: str = ""
    documento_praca: str = ""
    tempo_servico_anterior_anos: int = 0
    tempo_servico_anterior_meses: int = 0
    tempo_servico_anterior_dias: int = 0
    tempo_servico_publico_anos: int = 0
    tempo_servico_publico_meses: int = 0
    tempo_servico_publico_dias: int = 0
    observacoes_calculo: str = ""
    afastamentos: list[SicapexAfastamento] = field(default_factory=list)
    agregacoes: list[dict[str, Any]] = field(default_factory=list)
    alteracoes_arquivadas: list[dict[str, Any]] = field(default_factory=list)
    habilitacoes: list[dict[str, Any]] = field(default_factory=list)
    inspecoes_saude: list[dict[str, Any]] = field(default_factory=list)
    comportamento_atual: SicapexComportamento | None = None
    historico_comportamento: list[SicapexComportamento] = field(default_factory=list)
    movimentacoes: list[SicapexMovimentacao] = field(default_factory=list)
    situacoes_regulamentares: list[SicapexSituacaoRegulamentar] = field(default_factory=list)
    desconto_tempo_servico: list[SicapexTempoServico] = field(default_factory=list)
    acrescimos_tempo_servico: list[SicapexTempoServico] = field(default_factory=list)
    tempo_efetivo_servico_apos_ultima: str = ""
    tempo_efetivo_servico_apos_ultima_dias: int | None = None
    tempo_servico_bruto_json: dict[str, Any] = field(default_factory=dict)
    periodos_servico_sugeridos: list[SicapexPeriodoServicoSugerido] = field(default_factory=list)
    pendencias_calculo: list[str] = field(default_factory=list)
    taf: list[dict[str, Any]] = field(default_factory=list)
    tat: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    raw_excerpt: str = ""
    source_sha256: str = ""
    source_filename: str = ""
    ocr_required: bool = False


@dataclass(slots=True)
class SicapexImportResult:
    filename: str
    sha256: str
    status: str
    militar_id: int | None = None
    militar_nome: str = ""
    identidade_mascarada: str = ""
    om_atual: str = ""
    data_praca: date | None = None
    comportamento_atual: str = ""
    afastamentos_count: int = 0
    movimentacoes_count: int = 0
    situacoes_regulamentares_count: int = 0
    tempo_efetivo_servico_apos_ultima: str = ""
    descontos_count: int = 0
    acrescimos_count: int = 0
    eventos_funcionais_criados: int = 0
    periodos_servico_criados: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(slots=True)
class SicapexBatchReport:
    batch_id: str
    source_folder: str = ""
    total_files: int = 0
    success_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
    duplicate_count: int = 0
    items: list[SicapexImportResult] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow_naive)

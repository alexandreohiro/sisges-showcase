from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


DocumentoUpdateTipo = Literal[
    "folha_alteracao",
    "ctsm",
    "declaracao",
    "calculo_tempo_servico",
    "outro",
]


class FolhaCreate(BaseModel):
    militar_id: int
    periodo_inicio: date
    periodo_fim: date
    status: str = "rascunho"
    origem_dados: Optional[str] = "manual"
    responsavel_user_id: Optional[str] = None
    revisor_user_id: Optional[str] = None
    observacoes: Optional[str] = None


class FolhaUpdate(BaseModel):
    status: Optional[str] = None
    origem_dados: Optional[str] = None
    responsavel_user_id: Optional[str] = None
    revisor_user_id: Optional[str] = None
    header_json: Optional[dict] = None
    part1_json: Optional[dict] = None
    part2_json: Optional[dict] = None
    diagnostico_json: Optional[dict] = None
    odt_path: Optional[str] = None
    pdf_path: Optional[str] = None
    observacoes: Optional[str] = None


class FolhaRead(BaseModel):
    id: int
    codigo: Optional[str] = None
    militar_id: int
    periodo_inicio: date
    periodo_fim: date
    status: str
    origem_dados: Optional[str] = None
    responsavel_user_id: Optional[str] = None
    revisor_user_id: Optional[str] = None
    header_json: Optional[dict] = None
    part1_json: Optional[dict] = None
    part2_json: Optional[dict] = None
    diagnostico_json: Optional[dict] = None
    odt_path: Optional[str] = None
    pdf_path: Optional[str] = None
    observacoes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FolhaActionInput(BaseModel):
    observacao: Optional[str] = None
    assinante_user_id: Optional[str] = None
    modalidade_assinatura: Optional[str] = None


class FolhaDocumentUpdateInput(BaseModel):
    tipo_documento: DocumentoUpdateTipo = "folha_alteracao"
    ano: int = Field(ge=1900, le=2100)
    semestre: int = Field(ge=1, le=2)
    cpf: str = Field(min_length=11, max_length=18)
    codom: str = Field(min_length=1, max_length=40)
    observacao: Optional[str] = Field(default=None, max_length=500)

    @field_validator("cpf")
    @classmethod
    def validate_cpf_digits(cls, value: str) -> str:
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) != 11:
            raise ValueError("CPF deve conter 11 digitos.")
        return digits

    @field_validator("codom")
    @classmethod
    def normalize_codom(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("CODOM obrigatorio.")
        return normalized


class FolhaDocumentUpdateRead(BaseModel):
    document_id: str
    status: str
    tipo_documento: str
    ano: int
    semestre: int
    codom: str
    cpf_masked: str
    militar_id: Optional[int] = None
    militar_nome: Optional[str] = None
    output_path: str
    message: str
    uploaded_filename: Optional[str] = None
    uploaded_sha256: Optional[str] = None


class FolhaDocumentUpdateHistoryItem(BaseModel):
    document_id: str
    status: str
    tipo_documento: str
    ano: Optional[int] = None
    semestre: Optional[int] = None
    codom: Optional[str] = None
    cpf_masked: Optional[str] = None
    militar_id: Optional[int] = None
    militar_nome: Optional[str] = None
    output_sha256: Optional[str] = None
    uploaded_filename: Optional[str] = None
    uploaded_sha256: Optional[str] = None
    has_attachment: bool = False
    has_manifest: bool = False
    trace_id: Optional[str] = None
    created_at: Optional[datetime] = None


class FolhaDocumentUpdateSummary(BaseModel):
    total: int = 0
    with_attachment: int = 0
    without_attachment: int = 0
    with_manifest: int = 0
    is_limited: bool = False
    oldest_created_at: Optional[datetime] = None
    latest_created_at: Optional[datetime] = None
    applied_filters: dict[str, str | int | bool] = Field(default_factory=dict)
    by_tipo_documento: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)
    limit: int = 0


class FolhaEventoRead(BaseModel):
    id: int
    folha_id: int
    tipo_evento: str
    descricao: str
    user_id: Optional[str] = None
    payload_json: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FolhaWorkflowRead(FolhaRead):
    militar_nome: str
    militar_nome_guerra: Optional[str] = None
    militar_posto_graduacao: Optional[str] = None
    militar_identidade: Optional[str] = None
    document_id: Optional[str] = None
    compiler_run_id: Optional[str] = None
    assinatura_user_id: Optional[str] = None
    eventos: list[FolhaEventoRead] = Field(default_factory=list)
    acoes_permitidas: list[str] = Field(default_factory=list)

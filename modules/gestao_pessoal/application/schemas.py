from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class MilitarBase(BaseModel):
    om: Optional[str] = None
    posto_graduacao: Optional[str] = None
    situacao_militar: Optional[str] = None
    nome_completo: str
    nome_guerra: Optional[str] = None
    identidade: Optional[str] = None
    cpf: Optional[str] = None
    cp: Optional[str] = None
    prec_cp: Optional[str] = None
    pis_pasep: Optional[str] = None
    cnh: Optional[str] = None
    titulo_numero: Optional[str] = None
    titulo_zona: Optional[str] = None
    titulo_secao: Optional[str] = None
    data_nascimento: Optional[date] = None
    local_nascimento: Optional[str] = None
    nome_pai: Optional[str] = None
    nome_mae: Optional[str] = None
    estado_civil: Optional[str] = None
    data_praca: Optional[date] = None
    apresentacao_om: Optional[date] = None
    apresentacao_gu: Optional[date] = None
    tempo_servico_anterior_anos: int = 0
    tempo_servico_anterior_meses: int = 0
    tempo_servico_anterior_dias: int = 0
    tempo_servico_publico_anos: int = 0
    tempo_servico_publico_meses: int = 0
    tempo_servico_publico_dias: int = 0
    ultima_promocao: Optional[date] = None
    secao: Optional[str] = None
    funcao: Optional[str] = None
    endereco: Optional[str] = None
    ramal: Optional[str] = None
    telefone: Optional[str] = None
    celular: Optional[str] = None
    contato_emergencia: Optional[str] = None
    email: Optional[str] = None
    religiao: Optional[str] = None
    status_servico: Optional[str] = None
    foto_path: Optional[str] = None
    observacoes: Optional[str] = None
    ativo: bool = True
    situacao_regulamentar: Optional[str] = None
    qas_qms: Optional[str] = None
    rm: Optional[str] = None
    local_om: Optional[str] = None
    data_turma: Optional[date] = None
    comportamento: Optional[str] = None

    sexo: Optional[str] = None
    escolaridade: Optional[str] = None
    nacionalidade: Optional[str] = None
    data_falecimento: Optional[date] = None
    identidade_civil: Optional[str] = None
    categoria: Optional[str] = None
    autodeclaracao_etnico_racial: Optional[str] = None
    ra: Optional[str] = None
    tipo_sanguineo: Optional[str] = None
    fator_rh: Optional[str] = None
    doador_orgaos: Optional[str] = None

    data_incorporacao: Optional[date] = None
    data_engajamento: Optional[date] = None
    data_reengajamento: Optional[date] = None
    data_desengajamento: Optional[date] = None
    data_licenciamento: Optional[date] = None
    data_exclusao_servico_ativo: Optional[date] = None

    observacoes_calculo: Optional[str] = None
    ficha_cadastro_json: Optional[dict[str, Any]] = None
    ficha_cadastro_pdf_hash: Optional[str] = None
    ficha_cadastro_origem: Optional[str] = None
    ficha_cadastro_importado_em: Optional[datetime] = None


class MilitarCreate(MilitarBase):
    pass


class MilitarUpdate(BaseModel):
    om: Optional[str] = None
    posto_graduacao: Optional[str] = None
    situacao_militar: Optional[str] = None
    nome_completo: Optional[str] = None
    nome_guerra: Optional[str] = None
    identidade: Optional[str] = None
    cpf: Optional[str] = None
    cp: Optional[str] = None
    prec_cp: Optional[str] = None
    pis_pasep: Optional[str] = None
    cnh: Optional[str] = None
    titulo_numero: Optional[str] = None
    titulo_zona: Optional[str] = None
    titulo_secao: Optional[str] = None
    data_nascimento: Optional[date] = None
    local_nascimento: Optional[str] = None
    nome_pai: Optional[str] = None
    nome_mae: Optional[str] = None
    estado_civil: Optional[str] = None
    data_praca: Optional[date] = None
    apresentacao_om: Optional[date] = None
    apresentacao_gu: Optional[date] = None
    tempo_servico_anterior_anos: Optional[int] = None
    tempo_servico_anterior_meses: Optional[int] = None
    tempo_servico_anterior_dias: Optional[int] = None
    tempo_servico_publico_anos: Optional[int] = None
    tempo_servico_publico_meses: Optional[int] = None
    tempo_servico_publico_dias: Optional[int] = None
    ultima_promocao: Optional[date] = None
    secao: Optional[str] = None
    funcao: Optional[str] = None
    endereco: Optional[str] = None
    ramal: Optional[str] = None
    telefone: Optional[str] = None
    celular: Optional[str] = None
    contato_emergencia: Optional[str] = None
    email: Optional[str] = None
    religiao: Optional[str] = None
    status_servico: Optional[str] = None
    foto_path: Optional[str] = None
    observacoes: Optional[str] = None
    ativo: Optional[bool] = None

    situacao_regulamentar: Optional[str] = None
    qas_qms: Optional[str] = None
    rm: Optional[str] = None
    local_om: Optional[str] = None
    data_turma: Optional[date] = None
    comportamento: Optional[str] = None

    sexo: Optional[str] = None
    escolaridade: Optional[str] = None
    nacionalidade: Optional[str] = None
    data_falecimento: Optional[date] = None
    identidade_civil: Optional[str] = None
    categoria: Optional[str] = None
    autodeclaracao_etnico_racial: Optional[str] = None
    ra: Optional[str] = None
    tipo_sanguineo: Optional[str] = None
    fator_rh: Optional[str] = None
    doador_orgaos: Optional[str] = None

    data_incorporacao: Optional[date] = None
    data_engajamento: Optional[date] = None
    data_reengajamento: Optional[date] = None
    data_desengajamento: Optional[date] = None
    data_licenciamento: Optional[date] = None
    data_exclusao_servico_ativo: Optional[date] = None

    observacoes_calculo: Optional[str] = None
    ficha_cadastro_json: Optional[dict[str, Any]] = None
    ficha_cadastro_pdf_hash: Optional[str] = None
    ficha_cadastro_origem: Optional[str] = None
    ficha_cadastro_importado_em: Optional[datetime] = None


class MilitarPeriodoServicoBase(BaseModel):
    tipo_registro: str
    subtipo_registro: Optional[str] = None
    natureza_servico: Optional[str] = None
    categoria_tempo: str
    origem: Optional[str] = None

    data_inicio: date
    data_fim: Optional[date] = None

    computa_tempo: bool = True
    arregimentado: bool = False

    dias_lancados_override: Optional[int] = None
    documento_referencia: Optional[str] = None
    status_calculo: Optional[str] = None

    om_origem: Optional[str] = None
    om_destino: Optional[str] = None

    descricao: Optional[str] = None
    observacoes: Optional[str] = None
    source_file_id: Optional[str] = None
    payload_json: Optional[dict[str, Any]] = None
    hash_evento: Optional[str] = None
    origem_documental: Optional[str] = None
    confianca_parse: Optional[str] = None


class MilitarPeriodoServicoCreate(MilitarPeriodoServicoBase):
    pass


class MilitarPeriodoServicoUpdate(BaseModel):
    tipo_registro: Optional[str] = None
    subtipo_registro: Optional[str] = None
    natureza_servico: Optional[str] = None
    categoria_tempo: Optional[str] = None
    origem: Optional[str] = None

    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None

    computa_tempo: Optional[bool] = None
    arregimentado: Optional[bool] = None

    dias_lancados_override: Optional[int] = None
    documento_referencia: Optional[str] = None
    status_calculo: Optional[str] = None

    om_origem: Optional[str] = None
    om_destino: Optional[str] = None

    descricao: Optional[str] = None
    observacoes: Optional[str] = None
    source_file_id: Optional[str] = None
    payload_json: Optional[dict[str, Any]] = None
    hash_evento: Optional[str] = None
    origem_documental: Optional[str] = None
    confianca_parse: Optional[str] = None


class MilitarPeriodoServicoRead(MilitarPeriodoServicoBase):
    id: int
    militar_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MilitarRead(BaseModel):
    id: int

    om: Optional[str] = None
    posto_graduacao: Optional[str] = None
    situacao_militar: Optional[str] = None
    situacao_regulamentar: Optional[str] = None

    nome_completo: str
    nome_guerra: Optional[str] = None
    identidade: Optional[str] = None
    cpf: Optional[str] = None
    cp: Optional[str] = None
    prec_cp: Optional[str] = None
    pis_pasep: Optional[str] = None
    cnh: Optional[str] = None
    titulo_numero: Optional[str] = None
    titulo_zona: Optional[str] = None
    titulo_secao: Optional[str] = None

    data_nascimento: Optional[date] = None
    local_nascimento: Optional[str] = None
    nome_pai: Optional[str] = None
    nome_mae: Optional[str] = None
    estado_civil: Optional[str] = None
    sexo: Optional[str] = None
    escolaridade: Optional[str] = None
    nacionalidade: Optional[str] = None
    data_falecimento: Optional[date] = None
    identidade_civil: Optional[str] = None
    categoria: Optional[str] = None
    autodeclaracao_etnico_racial: Optional[str] = None
    ra: Optional[str] = None
    tipo_sanguineo: Optional[str] = None
    fator_rh: Optional[str] = None
    doador_orgaos: Optional[str] = None

    data_praca: Optional[date] = None
    apresentacao_om: Optional[date] = None
    apresentacao_gu: Optional[date] = None
    data_incorporacao: Optional[date] = None
    data_engajamento: Optional[date] = None
    data_reengajamento: Optional[date] = None
    data_desengajamento: Optional[date] = None
    data_licenciamento: Optional[date] = None
    data_exclusao_servico_ativo: Optional[date] = None
    data_turma: Optional[date] = None
    ultima_promocao: Optional[date] = None

    tempo_servico_anterior_anos: Optional[int] = None
    tempo_servico_anterior_meses: Optional[int] = None
    tempo_servico_anterior_dias: Optional[int] = None
    tempo_servico_publico_anos: Optional[int] = None
    tempo_servico_publico_meses: Optional[int] = None
    tempo_servico_publico_dias: Optional[int] = None

    qas_qms: Optional[str] = None
    rm: Optional[str] = None
    local_om: Optional[str] = None
    comportamento: Optional[str] = None
    secao: Optional[str] = None
    funcao: Optional[str] = None

    endereco: Optional[str] = None
    ramal: Optional[str] = None
    telefone: Optional[str] = None
    celular: Optional[str] = None
    contato_emergencia: Optional[str] = None
    email: Optional[str] = None
    religiao: Optional[str] = None
    status_servico: Optional[str] = None
    foto_path: Optional[str] = None
    observacoes: Optional[str] = None
    observacoes_calculo: Optional[str] = None
    ficha_cadastro_json: Optional[dict[str, Any]] = None
    ficha_cadastro_pdf_hash: Optional[str] = None
    ficha_cadastro_origem: Optional[str] = None
    ficha_cadastro_importado_em: Optional[datetime] = None

    ativo: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompiladorContextoRead(BaseModel):
    militar_id: int
    tipo_documento_sugerido: str
    militar: MilitarRead


class MilitarParseTextInput(BaseModel):
    raw_text: str


class MilitarParseTextResponse(BaseModel):
    parsed_data: dict[str, Any]
    warnings: list[str]
    unmapped_lines: list[str]


class MilitarFromTextResponse(BaseModel):
    militar: "MilitarRead"
    warnings: list[str]
    unmapped_lines: list[str]


class MilitarParseFullTextResponse(BaseModel):
    parsed_data: dict[str, Any]
    parsed_periodos: list[dict[str, Any]]
    warnings: list[str]
    unmapped_lines: list[str]


class MilitarFromFullTextResponse(BaseModel):
    militar: "MilitarRead"
    periodos_criados: int
    warnings: list[str]
    unmapped_lines: list[str]


class MilitarEfetivoOmResponse(BaseModel):
    ativos_na_om: list[MilitarRead]
    inativos_na_om: list[MilitarRead]
    total_ativos: int
    total_inativos: int


class GestaoPessoalUserScopeRead(BaseModel):
    scope_available: bool
    source: str
    militar_id: Optional[int] = None
    nome_completo: Optional[str] = None
    nome_guerra: Optional[str] = None
    posto_graduacao: Optional[str] = None
    secao: Optional[str] = None
    divisao: Optional[str] = None
    warnings: list[str] = []


class GestaoPessoalFilterOptionsRead(BaseModel):
    postos_graduacoes: list[str]
    secoes: list[str]
    divisoes: list[str]


class MilitarParsePdfResponse(BaseModel):
    parsed_data: dict[str, Any]
    warnings: list[str]
    unmapped_lines: list[str]
    raw_excerpt: str


class MilitarFromPdfResponse(BaseModel):
    militar: "MilitarRead"
    action: str
    warnings: list[str]
    unmapped_lines: list[str]
    raw_excerpt: str

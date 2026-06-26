from __future__ import annotations

from pydantic import BaseModel, Field


class CTSMFromCalculoInput(BaseModel):
    calculo_id: int
    observacoes: str | None = None
    emitir_documento: bool = True


class CTSMEmitirInput(BaseModel):
    observacoes: str | None = None


class CTSMRead(BaseModel):
    id: int
    codigo: str | None
    militar_id: int
    calculo_id: int | None
    document_id: str | None
    folha_id: int | None
    status: str
    conteudo_json: dict | None = Field(default=None)
    odt_path: str | None
    pdf_path: str | None
    emitido_em: str | None
    emitido_por_user_id: str | None
    observacoes: str | None
    created_at: str
    updated_at: str

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


BoardVisibility = Literal["private", "shared"]


class QuadroContent(BaseModel):
    schema_version: str = "quadro.sisges.v1"
    elements: list[dict[str, Any]] = Field(default_factory=list)
    viewport: dict[str, Any] = Field(default_factory=dict)
    background: dict[str, Any] = Field(default_factory=dict)


class QuadroBoardCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=160)
    descricao: str | None = None
    visibility: BoardVisibility = "private"
    content_json: QuadroContent | dict[str, Any] | None = None
    thumbnail_png: str | None = None


class QuadroBoardUpdate(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=160)
    descricao: str | None = None
    visibility: BoardVisibility | None = None
    content_json: QuadroContent | dict[str, Any] | None = None
    thumbnail_png: str | None = None


class QuadroBoardRead(BaseModel):
    id: int
    titulo: str
    descricao: str | None = None
    visibility: str
    owner_user_id: str
    content_json: dict[str, Any]
    thumbnail_png: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from infra.config import settings


DEFAULT_POSTO_GRADUACAO_ORDER = {
    "gen ex": 10,
    "general de exercito": 10,
    "gen div": 20,
    "general de divisao": 20,
    "gen bda": 30,
    "general de brigada": 30,
    "cel": 40,
    "coronel": 40,
    "ten cel": 50,
    "tenente coronel": 50,
    "maj": 60,
    "major": 60,
    "cap": 70,
    "capitao": 70,
    "1 ten": 80,
    "1o ten": 80,
    "primeiro tenente": 80,
    "2 ten": 90,
    "2o ten": 90,
    "segundo tenente": 90,
    "asp": 100,
    "aspirante": 100,
    "sten": 110,
    "st": 110,
    "s ten": 110,
    "sub ten": 110,
    "subtenente": 110,
    "1 sgt": 120,
    "1o sgt": 120,
    "primeiro sargento": 120,
    "2 sgt": 130,
    "2o sgt": 130,
    "segundo sargento": 130,
    "3 sgt": 140,
    "3o sgt": 140,
    "terceiro sargento": 140,
    "cb": 150,
    "cabo": 150,
    "sd": 160,
    "soldado": 160,
    "rec": 170,
    "rcr": 170,
    "recruta": 170,
}

DEFAULT_COMMAND_PRECEDENCE = {
    "nilton": 0,
    "rogerio": 1,
}

DEFAULT_DIVISION_FIELDS = ["local_om", "om"]
CONFIG_RELATIVE_PATH = Path("data/config/gestao_pessoal_hierarchy.json")


class GestaoPessoalHierarchyConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "gestao-pessoal-hierarchy-v1"
    posto_graduacao_order: dict[str, int] = Field(default_factory=dict)
    command_precedence: dict[str, int] = Field(default_factory=dict)
    default_view_scope: Literal["usuario", "efetivo_completo"] = "usuario"
    auto_scope_enabled: bool = True
    division_fields: list[str] = Field(default_factory=list)
    unknown_rank: int = 999


def default_hierarchy_config() -> GestaoPessoalHierarchyConfig:
    return GestaoPessoalHierarchyConfig(
        posto_graduacao_order=dict(DEFAULT_POSTO_GRADUACAO_ORDER),
        command_precedence=dict(DEFAULT_COMMAND_PRECEDENCE),
        division_fields=list(DEFAULT_DIVISION_FIELDS),
    )


def hierarchy_config_path() -> Path:
    return settings.base_dir / CONFIG_RELATIVE_PATH


def load_hierarchy_config(path: Path | None = None) -> GestaoPessoalHierarchyConfig:
    config = default_hierarchy_config()
    target = path or hierarchy_config_path()
    if not target.exists():
        return config

    raw = json.loads(target.read_text(encoding="utf-8"))
    configured = GestaoPessoalHierarchyConfig.model_validate(raw)
    merged = config.model_copy(deep=True)
    merged.posto_graduacao_order.update(configured.posto_graduacao_order)
    merged.command_precedence.update(configured.command_precedence)
    merged.default_view_scope = configured.default_view_scope
    merged.auto_scope_enabled = configured.auto_scope_enabled
    merged.division_fields = configured.division_fields or list(DEFAULT_DIVISION_FIELDS)
    merged.unknown_rank = configured.unknown_rank
    return merged


def save_hierarchy_config(
    payload: GestaoPessoalHierarchyConfig,
    path: Path | None = None,
) -> GestaoPessoalHierarchyConfig:
    config = default_hierarchy_config()
    config.posto_graduacao_order.update(payload.posto_graduacao_order)
    config.command_precedence.update(payload.command_precedence)
    config.default_view_scope = payload.default_view_scope
    config.auto_scope_enabled = payload.auto_scope_enabled
    config.division_fields = payload.division_fields or list(DEFAULT_DIVISION_FIELDS)
    config.unknown_rank = payload.unknown_rank

    target = path or hierarchy_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(config.model_dump(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return config

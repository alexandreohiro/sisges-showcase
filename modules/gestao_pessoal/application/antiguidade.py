from __future__ import annotations

from datetime import date
import re
import unicodedata
from typing import Any

from modules.gestao_pessoal.application.hierarchy_config import (
    DEFAULT_COMMAND_PRECEDENCE,
    DEFAULT_POSTO_GRADUACAO_ORDER,
    GestaoPessoalHierarchyConfig,
    load_hierarchy_config,
)

POSTO_GRADUACAO_ORDER = DEFAULT_POSTO_GRADUACAO_ORDER
COMMAND_PRECEDENCE = DEFAULT_COMMAND_PRECEDENCE

INACTIVE_MARKERS = {
    "adido aguardando desligamento",
    "desligado",
    "excluido",
    "excluido do servico ativo",
    "exclusao",
    "falecido",
    "inativo",
    "licenciado",
    "nao apresentado",
    "reserva",
    "reformado",
}


def normalize_text(value: str | None) -> str:
    raw = unicodedata.normalize("NFD", value or "")
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    raw = raw.lower().strip()
    raw = raw.replace("º", "o").replace("ª", "a")
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def posto_graduacao_rank(
    value: str | None,
    config: GestaoPessoalHierarchyConfig | None = None,
) -> int:
    hierarchy = config or load_hierarchy_config()
    normalized = normalize_text(value)
    return hierarchy.posto_graduacao_order.get(normalized, hierarchy.unknown_rank)


def command_precedence_rank(
    militar: Any,
    config: GestaoPessoalHierarchyConfig | None = None,
) -> int:
    hierarchy = config or load_hierarchy_config()
    cel_rank = hierarchy.posto_graduacao_order.get("cel", 40)
    if posto_graduacao_rank(getattr(militar, "posto_graduacao", None), hierarchy) != cel_rank:
        return hierarchy.unknown_rank

    name_blob = normalize_text(
        " ".join(
            str(getattr(militar, field, "") or "")
            for field in ("nome_guerra", "nome_completo")
        ),
    )
    for name, rank in hierarchy.command_precedence.items():
        if re.search(rf"\b{re.escape(name)}\b", name_blob):
            return rank
    return hierarchy.unknown_rank


def is_ativo_na_om(militar: Any) -> bool:
    if not bool(getattr(militar, "ativo", False)):
        return False

    status_text = " ".join(
        normalize_text(getattr(militar, field, None))
        for field in ("situacao_militar", "situacao_regulamentar", "status_servico")
    )
    return not any(marker in status_text for marker in INACTIVE_MARKERS)


def antiguidade_sort_key(
    militar: Any,
    config: GestaoPessoalHierarchyConfig | None = None,
) -> tuple:
    hierarchy = config or load_hierarchy_config()
    data_incorporacao = getattr(militar, "data_incorporacao", None) or date.max
    data_nascimento = getattr(militar, "data_nascimento", None) or date.max
    return (
        command_precedence_rank(militar, hierarchy),
        posto_graduacao_rank(getattr(militar, "posto_graduacao", None), hierarchy),
        data_incorporacao,
        data_nascimento,
        normalize_text(getattr(militar, "nome_completo", None)),
    )

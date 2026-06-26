from __future__ import annotations

from dataclasses import dataclass, field


EMPTY_MONTH_BLOCK = "BLOCK"
EMPTY_MONTH_COMPACT_SINGULAR = "COMPACT_SINGULAR"
EMPTY_MONTH_COMPACT_PLURAL = "COMPACT_PLURAL"

EMPTY_MONTH_MODES = {
    EMPTY_MONTH_BLOCK,
    EMPTY_MONTH_COMPACT_SINGULAR,
    EMPTY_MONTH_COMPACT_PLURAL,
}


@dataclass(slots=True)
class FolhaFormatContract:
    """Contrato visual/formal da Folha de Alteracoes.

    O contrato separa decisao de formatacao de decisao semantica. A fixture
    visual de referencia (ALPHA_ODT_REFERENCE) orienta aparencia documental;
    filtros de eventos e assinatura continuam como regras operacionais separadas.
    """

    schema_version: str = "folha-format-contract-v1"
    source: str = "SISGES_INTERNAL_DEFAULT"
    font_family: str = "Calibri Light"
    font_size: int = 12
    month_style: str = "Month"
    empty_month_mode: str = EMPTY_MONTH_BLOCK
    event_title_style: str = "Bold"
    bi_reference_style: str = "Standard"
    body_style: str = "Standard"
    table_style: str = "Table"
    segunda_parte_style: str = "Table"
    signature_style: str = "Center"
    header_style: str = "Header"
    page_style: str = "Standard"
    table_policy: str = "PRESERVE"
    warnings: list[str] = field(default_factory=list)

    def normalized_empty_month_mode(self) -> str:
        if self.empty_month_mode in EMPTY_MONTH_MODES:
            return self.empty_month_mode
        self.warnings.append("WARN_EMPTY_MONTH_MODE_INVALID_DEFAULTED")
        return EMPTY_MONTH_BLOCK


def default_folha_format_contract(
    *, empty_month_mode: str = EMPTY_MONTH_BLOCK, source: str = "SISGES_INTERNAL_DEFAULT"
) -> FolhaFormatContract:
    return FolhaFormatContract(source=source, empty_month_mode=empty_month_mode)


def alpha_visual_format_contract() -> FolhaFormatContract:
    return FolhaFormatContract(
        source="ALPHA_ODT_REFERENCE",
        empty_month_mode=EMPTY_MONTH_COMPACT_SINGULAR,
        table_policy="FILTERED_TO_MILITAR_ALLOWED",
    )


def empty_month_text(month: str, mode: str) -> str:
    if mode == EMPTY_MONTH_COMPACT_SINGULAR:
        return f"{month}: Sem Alteração."
    if mode == EMPTY_MONTH_COMPACT_PLURAL:
        return f"{month}: Sem alterações."
    return "Sem alterações."

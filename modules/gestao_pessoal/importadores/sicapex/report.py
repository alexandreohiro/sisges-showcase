from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
import json
from typing import Any

from modules.gestao_pessoal.importadores.sicapex.schemas import (
    SicapexBatchReport,
    SicapexImportResult,
)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value


def result_to_dict(result: SicapexImportResult) -> dict[str, Any]:
    return to_jsonable(asdict(result))


def report_to_dict(report: SicapexBatchReport) -> dict[str, Any]:
    data = asdict(report)
    return to_jsonable(data)


def report_to_json(report: SicapexBatchReport) -> str:
    return json.dumps(report_to_dict(report), ensure_ascii=False, indent=2)


def report_to_txt(report: SicapexBatchReport) -> str:
    lines = [
        "RELATORIO DE IMPORTACAO SICAPEX",
        f"Batch: {report.batch_id}",
        f"Origem: {report.source_folder or '-'}",
        f"Total: {report.total_files}",
        f"Sucessos: {report.success_count}",
        f"Pendencias: {report.pending_count}",
        f"Falhas: {report.failed_count}",
        f"Duplicidades: {report.duplicate_count}",
        "",
    ]
    for item in report.items:
        lines.extend(
            [
                f"Arquivo: {item.filename}",
                f"SHA-256: {item.sha256}",
                f"Status: {item.status}",
                f"Militar: {item.militar_nome or '-'}",
                f"Identidade: {item.identidade_mascarada or '-'}",
                f"OM atual: {item.om_atual or '-'}",
                f"Data de praca: {item.data_praca.isoformat() if item.data_praca else '-'}",
                f"Comportamento: {item.comportamento_atual or '-'}",
                f"Afastamentos: {item.afastamentos_count}",
                f"Descontos: {item.descontos_count}",
                f"Acrescimos: {item.acrescimos_count}",
                f"Movimentacoes: {item.movimentacoes_count}",
                f"Situacoes regulamentares: {item.situacoes_regulamentares_count}",
                f"Eventos funcionais criados: {item.eventos_funcionais_criados}",
                f"Periodos de servico criados: {item.periodos_servico_criados}",
                f"Tempo efetivo apos ultima: {item.tempo_efetivo_servico_apos_ultima or '-'}",
                f"Pendencias: {', '.join(item.pending) if item.pending else '-'}",
                f"Erros: {', '.join(item.errors) if item.errors else '-'}",
                "",
            ]
        )
    return "\n".join(lines)

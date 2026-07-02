from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from infra.persistence.models import (
    MilitarModel,
    MilitarPeriodoServicoModel,
    SicapexEventoFuncionalModel,
    SicapexImportFileModel,
)


def build_tempo_servico_context(militar_id: int, db: Session) -> dict[str, Any]:
    militar = db.get(MilitarModel, militar_id)
    if not militar:
        raise ValueError("Militar nao encontrado.")

    latest_file = (
        db.query(SicapexImportFileModel)
        .filter(SicapexImportFileModel.militar_id == militar_id)
        .order_by(SicapexImportFileModel.created_at.desc())
        .first()
    )
    periodos = (
        db.query(MilitarPeriodoServicoModel)
        .filter(MilitarPeriodoServicoModel.militar_id == militar_id)
        .order_by(MilitarPeriodoServicoModel.data_inicio.asc())
        .all()
    )
    eventos = (
        db.query(SicapexEventoFuncionalModel)
        .filter(SicapexEventoFuncionalModel.militar_id == militar_id)
        .order_by(SicapexEventoFuncionalModel.created_at.desc(), SicapexEventoFuncionalModel.id.desc())
        .all()
    )

    parsed = latest_file.parsed_json if latest_file and latest_file.parsed_json else {}
    pendencias = list(parsed.get("pendencias_calculo") or parsed.get("pending") or [])
    has_sicapex = latest_file is not None
    has_data_praca = militar.data_praca is not None
    if not latest_file:
        status = "SEM_SICAPEX"
        pendencias.append("SEM_FICHA_SICAPEX_IMPORTADA")
    elif not has_data_praca:
        status = "SICAPEX_INCOMPLETO"
        pendencias.append("SEM_DATA_PRACA")
    elif pendencias:
        status = "SICAPEX_INCOMPLETO"
    else:
        status = "SICAPEX_COMPLETO"
    requires_sicapex_pdf = status != "SICAPEX_COMPLETO"

    return {
        "militar_id": militar_id,
        "status": status,
        "has_sicapex": has_sicapex,
        "has_data_praca": has_data_praca,
        "has_tempo_context": has_sicapex and has_data_praca,
        "source": "GESTAO_PESSOAL_DB",
        "requires_sicapex_pdf": requires_sicapex_pdf,
        "warnings": list(dict.fromkeys(pendencias)),
        "militar": _militar_dict(militar),
        "data_praca": _iso(militar.data_praca),
        "data_corte_sugerida": date.today().isoformat(),
        "tempo_efetivo_servico_apos_ultima": parsed.get("tempo_efetivo_servico_apos_ultima") or "",
        "tempo_efetivo_servico_apos_ultima_dias": parsed.get("tempo_efetivo_servico_apos_ultima_dias"),
        "periodos_computaveis": [
            _periodo_dict(item)
            for item in periodos
            if item.computa_tempo and item.categoria_tempo != "adicional"
        ],
        "periodos_nao_computaveis": [
            _periodo_dict(item)
            for item in periodos
            if item.tipo_registro == "desconto_tempo" or item.categoria_tempo == "nao_computado"
        ],
        "acrescimos": [_periodo_dict(item) for item in periodos if item.categoria_tempo == "adicional"],
        "afastamentos_informativos": [
            _periodo_dict(item) for item in periodos if item.tipo_registro == "afastamento"
        ],
        "movimentacoes": [_evento_dict(item) for item in eventos if item.tipo_evento == "MOVIMENTACAO"],
        "situacoes_regulamentares": [
            _evento_dict(item) for item in eventos if item.tipo_evento == "SITUACAO_REGULAMENTAR"
        ],
        "eventos": [_evento_dict(item) for item in eventos],
        "periodos": [_periodo_dict(item) for item in periodos],
        "fonte_sicapex": _source_dict(latest_file),
        "pendencias": list(dict.fromkeys(pendencias)),
        "status_confiabilidade": status,
        "calculo_pendente_validacao": True,
    }


def _militar_dict(militar: MilitarModel) -> dict[str, Any]:
    return {
        "id": militar.id,
        "nome_completo": militar.nome_completo,
        "nome_guerra": militar.nome_guerra,
        "posto_graduacao": militar.posto_graduacao,
        "qas_qms": militar.qas_qms,
        "identidade": militar.identidade,
        "prec_cp": militar.prec_cp,
        "om": militar.om,
        "local_om": militar.local_om,
        "data_praca": _iso(militar.data_praca),
        "data_licenciamento": _iso(militar.data_licenciamento),
        "data_desligamento": _iso(militar.data_exclusao_servico_ativo),
        "apresentacao_om": _iso(militar.apresentacao_om),
        "comportamento": militar.comportamento,
        "observacoes_calculo": militar.observacoes_calculo,
    }


def _periodo_dict(item: MilitarPeriodoServicoModel) -> dict[str, Any]:
    return {
        "id": item.id,
        "tipo_registro": item.tipo_registro,
        "subtipo_registro": item.subtipo_registro,
        "natureza_servico": item.natureza_servico,
        "categoria_tempo": item.categoria_tempo,
        "origem": item.origem,
        "data_inicio": _iso(item.data_inicio),
        "data_fim": _iso(item.data_fim),
        "computa_tempo": item.computa_tempo,
        "arregimentado": item.arregimentado,
        "dias_lancados_override": item.dias_lancados_override,
        "documento_referencia": item.documento_referencia,
        "status_calculo": item.status_calculo,
        "om_origem": item.om_origem,
        "om_destino": item.om_destino,
        "descricao": item.descricao,
        "observacoes": item.observacoes,
        "source_file_id": item.source_file_id,
        "hash_evento": item.hash_evento,
        "origem_documental": item.origem_documental,
        "confianca_parse": item.confianca_parse,
        "payload_json": item.payload_json,
    }


def _evento_dict(item: SicapexEventoFuncionalModel) -> dict[str, Any]:
    return {
        "id": item.id,
        "tipo_evento": item.tipo_evento,
        "subtipo_evento": item.subtipo_evento,
        "data_inicio": _iso(item.data_inicio),
        "data_fim": _iso(item.data_fim),
        "documento": item.documento,
        "source_file_id": item.source_file_id,
        "payload_json": item.payload_json,
    }


def _source_dict(item: SicapexImportFileModel | None) -> dict[str, Any] | None:
    if not item:
        return None
    return {
        "id": item.id,
        "batch_id": item.batch_id,
        "filename": item.filename,
        "sha256": item.sha256,
        "status": item.status,
        "created_at": _iso(item.created_at),
        "warnings": item.warnings_json or [],
    }


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None

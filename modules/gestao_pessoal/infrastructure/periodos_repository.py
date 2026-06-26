from __future__ import annotations

from sqlalchemy.orm import Session

from infra.persistence.models import MilitarPeriodoServicoModel
from modules.gestao_pessoal.application.schemas import (
    MilitarPeriodoServicoCreate,
    MilitarPeriodoServicoUpdate,
)


class MilitarPeriodosRepository:
    def __init__(self, db: Session):
        self.db = db

    def _validate_payload(self, payload_dict: dict):
        data_inicio = payload_dict.get("data_inicio")
        data_fim = payload_dict.get("data_fim")
        tipo_registro = payload_dict.get("tipo_registro")
        subtipo_registro = payload_dict.get("subtipo_registro")
        natureza_servico = payload_dict.get("natureza_servico")
        categoria_tempo = payload_dict.get("categoria_tempo")
        om_origem = payload_dict.get("om_origem")
        om_destino = payload_dict.get("om_destino")
        documento_referencia = payload_dict.get("documento_referencia")

        if data_inicio and data_fim and data_fim < data_inicio:
            raise ValueError("Data final não pode ser menor que a data inicial.")

        if tipo_registro == "movimentacao" and not (om_origem or om_destino):
            raise ValueError(
                "Movimentação exige OM de origem, OM de destino ou ambas."
            )

        if tipo_registro == "servico_anterior" and not natureza_servico:
            raise ValueError("Serviço anterior exige natureza do serviço.")

        if tipo_registro == "acrescimo_tempo" and not subtipo_registro:
            raise ValueError("Acréscimo de tempo exige subtipo do registro.")

        if categoria_tempo in {"tscmm", "tsnr"} and not documento_referencia:
            raise ValueError(
                "TSCMM e TSNR exigem documento de referência."
            )

    def list_by_militar(self, militar_id: int):
        return (
            self.db.query(MilitarPeriodoServicoModel)
            .filter(MilitarPeriodoServicoModel.militar_id == militar_id)
            .order_by(MilitarPeriodoServicoModel.data_inicio.desc())
            .all()
        )

    def create(self, militar_id: int, payload: MilitarPeriodoServicoCreate):
        payload_dict = payload.model_dump()
        self._validate_payload(payload_dict)

        model = MilitarPeriodoServicoModel(
            militar_id=militar_id,
            **payload_dict,
        )
        self.db.add(model)
        self.db.flush()
        self.db.refresh(model)
        return model

    def get(self, periodo_id: int):
        return (
            self.db.query(MilitarPeriodoServicoModel)
            .filter(MilitarPeriodoServicoModel.id == periodo_id)
            .first()
        )

    def update(self, periodo_id: int, payload: MilitarPeriodoServicoUpdate):
        model = self.get(periodo_id)
        if not model:
            return None

        payload_dict = payload.model_dump(exclude_unset=True)

        merged = {
            "tipo_registro": payload_dict.get("tipo_registro", model.tipo_registro),
            "subtipo_registro": payload_dict.get("subtipo_registro", model.subtipo_registro),
            "natureza_servico": payload_dict.get("natureza_servico", model.natureza_servico),
            "categoria_tempo": payload_dict.get("categoria_tempo", model.categoria_tempo),
            "origem": payload_dict.get("origem", model.origem),
            "data_inicio": payload_dict.get("data_inicio", model.data_inicio),
            "data_fim": payload_dict.get("data_fim", model.data_fim),
            "computa_tempo": payload_dict.get("computa_tempo", model.computa_tempo),
            "arregimentado": payload_dict.get("arregimentado", model.arregimentado),
            "dias_lancados_override": payload_dict.get(
                "dias_lancados_override",
                model.dias_lancados_override,
            ),
            "documento_referencia": payload_dict.get(
                "documento_referencia",
                model.documento_referencia,
            ),
            "status_calculo": payload_dict.get("status_calculo", model.status_calculo),
            "om_origem": payload_dict.get("om_origem", model.om_origem),
            "om_destino": payload_dict.get("om_destino", model.om_destino),
            "descricao": payload_dict.get("descricao", model.descricao),
            "observacoes": payload_dict.get("observacoes", model.observacoes),
        }

        self._validate_payload(merged)

        for key, value in payload_dict.items():
            setattr(model, key, value)

        self.db.flush()
        self.db.refresh(model)
        return model

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from infra.persistence.models import (
    CTSMModel,
    DocumentModel,
    FolhaAlteracaoModel,
    MilitarModel,
    MilitarPeriodoServicoModel,
    TarefaModel,
)


class Militar360Service:
    def __init__(self, db):
        self.db = db

    def get_profile(self, militar_id: int) -> dict[str, Any]:
        militar = self._get_militar(militar_id)
        periodos = self._periodos(militar_id)
        calculos = self._calculos(militar_id)
        folhas = self._folhas(militar_id)
        ctsms = self._ctsms(militar_id)
        documents = self._documents(militar_id, ctsms)
        tarefas = self._tarefas(militar_id)
        return {
            "militar": self._militar_to_dict(militar),
            "periodos_servico": periodos,
            "calculos": calculos,
            "snapshots": [item.get("base_legal_json") for item in calculos],
            "folhas": folhas,
            "ctsms": ctsms,
            "documents": documents,
            "tarefas": tarefas,
            "timeline": self.timeline(militar_id),
            "resumo": {
                "periodos": len(periodos),
                "calculos": len(calculos),
                "folhas": len(folhas),
                "ctsms": len(ctsms),
                "documents": len(documents),
                "tarefas": len(tarefas),
            },
        }

    def timeline(self, militar_id: int) -> list[dict[str, Any]]:
        militar = self._get_militar(militar_id)
        events = [
            self._event(
                when=militar.created_at,
                module="gestao_pessoal",
                kind="militar_criado",
                title="Cadastro do militar criado",
                ref_type="militar",
                ref_id=str(militar.id),
            )
        ]
        for periodo in self.db.query(MilitarPeriodoServicoModel).filter(
            MilitarPeriodoServicoModel.militar_id == militar_id
        ):
            events.append(
                self._event(
                    when=periodo.created_at,
                    module="gestao_pessoal",
                    kind="periodo_servico",
                    title=f"Periodo de servico: {periodo.tipo_registro}",
                    ref_type="militar_periodo_servico",
                    ref_id=str(periodo.id),
                )
            )
        for calculo in militar.calculos:
            events.append(
                self._event(
                    when=calculo.created_at,
                    module="calculo",
                    kind="snapshot_calculo",
                    title="Snapshot de calculo aprovado",
                    ref_type="calculo_tempo_servico",
                    ref_id=str(calculo.id),
                )
            )
        for folha in militar.folhas:
            events.append(
                self._event(
                    when=folha.created_at,
                    module="folhas",
                    kind="folha",
                    title=f"Folha de alteracao {folha.status}",
                    ref_type="folha_alteracao",
                    ref_id=str(folha.id),
                )
            )
        for ctsm in militar.ctsms:
            events.append(
                self._event(
                    when=ctsm.emitido_em or ctsm.created_at,
                    module="ctsm",
                    kind="ctsm",
                    title=f"CTSM {ctsm.status}",
                    ref_type="ctsm",
                    ref_id=str(ctsm.id),
                )
            )
        for tarefa in self.db.query(TarefaModel).filter(TarefaModel.militar_id == militar_id):
            events.append(
                self._event(
                    when=tarefa.created_at,
                    module="tarefas",
                    kind="tarefa",
                    title=f"Tarefa {tarefa.status}: {tarefa.titulo}",
                    ref_type="tarefa",
                    ref_id=str(tarefa.id),
                )
            )
        return sorted(events, key=lambda item: item["when"] or "", reverse=True)

    def _get_militar(self, militar_id: int) -> MilitarModel:
        militar = self.db.query(MilitarModel).filter(MilitarModel.id == militar_id).first()
        if not militar:
            raise ValueError("Militar nao encontrado.")
        return militar

    def _periodos(self, militar_id: int) -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "tipo_registro": item.tipo_registro,
                "subtipo_registro": item.subtipo_registro,
                "categoria_tempo": item.categoria_tempo,
                "data_inicio": self._serialize(item.data_inicio),
                "data_fim": self._serialize(item.data_fim),
                "computa_tempo": item.computa_tempo,
                "arregimentado": item.arregimentado,
                "documento_referencia": item.documento_referencia,
                "om_origem": item.om_origem,
                "om_destino": item.om_destino,
            }
            for item in self.db.query(MilitarPeriodoServicoModel)
            .filter(MilitarPeriodoServicoModel.militar_id == militar_id)
            .order_by(MilitarPeriodoServicoModel.data_inicio.asc())
            .all()
        ]

    def _calculos(self, militar_id: int) -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "referencia_data": self._serialize(item.referencia_data),
                "tempo_total": {
                    "anos": item.tempo_total_anos,
                    "meses": item.tempo_total_meses,
                    "dias": item.tempo_total_dias,
                },
                "tempo_computado": {
                    "anos": item.tempo_computado_anos,
                    "meses": item.tempo_computado_meses,
                    "dias": item.tempo_computado_dias,
                },
                "base_legal_json": item.base_legal_json,
                "created_at": self._serialize(item.created_at),
            }
            for item in self._get_militar(militar_id).calculos
        ]

    def _folhas(self, militar_id: int) -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "codigo": item.codigo,
                "status": item.status,
                "periodo_inicio": self._serialize(item.periodo_inicio),
                "periodo_fim": self._serialize(item.periodo_fim),
                "odt_path": item.odt_path,
                "pdf_path": item.pdf_path,
                "created_at": self._serialize(item.created_at),
            }
            for item in self.db.query(FolhaAlteracaoModel)
            .filter(FolhaAlteracaoModel.militar_id == militar_id)
            .order_by(FolhaAlteracaoModel.created_at.desc())
            .all()
        ]

    def _ctsms(self, militar_id: int) -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "codigo": item.codigo,
                "status": item.status,
                "calculo_id": item.calculo_id,
                "document_id": item.document_id,
                "folha_id": item.folha_id,
                "emitido_em": self._serialize(item.emitido_em),
                "created_at": self._serialize(item.created_at),
            }
            for item in self.db.query(CTSMModel)
            .filter(CTSMModel.militar_id == militar_id)
            .order_by(CTSMModel.created_at.desc())
            .all()
        ]

    def _documents(self, militar_id: int, ctsms: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ctsm_doc_ids = {item["document_id"] for item in ctsms if item.get("document_id")}
        docs = []
        for doc in self.db.query(DocumentModel).order_by(DocumentModel.created_at.desc()).all():
            metadata = doc.metadata_json or {}
            if doc.id not in ctsm_doc_ids and metadata.get("militar_id") != militar_id:
                continue
            docs.append(
                {
                    "id": doc.id,
                    "kind": doc.kind,
                    "filename": doc.filename,
                    "status": doc.status,
                    "source_module": doc.source_module,
                    "output_path": doc.output_path,
                    "trace_id": doc.trace_id,
                    "output_sha256": doc.output_sha256,
                    "template_version": doc.template_version,
                    "created_at": self._serialize(doc.created_at),
                }
            )
        return docs

    def _tarefas(self, militar_id: int) -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "titulo": item.titulo,
                "tipo": item.tipo,
                "prioridade": item.prioridade,
                "status": item.status,
                "origem_modulo": item.origem_modulo,
                "created_at": self._serialize(item.created_at),
            }
            for item in self.db.query(TarefaModel)
            .filter(TarefaModel.militar_id == militar_id)
            .order_by(TarefaModel.created_at.desc())
            .all()
        ]

    @staticmethod
    def _militar_to_dict(item: MilitarModel) -> dict[str, Any]:
        return {
            "id": item.id,
            "om": item.om,
            "posto_graduacao": item.posto_graduacao,
            "nome_completo": item.nome_completo,
            "nome_guerra": item.nome_guerra,
            "identidade": item.identidade,
            "cpf": item.cpf,
            "data_praca": Militar360Service._serialize(item.data_praca),
            "ativo": item.ativo,
            "created_at": Militar360Service._serialize(item.created_at),
            "updated_at": Militar360Service._serialize(item.updated_at),
        }

    @staticmethod
    def _event(
        *,
        when: datetime | None,
        module: str,
        kind: str,
        title: str,
        ref_type: str,
        ref_id: str,
    ) -> dict[str, Any]:
        return {
            "when": Militar360Service._serialize(when),
            "module": module,
            "kind": kind,
            "title": title,
            "referencia_tipo": ref_type,
            "referencia_id": ref_id,
        }

    @staticmethod
    def _serialize(value: date | datetime | None) -> str | None:
        return value.isoformat() if value else None

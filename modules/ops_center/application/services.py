from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from infra.persistence.models import WorkflowItemModel
from infra.persistence.transactions import atomic
from modules.consistencia.application.services import ConsistenciaService, ConsistencyIssue


OPEN_STATUSES = {"aberto", "em_andamento"}
SEVERITY_ORDER = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}


class OpsCenterService:
    def __init__(self, db):
        self.db = db

    def inbox(
        self,
        *,
        status: str = "aberto",
        modulo: str | None = None,
        militar_id: int | None = None,
        limit: int = 100,
    ) -> list[WorkflowItemModel]:
        query = self.db.query(WorkflowItemModel)
        if status != "todos":
            query = query.filter(WorkflowItemModel.status == status)
        if modulo:
            query = query.filter(WorkflowItemModel.modulo == modulo)
        if militar_id is not None:
            query = query.filter(WorkflowItemModel.militar_id == militar_id)
        return (
            query.order_by(
                WorkflowItemModel.score.desc(),
                WorkflowItemModel.created_at.asc(),
            )
            .limit(limit)
            .all()
        )

    def summary(self) -> dict[str, Any]:
        items = self.db.query(WorkflowItemModel).filter(
            WorkflowItemModel.status.in_(OPEN_STATUSES)
        ).all()
        by_module: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        next_actions: dict[str, int] = {}
        for item in items:
            by_module[item.modulo] = by_module.get(item.modulo, 0) + 1
            by_severity[item.severidade] = by_severity.get(item.severidade, 0) + 1
            next_actions[item.acao_recomendada] = next_actions.get(item.acao_recomendada, 0) + 1

        ordered = sorted(
            items,
            key=lambda item: (
                SEVERITY_ORDER.get(item.severidade, 99),
                -item.score,
                item.created_at,
            ),
        )
        return {
            "total_abertos": len(items),
            "por_modulo": by_module,
            "por_severidade": by_severity,
            "acoes_recomendadas": next_actions,
            "proxima_acao": self.to_dict(ordered[0]) if ordered else None,
        }

    def rebuild(self, *, militar_id: int | None = None) -> dict[str, Any]:
        issues = ConsistenciaService(self.db).reprocessar(militar_id=militar_id)
        fingerprints = {issue.fingerprint for issue in issues}

        with atomic(self.db):
            existing = {
                item.fingerprint: item
                for item in self.db.query(WorkflowItemModel)
                .filter(WorkflowItemModel.status.in_(OPEN_STATUSES))
                .all()
            }

            created = 0
            updated = 0
            for issue in issues:
                item = existing.get(issue.fingerprint)
                if item:
                    self._apply_issue(item, issue)
                    updated += 1
                else:
                    self.db.add(self._from_issue(issue))
                    created += 1

            obsoleted = 0
            for fingerprint, item in existing.items():
                if militar_id is not None and item.militar_id != militar_id:
                    continue
                if fingerprint not in fingerprints:
                    item.status = "obsoleto"
                    item.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    obsoleted += 1

        return {
            "issues_detectados": len(issues),
            "criados": created,
            "atualizados": updated,
            "obsoletos": obsoleted,
        }

    def resolve(
        self,
        *,
        item_id: int,
        actor_user_id: str | None,
        note: str | None = None,
    ) -> WorkflowItemModel:
        item = self.db.query(WorkflowItemModel).filter(WorkflowItemModel.id == item_id).first()
        if not item:
            raise ValueError("Item operacional nao encontrado.")
        with atomic(self.db):
            item.status = "resolvido"
            item.resolved_at = datetime.now(UTC).replace(tzinfo=None)
            item.resolved_by_user_id = actor_user_id
            payload = dict(item.payload_json or {})
            if note:
                payload["resolution_note"] = note
            item.payload_json = payload
            self.db.flush()
            self.db.refresh(item)
        return item

    @staticmethod
    def _from_issue(issue: ConsistencyIssue) -> WorkflowItemModel:
        return WorkflowItemModel(
            fingerprint=issue.fingerprint,
            modulo=issue.modulo,
            tipo=issue.tipo,
            severidade=issue.severidade,
            score=issue.score,
            status="aberto",
            militar_id=issue.militar_id,
            referencia_tipo=issue.referencia_tipo,
            referencia_id=issue.referencia_id,
            titulo=issue.titulo,
            descricao=issue.descricao,
            acao_recomendada=issue.acao_recomendada,
            motivo_regra=issue.motivo_regra,
            payload_json={"source": "consistencia", **issue.payload},
        )

    @staticmethod
    def _apply_issue(item: WorkflowItemModel, issue: ConsistencyIssue) -> None:
        item.modulo = issue.modulo
        item.tipo = issue.tipo
        item.severidade = issue.severidade
        item.score = issue.score
        item.militar_id = issue.militar_id
        item.referencia_tipo = issue.referencia_tipo
        item.referencia_id = issue.referencia_id
        item.titulo = issue.titulo
        item.descricao = issue.descricao
        item.acao_recomendada = issue.acao_recomendada
        item.motivo_regra = issue.motivo_regra
        item.payload_json = {"source": "consistencia", **issue.payload}
        item.updated_at = datetime.now(UTC).replace(tzinfo=None)

    @staticmethod
    def to_dict(item: WorkflowItemModel) -> dict[str, Any]:
        return {
            "id": item.id,
            "modulo": item.modulo,
            "tipo": item.tipo,
            "severidade": item.severidade,
            "score": item.score,
            "status": item.status,
            "militar_id": item.militar_id,
            "referencia_tipo": item.referencia_tipo,
            "referencia_id": item.referencia_id,
            "titulo": item.titulo,
            "descricao": item.descricao,
            "acao_recomendada": item.acao_recomendada,
            "motivo_regra": item.motivo_regra,
            "payload": item.payload_json,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        }

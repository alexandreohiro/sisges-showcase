from __future__ import annotations

from typing import Any

from infra.persistence.models import WorkflowItemModel
from modules.ops_center.application.services import OpsCenterService


ACTION_TARGETS = {
    "COMPLETAR_DADO_DATA_PRACA": {
        "method": "GET",
        "path_template": "/militar-360/{militar_id}",
        "description": "Abrir visao Militar 360 e completar data_praca na gestao de pessoal.",
    },
    "GERAR_CTSM_A_PARTIR_DE_CALCULO": {
        "method": "POST",
        "path_template": "/ctsm/from-calculo",
        "description": "Selecionar calculo aprovado e gerar CTSM.",
    },
    "REEMITIR_CTSM": {
        "method": "POST",
        "path_template": "/ctsm/{referencia_id}/emitir",
        "description": "Reemitir CTSM com snapshot mais recente.",
    },
    "REVISAR_FOLHA": {
        "method": "GET",
        "path_template": "/folhas/{referencia_id}",
        "description": "Revisar vinculo e periodo da folha de alteracao.",
    },
    "REPROCESSAR_DOCUMENTO": {
        "method": "POST",
        "path_template": "/compilador/render-odt-from-record",
        "description": "Reprocessar documento para gerar hash e metadados de template.",
    },
    "CORRIGIR_PERIODO_SERVICO": {
        "method": "GET",
        "path_template": "/militar-360/{militar_id}",
        "description": "Corrigir periodo de servico na gestao de pessoal.",
    },
    "REVISAR_SOBREPOSICAO_PERIODOS": {
        "method": "GET",
        "path_template": "/militar-360/{militar_id}/timeline",
        "description": "Abrir timeline para revisar periodos sobrepostos.",
    },
    "ANEXAR_OU_REGISTRAR_ARTEFATO": {
        "method": "GET",
        "path_template": "/tarefas/{referencia_id}",
        "description": "Registrar resultado ou artefato da tarefa concluida.",
    },
}


class AcoesSugeridasService:
    def __init__(self, db):
        self.db = db

    def executar(
        self,
        *,
        acao: str | None,
        item_id: int | None,
        actor_user_id: str | None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        if acao == "REPROCESSAR_CONSISTENCIA":
            return {
                "executed": True,
                "action": acao,
                "result": OpsCenterService(self.db).rebuild(
                    militar_id=payload.get("militar_id"),
                ),
            }

        item = self._get_item(item_id) if item_id is not None else None
        action_code = acao or (item.acao_recomendada if item else None)
        if not action_code:
            raise ValueError("Informe acao ou item_id.")

        if action_code == "RESOLVER_ITEM":
            if not item:
                raise ValueError("RESOLVER_ITEM exige item_id.")
            resolved = OpsCenterService(self.db).resolve(
                item_id=item.id,
                actor_user_id=actor_user_id,
                note=payload.get("note"),
            )
            return {
                "executed": True,
                "action": action_code,
                "item": OpsCenterService.to_dict(resolved),
            }

        target = ACTION_TARGETS.get(action_code)
        if not target:
            raise ValueError(f"Acao sugerida desconhecida: {action_code}.")

        return {
            "executed": False,
            "manual_required": True,
            "action": action_code,
            "reason": "A acao exige decisao operacional humana antes de alterar dados.",
            "target": self._render_target(target, item=item, payload=payload),
            "item": OpsCenterService.to_dict(item) if item else None,
        }

    def _get_item(self, item_id: int | None) -> WorkflowItemModel:
        item = self.db.query(WorkflowItemModel).filter(WorkflowItemModel.id == item_id).first()
        if not item:
            raise ValueError("Item operacional nao encontrado.")
        return item

    @staticmethod
    def _render_target(
        target: dict[str, str],
        *,
        item: WorkflowItemModel | None,
        payload: dict[str, Any],
    ) -> dict[str, str]:
        path = target["path_template"]
        values = {
            "militar_id": payload.get("militar_id") or (item.militar_id if item else ""),
            "referencia_id": payload.get("referencia_id") or (item.referencia_id if item else ""),
        }
        for key, value in values.items():
            path = path.replace("{" + key + "}", str(value or ""))
        return {
            "method": target["method"],
            "path": path,
            "description": target["description"],
        }

from fastapi import APIRouter, Depends

from apps.web.dependencies.auth import require_permission
from infra.persistence.db import get_db
from modules.documents.application.services import DocumentService
from modules.ops_center.application.services import OpsCenterService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/pending")
def get_pending(
    user=Depends(require_permission("dashboard.pending.view")),
    db=Depends(get_db),
):
    service = OpsCenterService(db)
    items = service.inbox(status="aberto", limit=6)
    return {
        "total": len(items),
        "summary": service.summary(),
        "items": [
            {
                "id": item.id,
                "title": item.titulo,
                "description": item.descricao,
                "priority": item.severidade,
                "module": item.modulo,
                "next_action": item.acao_recomendada,
                "militar_id": item.militar_id,
            }
            for item in items
        ],
    }


@router.get("/metrics")
def get_metrics(
    user=Depends(require_permission("dashboard.metrics.view")),
    db=Depends(get_db),
):
    summary = OpsCenterService(db).summary()
    return {
        "cards": [
            {
                "id": "m1",
                "label": "Documentos hoje",
                "value": 7,
                "trend": "+2",
            },
            {
                "id": "m2",
                "label": "Pendencias abertas",
                "value": summary["total_abertos"],
                "trend": "ops",
            },
            {
                "id": "m3",
                "label": "Compilacoes OK",
                "value": 5,
                "trend": "+1",
            },
            {
                "id": "m4",
                "label": "Criticas",
                "value": summary["por_severidade"].get("critica", 0),
                "trend": "ops",
            },
        ]
    }


@router.get("/recent-docs")
def get_recent_docs(
    user=Depends(require_permission("documents.view")),
    db=Depends(get_db),
):
    items = DocumentService(db).list_recent(limit=6)
    return {
        "items": [
            {
                "id": item.id,
                "name": item.filename,
                "type": item.kind,
                "status": item.status,
                "owner": item.owner_user_id or "-",
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ]
    }

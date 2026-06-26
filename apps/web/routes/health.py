from fastapi import APIRouter, Response
from apps.web.dependencies.container import container
from infra.config import settings
from infra.persistence.health import database_healthcheck

router = APIRouter(tags=["health"])


@router.get("/health")
def healthcheck(response: Response):
    db = database_healthcheck()
    status = "ok" if db["status"] == "ok" else "degraded"
    if status != "ok":
        response.status_code = 503

    return {
        **container.health(),
        "status": status,
        "environment": settings.environment,
        "debug": settings.debug,
        "database": db,
    }


@router.get("/health/live")
def livecheck():
    return {"status": "ok"}


@router.get("/health/ready")
def readycheck(response: Response):
    db = database_healthcheck()
    if db["status"] != "ok":
        response.status_code = 503
    return {"status": db["status"], "database": db}

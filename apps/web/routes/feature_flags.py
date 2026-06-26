from fastapi import APIRouter, Depends
from pydantic import BaseModel

from infra.persistence.db import get_db
from apps.web.dependencies.auth import get_current_user, require_dev_mode
from apps.web.errors import bad_request
from modules.permissions.application.services import PermissionService

router = APIRouter(prefix="/feature-flags", tags=["feature_flags"])


class FeatureFlagUpdateInput(BaseModel):
    enabled: bool
    dev_only: bool | None = None


@router.get("")
def list_flags(
    user=Depends(require_dev_mode),
    db=Depends(get_db),
):
    flags = PermissionService(db).list_flags()
    return {
        "items": [
            {
                "key": f.key,
                "enabled": f.enabled,
                "dev_only": f.dev_only,
            }
            for f in flags
        ]
    }


@router.get("/visible")
def list_visible_flags(
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    flags = PermissionService(db).list_visible_flags_for_user(user["is_dev"])
    return {
        "items": [
            {
                "key": f.key,
                "enabled": f.enabled,
                "dev_only": f.dev_only,
            }
            for f in flags
        ]
    }


@router.patch("/{key}")
def update_flag(
    key: str,
    payload: FeatureFlagUpdateInput,
    user=Depends(require_dev_mode),
    db=Depends(get_db),
):
    try:
        updated = PermissionService(db).update_flag(
            key=key,
            enabled=payload.enabled,
            dev_only=payload.dev_only,
        )
    except Exception as exc:
        raise bad_request("FEATURE_FLAG_UPDATE_FAILED", str(exc))

    return {
        "item": {
            "key": updated.key,
            "enabled": updated.enabled,
            "dev_only": updated.dev_only,
        }
    }

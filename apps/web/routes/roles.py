from fastapi import APIRouter, Depends
from infra.persistence.db import get_db
from apps.web.dependencies.auth import require_permission
from modules.permissions.application.services import PermissionService
from modules.users.application.services import DEV_MODE_PERMISSION, DEV_ROLE_NAMES

router = APIRouter(prefix="/roles", tags=["roles"])


def _role_is_dev_only(role) -> bool:
    role_name = str(role.name or "").strip().lower()
    if role_name in DEV_ROLE_NAMES:
        return True
    return any(permission.key == DEV_MODE_PERMISSION for permission in role.permissions)

@router.get("")
def list_roles(
    user = Depends(require_permission("permissions.manage")),
    db = Depends(get_db),
):
    roles = PermissionService(db).list_roles()
    if not user.get("is_dev"):
        roles = [role for role in roles if not _role_is_dev_only(role)]
    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "permissions": [p.key for p in r.permissions],
            }
            for r in roles
        ]
    }

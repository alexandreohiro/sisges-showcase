from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr

from apps.web.dependencies.auth import auth_http_exception, get_current_user, require_permission
from apps.web.errors import bad_request
from infra.config import settings
from infra.persistence.db import get_db
from infra.pipeline.uploads import IMAGE_UPLOAD_POLICY, UploadValidationError, save_upload_to_path
from modules.users.application.services import UserService

router = APIRouter(prefix="/users", tags=["users"])

OPERATIONAL_PROFILE_FIELDS = {
    "identidade",
    "posto_graduacao",
    "nome_guerra",
    "telefone",
    "contato",
    "divisao",
    "secao",
}


class UserCreateInput(BaseModel):
    username: str
    display_name: str
    email: EmailStr
    password: str
    role_names: list[str]
    is_dev: bool = False
    identidade: str | None = None
    posto_graduacao: str | None = None
    nome_guerra: str | None = None
    telefone: str | None = None
    contato: str | None = None
    divisao: str | None = None
    secao: str | None = None


class UserUpdateInput(BaseModel):
    display_name: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = None
    role_names: list[str] | None = None
    is_dev: bool | None = None
    identidade: str | None = None
    posto_graduacao: str | None = None
    nome_guerra: str | None = None
    telefone: str | None = None
    contato: str | None = None
    divisao: str | None = None
    secao: str | None = None


class ResetPasswordInput(BaseModel):
    new_password: str


def _user_item(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "is_active": user.is_active,
        "is_dev": user.is_dev,
        "avatar_path": user.avatar_path,
        "identidade": user.identidade,
        "posto_graduacao": user.posto_graduacao,
        "nome_guerra": user.nome_guerra,
        "telefone": user.telefone,
        "contato": user.contato,
        "divisao": user.divisao,
        "secao": user.secao,
        "roles": [role.name for role in user.roles],
    }


@router.get("")
def list_users(
    user=Depends(require_permission("users.manage")),
    db=Depends(get_db),
):
    items = UserService(db).list_users()
    return {
        "items": [_user_item(u) for u in items]
    }


@router.post("")
def create_user(
    payload: UserCreateInput,
    user=Depends(require_permission("users.manage")),
    db=Depends(get_db),
):
    try:
        created = UserService(db).create_user(
            **payload.model_dump(),
            actor_user_id=user.get("id"),
            actor_is_dev=bool(user.get("is_dev")),
        )
    except ValueError as exc:
        raise bad_request("USER_CREATE_FAILED", str(exc))

    return {
        "item": _user_item(created)
    }


@router.patch("/{user_id}")
def update_user(
    user_id: str,
    payload: UserUpdateInput,
    user=Depends(require_permission("users.manage")),
    db=Depends(get_db),
):
    update_data = payload.model_dump(exclude_unset=True)
    for field in OPERATIONAL_PROFILE_FIELDS & payload.model_fields_set:
        if update_data.get(field) is None:
            update_data[field] = ""

    try:
        updated = UserService(db).update_user(
            user_id,
            **update_data,
            actor_user_id=user.get("id"),
            actor_is_dev=bool(user.get("is_dev")),
        )
    except ValueError as exc:
        raise bad_request("USER_UPDATE_FAILED", str(exc))

    return {
        "item": _user_item(updated)
    }


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: str,
    payload: ResetPasswordInput,
    user=Depends(require_permission("users.manage")),
    db=Depends(get_db),
):
    try:
        updated = UserService(db).reset_password(
            user_id,
            payload.new_password,
            actor_user_id=user.get("id"),
            actor_is_dev=bool(user.get("is_dev")),
        )
    except ValueError as exc:
        raise bad_request("USER_PASSWORD_RESET_FAILED", str(exc))

    return {
        "ok": True,
        "item": {
            "id": updated.id,
            "username": updated.username,
        }
    }


@router.delete("/{user_id}")
def deactivate_user(
    user_id: str,
    user=Depends(require_permission("users.manage")),
    db=Depends(get_db),
):
    try:
        updated = UserService(db).deactivate_user(
            user_id,
            actor_user_id=user.get("id"),
            actor_is_dev=bool(user.get("is_dev")),
        )
    except ValueError as exc:
        raise bad_request("USER_DEACTIVATE_FAILED", str(exc))

    return {
        "ok": True,
        "item": _user_item(updated),
    }


@router.patch("/{user_id}/reactivate")
def reactivate_user(
    user_id: str,
    user=Depends(require_permission("users.manage")),
    db=Depends(get_db),
):
    try:
        updated = UserService(db).reactivate_user(
            user_id,
            actor_user_id=user.get("id"),
            actor_is_dev=bool(user.get("is_dev")),
        )
    except ValueError as exc:
        raise bad_request("USER_REACTIVATE_FAILED", str(exc))

    return {
        "ok": True,
        "item": _user_item(updated),
    }


@router.post("/{user_id}/avatar")
async def upload_user_avatar(
    user_id: str,
    avatar: UploadFile = File(...),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    _ensure_user_avatar_permission(user, user_id)
    suffix = Path(avatar.filename or "").suffix.lower()
    output_path = settings.base_dir / "data" / "uploads" / "users" / f"{user_id}{suffix}"
    try:
        await save_upload_to_path(avatar, output_path, IMAGE_UPLOAD_POLICY)
        updated = UserService(db).update_avatar(
            user_id,
            output_path.relative_to(settings.base_dir).as_posix(),
            actor_user_id=user.get("id"),
            actor_is_dev=bool(user.get("is_dev")),
        )
    except UploadValidationError as exc:
        raise bad_request(exc.code, exc.message) from exc
    except ValueError as exc:
        raise bad_request("USER_AVATAR_UPLOAD_FAILED", str(exc)) from exc

    return {"ok": True, "item": _user_item(updated)}


@router.get("/{user_id}/avatar")
def get_user_avatar(
    user_id: str,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    _ensure_user_avatar_permission(user, user_id)
    target = UserService(db).get_user(user_id)
    if not target or not target.avatar_path:
        raise bad_request("USER_AVATAR_NOT_FOUND", "Foto do usuario nao encontrada.")

    avatar_path = (settings.base_dir / target.avatar_path).resolve()
    uploads_root = (settings.base_dir / "data" / "uploads").resolve()
    if uploads_root not in avatar_path.parents or not avatar_path.exists():
        raise bad_request("USER_AVATAR_NOT_FOUND", "Foto do usuario nao encontrada.")
    return FileResponse(avatar_path)


def _ensure_user_avatar_permission(user: dict, user_id: str) -> None:
    permissions = set(user.get("permissions") or [])
    if user.get("id") == user_id or user.get("is_dev") or "users.manage" in permissions:
        return
    raise auth_http_exception(403, "AUTH_FORBIDDEN", "Sem permissao.")

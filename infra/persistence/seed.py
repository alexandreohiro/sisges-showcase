from __future__ import annotations

import os
from collections.abc import Iterable

from sqlalchemy.orm import Session

from infra.persistence.db import Base, SessionLocal, engine
from infra.persistence.models import (
    FeatureFlagModel,
    PermissionModel,
    RoleModel,
    UserModel,
)
from infra.security.passwords import hash_password
from modules.acessos.application.credential_vault import record_user_snapshot_if_changed


BASE_PERMISSIONS = [
    "dashboard.view",
    "dashboard.pending.view",
    "dashboard.metrics.view",
    "documents.view",
    "documents.download",
    "compilador.run",
    "compilador.resolve_pending",
    "compilador.generate_odt",
    "compilador.memory.view",
    "compilador.memory.upload",
    "compilador.memory.download",
    "compilador.memory.delete",
    "compilador.reprocess",
    "users.manage",
    "permissions.manage",
    "dev_mode.access",
    "ops_center.view",
    "ops_center.rebuild",
    "ops_center.resolve",
    "militar_360.view",
    "consistencia.view",
    "consistencia.reprocess",
    "acoes_sugeridas.execute",
]

OPS_PERMISSIONS = [
    "mod.gestao_pessoal.view",
    "mod.gestao_pessoal.create",
    "mod.gestao_pessoal.edit",
    "mod.gestao_pessoal.delete",
    "mod.tarefas.view",
    "mod.tarefas.create",
    "mod.tarefas.edit",
    "mod.tarefas.assign",
    "mod.tarefas.close",
    "mod.missoes.view",
    "mod.missoes.create",
    "mod.missoes.edit",
    "mod.folhas.view",
    "mod.folhas.create",
    "mod.folhas.edit",
    "mod.folhas.compile",
    "mod.folhas.review",
    "mod.folhas.finalize",
    "mod.ctsm.view",
    "mod.ctsm.create",
    "mod.ctsm.emit",
    "mod.ctsm.review",
    "mod.calculo.view",
    "mod.calculo.run",
    "mod.calculo.review",
    "mod.quadro.view",
    "mod.quadro.edit",
    "mod.legislacoes.view",
    "mod.legislacoes.create",
    "mod.legislacoes.edit",
]

BASE_FLAGS = [
    ("nav.compilador", True, False),
    ("nav.gestao_pessoal", True, False),
    ("nav.declaracoes", True, False),
    ("nav.documentos", True, False),
    ("nav.historico", True, False),
    ("nav.quadro", True, False),
    ("page.configuracoes.acessos", True, False),
    ("page.configuracoes.modo_dev", True, True),
    ("widget.home.pending", True, False),
    ("widget.home.metrics", True, False),
    ("widget.home.recent_docs", True, False),
]

OPS_FLAGS = [
    ("nav.tarefas", True, False),
    ("nav.missoes", True, False),
    ("nav.folhas", True, False),
    ("nav.ctsm", True, False),
    ("nav.calculo", True, False),
    ("nav.legislacoes", True, False),
    ("widget.home.tasks", True, False),
    ("widget.home.notifications", True, False),
]

ROLE_DEFINITIONS: dict[str, list[str]] = {
    "dev": BASE_PERMISSIONS + OPS_PERMISSIONS,
    "admin": [
        "dashboard.view",
        "dashboard.pending.view",
        "dashboard.metrics.view",
        "documents.view",
        "documents.download",
        "compilador.run",
        "compilador.resolve_pending",
        "compilador.generate_odt",
        "compilador.memory.view",
        "compilador.memory.upload",
        "compilador.memory.download",
        "compilador.memory.delete",
        "compilador.reprocess",
        "users.manage",
        "permissions.manage",
        "mod.gestao_pessoal.view",
        "mod.gestao_pessoal.create",
        "mod.gestao_pessoal.edit",
        "mod.gestao_pessoal.delete",
        "mod.tarefas.view",
        "mod.tarefas.create",
        "mod.tarefas.edit",
        "mod.tarefas.assign",
        "mod.tarefas.close",
        "mod.missoes.view",
        "mod.folhas.view",
        "mod.folhas.create",
        "mod.folhas.edit",
        "mod.folhas.review",
        "mod.ctsm.view",
        "mod.ctsm.create",
        "mod.ctsm.emit",
        "mod.calculo.view",
        "mod.quadro.view",
        "mod.quadro.edit",
        "ops_center.view",
        "ops_center.rebuild",
        "ops_center.resolve",
        "militar_360.view",
        "consistencia.view",
        "consistencia.reprocess",
        "acoes_sugeridas.execute",
    ],
    "operador": [
        "dashboard.view",
        "dashboard.pending.view",
        "documents.view",
        "compilador.run",
        "compilador.resolve_pending",
        "compilador.generate_odt",
        "compilador.memory.view",
        "compilador.memory.upload",
        "compilador.memory.download",
        "compilador.reprocess",
        "mod.gestao_pessoal.view",
        "mod.tarefas.view",
        "mod.tarefas.create",
        "mod.tarefas.edit",
        "mod.tarefas.assign",
        "mod.tarefas.close",
        "mod.folhas.view",
        "mod.folhas.create",
        "mod.ctsm.view",
        "mod.ctsm.create",
        "mod.quadro.view",
        "mod.quadro.edit",
        "ops_center.view",
        "militar_360.view",
        "consistencia.view",
        "acoes_sugeridas.execute",
    ],
    "consulta": [
        "dashboard.view",
        "documents.view",
        "mod.gestao_pessoal.view",
        "mod.tarefas.view",
        "mod.folhas.view",
        "mod.legislacoes.view",
        "mod.quadro.view",
        "ops_center.view",
        "militar_360.view",
        "consistencia.view",
    ],
}


def _split_csv(value: str | None, *, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _ensure_permissions(db: Session, keys: Iterable[str]) -> dict[str, PermissionModel]:
    permissions: dict[str, PermissionModel] = {}
    for key in keys:
        permission = db.query(PermissionModel).filter(PermissionModel.key == key).first()
        if not permission:
            permission = PermissionModel(id=key, key=key)
            db.add(permission)
        permissions[key] = permission
    db.flush()
    return permissions


def _ensure_roles(
    db: Session,
    permission_models: dict[str, PermissionModel],
) -> dict[str, RoleModel]:
    roles: dict[str, RoleModel] = {}
    for role_name, permission_keys in ROLE_DEFINITIONS.items():
        role = db.query(RoleModel).filter(RoleModel.name == role_name).first()
        if not role:
            role = RoleModel(id=role_name, name=role_name)
            db.add(role)
        role.permissions = [permission_models[key] for key in permission_keys]
        roles[role_name] = role
    db.flush()
    return roles


def _ensure_feature_flags(db: Session) -> None:
    for key, enabled, dev_only in BASE_FLAGS + OPS_FLAGS:
        flag = db.query(FeatureFlagModel).filter(FeatureFlagModel.key == key).first()
        if not flag:
            db.add(
                FeatureFlagModel(
                    key=key,
                    enabled=enabled,
                    dev_only=dev_only,
                )
            )


def _ensure_bootstrap_admin(db: Session, roles: dict[str, RoleModel]) -> UserModel | None:
    username = os.getenv("SISGES_BOOTSTRAP_ADMIN_USERNAME")
    password = os.getenv("SISGES_BOOTSTRAP_ADMIN_PASSWORD")

    if not username and not password:
        return None
    if not username or not password:
        raise RuntimeError(
            "SISGES_BOOTSTRAP_ADMIN_USERNAME e SISGES_BOOTSTRAP_ADMIN_PASSWORD "
            "devem ser informados juntos."
        )
    if len(password) < 12:
        raise RuntimeError("SISGES_BOOTSTRAP_ADMIN_PASSWORD deve ter pelo menos 12 caracteres.")

    role_names = _split_csv(os.getenv("SISGES_BOOTSTRAP_ADMIN_ROLES"), default=["admin"])
    missing_roles = [role_name for role_name in role_names if role_name not in roles]
    if missing_roles:
        raise RuntimeError(f"Papeis inexistentes para bootstrap admin: {', '.join(missing_roles)}")

    user = db.query(UserModel).filter(UserModel.username == username).first()
    if not user:
        user = UserModel(
            id=f"bootstrap-{username}",
            username=username,
            display_name=os.getenv("SISGES_BOOTSTRAP_ADMIN_DISPLAY_NAME", username),
            email=os.getenv("SISGES_BOOTSTRAP_ADMIN_EMAIL", f"{username}@sisges.local"),
            password_hash=hash_password(password),
            is_active=True,
            is_dev=os.getenv("SISGES_BOOTSTRAP_ADMIN_IS_DEV", "").lower()
            in {"1", "true", "yes", "sim"},
            roles=[roles[role_name] for role_name in role_names],
        )
        db.add(user)
    else:
        user.display_name = os.getenv("SISGES_BOOTSTRAP_ADMIN_DISPLAY_NAME", user.display_name)
        user.email = os.getenv("SISGES_BOOTSTRAP_ADMIN_EMAIL", user.email)
        user.password_hash = hash_password(password)
        user.is_active = True
        user.roles = [roles[role_name] for role_name in role_names]
    return user


def seed(*, db: Session | None = None, create_schema: bool = False) -> None:
    if create_schema:
        Base.metadata.create_all(bind=engine)

    owns_session = db is None
    session = db or SessionLocal()
    try:
        all_permission_keys = sorted(set(BASE_PERMISSIONS + OPS_PERMISSIONS))
        permissions = _ensure_permissions(session, all_permission_keys)
        roles = _ensure_roles(session, permissions)
        _ensure_feature_flags(session)
        _ensure_bootstrap_admin(session, roles)
        for user in session.query(UserModel).all():
            record_user_snapshot_if_changed(session, user)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


if __name__ == "__main__":
    seed(create_schema=os.getenv("SISGES_SEED_CREATE_SCHEMA", "").lower() in {"1", "true", "yes"})

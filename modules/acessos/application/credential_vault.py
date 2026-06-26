from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet

from infra.config import settings
from infra.persistence.models import CredentialAuditModel, UserModel

CRYPTO_VERSION = "fernet-sha256-secret-v2"


def _fernet() -> Fernet:
    material = f"{settings.vault_key}:sisges-credential-vault:v2".encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)


def _json_default(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def encrypt_payload(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=_json_default).encode("utf-8")
    return _fernet().encrypt(data).decode("utf-8")


def decrypt_payload(encrypted_payload: str) -> dict[str, Any]:
    data = _fernet().decrypt(encrypted_payload.encode("utf-8"))
    return json.loads(data.decode("utf-8"))


def payload_sha256(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=_json_default).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def password_hash_fingerprint(password_hash: str | None) -> str | None:
    if not password_hash:
        return None
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()


def user_snapshot(user: UserModel, *, include_password_fingerprint: bool = True) -> dict[str, Any]:
    snapshot = {
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
        "roles": sorted(role.name for role in user.roles),
    }
    if include_password_fingerprint:
        snapshot["password_hash_sha256"] = password_hash_fingerprint(user.password_hash)
    return snapshot


def record_credential_event(
    db,
    *,
    user_id: str | None,
    event_type: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> CredentialAuditModel:
    audit = CredentialAuditModel(
        user_id=user_id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        encrypted_payload=encrypt_payload(payload),
        payload_sha256=payload_sha256(payload),
        crypto_version=CRYPTO_VERSION,
    )
    db.add(audit)
    db.flush()
    return audit


def record_user_snapshot_if_changed(
    db,
    user: UserModel,
    *,
    event_type: str = "USER_CREDENTIAL_SNAPSHOT",
    actor_user_id: str | None = None,
) -> CredentialAuditModel | None:
    payload = user_snapshot(user)
    digest = payload_sha256(payload)
    latest = (
        db.query(CredentialAuditModel)
        .filter(
            CredentialAuditModel.user_id == user.id,
            CredentialAuditModel.event_type == event_type,
        )
        .order_by(CredentialAuditModel.id.desc())
        .first()
    )
    if latest and latest.payload_sha256 == digest:
        return None
    return record_credential_event(
        db,
        user_id=user.id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        payload=payload,
    )

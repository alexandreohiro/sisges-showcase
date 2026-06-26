from __future__ import annotations

from infra.persistence.models import UserModel
from infra.persistence.repositories.users_repo import UsersRepository
from infra.persistence.transactions import atomic
from infra.security.passwords import verify_password
from infra.security.tokens import SessionTokenError, create_session_token, read_session_token
from modules.acessos.application.credential_vault import record_credential_event


class AuthError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AuthService:
    def __init__(self, db):
        self.users_repo = UsersRepository(db)
        self.db = db

    def _public_user_payload(self, user: UserModel) -> dict:
        permissions = sorted(
            {
                perm.key
                for role in user.roles
                for perm in role.permissions
            }
        )

        return {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "roles": [role.name for role in user.roles],
            "permissions": permissions,
            "is_dev": user.is_dev,
            "avatar_path": user.avatar_path,
            "identidade": user.identidade,
            "posto_graduacao": user.posto_graduacao,
            "nome_guerra": user.nome_guerra,
            "telefone": user.telefone,
            "contato": user.contato,
            "divisao": user.divisao,
            "secao": user.secao,
        }

    def login(self, username: str, password: str):
        user = self.users_repo.get_by_username(username)
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            with atomic(self.db):
                record_credential_event(
                    self.db,
                    user_id=user.id if user else None,
                    event_type="LOGIN_FAILED",
                    payload={
                        "username": username,
                        "user_known": bool(user),
                        "user_active": bool(user and user.is_active),
                        "reason": "AUTH_INVALID_CREDENTIALS",
                    },
                )
            raise AuthError("AUTH_INVALID_CREDENTIALS", "Credenciais invalidas.")

        payload = self._public_user_payload(user)
        token = create_session_token(
            {
                "sub": user.id,
                "username": user.username,
                "token_type": "session",
            }
        )
        with atomic(self.db):
            record_credential_event(
                self.db,
                user_id=user.id,
                event_type="LOGIN_SUCCESS",
                payload={"username": user.username, "user_id": user.id},
            )
        return token, payload

    def me_from_token(self, token: str):
        try:
            payload = read_session_token(token)
        except SessionTokenError as exc:
            raise AuthError("AUTH_INVALID_SESSION", exc.args[0] or "Sessao invalida.") from exc

        if payload.get("token_type") != "session" or not payload.get("sub"):
            raise AuthError("AUTH_INVALID_SESSION", "Sessao invalida.")

        user = self.users_repo.get_by_id(str(payload["sub"]))
        if not user or not user.is_active:
            raise AuthError("AUTH_INVALID_SESSION", "Sessao invalida.")

        return self._public_user_payload(user)

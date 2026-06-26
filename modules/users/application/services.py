from uuid import uuid4

from infra.persistence.models import UserModel
from infra.persistence.repositories.roles_repo import RolesRepository
from infra.persistence.repositories.users_repo import UsersRepository
from infra.persistence.transactions import atomic
from infra.security.passwords import hash_password
from modules.acessos.application.credential_vault import record_credential_event, user_snapshot

DEV_MODE_PERMISSION = "dev_mode.access"
DEV_ROLE_NAMES = {"dev", "desenvolvedor"}


def _clean_profile_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _role_is_dev_mode(role) -> bool:
    role_name = str(role.name or "").strip().lower()
    if role_name in DEV_ROLE_NAMES:
        return True
    return any(permission.key == DEV_MODE_PERMISSION for permission in role.permissions)


class UserService:
    def __init__(self, db):
        self.users_repo = UsersRepository(db)
        self.roles_repo = RolesRepository(db)
        self.db = db

    def _role_names_include_dev_mode(self, role_names: list[str]) -> bool:
        for role_name in role_names:
            role = self.roles_repo.get_role_by_name(role_name)
            if not role:
                raise ValueError(f"Papel inexistente: {role_name}")
            if _role_is_dev_mode(role):
                return True
        return False

    def _user_has_dev_surface(self, user: UserModel) -> bool:
        return bool(user.is_dev) or any(_role_is_dev_mode(role) for role in user.roles)

    @staticmethod
    def _ensure_actor_can_manage_dev_surface(actor_is_dev: bool, *, message: str) -> None:
        if not actor_is_dev:
            raise ValueError(message)

    def list_users(self):
        return self.users_repo.list_all()

    def get_user(self, user_id: str):
        return self.users_repo.get_by_id(user_id)

    def create_user(
        self,
        username,
        display_name,
        email,
        password,
        role_names,
        is_dev=False,
        identidade: str | None = None,
        posto_graduacao: str | None = None,
        nome_guerra: str | None = None,
        telefone: str | None = None,
        contato: str | None = None,
        divisao: str | None = None,
        secao: str | None = None,
        actor_user_id: str | None = None,
        actor_is_dev: bool = False,
    ):
        if self.users_repo.get_by_username(username):
            raise ValueError("Usuario ja existe.")

        if is_dev or self._role_names_include_dev_mode(role_names):
            self._ensure_actor_can_manage_dev_surface(
                actor_is_dev,
                message="Apenas usuario em modo dev pode criar acesso dev.",
            )

        roles = []
        for role_name in role_names:
            role = self.roles_repo.get_role_by_name(role_name)
            if not role:
                raise ValueError(f"Papel inexistente: {role_name}")
            roles.append(role)

        user = UserModel(
            id=str(uuid4()),
            username=username,
            display_name=display_name,
            email=email,
            password_hash=hash_password(password),
            is_active=True,
            is_dev=is_dev,
            identidade=_clean_profile_value(identidade),
            posto_graduacao=_clean_profile_value(posto_graduacao),
            nome_guerra=_clean_profile_value(nome_guerra),
            telefone=_clean_profile_value(telefone),
            contato=_clean_profile_value(contato),
            divisao=_clean_profile_value(divisao),
            secao=_clean_profile_value(secao),
            roles=roles,
        )
        with atomic(self.db):
            created = self.users_repo.save(user)
            record_credential_event(
                self.db,
                user_id=created.id,
                actor_user_id=actor_user_id,
                event_type="USER_CREATED",
                payload=user_snapshot(created),
            )
            return created

    def update_user(
        self,
        user_id: str,
        display_name: str | None = None,
        email: str | None = None,
        is_active: bool | None = None,
        role_names: list[str] | None = None,
        is_dev: bool | None = None,
        identidade: str | None = None,
        posto_graduacao: str | None = None,
        nome_guerra: str | None = None,
        telefone: str | None = None,
        contato: str | None = None,
        divisao: str | None = None,
        secao: str | None = None,
        actor_user_id: str | None = None,
        actor_is_dev: bool = False,
    ):
        user = self.users_repo.get_by_id(user_id)
        if not user:
            raise ValueError("Usuario nao encontrado.")

        if not actor_is_dev:
            if self._user_has_dev_surface(user):
                raise ValueError("Apenas usuario em modo dev pode alterar acesso dev.")
            if is_dev is not None:
                raise ValueError("Apenas usuario em modo dev pode alterar modo dev.")
            if role_names is not None and self._role_names_include_dev_mode(role_names):
                raise ValueError("Apenas usuario em modo dev pode atribuir papel dev.")

        if display_name is not None:
            user.display_name = display_name

        if email is not None:
            user.email = email

        if is_active is not None:
            user.is_active = is_active

        if is_dev is not None:
            user.is_dev = is_dev

        profile_updates = {
            "identidade": identidade,
            "posto_graduacao": posto_graduacao,
            "nome_guerra": nome_guerra,
            "telefone": telefone,
            "contato": contato,
            "divisao": divisao,
            "secao": secao,
        }
        for field, value in profile_updates.items():
            if value is not None:
                setattr(user, field, _clean_profile_value(value))

        if role_names is not None:
            roles = []
            for role_name in role_names:
                role = self.roles_repo.get_role_by_name(role_name)
                if not role:
                    raise ValueError(f"Papel inexistente: {role_name}")
                roles.append(role)
            user.roles = roles

        with atomic(self.db):
            self.db.add(user)
            self.db.flush()
            self.db.refresh(user)
            record_credential_event(
                self.db,
                user_id=user.id,
                actor_user_id=actor_user_id,
                event_type="USER_UPDATED",
                payload=user_snapshot(user),
            )
        return user

    def deactivate_user(
        self,
        user_id: str,
        *,
        actor_user_id: str | None = None,
        actor_is_dev: bool = False,
    ):
        user = self.users_repo.get_by_id(user_id)
        if not user:
            raise ValueError("Usuario nao encontrado.")
        if actor_user_id and user.id == actor_user_id:
            raise ValueError("Nao e permitido inativar o proprio usuario logado.")
        if self._user_has_dev_surface(user):
            self._ensure_actor_can_manage_dev_surface(
                actor_is_dev,
                message="Apenas usuario em modo dev pode inativar acesso dev.",
            )

        user.is_active = False
        with atomic(self.db):
            self.db.add(user)
            self.db.flush()
            self.db.refresh(user)
            record_credential_event(
                self.db,
                user_id=user.id,
                actor_user_id=actor_user_id,
                event_type="USER_DEACTIVATED",
                payload=user_snapshot(user),
            )
        return user

    def reactivate_user(
        self,
        user_id: str,
        *,
        actor_user_id: str | None = None,
        actor_is_dev: bool = False,
    ):
        user = self.users_repo.get_by_id(user_id)
        if not user:
            raise ValueError("Usuario nao encontrado.")
        if self._user_has_dev_surface(user):
            self._ensure_actor_can_manage_dev_surface(
                actor_is_dev,
                message="Apenas usuario em modo dev pode reativar acesso dev.",
            )

        user.is_active = True
        with atomic(self.db):
            self.db.add(user)
            self.db.flush()
            self.db.refresh(user)
            record_credential_event(
                self.db,
                user_id=user.id,
                actor_user_id=actor_user_id,
                event_type="USER_REACTIVATED",
                payload=user_snapshot(user),
            )
        return user

    def update_avatar(
        self,
        user_id: str,
        avatar_path: str,
        *,
        actor_user_id: str | None = None,
        actor_is_dev: bool = False,
    ):
        user = self.users_repo.get_by_id(user_id)
        if not user:
            raise ValueError("Usuario nao encontrado.")
        if self._user_has_dev_surface(user):
            self._ensure_actor_can_manage_dev_surface(
                actor_is_dev,
                message="Apenas usuario em modo dev pode alterar perfil dev.",
            )

        user.avatar_path = avatar_path
        with atomic(self.db):
            self.db.add(user)
            self.db.flush()
            self.db.refresh(user)
            record_credential_event(
                self.db,
                user_id=user.id,
                actor_user_id=actor_user_id,
                event_type="USER_AVATAR_UPDATED",
                payload=user_snapshot(user),
            )
        return user

    def reset_password(
        self,
        user_id: str,
        new_password: str,
        *,
        actor_user_id: str | None = None,
        actor_is_dev: bool = False,
    ):
        user = self.users_repo.get_by_id(user_id)
        if not user:
            raise ValueError("Usuario nao encontrado.")
        if self._user_has_dev_surface(user):
            self._ensure_actor_can_manage_dev_surface(
                actor_is_dev,
                message="Apenas usuario em modo dev pode redefinir senha de acesso dev.",
            )

        user.password_hash = hash_password(new_password)
        with atomic(self.db):
            self.db.add(user)
            self.db.flush()
            self.db.refresh(user)
            record_credential_event(
                self.db,
                user_id=user.id,
                actor_user_id=actor_user_id,
                event_type="PASSWORD_CHANGED",
                payload=user_snapshot(user),
            )
        return user

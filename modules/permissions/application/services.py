from infra.persistence.models import FeatureFlagModel
from infra.persistence.repositories.roles_repo import RolesRepository
from infra.persistence.transactions import atomic


class PermissionService:
    def __init__(self, db):
        self.roles_repo = RolesRepository(db)
        self.db = db

    def list_roles(self):
        return self.roles_repo.list_roles()

    def list_flags(self):
        return self.roles_repo.list_flags()

    def get_flag(self, key: str):
        return self.roles_repo.get_flag_by_key(key)

    def update_flag(self, key: str, enabled: bool, dev_only: bool | None = None):
        flag = self.roles_repo.get_flag_by_key(key)
        if not flag:
            flag = FeatureFlagModel(
                key=key,
                enabled=enabled,
                dev_only=bool(dev_only),
            )
            self.db.add(flag)
        else:
            flag.enabled = enabled
            if dev_only is not None:
                flag.dev_only = dev_only

        with atomic(self.db):
            self.db.add(flag)
            self.db.flush()
            self.db.refresh(flag)
        return flag

    def list_visible_flags_for_user(self, is_dev: bool):
        flags = self.roles_repo.list_flags()
        visible = []

        for flag in flags:
            if flag.dev_only and not is_dev:
                continue
            visible.append(flag)

        return visible

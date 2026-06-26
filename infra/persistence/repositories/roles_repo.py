from sqlalchemy.orm import Session
from infra.persistence.models import RoleModel, PermissionModel, FeatureFlagModel


class RolesRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_roles(self):
        return self.db.query(RoleModel).order_by(RoleModel.name.asc()).all()

    def get_role_by_name(self, name: str):
        return self.db.query(RoleModel).filter(RoleModel.name == name).first()

    def list_permissions(self):
        return self.db.query(PermissionModel).order_by(PermissionModel.key.asc()).all()

    def list_flags(self):
        return self.db.query(FeatureFlagModel).order_by(FeatureFlagModel.key.asc()).all()

    def get_flag_by_key(self, key: str):
        return self.db.query(FeatureFlagModel).filter(FeatureFlagModel.key == key).first()
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import infra.persistence.models  # noqa: F401
from infra.persistence.db import Base
from infra.persistence.models import FeatureFlagModel, PermissionModel, RoleModel, UserModel
from infra.persistence.seed import seed


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_seed_creates_roles_permissions_and_flags_without_default_user(monkeypatch):
    monkeypatch.delenv("SISGES_BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("SISGES_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    db = _session()

    seed(db=db)

    assert db.query(PermissionModel).count() > 0
    assert db.query(RoleModel).filter(RoleModel.name == "admin").first() is not None
    assert db.query(FeatureFlagModel).count() > 0
    assert db.query(UserModel).count() == 0


def test_seed_rejects_weak_bootstrap_password(monkeypatch):
    monkeypatch.setenv("SISGES_BOOTSTRAP_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("SISGES_BOOTSTRAP_ADMIN_PASSWORD", "123456")
    db = _session()

    with pytest.raises(RuntimeError, match="pelo menos 12"):
        seed(db=db)


def test_seed_creates_bootstrap_admin_with_explicit_strong_password(monkeypatch):
    monkeypatch.setenv("SISGES_BOOTSTRAP_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("SISGES_BOOTSTRAP_ADMIN_PASSWORD", "senha-forte-123")
    monkeypatch.setenv("SISGES_BOOTSTRAP_ADMIN_EMAIL", "admin@sisges.local")
    db = _session()

    seed(db=db)

    user = db.query(UserModel).filter(UserModel.username == "admin").one()
    assert user.email == "admin@sisges.local"
    assert [role.name for role in user.roles] == ["admin"]

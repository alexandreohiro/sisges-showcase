from infra.persistence.db import Base, engine, SessionLocal
from infra.persistence.models import PermissionModel, FeatureFlagModel

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
    "mod.legislacoes.view",
    "mod.legislacoes.create",
    "mod.legislacoes.edit",
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


def ensure_permissions(db):
    for key in OPS_PERMISSIONS:
        exists = db.query(PermissionModel).filter(PermissionModel.key == key).first()
        if not exists:
            db.add(PermissionModel(id=key, key=key))


def ensure_feature_flags(db):
    for key, enabled, dev_only in OPS_FLAGS:
        exists = db.query(FeatureFlagModel).filter(FeatureFlagModel.key == key).first()
        if not exists:
            db.add(
                FeatureFlagModel(
                    key=key,
                    enabled=enabled,
                    dev_only=dev_only,
                )
            )


def main():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        ensure_permissions(db)
        ensure_feature_flags(db)
        db.commit()
        print("OPS.1A aplicada com sucesso.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
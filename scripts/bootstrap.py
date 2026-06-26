from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config

from infra.config import settings
from infra.logging.setup import configure_logging
from infra.persistence.seed import seed
from infra.pipeline.cleanup import cleanup_old_workspaces


logger = logging.getLogger("sisges.bootstrap")


def main() -> None:
    configure_logging()
    logger.info("Starting SISGES bootstrap", extra={"environment": settings.environment})

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    logger.info("Database migrations applied")

    seed(create_schema=False)
    logger.info("Seed applied")

    cleanup = cleanup_old_workspaces(
        retention_hours=settings.workspace_retention_hours,
        dry_run=False,
    )
    logger.info(
        "Workspace cleanup completed",
        extra={
            "removed_count": len(cleanup.removed),
            "skipped_count": len(cleanup.skipped),
            "retention_hours": cleanup.retention_hours,
        },
    )


if __name__ == "__main__":
    main()

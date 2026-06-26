from __future__ import annotations

import argparse
import json

from infra.config import settings
from infra.pipeline.cleanup import cleanup_old_workspaces


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove workspaces antigos do compilador.")
    parser.add_argument(
        "--retention-hours",
        type=int,
        default=settings.workspace_retention_hours,
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = cleanup_old_workspaces(
        retention_hours=args.retention_hours,
        dry_run=args.dry_run,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

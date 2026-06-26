from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil


@dataclass(frozen=True)
class CleanupResult:
    base_dir: str
    retention_hours: int
    removed: list[str]
    skipped: list[str]


def cleanup_old_workspaces(
    *,
    base_dir: str | Path = "data/temp/compilador",
    retention_hours: int = 24,
    dry_run: bool = False,
) -> CleanupResult:
    root = Path(base_dir)
    if not root.exists():
        return CleanupResult(
            base_dir=str(root),
            retention_hours=retention_hours,
            removed=[],
            skipped=[],
        )

    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    removed: list[str] = []
    skipped: list[str] = []

    for item in root.iterdir():
        if not item.is_dir():
            skipped.append(str(item))
            continue

        modified_at = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
        if modified_at > cutoff:
            skipped.append(str(item))
            continue

        removed.append(str(item))
        if not dry_run:
            shutil.rmtree(item)

    return CleanupResult(
        base_dir=str(root),
        retention_hours=retention_hours,
        removed=removed,
        skipped=skipped,
    )

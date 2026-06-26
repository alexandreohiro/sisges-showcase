from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

from infra.pipeline.cleanup import cleanup_old_workspaces


def test_cleanup_old_workspaces_removes_only_expired_directories(tmp_path: Path) -> None:
    old_dir = tmp_path / "old"
    fresh_dir = tmp_path / "fresh"
    old_dir.mkdir()
    fresh_dir.mkdir()

    old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
    os.utime(old_dir, (old_time, old_time))

    result = cleanup_old_workspaces(
        base_dir=tmp_path,
        retention_hours=24,
    )

    assert str(old_dir) in result.removed
    assert not old_dir.exists()
    assert fresh_dir.exists()
    assert str(fresh_dir) in result.skipped


def test_cleanup_old_workspaces_dry_run_keeps_files(tmp_path: Path) -> None:
    old_dir = tmp_path / "old"
    old_dir.mkdir()
    old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
    os.utime(old_dir, (old_time, old_time))

    result = cleanup_old_workspaces(
        base_dir=tmp_path,
        retention_hours=24,
        dry_run=True,
    )

    assert str(old_dir) in result.removed
    assert old_dir.exists()

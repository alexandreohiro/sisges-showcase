from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4


@dataclass(frozen=True)
class PipelineWorkspace:
    trace_id: str
    root: Path
    input_dir: Path
    output_dir: Path


class PipelineWorkspaceManager:
    def __init__(self, base_dir: str | Path = "data/temp/compilador") -> None:
        self.base_dir = Path(base_dir)
        self._tmp: TemporaryDirectory[str] | None = None

    def __enter__(self) -> PipelineWorkspace:
        trace_id = str(uuid4())
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._tmp = TemporaryDirectory(prefix=f"{trace_id}-", dir=self.base_dir)
        root = Path(self._tmp.name)
        input_dir = root / "input"
        output_dir = root / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        return PipelineWorkspace(
            trace_id=trace_id,
            root=root,
            input_dir=input_dir,
            output_dir=output_dir,
        )

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()

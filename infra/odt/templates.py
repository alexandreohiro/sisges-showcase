from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import zipfile

from shared.utils.hashing import sha256_file


@dataclass(frozen=True)
class TemplateVersion:
    original_filename: str
    storage_path: Path
    sha256: str
    version: str


class TemplateValidationError(ValueError):
    pass


class OdtTemplateRegistry:
    def __init__(self, storage_dir: str | Path = "data/templates/odt") -> None:
        self.storage_dir = Path(storage_dir)

    def register_uploaded_template(self, source_path: str | Path, original_filename: str) -> TemplateVersion:
        source_path = Path(source_path)
        self._validate_odt(source_path)

        digest = sha256_file(source_path)
        version = digest[:12]
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        destination = self.storage_dir / f"{version}.odt"
        if not destination.exists():
            shutil.copy2(source_path, destination)

        return TemplateVersion(
            original_filename=original_filename,
            storage_path=destination,
            sha256=digest,
            version=version,
        )

    @staticmethod
    def _validate_odt(path: Path) -> None:
        if not zipfile.is_zipfile(path):
            raise TemplateValidationError("Template ODT nao e um arquivo ZIP valido.")
        with zipfile.ZipFile(path, "r") as archive:
            names = set(archive.namelist())
            if "content.xml" not in names:
                raise TemplateValidationError("Template ODT nao possui content.xml.")

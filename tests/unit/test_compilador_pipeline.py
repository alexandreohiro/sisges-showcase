from __future__ import annotations

from pathlib import Path
from io import BytesIO
from zipfile import ZipFile

import pytest
from starlette.datastructures import Headers, UploadFile

from infra.odt.templates import OdtTemplateRegistry, TemplateValidationError
from infra.pipeline.uploads import (
    ODT_UPLOAD_POLICY,
    PDF_UPLOAD_POLICY,
    UploadValidationError,
    validate_upload_metadata,
)
from infra.pipeline.workspace import PipelineWorkspaceManager
from shared.utils.hashing import sha256_file


def test_validate_upload_metadata_rejects_wrong_extension() -> None:
    upload = UploadFile(
        filename="entrada.txt",
        file=BytesIO(b""),
        headers=Headers({"content-type": "application/pdf"}),
    )

    with pytest.raises(UploadValidationError) as exc:
        validate_upload_metadata(upload, PDF_UPLOAD_POLICY)

    assert exc.value.code == "UPLOAD_EXTENSION_INVALIDA"


def test_validate_upload_metadata_rejects_wrong_mime() -> None:
    upload = UploadFile(
        filename="template.odt",
        file=BytesIO(b""),
        headers=Headers({"content-type": "text/plain"}),
    )

    with pytest.raises(UploadValidationError) as exc:
        validate_upload_metadata(upload, ODT_UPLOAD_POLICY)

    assert exc.value.code == "UPLOAD_MIME_INVALIDO"


def test_workspace_manager_removes_execution_directory(tmp_path: Path) -> None:
    with PipelineWorkspaceManager(base_dir=tmp_path) as workspace:
        root = workspace.root
        (workspace.input_dir / "entrada.pdf").write_bytes(b"%PDF-1.4")
        assert root.exists()

    assert not root.exists()


def test_template_registry_versions_by_hash(tmp_path: Path) -> None:
    template = tmp_path / "template.odt"
    with ZipFile(template, "w") as archive:
        archive.writestr("content.xml", "<office:text>[NOME]</office:text>")

    registry = OdtTemplateRegistry(storage_dir=tmp_path / "registry")
    version = registry.register_uploaded_template(template, "template.odt")

    assert version.sha256 == sha256_file(template)
    assert version.version == version.sha256[:12]
    assert version.storage_path.exists()


def test_template_registry_rejects_invalid_odt(tmp_path: Path) -> None:
    invalid = tmp_path / "template.odt"
    invalid.write_bytes(b"not a zip")

    registry = OdtTemplateRegistry(storage_dir=tmp_path / "registry")
    with pytest.raises(TemplateValidationError):
        registry.register_uploaded_template(invalid, "template.odt")

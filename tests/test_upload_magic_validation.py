from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from starlette.datastructures import Headers, UploadFile

from infra.pipeline.uploads import (
    ODT_UPLOAD_POLICY,
    PDF_UPLOAD_POLICY,
    ZIP_UPLOAD_POLICY,
    UploadValidationError,
    save_upload_to_path,
    validate_upload_magic,
)


SECURITY_LOGGER = "sisges.security"


def _upload(filename: str, payload: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(payload),
        headers=Headers({"content-type": content_type}),
    )


def _minimal_odt_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr("content.xml", "<office:document-content />")
        archive.writestr("styles.xml", "<office:document-styles />")
        archive.writestr("META-INF/manifest.xml", "<manifest:manifest />")
    return buffer.getvalue()


def _minimal_zip_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("arquivo.txt", "conteudo")
    return buffer.getvalue()


def test_pdf_magic_accepts_real_pdf_signature(tmp_path: Path) -> None:
    upload = _upload("ficha.pdf", b"%PDF-1.7\nconteudo", "application/pdf")

    saved = asyncio.run(save_upload_to_path(upload, tmp_path / "ficha.pdf", PDF_UPLOAD_POLICY))

    assert saved > 0


def test_pdf_magic_rejects_zip_disguised_as_pdf(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.WARNING, logger=SECURITY_LOGGER)
    upload = _upload("ficha.pdf", _minimal_zip_bytes(), "application/pdf")

    with pytest.raises(UploadValidationError) as exc:
        asyncio.run(save_upload_to_path(upload, tmp_path / "ficha.pdf", PDF_UPLOAD_POLICY))

    assert exc.value.code == "UPLOAD_MAGIC_INVALIDO"
    record = next(
        item for item in caplog.records if getattr(item, "event_type", None) == "UPLOAD_REJECTED"
    )
    assert record.security_event is True
    assert record.event_code == "UPLOAD_MAGIC_INVALIDO"
    assert record.upload_filename == "ficha.pdf"
    assert record.expected_magic == ["pdf"]


def test_odt_magic_accepts_valid_odt_zip(tmp_path: Path) -> None:
    upload = _upload(
        "modelo.odt",
        _minimal_odt_bytes(),
        "application/vnd.oasis.opendocument.text",
    )

    saved = asyncio.run(save_upload_to_path(upload, tmp_path / "modelo.odt", ODT_UPLOAD_POLICY))

    assert saved > 0


def test_odt_magic_rejects_plain_zip_disguised_as_odt(tmp_path: Path) -> None:
    upload = _upload(
        "modelo.odt",
        _minimal_zip_bytes(),
        "application/vnd.oasis.opendocument.text",
    )

    with pytest.raises(UploadValidationError) as exc:
        asyncio.run(save_upload_to_path(upload, tmp_path / "modelo.odt", ODT_UPLOAD_POLICY))

    assert exc.value.code == "UPLOAD_MAGIC_INVALIDO"


def test_zip_magic_accepts_valid_zip(tmp_path: Path) -> None:
    upload = _upload("lote.zip", _minimal_zip_bytes(), "application/zip")

    saved = asyncio.run(save_upload_to_path(upload, tmp_path / "lote.zip", ZIP_UPLOAD_POLICY))

    assert saved > 0


def test_magic_validation_resets_upload_pointer() -> None:
    upload = _upload("ficha.pdf", b"%PDF-1.7\nconteudo", "application/pdf")

    asyncio.run(validate_upload_magic(upload, PDF_UPLOAD_POLICY))

    assert upload.file.tell() == 0
    assert upload.file.read(5) == b"%PDF-"

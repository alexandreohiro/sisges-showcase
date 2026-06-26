from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import zipfile

from fastapi import UploadFile

from infra.logging.security import log_security_event


MAGIC_PDF = "pdf"
MAGIC_ODT = "odt"
MAGIC_ZIP = "zip"
MAGIC_IMAGE = "image"
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


@dataclass(frozen=True)
class UploadPolicy:
    allowed_extensions: frozenset[str]
    allowed_mime_types: frozenset[str]
    max_bytes: int
    magic_kinds: frozenset[str] = frozenset()


class UploadValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _upload_metadata(upload: UploadFile, policy: UploadPolicy) -> dict:
    filename = Path(upload.filename or "").name
    return {
        "upload_filename": filename or None,
        "extension": Path(filename).suffix.lower() or None,
        "content_type": (upload.content_type or "").lower() or None,
        "allowed_extensions": sorted(policy.allowed_extensions),
        "allowed_mime_types": sorted(policy.allowed_mime_types),
        "expected_magic": sorted(policy.magic_kinds),
        "max_bytes": policy.max_bytes,
    }


def _raise_upload_rejected(
    upload: UploadFile,
    policy: UploadPolicy,
    code: str,
    message: str,
    **metadata,
) -> None:
    log_security_event(
        event_type="UPLOAD_REJECTED",
        event_code=code,
        **_upload_metadata(upload, policy),
        **metadata,
    )
    raise UploadValidationError(code, message)


PDF_UPLOAD_POLICY = UploadPolicy(
    allowed_extensions=frozenset({".pdf"}),
    allowed_mime_types=frozenset({"application/pdf"}),
    max_bytes=25 * 1024 * 1024,
    magic_kinds=frozenset({MAGIC_PDF}),
)

ODT_UPLOAD_POLICY = UploadPolicy(
    allowed_extensions=frozenset({".odt"}),
    allowed_mime_types=frozenset(
        {
            "application/vnd.oasis.opendocument.text",
            "application/octet-stream",
        }
    ),
    max_bytes=10 * 1024 * 1024,
    magic_kinds=frozenset({MAGIC_ODT}),
)

ZIP_UPLOAD_POLICY = UploadPolicy(
    allowed_extensions=frozenset({".zip"}),
    allowed_mime_types=frozenset(
        {
            "application/zip",
            "application/x-zip-compressed",
            "application/octet-stream",
        }
    ),
    max_bytes=250 * 1024 * 1024,
    magic_kinds=frozenset({MAGIC_ZIP}),
)

TXT_UPLOAD_POLICY = UploadPolicy(
    allowed_extensions=frozenset({".txt"}),
    allowed_mime_types=frozenset(
        {
            "text/plain",
            "application/octet-stream",
        }
    ),
    max_bytes=25 * 1024 * 1024,
)

IMAGE_UPLOAD_POLICY = UploadPolicy(
    allowed_extensions=frozenset({".jpg", ".jpeg", ".png", ".webp"}),
    allowed_mime_types=frozenset(
        {
            "image/jpeg",
            "image/png",
            "image/webp",
            "application/octet-stream",
        }
    ),
    max_bytes=5 * 1024 * 1024,
    magic_kinds=frozenset({MAGIC_IMAGE}),
)


def validate_upload_metadata(upload: UploadFile, policy: UploadPolicy) -> str:
    filename = upload.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in policy.allowed_extensions:
        _raise_upload_rejected(
            upload,
            policy,
            "UPLOAD_EXTENSION_INVALIDA",
            f"Extensao de arquivo invalida: {suffix or '<sem extensao>'}.",
        )

    content_type = (upload.content_type or "").lower()
    if content_type and content_type not in policy.allowed_mime_types:
        _raise_upload_rejected(
            upload,
            policy,
            "UPLOAD_MIME_INVALIDO",
            f"Tipo MIME invalido: {content_type}.",
        )

    return suffix


def _is_zip_signature(header: bytes) -> bool:
    return any(header.startswith(signature) for signature in ZIP_SIGNATURES)


def _is_supported_image_signature(header: bytes) -> bool:
    return (
        header.startswith(b"\xff\xd8\xff")
        or header.startswith(b"\x89PNG\r\n\x1a\n")
        or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
    )


def _is_odt_file(upload: UploadFile) -> bool:
    try:
        position = upload.file.tell()
    except (AttributeError, OSError):
        position = None

    try:
        upload.file.seek(0)
        with zipfile.ZipFile(upload.file) as archive:
            names = set(archive.namelist())
            if "mimetype" in names:
                mimetype = archive.read("mimetype").decode("utf-8", errors="ignore")
                if mimetype == "application/vnd.oasis.opendocument.text":
                    return True
            return {"content.xml", "META-INF/manifest.xml"}.issubset(names)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False
    finally:
        try:
            upload.file.seek(position or 0)
        except (AttributeError, OSError):
            pass


def _is_zip_file(upload: UploadFile) -> bool:
    try:
        position = upload.file.tell()
    except (AttributeError, OSError):
        position = None

    try:
        upload.file.seek(0)
        return zipfile.is_zipfile(upload.file)
    finally:
        try:
            upload.file.seek(position or 0)
        except (AttributeError, OSError):
            pass


async def validate_upload_magic(upload: UploadFile, policy: UploadPolicy) -> None:
    if not policy.magic_kinds:
        return

    await upload.seek(0)
    header = await upload.read(16)
    await upload.seek(0)

    matches: set[str] = set()
    if header.startswith(b"%PDF-"):
        matches.add(MAGIC_PDF)
    if _is_zip_signature(header):
        matches.add(MAGIC_ZIP)
        if MAGIC_ODT in policy.magic_kinds and _is_odt_file(upload):
            matches.add(MAGIC_ODT)
    if _is_supported_image_signature(header):
        matches.add(MAGIC_IMAGE)
    if MAGIC_ZIP in policy.magic_kinds and not matches.intersection({MAGIC_ODT, MAGIC_ZIP}):
        if _is_zip_file(upload):
            matches.add(MAGIC_ZIP)
    await upload.seek(0)

    if not matches.intersection(policy.magic_kinds):
        expected = ", ".join(sorted(policy.magic_kinds))
        _raise_upload_rejected(
            upload,
            policy,
            "UPLOAD_MAGIC_INVALIDO",
            f"Assinatura do arquivo nao corresponde ao tipo esperado: {expected}.",
            detected_magic=sorted(matches),
        )


async def save_upload_to_path(upload: UploadFile, output_path: Path, policy: UploadPolicy) -> int:
    validate_upload_metadata(upload, policy)
    await validate_upload_magic(upload, policy)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    with output_path.open("wb") as file_obj:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > policy.max_bytes:
                _raise_upload_rejected(
                    upload,
                    policy,
                    "UPLOAD_TAMANHO_EXCEDIDO",
                    f"Arquivo excede o limite de {policy.max_bytes} bytes.",
                    size_bytes=total,
                )
            file_obj.write(chunk)

    if total == 0:
        _raise_upload_rejected(
            upload,
            policy,
            "UPLOAD_VAZIO",
            "Arquivo enviado esta vazio.",
            size_bytes=0,
        )

    return total

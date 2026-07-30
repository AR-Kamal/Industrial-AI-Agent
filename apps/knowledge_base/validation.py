"""File validation and stable checksum helpers."""

import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from django.conf import settings

from .exceptions import UnsupportedDocumentError

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}


@dataclass(frozen=True)
class ValidatedDocument:
    path: Path
    extension: str
    media_type: str
    checksum: str
    size: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_document_file(path: Path) -> ValidatedDocument:
    resolved = path.resolve(strict=True)
    extension = resolved.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentError(f"Unsupported file extension: {extension}")

    size = resolved.stat().st_size
    if size == 0:
        raise UnsupportedDocumentError("The document is empty.")
    if size > settings.KNOWLEDGE_MAX_UPLOAD_BYTES:
        raise UnsupportedDocumentError(
            "The document exceeds the configured size limit."
        )

    if extension == ".pdf":
        with resolved.open("rb") as source:
            if source.read(5) != b"%PDF-":
                raise UnsupportedDocumentError("The file is not a valid PDF.")
    elif extension == ".docx":
        _validate_docx(resolved)
    else:
        _validate_text(resolved)

    return ValidatedDocument(
        path=resolved,
        extension=extension,
        media_type=MEDIA_TYPES[extension],
        checksum=sha256_file(resolved),
        size=size,
    )


def validate_uploaded_document(
    source: BinaryIO,
    filename: str,
) -> tuple[str, str, int, str]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentError(f"Unsupported file extension: {extension}")
    source.seek(0, 2)
    size = source.tell()
    source.seek(0)
    if size == 0:
        raise UnsupportedDocumentError("The document is empty.")
    if size > settings.KNOWLEDGE_MAX_UPLOAD_BYTES:
        raise UnsupportedDocumentError(
            "The document exceeds the configured size limit."
        )

    digest = hashlib.sha256()
    for block in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(block)
    source.seek(0)

    if extension == ".pdf":
        if source.read(5) != b"%PDF-":
            raise UnsupportedDocumentError("The file is not a valid PDF.")
    elif extension == ".docx":
        try:
            with zipfile.ZipFile(source) as archive:
                names = set(archive.namelist())
                if not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
                    raise UnsupportedDocumentError("The DOCX package is incomplete.")
        except zipfile.BadZipFile as exc:
            raise UnsupportedDocumentError("The file is not a valid DOCX.") from exc
    else:
        source.seek(0)
        try:
            text = source.read().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsupportedDocumentError("Text documents must use UTF-8.") from exc
        if "\x00" in text:
            raise UnsupportedDocumentError("The text document contains binary data.")
    source.seek(0)
    return extension, MEDIA_TYPES[extension], size, digest.hexdigest()


def _validate_docx(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            required = {"[Content_Types].xml", "word/document.xml"}
            if not required.issubset(names):
                raise UnsupportedDocumentError("The DOCX package is incomplete.")
            total_uncompressed = sum(item.file_size for item in archive.infolist())
            maximum = max(settings.KNOWLEDGE_MAX_UPLOAD_BYTES * 4, 100_000_000)
            if total_uncompressed > maximum:
                raise UnsupportedDocumentError(
                    "The DOCX package expands beyond the safe limit."
                )
    except (zipfile.BadZipFile, OSError) as exc:
        raise UnsupportedDocumentError("The file is not a valid DOCX.") from exc


def _validate_text(path: Path) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedDocumentError("Text documents must use UTF-8.") from exc
    if "\x00" in content:
        raise UnsupportedDocumentError("The text document contains binary data.")

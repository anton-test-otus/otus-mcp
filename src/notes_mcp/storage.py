"""Image ingestion into the local vault."""

from __future__ import annotations

import mimetypes
import shutil
import uuid
from pathlib import Path

from notes_mcp.config import ALLOWED_IMAGE_SUFFIXES, IMAGES_DIR, MAX_IMAGE_BYTES


class ImageValidationError(ValueError):
    pass


def validate_source_image(path: str) -> Path:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ImageValidationError(f"Image file not found: {path}")
    suffix = source.suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise ImageValidationError(
            f"Unsupported image type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_IMAGE_SUFFIXES))}"
        )
    size = source.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise ImageValidationError(
            f"Image too large ({size} bytes). Max allowed: {MAX_IMAGE_BYTES} bytes."
        )
    return source


def save_upload(note_id: str, filename: str, content: bytes) -> Path:
    """Persist uploaded bytes to a temp file before vault copy."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise ImageValidationError(
            f"Unsupported image type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_IMAGE_SUFFIXES))}"
        )
    if len(content) > MAX_IMAGE_BYTES:
        raise ImageValidationError(
            f"Image too large ({len(content)} bytes). Max allowed: {MAX_IMAGE_BYTES} bytes."
        )
    upload_dir = IMAGES_DIR / "_uploads" / note_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{uuid.uuid4()}{suffix}"
    dest.write_bytes(content)
    return dest


def store_image(note_id: str, source_path: Path) -> tuple[str, str | None]:
    """Copy image into vault; returns (vault_path, mime_type)."""
    image_id = str(uuid.uuid4())
    dest_dir = IMAGES_DIR / note_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{image_id}{source_path.suffix.lower()}"
    shutil.copy2(source_path, dest)
    mime_type, _ = mimetypes.guess_type(dest.name)
    return str(dest.resolve()), mime_type

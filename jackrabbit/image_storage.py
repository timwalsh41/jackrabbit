"""App-managed image storage for pasted ticket-description images (JRB-027).

Clipboard-pasted screenshots are saved under ``{DATA_DIR}/uploads/`` with
generated names — a random UUID plus an extension derived from the file's
magic bytes (user filenames are never trusted). Uploads are write-once and
retained forever: nothing in the app deletes them, even when the referencing
ticket is deleted or the description is edited to drop the reference.

Type detection is magic-byte based (Pillow is not a dependency); the accepted
set is PNG, JPEG, GIF and WebP with a 10 MiB per-image limit.
"""

import re
import uuid
from pathlib import Path
from typing import NamedTuple

from fastapi import Depends

from jackrabbit.config import Settings, get_settings

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MiB per image
UPLOADS_SUBDIR = "uploads"

# Generated-name shape: <uuid hex>.<known extension>. resolve() trusts only
# names matching this, so the served path can never leave the uploads dir.
_SAVED_NAME_RE = r"[0-9a-f]{32}\.(?:png|jpg|gif|webp)"


class UnsupportedImageError(Exception):
    """The uploaded bytes are not a supported image format."""


class OversizedImageError(Exception):
    """The uploaded image exceeds MAX_IMAGE_BYTES."""


def oversize_detail() -> str:
    """User-presentable 413 detail, shared by the API read loop and save()."""
    return f"Image is too large. The maximum size is {MAX_IMAGE_BYTES // (1024 * 1024)} MiB."


class ImageNotFoundError(Exception):
    """No stored image matches the requested name."""


class SavedImage(NamedTuple):
    """Result of a successful save."""

    name: str
    url: str
    size: int
    content_type: str


class _Format(NamedTuple):
    extension: str
    media_type: str


def _sniff_format(data: bytes) -> _Format:
    """Return the image format implied by magic bytes, or raise."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return _Format(".png", "image/png")
    if data.startswith(b"\xff\xd8\xff"):
        return _Format(".jpg", "image/jpeg")
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return _Format(".gif", "image/gif")
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _Format(".webp", "image/webp")
    raise UnsupportedImageError(
        "Unsupported image type. Only PNG, JPEG, GIF and WebP images can be pasted."
    )


class ImageStorage:
    """Save and resolve upload files under ``{data_dir}/uploads/``.

    Constructed via ``get_image_storage`` so tests can redirect the upload
    directory through the ``get_settings`` dependency override.
    """

    def __init__(self, data_dir: Path) -> None:
        self._uploads_dir = data_dir / UPLOADS_SUBDIR

    def save(self, data: bytes) -> SavedImage:
        """Validate, store and name one uploaded image."""
        if len(data) > MAX_IMAGE_BYTES:
            raise OversizedImageError(oversize_detail())
        fmt = _sniff_format(data)
        self._uploads_dir.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}{fmt.extension}"
        (self._uploads_dir / name).write_bytes(data)
        return SavedImage(
            name=name,
            url=f"/images/{name}",
            size=len(data),
            content_type=fmt.media_type,
        )

    def resolve(self, name: str) -> tuple[Path, str]:
        """Map a generated image name to its file path and media type.

        Only saved names inside the uploads directory resolve; anything else
        (traversal, separators, unknown names) raises ``ImageNotFoundError``
        so the serving route can never expose files outside uploads.
        """
        if not re.fullmatch(_SAVED_NAME_RE, name):
            raise ImageNotFoundError("Image not found")
        candidate = self._uploads_dir / name
        try:
            resolved = candidate.resolve()
            resolved.relative_to(self._uploads_dir.resolve())
        except (OSError, ValueError) as exc:
            raise ImageNotFoundError("Image not found") from exc
        if not resolved.is_file():
            raise ImageNotFoundError("Image not found")
        fmt = _sniff_format(resolved.read_bytes()[:16])
        return resolved, fmt.media_type


def get_image_storage(settings: Settings = Depends(get_settings)) -> ImageStorage:
    """FastAPI dependency: an ImageStorage bound to the configured DATA_DIR."""
    return ImageStorage(settings.data_dir)
